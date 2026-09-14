from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import time as system_time
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from gridee_aiohttp import ApiError, FIREBASE_KEY, GrideeClient
from gridee_wallet import fetch_wallet_details, find_balance, resolve_user_id


if hasattr(system_time, "tzset"):
    system_time.tzset()


DEFAULT_CONFIG = {
    "runAt": "05:00",
    "graceMinutes": 10,
    "rebook": {
        "enabled": True,
        "pollSeconds": 5,
        "retrySeconds": 5,
        "refundWaitSeconds": 120,
        "lateStartBufferMinutes": 5,
    },
    "userId": "current",
    "booking": {
        "spotId": "SAVE_SPOT_ID",
        "lotId": "SAVE_LOT_ID",
        "checkInTime": "{date}T08:00:00{offset}",
        "checkOutTime": "{date}T17:00:00{offset}",
        "vehicleNumber": "SAVE_VEHICLE_NUMBER",
    },
}
REQUIRED_BOOKING_FIELDS = {
    "spotId",
    "lotId",
    "checkInTime",
    "checkOutTime",
    "vehicleNumber",
}
REBOOKABLE_STATUSES = {
    "CANCELLED",
    "CANCELED",
    "EXPIRED",
    "FAILED",
    "MISSING",
    "REFUNDED",
    "REJECTED",
    "VOID",
    "VOIDED",
}
FINISHED_STATUSES = {"COMPLETED", "NO_SHOW"}
RESUMABLE_SERVICE_STATUSES = {
    "awaiting-refund",
    "failed",
    "monitor-error",
    "monitoring",
    "rebook-failed",
    "rebook-pending",
    "submitted",
}


class ServiceError(RuntimeError):
    pass


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise ServiceError(f"Missing {path}. Run with --init first.") from None
    if not isinstance(value, dict):
        raise ServiceError(f"{path} must contain one JSON object.")
    return value


def merge_config_defaults(config: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_CONFIG))

    def overlay(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                overlay(target[key], value)
            else:
                target[key] = value

    overlay(merged, config)
    return merged


def read_booking_config(path: Path) -> dict[str, Any]:
    return merge_config_defaults(read_json(path, {}))


def write_json(path: Path, value: dict[str, Any], *, overwrite: bool = True) -> None:
    if path.exists() and not overwrite:
        raise ServiceError(f"{path} already exists; it was not overwritten.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_run_time(value: Any) -> time:
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except ValueError as exc:
        raise ServiceError("runAt must use 24-hour HH:MM format.") from exc


def local_utc_offset(booking_date: date) -> str:
    value = datetime.combine(booking_date, time(hour=12)).astimezone().strftime("%z")
    if len(value) != 5:
        raise ServiceError("Could not determine the local UTC offset.")
    return f"{value[:3]}:{value[3:]}"


def render(value: Any, booking_date: date) -> Any:
    replacements = {
        "{date}": booking_date.isoformat(),
        "{tomorrow}": (booking_date + timedelta(days=1)).isoformat(),
        "{offset}": local_utc_offset(booking_date),
    }
    if isinstance(value, str):
        for marker, replacement in replacements.items():
            value = value.replace(marker, replacement)
    elif isinstance(value, dict):
        value = {key: render(item, booking_date) for key, item in value.items()}
    elif isinstance(value, list):
        value = [render(item, booking_date) for item in value]
    return value


def normalize_booking_times(body: dict[str, Any], booking_date: date) -> None:
    """Match the Android app's yyyy-MM-dd'T'HH:mm:ssXXX request format."""
    for key in ("checkInTime", "checkOutTime"):
        value = body.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            body[key] = parsed.isoformat(timespec="seconds") + local_utc_offset(booking_date)
        else:
            body[key] = parsed.isoformat(timespec="seconds")


def booking_body(config: dict[str, Any], booking_date: date) -> dict[str, Any]:
    body = render(config.get("booking"), booking_date)
    if not isinstance(body, dict):
        raise ServiceError("booking must be a JSON object.")
    normalize_booking_times(body, booking_date)
    missing = [
        key
        for key in REQUIRED_BOOKING_FIELDS
        if not str(body.get(key, "")).strip() or str(body[key]).startswith("SAVE_")
    ]
    if missing:
        raise ServiceError("Save real booking values for: " + ", ".join(sorted(missing)))
    return body


def find_user_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("id", "userId", "user_id", "sub"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        for key in ("user", "data", "principal", "profile", "account"):
            found = find_user_id(value.get(key))
            if found:
                return found
    return None


def find_field(value: Any, names: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for name in names:
            if value.get(name) not in (None, "", []):
                return value[name]
        for item in value.values():
            found = find_field(item, names)
            if found not in (None, "", []):
                return found
    return None


def rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("data", "content", "items", "results", "parkingLots", "lots", "spots"):
            found = rows(value.get(key))
            if found:
                return found
        if value.get("id") not in (None, ""):
            return [value]
    return []


def normalized_status(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def looks_like_booking_record(value: dict[str, Any]) -> bool:
    status = normalized_status(value.get("status"))
    return any(
        key in value
        for key in (
            "spotId",
            "lotId",
            "checkInTime",
            "checkOutTime",
            "startTime",
            "endTime",
            "bookingDate",
            "vehicleNumber",
            "cancelledAt",
        )
    ) or status in {
        "ACTIVE",
        "BOOKED",
        "CONFIRMED",
        "IN_PROGRESS",
        "PENDING",
        "STARTED",
        "CANCELLED",
        "CANCELED",
        "COMPLETED",
        "EXPIRED",
        "NO_SHOW",
        "REFUNDED",
        "REJECTED",
        "VOID",
        "VOIDED",
    }


def find_booking_record(value: Any, booking_id: str | None = None) -> dict[str, Any] | None:
    """Find a Booking inside any envelope shape returned by the API."""
    if isinstance(value, dict):
        record_id = value.get("id") or value.get("_id") or value.get("bookingId")
        looks_like_booking = looks_like_booking_record(value)
        if record_id not in (None, "") and (
            (booking_id is not None and str(record_id) == booking_id)
            or (booking_id is None and looks_like_booking)
        ):
            return value
        for item in value.values():
            found = find_booking_record(item, booking_id)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_booking_record(item, booking_id)
            if found is not None:
                return found
    return None


def find_booking_records(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        record_id = value.get("id") or value.get("_id") or value.get("bookingId")
        if record_id not in (None, "") and looks_like_booking_record(value):
            found.append(value)
        for item in value.values():
            found.extend(find_booking_records(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_booking_records(item))
    return found


def _booking_day(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def booking_matches_saved_entry(
    record: dict[str, Any], body: dict[str, Any], booking_date: date
) -> bool:
    if booking_needs_rebook(record) or normalized_status(record.get("status")) in FINISHED_STATUSES:
        return False
    for key in ("lotId", "spotId"):
        if str(record.get(key) or "") != str(body.get(key) or ""):
            return False
    expected_vehicle = "".join(ch for ch in str(body.get("vehicleNumber") or "").upper() if ch.isalnum())
    actual_vehicle = "".join(
        ch for ch in str(record.get("vehicleNumber") or "").upper() if ch.isalnum()
    )
    if expected_vehicle and actual_vehicle != expected_vehicle:
        return False
    return _booking_day(record.get("checkInTime")) == booking_date


def booking_record_day(record: dict[str, Any]) -> date | None:
    for key in ("checkInTime", "startTime", "bookingDate", "date"):
        booking_day = _booking_day(record.get(key))
        if booking_day is not None:
            return booking_day
    return None


def select_current_booking(
    value: Any, body: dict[str, Any], booking_date: date
) -> dict[str, Any] | None:
    """Prefer the configured booking, then any live booking for the same day."""
    records = find_booking_records(value)
    exact = next(
        (
            record
            for record in records
            if booking_matches_saved_entry(record, body, booking_date)
        ),
        None,
    )
    if exact is not None:
        return exact

    live = [
        record
        for record in records
        if not booking_needs_rebook(record)
        and normalized_status(record.get("status")) not in FINISHED_STATUSES
    ]
    same_day = [record for record in live if booking_record_day(record) == booking_date]
    if same_day:
        return same_day[0]

    # Some list responses contain only an ID and status. The /all route is the
    # current-booking collection, so a single undated live record is safe to adopt.
    undated = [record for record in live if booking_record_day(record) is None]
    return undated[0] if len(undated) == 1 else None


def find_booking_id(value: Any) -> str | None:
    record = find_booking_record(value)
    if record is None and isinstance(value, dict):
        # A successful create response may be a minimal {id: ...} envelope.
        for key in ("bookingId", "_id", "id"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        for key in ("booking", "data", "result"):
            found = find_booking_id(value.get(key))
            if found:
                return found
        return None
    if record is None:
        return None
    return str(record.get("id") or record.get("_id") or record.get("bookingId"))


def booking_needs_rebook(record: dict[str, Any]) -> bool:
    status = normalized_status(record.get("status"))
    terminal_marker = any(
        marker in status for marker in ("CANCEL", "REFUND", "EXPIRE", "REJECT", "VOID")
    )
    return (
        bool(record.get("cancelledAt"))
        or status in REBOOKABLE_STATUSES
        or terminal_marker
    )


def booking_started(record: dict[str, Any]) -> bool:
    status = normalized_status(record.get("status"))
    scanned = record.get("qrCodeScanned")
    return (
        status in {"ACTIVE", "IN_PROGRESS", "STARTED", "OCCUPIED"}
        or record.get("actualCheckInTime") not in (None, "")
        or scanned is True
        or (isinstance(scanned, str) and scanned.strip().lower() == "true")
    )


def find_refund_transaction(value: Any, booking_id: str) -> dict[str, Any] | None:
    for transaction in rows(value):
        linked_id = transaction.get("bookingId")
        if str(linked_id or "") != booking_id:
            continue
        refund_text = " ".join(
            str(transaction.get(key) or "")
            for key in ("type", "description", "method")
        ).upper()
        status = normalized_status(transaction.get("status"))
        if "REFUND" not in refund_text:
            continue
        if status in {"FAILED", "FAILURE", "PENDING", "PROCESSING", "REJECTED"}:
            continue
        return transaction
    return None


def booking_status(record: dict[str, Any]) -> str:
    if record.get("cancelledAt") and not record.get("status"):
        return "CANCELLED"
    return normalized_status(record.get("status")) or "UNKNOWN"


def rebook_options(config: dict[str, Any]) -> tuple[bool, int, int, int]:
    value = config.get("rebook")
    value = value if isinstance(value, dict) else {}
    enabled = value.get("enabled", True) is not False
    poll_seconds = max(5, int(value.get("pollSeconds", 5)))
    retry_seconds = max(5, int(value.get("retrySeconds", 5)))
    late_buffer = max(0, int(value.get("lateStartBufferMinutes", 5)))
    return enabled, poll_seconds, retry_seconds, late_buffer


def refund_wait_seconds(config: dict[str, Any]) -> int:
    value = config.get("rebook")
    value = value if isinstance(value, dict) else {}
    return max(5, int(value.get("refundWaitSeconds", 120)))


def rebook_deadline(config: dict[str, Any], booking_date: date) -> datetime:
    body = booking_body(config, booking_date)
    try:
        deadline = datetime.fromisoformat(str(body["checkOutTime"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceError("checkOutTime must be an ISO-8601 date and time.") from exc
    if deadline.tzinfo is None:
        deadline = deadline.astimezone()
    return deadline


def replacement_booking_body(
    config: dict[str, Any], booking_date: date, now: datetime
) -> dict[str, Any]:
    """Move a replacement's start forward when the original start is in the past."""
    body = booking_body(config, booking_date)
    try:
        starts_at = datetime.fromisoformat(str(body["checkInTime"]))
        ends_at = datetime.fromisoformat(str(body["checkOutTime"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceError("Booking times must be valid ISO-8601 date and times.") from exc
    if starts_at.tzinfo is None:
        starts_at = starts_at.astimezone()
    if ends_at.tzinfo is None:
        ends_at = ends_at.astimezone()
    now = now.astimezone(starts_at.tzinfo)
    if now <= starts_at:
        return body

    _, _, _, late_buffer = rebook_options(config)
    candidate = (now + timedelta(minutes=late_buffer)).replace(second=0, microsecond=0)
    remainder = candidate.minute % 5
    if remainder:
        candidate += timedelta(minutes=5 - remainder)
    if candidate >= ends_at:
        raise ServiceError("Too late to create a replacement before check-out time.")
    body["checkInTime"] = candidate.isoformat(timespec="seconds")
    return body


def should_resume_monitoring(
    config: dict[str, Any], state: dict[str, Any], now: datetime
) -> bool:
    enabled, _, _, _ = rebook_options(config)
    return (
        enabled
        and state.get("lastAttemptDate") == now.date().isoformat()
        and bool(state.get("bookingId"))
        and state.get("status") in RESUMABLE_SERVICE_STATUSES
        and now < rebook_deadline(config, now.date())
    )


def should_recover_booking(
    config: dict[str, Any], state: dict[str, Any], now: datetime, run_at: time
) -> bool:
    enabled, _, _, _ = rebook_options(config)
    scheduled = datetime.combine(now.date(), run_at, tzinfo=now.tzinfo)
    stale_missing_state = (
        state.get("status") == "missing-booking"
        or normalized_status(state.get("bookingStatus")) == "MISSING"
    )
    has_today_booking = (
        state.get("lastAttemptDate") == now.date().isoformat()
        and bool(state.get("bookingId"))
        and not stale_missing_state
    )
    conflict_already_checked = (
        state.get("lastAttemptDate") == now.date().isoformat()
        and state.get("status") == "booking-conflict-unresolved"
    )
    return (
        enabled
        and not has_today_booking
        and not conflict_already_checked
        and scheduled <= now < rebook_deadline(config, now.date())
    )


def choose(label: str, choices: list[tuple[str, str]]) -> str:
    choices = list(dict.fromkeys(choices))
    if not choices:
        value = input(f"No {label} detected. Enter it manually: ").strip()
        if not value:
            raise ServiceError(f"A {label} is required.")
        return value
    if len(choices) == 1:
        print(f"Using {label}: {choices[0][1]}")
        return choices[0][0]
    print(f"Choose {label}:")
    for number, (_, description) in enumerate(choices, 1):
        print(f"  {number}. {description}")
    while True:
        try:
            return choices[int(input("Number: ")) - 1][0]
        except (ValueError, IndexError):
            print(f"Enter a number from 1 to {len(choices)}.")


async def setup(config_path: Path) -> None:
    config = read_booking_config(config_path)
    email = os.getenv("GRIDEE_EMAIL") or input("Gridee email: ")
    password = os.getenv("GRIDEE_PASSWORD") or getpass.getpass("Gridee password: ")
    booking_date = datetime.now().astimezone().date()
    rendered = render(config.get("booking", {}), booking_date)
    if isinstance(rendered, dict):
        normalize_booking_times(rendered, booking_date)

    async with GrideeClient(
        email,
        password,
        base_url=os.getenv("GRIDEE_BASE_URL", "https://gridee.onrender.com"),
        firebase_key=os.getenv("GRIDEE_FIREBASE_API_KEY", FIREBASE_KEY),
    ) as client:
        print(f"Authenticated via {client.auth_method}.")
        try:
            user = await client.request("GET", "/api/oauth2/user")
        except Exception as exc:
            print(f"Current-user detection failed ({exc}); using login profile/manual entry.")
            user = client.user
        saved_user_id = str(config.get("userId") or "")
        user_id = find_user_id(user)
        if not user_id and saved_user_id.lower() not in {"", "current"}:
            user_id = saved_user_id
        if not user_id:
            user_id = choose("user ID", [])
        vehicles = find_field(user, ("vehicleNumbers", "vehicles"))
        if not isinstance(vehicles, list):
            vehicles = [find_field(user, ("defaultVehicle", "vehicleNumber"))]
        vehicle_choices = [
            (str(vehicle), str(vehicle))
            for vehicle in vehicles
            if vehicle not in (None, "")
        ]
        vehicle = choose("vehicle", vehicle_choices)

        try:
            lots = rows(await client.request("GET", "/api/parking-lots"))
        except Exception as exc:
            print(f"Parking-lot detection failed ({exc}); using manual entry.")
            lots = []
        lot_choices = []
        for lot in lots:
            lot_id = lot.get("id") or lot.get("lotId")
            if lot_id:
                name = lot.get("name") or lot.get("parkingLotName") or lot_id
                address = lot.get("address") or lot.get("location") or ""
                lot_choices.append((str(lot_id), f"{name} {address}".strip()))
        lot_id = choose("parking lot", lot_choices)

        try:
            available = await client.request(
                "GET",
                f"/api/parking-lots/{quote(lot_id, safe='')}/spots/available",
                params={
                    "startTime": str(rendered.get("checkInTime", "")),
                    "endTime": str(rendered.get("checkOutTime", "")),
                },
            )
        except Exception as exc:
            print(f"Availability detection failed ({exc}); trying the lot's spot list.")
            try:
                available = await client.request(
                    "GET", f"/api/parking-lots/{quote(lot_id, safe='')}/spots"
                )
            except Exception as fallback_exc:
                print(f"Spot detection failed ({fallback_exc}); using manual entry.")
                available = []
        spot_choices = []
        for item in rows(available):
            spot = item.get("spot") if isinstance(item.get("spot"), dict) else item
            is_available = item.get("available", spot.get("available", True))
            if is_available is False:
                continue
            spot_id = spot.get("id") or spot.get("spotId")
            if spot_id:
                name = spot.get("name") or spot.get("spotCode") or spot.get("slotName") or spot_id
                zone = spot.get("zoneName") or ""
                spot_choices.append((str(spot_id), f"{name} {zone}".strip()))
        spot_id = choose("available spot", spot_choices)

    config["userId"] = user_id or "current"
    booking = config.setdefault("booking", {})
    booking.update({"vehicleNumber": vehicle, "lotId": lot_id, "spotId": spot_id})
    write_json(config_path, config)
    print(f"Saved booking choices to {config_path}.")


def unattended_credentials() -> tuple[str, str]:
    email, password = os.getenv("GRIDEE_EMAIL"), os.getenv("GRIDEE_PASSWORD")
    if not email or not password:
        raise ServiceError("Set GRIDEE_EMAIL and GRIDEE_PASSWORD for unattended login.")
    return email, password


async def submit_with_client(
    client: GrideeClient,
    config: dict[str, Any],
    booking_date: date,
    user_id: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[str, Any]:
    body = body or booking_body(config, booking_date)
    configured_user_id = str(config.get("userId") or "current")
    user_id = user_id or await resolve_user_id(
        client,
        None if configured_user_id.lower() == "current" else configured_user_id,
    )
    _, wallet = await fetch_wallet_details(client, user_id)
    balance = find_balance(wallet)
    if balance is None:
        raise ServiceError("Wallet responded, but its balance could not be determined.")
    print(f"Wallet balance before booking: {balance:g}", flush=True)
    if balance <= 0:
        raise ServiceError(
            "Wallet balance is empty. Add credit through Gridee's official "
            "payment or reward flow before booking."
        )
    result = await client.request(
        "POST",
        f"/api/bookings/{quote(user_id, safe='')}/create",
        json=body,
    )
    print(json.dumps(result, indent=2), flush=True)
    return user_id, result


async def submit(config: dict[str, Any], booking_date: date, dry_run: bool) -> Any:
    body = booking_body(config, booking_date)
    if dry_run:
        result = {"dryRun": True, "bookingDate": booking_date.isoformat(), "body": body}
        print(json.dumps(result, indent=2), flush=True)
        return result

    email, password = unattended_credentials()

    async with GrideeClient(
        email,
        password,
        base_url=os.getenv("GRIDEE_BASE_URL", "https://gridee.onrender.com"),
        firebase_key=os.getenv("GRIDEE_FIREBASE_API_KEY", FIREBASE_KEY),
    ) as client:
        _, result = await submit_with_client(client, config, booking_date)
        return result


async def fetch_booking_record(
    client: GrideeClient, user_id: str, booking_id: str
) -> dict[str, Any]:
    encoded_user = quote(user_id, safe="")
    encoded_booking = quote(booking_id, safe="")
    try:
        result = await client.request(
            "GET", f"/api/bookings/{encoded_user}/{encoded_booking}"
        )
        return (
            find_booking_record(result, booking_id)
            or find_booking_record(result)
            or {"id": booking_id, "status": "UNKNOWN"}
        )
    except ApiError as exc:
        if exc.status != 404:
            raise

    # Cancelled bookings may move out of the live collection immediately.
    for suffix in ("all/history", "all"):
        try:
            result = await client.request(
                "GET", f"/api/bookings/{encoded_user}/{suffix}"
            )
        except ApiError:
            continue
        record = find_booking_record(result, booking_id)
        if record is not None:
            return record
    return {"id": booking_id, "status": "MISSING"}


async def fetch_matching_refund(
    client: GrideeClient, user_id: str, booking_id: str
) -> dict[str, Any] | None:
    result = await client.request(
        "GET",
        f"/api/users/{quote(user_id, safe='')}/wallet/transactions",
        params={"page": 0, "size": 100, "sort": "timestamp,desc"},
    )
    return find_refund_transaction(result, booking_id)


async def recover_or_create_booking(
    config: dict[str, Any], booking_date: date, state_path: Path
) -> dict[str, Any]:
    email, password = unattended_credentials()
    async with GrideeClient(
        email,
        password,
        base_url=os.getenv("GRIDEE_BASE_URL", "https://gridee.onrender.com"),
        firebase_key=os.getenv("GRIDEE_FIREBASE_API_KEY", FIREBASE_KEY),
    ) as client:
        configured_user_id = str(config.get("userId") or "current")
        user_id = await resolve_user_id(
            client,
            None if configured_user_id.lower() == "current" else configured_user_id,
        )
        encoded_user = quote(user_id, safe="")
        current = await client.request("GET", f"/api/bookings/{encoded_user}/all")
        saved_body = booking_body(config, booking_date)
        existing = select_current_booking(current, saved_body, booking_date)

        recovered_existing = existing is not None
        result: Any = existing
        if existing is None:
            body = replacement_booking_body(
                config, booking_date, datetime.now().astimezone()
            )
            try:
                _, result = await submit_with_client(
                    client, config, booking_date, user_id, body=body
                )
            except ApiError as exc:
                if exc.status != 409:
                    raise
                # A conflict is authoritative evidence of an existing booking.
                # Re-read and adopt it instead of retrying another create call.
                current = await client.request(
                    "GET", f"/api/bookings/{encoded_user}/all"
                )
                existing = select_current_booking(current, saved_body, booking_date)
                if existing is None:
                    state = {
                        "lastAttemptDate": booking_date.isoformat(),
                        "attemptedAt": datetime.now().astimezone().isoformat(),
                        "status": "booking-conflict-unresolved",
                        "userId": user_id,
                        "error": str(exc),
                    }
                    write_json(state_path, state)
                    print(
                        "The API reports an existing booking, but its ID was not "
                        "present in the current-bookings response. Duplicate create "
                        "attempts are disabled for today.",
                        flush=True,
                    )
                    return state
                recovered_existing = True
                result = existing

        booking_id = find_booking_id(result)
        if not booking_id:
            # Confirm the POST result through the live collection before giving up.
            current = await client.request("GET", f"/api/bookings/{encoded_user}/all")
            existing = select_current_booking(current, saved_body, booking_date)
            result = existing
            booking_id = find_booking_id(existing)
        if not booking_id:
            raise ServiceError(
                "Could not find a current booking or determine the ID of the "
                "replacement; stopped to avoid duplicate bookings."
            )

        state = {
            "lastAttemptDate": booking_date.isoformat(),
            "attemptedAt": datetime.now().astimezone().isoformat(),
            "status": "submitted",
            "userId": user_id,
            "bookingId": booking_id,
            "bookingStatus": booking_status(
                find_booking_record(result, booking_id)
                or find_booking_record(result)
                or {}
            ),
            "recoveredOnRestart": recovered_existing,
        }
        write_json(state_path, state)
        action = "Recovered existing" if recovered_existing else "Created missing"
        print(f"{action} booking on restart: {booking_id}", flush=True)
        return state


async def monitor_and_rebook(
    config: dict[str, Any],
    booking_date: date,
    state_path: Path,
    state: dict[str, Any],
) -> dict[str, Any]:
    enabled, poll_seconds, retry_seconds, _ = rebook_options(config)
    booking_id = str(state.get("bookingId") or "")
    if not enabled or not booking_id:
        return state

    deadline = rebook_deadline(config, booking_date)
    email, password = unattended_credentials()
    async with GrideeClient(
        email,
        password,
        base_url=os.getenv("GRIDEE_BASE_URL", "https://gridee.onrender.com"),
        firebase_key=os.getenv("GRIDEE_FIREBASE_API_KEY", FIREBASE_KEY),
    ) as client:
        configured_user_id = str(config.get("userId") or "current")
        user_id = await resolve_user_id(
            client,
            None if configured_user_id.lower() == "current" else configured_user_id,
        )
        previous_user_id = str(state.get("userId") or "")
        if previous_user_id and previous_user_id != user_id:
            state = {
                "lastAttemptDate": booking_date.isoformat(),
                "status": "account-changed",
                "previousUserId": previous_user_id,
                "userId": user_id,
                "accountChangedAt": datetime.now().astimezone().isoformat(),
            }
            write_json(state_path, state)
            print(
                "Authenticated account changed; discarded the previous account's "
                "tracked booking and starting safe recovery.",
                flush=True,
            )
            return state
        state["userId"] = user_id
        last_reported_status = ""
        while datetime.now().astimezone() < deadline:
            try:
                record = await fetch_booking_record(client, user_id, booking_id)
            except Exception as exc:
                state.update(
                    {
                        "status": "monitor-error",
                        "bookingId": booking_id,
                        "lastCheckedAt": datetime.now().astimezone().isoformat(),
                        "error": str(exc),
                    }
                )
                write_json(state_path, state)
                print(f"[!] Booking status check failed: {exc}", flush=True)
                await asyncio.sleep(poll_seconds)
                continue

            current_status = booking_status(record)
            state.update(
                {
                    "status": "monitoring",
                    "bookingId": booking_id,
                    "bookingStatus": current_status,
                    "lastCheckedAt": datetime.now().astimezone().isoformat(),
                }
            )
            state.pop("error", None)
            write_json(state_path, state)
            if current_status != last_reported_status:
                print(
                    f"[{state['lastCheckedAt']}] booking {booking_id} status: "
                    f"{current_status}",
                    flush=True,
                )
                last_reported_status = current_status

            if current_status == "MISSING":
                stale_booking_id = booking_id
                state = {
                    "lastAttemptDate": booking_date.isoformat(),
                    "status": "missing-booking",
                    "userId": user_id,
                    "missingBookingId": stale_booking_id,
                    "missingDetectedAt": datetime.now().astimezone().isoformat(),
                }
                write_json(state_path, state)
                print(
                    f"Booking {stale_booking_id} is absent from live and history "
                    "results; discarded the stale ID and starting safe recovery.",
                    flush=True,
                )
                return state

            if booking_started(record):
                state.update(
                    {
                        "status": "booking-started",
                        "wasStarted": True,
                        "startedDetectedAt": datetime.now().astimezone().isoformat(),
                    }
                )
                write_json(state_path, state)
                print(
                    f"Booking {booking_id} is in progress; automatic rebooking stopped.",
                    flush=True,
                )
                return state

            if current_status in FINISHED_STATUSES:
                state["status"] = "monitor-complete"
                write_json(state_path, state)
                return state

            if not booking_needs_rebook(record):
                await asyncio.sleep(poll_seconds)
                continue

            first_refund_wait = state.get("refundAwaitingBookingId") != booking_id
            detected_at = datetime.now().astimezone()
            if first_refund_wait:
                refund_wait_started = detected_at
                state["refundWaitStartedAt"] = refund_wait_started.isoformat()
            else:
                try:
                    refund_wait_started = datetime.fromisoformat(
                        str(state["refundWaitStartedAt"])
                    )
                except (KeyError, TypeError, ValueError):
                    refund_wait_started = detected_at
                    state["refundWaitStartedAt"] = refund_wait_started.isoformat()
            try:
                refund = await fetch_matching_refund(client, user_id, booking_id)
            except Exception as exc:
                state.update(
                    {
                        "status": "awaiting-refund",
                        "refundAwaitingBookingId": booking_id,
                        "error": f"Refund check failed: {exc}",
                    }
                )
                write_json(state_path, state)
                print(f"[!] {state['error']}", flush=True)
                await asyncio.sleep(poll_seconds)
                continue
            if refund is None:
                wait_limit = refund_wait_seconds(config)
                waited = (detected_at - refund_wait_started).total_seconds()
                if waited >= wait_limit:
                    state.update(
                        {
                            "status": "cancelled-no-refund",
                            "refundWaitExpiredAt": detected_at.isoformat(),
                            "monitorCompletedAt": detected_at.isoformat(),
                        }
                    )
                    state.pop("error", None)
                    write_json(state_path, state)
                    print(
                        f"No matching refund appeared for {booking_id} within "
                        f"{wait_limit}s; treating it as a manual cancellation and "
                        "scheduling the next normal booking day.",
                        flush=True,
                    )
                    return state
                state.update(
                    {
                        "status": "awaiting-refund",
                        "refundAwaitingBookingId": booking_id,
                    }
                )
                state.pop("error", None)
                write_json(state_path, state)
                if first_refund_wait:
                    print(
                        f"Booking {booking_id} is {current_status}; waiting for its "
                        f"matching wallet refund for up to {wait_limit}s before rebooking.",
                        flush=True,
                    )
                await asyncio.sleep(poll_seconds)
                continue

            state.update(
                {
                    "status": "rebook-pending",
                    "cancelledBookingId": booking_id,
                    "cancelledBookingStatus": current_status,
                    "rebookDetectedAt": datetime.now().astimezone().isoformat(),
                    "refundTransactionId": refund.get("id"),
                    "refundConfirmedAt": datetime.now().astimezone().isoformat(),
                }
            )
            state.pop("refundAwaitingBookingId", None)
            write_json(state_path, state)
            print(
                f"Refund confirmed for {booking_id}; creating a replacement now. "
                f"Failures retry every {retry_seconds}s until {deadline.isoformat()}.",
                flush=True,
            )

            while datetime.now().astimezone() < deadline:
                state["rebookAttempts"] = int(state.get("rebookAttempts", 0)) + 1
                state["rebookAttemptedAt"] = datetime.now().astimezone().isoformat()
                try:
                    replacement_body = replacement_booking_body(
                        config, booking_date, datetime.now().astimezone()
                    )
                    _, result = await submit_with_client(
                        client,
                        config,
                        booking_date,
                        user_id,
                        body=replacement_body,
                    )
                except Exception as exc:
                    state.update({"status": "rebook-failed", "error": str(exc)})
                    write_json(state_path, state)
                    print(f"[!] Rebook attempt failed: {exc}", flush=True)
                    await asyncio.sleep(retry_seconds)
                    continue

                replacement_id = find_booking_id(result)
                if not replacement_id:
                    state.update(
                        {
                            "status": "submitted-untracked",
                            "error": (
                                "Rebook succeeded but the response contained no booking ID; "
                                "stopped automatic retries to avoid a duplicate."
                            ),
                        }
                    )
                    write_json(state_path, state)
                    print(f"[!] {state['error']}", flush=True)
                    return state

                booking_id = replacement_id
                state.update(
                    {
                        "status": "monitoring",
                        "bookingId": booking_id,
                        "bookingStatus": booking_status(
                            find_booking_record(result, booking_id)
                            or find_booking_record(result)
                            or {}
                        ),
                        "rebookedAt": datetime.now().astimezone().isoformat(),
                    }
                )
                state.pop("error", None)
                write_json(state_path, state)
                print(f"Replacement booking created: {booking_id}", flush=True)
                last_reported_status = ""
                break

    state.update(
        {
            "status": "monitor-complete",
            "monitorCompletedAt": datetime.now().astimezone().isoformat(),
        }
    )
    write_json(state_path, state)
    print(f"Reached check-out time; automatic rebooking stopped for {booking_date}.", flush=True)
    return state


def next_due(now: datetime, run_at: time, grace_minutes: int, last_date: str) -> datetime:
    today = datetime.combine(now.date(), run_at, tzinfo=now.tzinfo)
    if now < today:
        return today
    if now <= today + timedelta(minutes=grace_minutes) and last_date != now.date().isoformat():
        return now
    return today + timedelta(days=1)


def should_retry_invalid_date(state: dict[str, Any], today: date) -> bool:
    return (
        state.get("lastAttemptDate") == today.isoformat()
        and state.get("status") == "failed"
        and "Invalid date format" in str(state.get("error", ""))
        and not state.get("formatRetryAttempted")
    )


async def run_service(config_path: Path, state_path: Path, dry_run: bool) -> None:
    while True:
        config = read_booking_config(config_path)
        state = read_json(state_path, {})
        grace = max(0, int(config.get("graceMinutes", 10)))
        now = datetime.now().astimezone()
        run_at = parse_run_time(config.get("runAt", "05:00"))
        resume_monitor = should_resume_monitoring(config, state, now) and not dry_run
        recovery_due = should_recover_booking(config, state, now, run_at) and not dry_run
        format_retry = should_retry_invalid_date(state, now.date())
        due = now if (resume_monitor or recovery_due or format_retry) else next_due(
            now, run_at, grace, str(state.get("lastAttemptDate", ""))
        )
        delay = max(0.0, (due - now).total_seconds())
        if resume_monitor:
            label = "resuming cancellation/refund monitor"
        elif recovery_due:
            label = "checking for a missing booking after restart"
        elif format_retry:
            label = "retrying corrected date format"
        else:
            label = "next booking attempt"
        print(f"[{now.isoformat()}] {label}: {due.isoformat()}", flush=True)
        await asyncio.sleep(delay)

        woke_at = datetime.now().astimezone()
        window_end = datetime.combine(due.date(), run_at, tzinfo=woke_at.tzinfo) + timedelta(
            minutes=grace
        )
        if woke_at > window_end and not (format_retry or resume_monitor or recovery_due):
            print(f"[{woke_at.isoformat()}] missed booking window; waiting for tomorrow", flush=True)
            continue

        if resume_monitor:
            attempt_date = date.fromisoformat(str(state["lastAttemptDate"]))
        else:
            attempt_date = due.date()
            state = {
                "lastAttemptDate": attempt_date.isoformat(),
                "attemptedAt": datetime.now().astimezone().isoformat(),
                "status": "starting",
            }
            if format_retry:
                state["formatRetryAttempted"] = True
            write_json(state_path, state)
        try:
            config = read_booking_config(config_path)
            if resume_monitor:
                state = await monitor_and_rebook(
                    config, attempt_date, state_path, state
                )
            elif not dry_run:
                state = await recover_or_create_booking(
                    config, attempt_date, state_path
                )
                state = await monitor_and_rebook(
                    config, attempt_date, state_path, state
                )
            else:
                result = await submit(config, attempt_date, dry_run)
                state["status"] = "dry-run"
        except Exception as exc:
            state = read_json(state_path, state)
            if state.get("status") not in {"rebook-failed", "monitor-error"}:
                state["status"] = "failed"
            state["error"] = str(exc)
            print(f"[!] {exc}", flush=True)
        write_json(state_path, state)
        if not dry_run and not state.get("bookingId"):
            _, _, retry_seconds, _ = rebook_options(config)
            print(
                f"No booking is currently tracked; checking again in {retry_seconds}s.",
                flush=True,
            )
            await asyncio.sleep(retry_seconds)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily 05:00 Gridee API booking service.")
    parser.add_argument("--config", type=Path, default=Path("booking_service.json"))
    parser.add_argument("--state", type=Path, default=Path("booking_service.state.json"))
    parser.add_argument("--init", action="store_true", help="Create the saved booking template.")
    parser.add_argument("--setup", action="store_true", help="Detect and choose booking values.")
    parser.add_argument("--once", action="store_true", help="Run immediately instead of waiting.")
    parser.add_argument("--dry-run", action="store_true", help="Print the rendered request without sending it.")
    return parser


async def main() -> None:
    args = make_parser().parse_args()
    if args.init:
        write_json(args.config, DEFAULT_CONFIG, overwrite=False)
        print(f"Created {args.config}. Fill in the saved booking fields before starting.")
        return
    if args.setup:
        await setup(args.config)
        return
    config = read_booking_config(args.config)
    try:
        booking_body(config, datetime.now().astimezone().date())
    except ServiceError:
        if not sys.stdin.isatty():
            raise
        print("Saved booking is incomplete; starting interactive detection.")
        await setup(args.config)
        config = read_booking_config(args.config)
    if args.once:
        await submit(config, datetime.now().astimezone().date(), args.dry_run)
    else:
        await run_service(args.config, args.state, args.dry_run)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        raise SystemExit(f"[!] {exc}") from exc
