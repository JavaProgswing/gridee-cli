from __future__ import annotations

import argparse
import difflib
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, time as clock_time, timedelta
from typing import Any

from .core import Gridee


class BookingError(RuntimeError):
    pass


@dataclass
class BookingNode:
    element: ET.Element
    text: str
    desc: str
    resource_id: str
    class_name: str
    enabled: bool
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


@dataclass
class Venue:
    name: str
    available: int
    action: BookingNode
    score: float = 0.0


def parse_hhmm(value: str) -> clock_time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must be HH:MM in 24-hour format") from exc


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def round_up(moment: datetime, minutes: int = 5) -> datetime:
    trimmed = moment.replace(second=0, microsecond=0)
    remainder = trimmed.minute % minutes
    if remainder or moment.second or moment.microsecond:
        trimmed += timedelta(minutes=minutes - remainder if remainder else minutes)
    return trimmed


def resolve_schedule(args: Any, now: datetime) -> tuple[datetime, datetime, datetime]:
    booking_date = args.date
    if booking_date is None:
        booking_date = now.date()
        if now >= datetime.combine(booking_date, args.end):
            booking_date += timedelta(days=1)

    open_at = datetime.combine(booking_date, args.open_at)
    start_at = datetime.combine(booking_date, args.start)
    end_at = datetime.combine(booking_date, args.end)
    if end_at <= start_at:
        raise BookingError("end time must be later than start time on the same date")

    if booking_date == now.date() and now > start_at:
        start_at = round_up(now + timedelta(minutes=args.late_buffer_minutes))
        if start_at >= end_at:
            if args.date is not None:
                raise BookingError("the explicitly requested booking window has already ended")
            booking_date += timedelta(days=1)
            open_at = datetime.combine(booking_date, args.open_at)
            start_at = datetime.combine(booking_date, args.start)
            end_at = datetime.combine(booking_date, args.end)
    return open_at, start_at, end_at


def normalized(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    ascii_value = re.sub(r"\btp\b", "tech park", ascii_value)
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value))


def venue_score(requested: str, candidate: str) -> float:
    requested_n = normalized(requested)
    candidate_n = normalized(candidate)
    sequence = difflib.SequenceMatcher(None, requested_n, candidate_n).ratio()
    requested_tokens = set(requested_n.split())
    candidate_tokens = set(candidate_n.split())
    union = requested_tokens | candidate_tokens
    token_score = len(requested_tokens & candidate_tokens) / len(union) if union else 0.0
    contains = 1.0 if requested_n in candidate_n or candidate_n in requested_n else 0.0
    return 0.55 * sequence + 0.35 * token_score + 0.10 * contains


def nodes_from_root(root: ET.Element) -> list[BookingNode]:
    nodes: list[BookingNode] = []
    for element in root.iter("node"):
        try:
            bounds = Gridee.parse_bounds(element.attrib.get("bounds", ""))
        except (RuntimeError, ValueError):
            bounds = (0, 0, 0, 0)
        nodes.append(
            BookingNode(
                element=element,
                text=element.attrib.get("text", "").strip(),
                desc=element.attrib.get("content-desc", "").strip(),
                resource_id=element.attrib.get("resource-id", ""),
                class_name=element.attrib.get("class", ""),
                enabled=element.attrib.get("enabled", "true").lower() == "true",
                bounds=bounds,
            )
        )
    return nodes


def by_id(nodes: list[BookingNode], *suffixes: str) -> BookingNode | None:
    wanted = tuple(f":id/{suffix}" for suffix in suffixes)
    return next((node for node in nodes if node.resource_id.endswith(wanted) and node.enabled), None)


def by_text(nodes: list[BookingNode], pattern: str) -> BookingNode | None:
    regex = re.compile(pattern, re.IGNORECASE)
    return next((node for node in nodes if regex.search(node.text or node.desc) and node.enabled), None)


def parse_venues(nodes: list[BookingNode]) -> list[Venue]:
    names = [node for node in nodes if node.resource_id.endswith(":id/tv_spot_name") and node.text]
    actions = [node for node in nodes if (node.text or node.desc).strip().lower() == "park"]
    availability_nodes = [
        node for node in nodes if node.resource_id.endswith(":id/tv_spot_availability")
    ]
    venues: list[Venue] = []
    for name in names:
        name_y = name.center[1]
        action = min(actions, key=lambda item: abs(item.center[1] - name_y), default=name)
        availability_node = min(
            availability_nodes,
            key=lambda item: abs(item.center[1] - name_y),
            default=name,
        )
        match = re.search(r"\d+", availability_node.text)
        venues.append(Venue(name=name.text, available=int(match.group()) if match else 0, action=action))
    return venues


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def wait_until(target: datetime, poll_seconds: float) -> None:
    last_notice = 0.0
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        if time.monotonic() - last_notice >= 60:
            log(f"waiting for booking opening at {target:%Y-%m-%d %H:%M} ({remaining / 60:.1f} min)")
            last_notice = time.monotonic()
        time.sleep(min(poll_seconds, remaining))


def wait_for_venue(app: Gridee, requested: str, threshold: float, timeout: float) -> Venue:
    deadline = time.monotonic() + timeout
    last_status = ""
    while time.monotonic() < deadline:
        root = app.dump_ui("booking-venues")
        if root is None:
            time.sleep(app.config.poll_interval)
            continue
        nodes = nodes_from_root(root)
        venues = parse_venues(nodes)
        if venues:
            for venue in venues:
                venue.score = venue_score(requested, venue.name)
            available = [venue for venue in venues if venue.available > 0]
            if not available:
                raise BookingError("all visible venues report zero availability")
            chosen = max(available, key=lambda venue: (venue.score, venue.available))
            log("venues: " + ", ".join(f"{v.name} ({v.available} available)" for v in venues))
            if chosen.score < threshold:
                raise BookingError(
                    f"best venue match {chosen.name!r} scored {chosen.score:.3f}, below {threshold:.3f}"
                )
            log(f"selected venue: {chosen.name!r}; match={chosen.score:.3f}; available={chosen.available}")
            return chosen
        closed = by_text(nodes, r"bookings are closed|bookings begin at")
        status = closed.text if closed else "waiting for venue list"
        if status != last_status:
            log(status)
            last_status = status
        time.sleep(app.config.poll_interval)
    raise BookingError("venue list did not become available before timeout")


def display_value(nodes: list[BookingNode], *ids: str) -> str:
    node = by_id(nodes, *ids)
    return node.text if node else ""


def clear_and_type(app: Gridee, node: BookingNode, value: str) -> None:
    app.tap_node(node.element, "time input")
    app.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
    for _ in range(8):
        app.adb("shell", "input", "keyevent", "KEYCODE_DEL")
    app.adb("shell", "input", "text", value)


def set_material_time(app: Gridee, card_id: str, target: clock_time) -> None:
    root = app.dump_ui("booking-time-card")
    if root is None:
        raise BookingError("could not inspect the booking time control")
    nodes = nodes_from_root(root)
    card = by_id(nodes, card_id)
    if card is None:
        raise BookingError(f"time control {card_id} was not found")
    app.tap_node(card.element, card_id)
    time.sleep(0.5)

    root = app.dump_ui("booking-time-picker")
    if root is None:
        raise BookingError("could not inspect the material time picker")
    nodes = nodes_from_root(root)
    edit_nodes = [node for node in nodes if node.class_name.endswith("EditText")]
    mode = by_id(nodes, "material_timepicker_mode_button")
    if len(edit_nodes) < 2 and mode is not None:
        app.tap_node(mode.element, "time picker input mode")
        time.sleep(0.5)
        root = app.dump_ui("booking-time-picker-input")
        nodes = nodes_from_root(root) if root is not None else []
        edit_nodes = [node for node in nodes if node.class_name.endswith("EditText")]
    if len(edit_nodes) < 2:
        raise BookingError("material time picker did not expose hour/minute inputs")

    display_hour = target.hour % 12 or 12
    clear_and_type(app, edit_nodes[0], str(display_hour))
    clear_and_type(app, edit_nodes[1], f"{target.minute:02d}")
    root = app.dump_ui("booking-time-picker-filled")
    nodes = nodes_from_root(root) if root is not None else []
    period = by_text(nodes, r"^PM$" if target.hour >= 12 else r"^AM$")
    if period is not None:
        app.tap_node(period.element, period.text)
    ok = by_id(nodes, "material_timepicker_ok_button") or by_text(nodes, r"^OK$")
    if ok is None:
        raise BookingError("time picker OK button was not found")
    app.tap_node(ok.element, "time picker OK")
    time.sleep(0.7)


def ensure_schedule(app: Gridee, start_at: datetime, end_at: datetime) -> None:
    root = app.dump_ui("booking-sheet")
    if root is None:
        raise BookingError("could not inspect the booking sheet")
    nodes = nodes_from_root(root)
    start_value = display_value(nodes, "tvStartTime", "tv_start_time")
    end_value = display_value(nodes, "tvEndTime", "tv_end_time")
    log(f"booking sheet initial times: start={start_value!r}, end={end_value!r}")
    wanted_start = start_at.strftime("%I:%M %p").lstrip("0")
    wanted_end = end_at.strftime("%I:%M %p").lstrip("0")
    if normalized(start_value) != normalized(wanted_start):
        set_material_time(app, "cardStartTime", start_at.time())
    if normalized(end_value) != normalized(wanted_end):
        set_material_time(app, "cardEndTime", end_at.time())


def submit_booking(app: Gridee, execute: bool) -> None:
    root = app.dump_ui("booking-ready")
    if root is None:
        raise BookingError("could not inspect the final booking screen")
    nodes = nodes_from_root(root)
    vehicle = display_value(nodes, "tvSelectedVehicle", "tv_vehicle_number", "tvVehicleNumber")
    spot = display_value(nodes, "tvSelectedSpot", "tv_spot_summary", "tvParkingSpotName")
    log(f"vehicle selection: {vehicle or 'app default'}")
    log(f"spot selection: {spot or 'any available spot/app default'}")
    confirm = by_id(nodes, "btnConfirmContainer", "btnConfirm", "confirm_button") or by_text(
        nodes, r"confirm booking|book now|reserve"
    )
    if confirm is None:
        raise BookingError("booking confirmation control was not found")
    if not execute:
        log("dry run complete; final booking control was found but not pressed")
        return
    log("submitting booking through the app")
    app.tap_node(confirm.element, "confirm booking")
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        time.sleep(1)
        root = app.dump_ui("booking-result")
        nodes = nodes_from_root(root) if root is not None else []
        success = by_text(nodes, r"booking confirmed|booking successful|booking id|view booking|qr pass")
        failure = by_text(nodes, r"failed|unavailable|error|insufficient|already booked")
        if success:
            log(f"booking result: {success.text or success.desc}")
            return
        if failure:
            raise BookingError(f"booking failed: {failure.text or failure.desc}")
    raise BookingError("booking submission did not reach a recognizable success state")


def run_booking(app: Gridee, args: Any) -> int:
    open_at, start_at, end_at = resolve_schedule(args, datetime.now())
    log(f"target window: {start_at:%Y-%m-%d %H:%M} to {end_at:%H:%M}")
    log(f"booking opens: {open_at:%Y-%m-%d %H:%M}")
    if datetime.now() < open_at:
        if args.no_wait:
            raise BookingError("booking is not open yet and --no-wait was supplied")
        wait_until(open_at, app.config.poll_interval)

    original_awake = app.get_stay_awake_setting()
    try:
        app.set_stay_awake(True)
        app.wake_screen()
        app.launch()
        time.sleep(args.startup_delay)
        venue = wait_for_venue(app, args.venue, args.venue_threshold, args.venue_timeout)
        app.tap_node(venue.action.element, f"Park at {venue.name}")
        time.sleep(1.2)
        ensure_schedule(app, start_at, end_at)
        submit_booking(app, args.execute)
        return 0
    finally:
        if not args.keep_awake:
            app.restore_stay_awake_setting(original_awake)
