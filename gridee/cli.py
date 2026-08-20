from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from .api import ApiError, DEFAULT_BASE_URL, default_session_file, run_api, run_auth
from .booking import BookingError, parse_date, parse_hhmm, run_booking
from .core import Config, Gridee
from .scheduler import parse_datetime, run_scheduler


class GrideeParser(argparse.ArgumentParser):
    """ArgumentParser with a concise error message and a help hint."""

    def error(self, message: str):
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.stderr.write(f"Try '{self.prog} --help' for the full list of options.\n")
        self.exit(2)


REWARD_EPILOG = """\
examples:
  gridee reward                     watch one ad
  gridee reward --earn 200          earn 200 more coins, then stop
  gridee reward --target 2000       run ads until the balance reaches 2000
  gridee --device SERIAL reward     target a specific device
"""


def add_api_connection_options(parser: argparse.ArgumentParser, *, allow_login: bool = True) -> None:
    parser.add_argument(
        "--base-url",
        default=os.getenv("GRIDEE_BASE_URL", DEFAULT_BASE_URL),
        help="Gridee API origin (env: GRIDEE_BASE_URL).",
    )
    parser.add_argument(
        "--session-file",
        type=Path,
        default=Path(os.getenv("GRIDEE_SESSION_FILE", str(default_session_file()))),
        help="Saved bearer-session file (env: GRIDEE_SESSION_FILE).",
    )
    parser.add_argument("--token", default=os.getenv("GRIDEE_TOKEN"), help="Bearer token (env: GRIDEE_TOKEN).")
    parser.add_argument(
        "--token-type",
        default=os.getenv("GRIDEE_TOKEN_TYPE"),
        help="Authentication scheme returned by login (default: Bearer).",
    )
    parser.add_argument("--api-timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    if allow_login:
        parser.add_argument("--email", default=os.getenv("GRIDEE_EMAIL"), help="Login email (env: GRIDEE_EMAIL).")
        password = parser.add_mutually_exclusive_group()
        password.add_argument(
            "--password",
            default=os.getenv("GRIDEE_PASSWORD"),
            help="Login password; secure prompt or --password-stdin is preferred.",
        )
        password.add_argument(
            "--password-stdin",
            action="store_true",
            help="Read one password line from stdin.",
        )
        parser.add_argument("--no-save", action="store_true", help="Do not save a successful login token.")


def make_parser() -> argparse.ArgumentParser:
    parser = GrideeParser(
        prog="gridee",
        description="ADB/UIAutomator CLI for the Gridee Android app.",
        epilog="Run 'gridee <command> --help' for command-specific options.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--device", default=os.getenv("GRIDEE_DEVICE", "a2628a8c"),
                        help="ADB serial (env: GRIDEE_DEVICE).")
    parser.add_argument("--package", default=os.getenv("GRIDEE_PACKAGE", "com.gridee.parking"),
                        help="App package (env: GRIDEE_PACKAGE).")
    parser.add_argument("--activity", default=os.getenv("GRIDEE_ACTIVITY", ".ui.auth.SplashActivity"),
                        help="Launch activity (env: GRIDEE_ACTIVITY).")
    parser.add_argument("--adb", default=os.getenv("GRIDEE_ADB", "adb"),
                        help="Path to the adb binary (env: GRIDEE_ADB).")
    parser.add_argument("--output", type=Path, default=Path(os.getenv("GRIDEE_OUTPUT", "runs")),
                        help="Output directory for artifacts (env: GRIDEE_OUTPUT).")
    parser.add_argument("--poll", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each adb command.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON where supported.")

    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    sub.add_parser("devices", help="List connected ADB devices.")
    sub.add_parser("info", help="Show device and app information.")
    sub.add_parser("launch", help="Launch Gridee.")
    sub.add_parser("wallet", help="Open Wallet.")
    sub.add_parser("balance", help="Open Wallet and print balance.")
    sub.add_parser("back", help="Press Android Back.")
    sub.add_parser("home", help="Press Android Home.")
    sub.add_parser("config", help="Print effective configuration.")

    p = sub.add_parser("screenshot", help="Save a screenshot.")
    p.add_argument("--name", default="screen")

    p = sub.add_parser("dump", help="Save and summarize current UI hierarchy.")
    p.add_argument("--list", action="store_true", help="Print inspectable nodes.")

    p = sub.add_parser("tap", help="Tap raw screen coordinates.")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)

    p = sub.add_parser("click", help="Tap an element after a fresh UI dump.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--id")
    group.add_argument("--text")
    group.add_argument("--desc")
    p.add_argument("--timeout", type=float, default=30)

    p = sub.add_parser("wait", help="Wait for an element or Wallet.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--id")
    group.add_argument("--text")
    group.add_argument("--desc")
    group.add_argument("--wallet", action="store_true")
    p.add_argument("--timeout", type=float, default=60)

    p = sub.add_parser("monitor", help="Monitor Wallet balance.")
    p.add_argument("--timeout", type=float, default=0, help="0 means run until interrupted.")
    p.add_argument("--until-change", action="store_true")

    p = sub.add_parser(
        "reward",
        help="Watch rewarded ads and verify Wallet credit.",
        description="Watch rewarded ads until a balance goal is met.",
        epilog=REWARD_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--amount",
        type=float,
        default=10.0,
        help="Reward granted per ad (default 10).",
    )
    goal = p.add_mutually_exclusive_group()
    goal.add_argument(
        "--target",
        type=float,
        default=None,
        help=(
            "Final Wallet balance goal. When set, reward cycles repeat until the "
            "Wallet reaches this balance instead of running a single cycle."
        ),
    )
    goal.add_argument(
        "--earn",
        type=float,
        default=None,
        help=(
            "Total additional coins to earn this run (a top-up relative to the "
            "starting balance), instead of a fixed final-balance goal."
        ),
    )
    p.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Safety cap on reward cycles in --target mode. 0 means unlimited.",
    )
    p.add_argument(
        "--allow-custom-amount",
        action="store_true",
        help="Allow an expected one-cycle reward amount other than 10.",
    )
    p.add_argument(
        "--no-keep-awake",
        action="store_true",
        help="Do not temporarily keep the phone awake while connected over USB.",
    )
    p.add_argument(
        "--poke-interval",
        type=float,
        default=20.0,
        help="Seconds between input pokes that keep the screen from dimming (0 to disable).",
    )
    p.add_argument("--timeout", type=float, default=240.0, help="Per-ad timeout in seconds.")
    p.add_argument(
        "--ad-open-timeout",
        type=float,
        default=25.0,
        help="Seconds to wait for an ad to open after tapping Watch & Claim.",
    )
    p.add_argument(
        "--credit-deadline",
        type=float,
        default=60.0,
        help=(
            "Seconds to wait for a launched ad's reward to credit before assuming "
            "it failed and launching a replacement."
        ),
    )
    p.add_argument("--startup-delay", type=float, default=4.0,
                   help="Seconds to wait after launching Gridee (default 4).")

    p = sub.add_parser("booking", help="Prepare or submit a parking booking through the Android UI.")
    p.add_argument("--venue", default="Tech Park Avenue", help="Preferred venue name (fuzzy matched).")
    p.add_argument("--venue-threshold", type=float, default=0.35, help="Minimum fuzzy-match score.")
    p.add_argument("--open-at", type=parse_hhmm, default=parse_hhmm("05:00"))
    p.add_argument("--start", type=parse_hhmm, default=parse_hhmm("08:00"))
    p.add_argument("--end", type=parse_hhmm, default=parse_hhmm("17:00"))
    p.add_argument("--date", type=parse_date, help="Booking date (YYYY-MM-DD); defaults automatically.")
    p.add_argument("--late-buffer-minutes", type=int, default=5)
    p.add_argument("--venue-timeout", type=float, default=180)
    p.add_argument("--startup-delay", type=float, default=2.0)
    p.add_argument("--no-wait", action="store_true", help="Fail instead of waiting for booking opening time.")
    p.add_argument("--execute", action="store_true", help="Press the final booking button (default is dry run).")
    p.add_argument("--keep-awake", action="store_true", help="Leave USB stay-awake enabled afterward.")

    auth = sub.add_parser("auth", help="Manage a live API login session.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True, metavar="<auth-command>")
    p = auth_sub.add_parser("login", help="Log in with an email/password and optionally save the bearer token.")
    add_api_connection_options(p)
    p.add_argument("--show-token", action="store_true", help="Print the token (normally redacted).")
    p = auth_sub.add_parser("status", help="Show saved-session status.")
    add_api_connection_options(p, allow_login=False)
    p.add_argument("--live", action="store_true", help="Verify the token against /api/oauth2/user.")
    p = auth_sub.add_parser("logout", help="Remove the locally saved session.")
    p.add_argument(
        "--session-file",
        type=Path,
        default=Path(os.getenv("GRIDEE_SESSION_FILE", str(default_session_file()))),
    )

    api = sub.add_parser("api", help="Call documented Gridee HTTP endpoints.")
    api_sub = api.add_subparsers(dest="api_command", required=True, metavar="<api-command>")
    p = api_sub.add_parser("user", help="GET /api/oauth2/user.")
    add_api_connection_options(p)
    p = api_sub.add_parser("parking-lots", help="GET /api/parking-lots.")
    add_api_connection_options(p)
    p = api_sub.add_parser("wallet", help="GET the current account's wallet.")
    add_api_connection_options(p)
    p.add_argument("--user-id", help="Optional user ID override; defaults to current account.")
    p = api_sub.add_parser(
        "wallet-topup", help="Initiate POST /api/users/{userId}/wallet/topup."
    )
    add_api_connection_options(p)
    p.add_argument("--user-id", help="Optional user ID override; defaults to current account.")
    p.add_argument("--amount", required=True, type=float, help="Positive top-up amount.")
    p.add_argument("--execute", action="store_true", help="Send the write request (default: preview).")
    p = api_sub.add_parser("request", help="Call any documented endpoint.")
    add_api_connection_options(p)
    p.add_argument("path", help="API path, for example /api/bookings/my-bookings.")
    p.add_argument("--method", default="GET", choices=("GET", "POST", "PUT", "PATCH", "DELETE"))
    body = p.add_mutually_exclusive_group()
    body.add_argument("--data", help="JSON request body.")
    body.add_argument("--data-file", type=Path, help="Read JSON request body from a file.")
    p.add_argument("--query", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--header", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--anonymous", action="store_true", help="Do not attach authentication.")

    scheduler = sub.add_parser("scheduler", help="Build and control the on-device booking scheduler.")
    scheduler_sub = scheduler.add_subparsers(
        dest="scheduler_command", required=True, metavar="<scheduler-command>"
    )
    p = scheduler_sub.add_parser("build", help="Build the Android helper APK.")
    p.add_argument("--android-sdk")
    p.add_argument("--build-tools-version", default="35.0.0")
    p = scheduler_sub.add_parser("install", help="Install or update the built helper APK.")
    p.add_argument("--apk", type=Path, default=Path("android-helper/build/gridee-scheduler-debug.apk"))
    scheduler_sub.add_parser("enable", help="Open Android accessibility settings.")
    p = scheduler_sub.add_parser("schedule", help="Configure a one-shot on-device UI booking.")
    p.add_argument("--at", type=parse_datetime, required=True, help="Local ISO date/time to launch automation.")
    p.add_argument("--venue", default="Tech Park Avenue")
    p.add_argument("--start", default="08:00")
    p.add_argument("--end", default="17:00")
    p.add_argument("--date", help="Booking date passed to the helper (YYYY-MM-DD).")
    p.add_argument("--venue-threshold", type=float, default=0.35)
    p.add_argument("--execute", action="store_true", help="Allow final booking confirmation.")
    scheduler_sub.add_parser("status", help="Read the helper's current schedule/status.")
    scheduler_sub.add_parser("cancel", help="Cancel the pending on-device schedule.")

    sub.add_parser("inspect", help="Interactive UI inspector.")
    return parser


def list_devices(adb: str, as_json: bool) -> int:
    result = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True)
    if as_json:
        devices = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                devices.append({"serial": parts[0], "state": parts[1], "details": parts[2:]})
        print(json.dumps(devices, indent=2))
    else:
        print(result.stdout.rstrip())
    return result.returncode


def print_nodes(app: Gridee, root) -> list:
    nodes = app.list_nodes(root)
    for n in nodes:
        marker = "*" if n.clickable else " "
        print(
            f"{marker}[{n.index:03d}] text={n.text!r} desc={n.desc!r} "
            f"id={n.resource_id!r} enabled={n.enabled} bounds={n.bounds!r}"
        )
    return nodes


def inspect(app: Gridee) -> int:
    print("Commands: r, number, f QUERY, id ID, text TEXT, desc DESC, w, s, d, b, h, q")
    root = app.dump_ui("inspect")
    nodes = [] if root is None else print_nodes(app, root)

    while True:
        try:
            cmd = input("gridee> ").strip()
        except EOFError:
            return 0

        if not cmd:
            continue
        if cmd == "q":
            return 0
        if cmd == "r":
            root = app.dump_ui("inspect-refresh")
            nodes = [] if root is None else print_nodes(app, root)
            continue
        if cmd == "s":
            print(app.screenshot("inspect"))
            continue
        if cmd == "d":
            root = app.dump_ui("manual-dump")
            print("dumped" if root is not None else "dump failed")
            continue
        if cmd == "b":
            app.adb("shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1)
            root = app.dump_ui("after-back")
            nodes = [] if root is None else print_nodes(app, root)
            continue
        if cmd == "h":
            app.adb("shell", "input", "keyevent", "KEYCODE_HOME")
            continue
        if cmd == "w":
            root = app.open_wallet(timeout=180)
            nodes = print_nodes(app, root)
            continue
        if cmd.startswith("f "):
            q = cmd[2:].lower()
            for n in nodes:
                if q in f"{n.text} {n.desc} {n.resource_id}".lower():
                    print(n)
            continue
        if cmd.startswith("id "):
            app.fresh_tap(resource_id=cmd[3:].strip(), name="resource-id")
            continue
        if cmd.startswith("text "):
            app.fresh_tap(text=cmd[5:].strip(), name="text")
            continue
        if cmd.startswith("desc "):
            app.fresh_tap(desc=cmd[5:].strip(), name="description")
            continue
        if cmd.isdigit():
            idx = int(cmd)
            if not 0 <= idx < len(nodes):
                print("[!] Invalid index")
                continue
            selected = nodes[idx]
            try:
                if selected.resource_id:
                    app.fresh_tap(resource_id=selected.resource_id, name="selected element")
                elif selected.desc:
                    app.fresh_tap(desc=selected.desc, name="selected element")
                elif selected.text:
                    app.fresh_tap(text=selected.text, name="selected element")
                else:
                    print("[!] Element has no stable selector")
            except Exception as exc:
                print(f"[!] {exc}")
            continue
        print("[!] Unknown command")


def pump_notifications(app: Gridee, state: dict, now: float) -> None:
    """Fold any new wallet-credit notifications into the pipeline state.

    Each new notification is a reward that has landed; match it (FIFO) against a
    launched-but-uncredited ad and add its points to the running total.
    """
    for item in app.get_gridee_wallet_notifications():
        key = item.get("key")
        if not key or key in state["seen_keys"]:
            continue
        state["seen_keys"].add(key)
        amount = item.get("amount")
        if not isinstance(amount, (int, float)):
            amount = state["amount"]
        state["credited_points"] += amount
        state["credited_count"] += 1
        if state["launches"]:
            state["launches"].pop(0)
        state["last_credit_time"] = now
        print(
            f"[+] Reward credited +{amount:g}  "
            f"({state['credited_points']:g}/{state['needed']:g} earned)"
        )


def _tap_button(app: Gridee, state: dict, resource_id: str, name: str, settle: float) -> bool:
    """Tap a button by resource-id.

    The center is learned once via a UI dump and cached, then tapped directly on
    later calls -- uiautomator commonly wedges after an ad WebView, and a dump
    per launch would stall for seconds. Button positions are fixed, so this is safe.
    """
    coords = state["coords"].get(resource_id)

    if coords is None:
        root = app.dump_ui("locate", retries=2)
        if root is not None:
            node = app.find_node(root, resource_id=resource_id)
            if node is not None and node.attrib.get("enabled", "true").lower() == "true":
                try:
                    x1, y1, x2, y2 = app.parse_bounds(node.attrib.get("bounds", ""))
                    coords = ((x1 + x2) // 2, (y1 + y2) // 2)
                    state["coords"][resource_id] = coords
                except Exception:
                    coords = None
        if coords is None:
            return False

    print(f"[+] Tapping {name} at {coords}")
    app.tap_xy(*coords)
    time.sleep(settle)
    return True


def activity_state(app: Gridee) -> str:
    """Classify the foreground activity via dumpsys (works when uiautomator is
    wedged): 'wallet', 'ad', 'gridee_other', 'stray', or 'unknown'."""
    act = app.current_activity()
    low = act.lower()
    if "adactivity" in low or "com.google.android.gms.ads" in low:
        return "ad"
    if "maincontaineractivity" in low:
        return "wallet"
    if not act:
        return "unknown"
    if act.startswith(app.config.package + "/"):
        return "gridee_other"
    return "stray"  # Play Store, browser, launcher -- e.g. an ad mis-tap


def ensure_on_wallet(app: Gridee, timeout: float) -> bool:
    """Wait until Gridee's main screen is foreground, backing out of stray
    screens (e.g. a Play Store page from an ad mis-tap) along the way."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = activity_state(app)
        if st == "wallet":
            return True
        if st == "stray":
            print("[!] Stray screen (e.g. Play Store); pressing Back to return to Gridee.")
            app.adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False, timeout=5)
            time.sleep(1.2)
        elif st == "ad":
            time.sleep(0.6)
        else:
            time.sleep(0.5)
    return activity_state(app) == "wallet"


def _back(app: Gridee) -> None:
    app.adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False, timeout=5)


def play_one_ad(app: Gridee, args, state: dict) -> bool:
    """Tap Earn + Watch & Claim and wait for the ad to open then close.

    Every tap is gated on Gridee's own screen being foreground, so a tap can
    never land on an ad creative or the Play Store. Does NOT wait for the reward
    to credit -- that lands asynchronously while the next ad plays.
    """
    if not ensure_on_wallet(app, 15):
        app.launch()
        time.sleep(2)
        if not ensure_on_wallet(app, 10):
            print("[!] Could not return to the Wallet screen; skipping this launch.")
            return False

    time.sleep(0.8)

    if not _tap_button(app, state, app.EARN_BUTTON_ID, f"Earn {args.amount:g}", settle=1.5):
        print("[!] Could not find the Earn button.")
        return False

    t0 = time.time()
    next_poke = t0 + args.poke_interval

    st = activity_state(app)
    if st == "stray":
        print("[!] Earn tap opened a stray screen; backing out.")
        _back(app)
        return False
    if st != "ad":
        if not _tap_button(app, state, app.CLAIM_BUTTON_ID, "Watch & Claim", settle=0.5):
            print("[!] Could not find the Watch & Claim button.")
            return False
        if activity_state(app) == "stray":
            print("[!] Watch & Claim opened a stray screen; backing out.")
            _back(app)
            return False

    opened = False
    while time.time() - t0 < args.ad_open_timeout:
        pump_notifications(app, state, time.time())
        st = activity_state(app)
        if st == "ad":
            opened = True
            break
        if st == "stray":
            print("[!] A tap opened the Play Store; backing out and retrying.")
            _back(app)
            time.sleep(1.0)
            return False
        time.sleep(0.5)

    if not opened:
        return False

    while time.time() - t0 < args.timeout:
        now = time.time()
        if not app.is_screen_on():
            app.wake_screen()
            time.sleep(1)
        if args.poke_interval > 0 and now >= next_poke:
            app.poke()
            next_poke = now + args.poke_interval
        pump_notifications(app, state, now)
        if activity_state(app) != "ad":
            return True
        time.sleep(0.6)

    return True


def run_reward(app: Gridee, args) -> int:
    app.verify_device()

    if args.amount <= 0:
        raise RuntimeError("--amount must be greater than 0.")

    if args.amount != 10.0 and not args.allow_custom_amount:
        raise RuntimeError(
            "--amount is the per-ad reward, not a final balance goal. This app "
            "grants 10 per ad. Use --amount 10, and pass --target/--earn to set a "
            "goal. Pass --allow-custom-amount only if the per-ad reward changed."
        )

    if args.earn is not None and args.earn <= 0:
        raise RuntimeError("--earn must be greater than 0.")
    if args.max_cycles < 0:
        raise RuntimeError("--max-cycles cannot be negative.")

    original_stay_awake = None
    if not args.no_keep_awake:
        original_stay_awake = app.get_stay_awake_setting()
        app._original_stay_awake = original_stay_awake
        app.set_stay_awake(True)
        app._original_screen_timeout = app.get_screen_off_timeout()
        app.set_screen_off_timeout(1800000)  # 30 minutes; keeps the screen from dimming
        app.wake_screen()
        print("[+] Keeping device awake while connected over USB.")

    app.launch()
    time.sleep(args.startup_delay)

    start_balance = None
    for attempt in range(2):
        try:
            wallet = app.open_wallet(timeout=30)
            start_balance = app.read_balance(wallet)
        except TimeoutError:
            start_balance = None
        if start_balance is not None:
            break
        if attempt == 0:
            print("[.] Wallet not readable; restarting Gridee for a clean state.")
            app.adb("shell", "am", "force-stop", app.config.package, check=False)
            time.sleep(2)
            app.launch()
            time.sleep(args.startup_delay)
    if start_balance is None:
        raise RuntimeError("Could not read starting Wallet balance.")

    if args.earn is not None:
        final_target = start_balance + args.earn
    elif args.target is not None:
        final_target = args.target
    else:
        final_target = start_balance + args.amount

    started_at = time.time()
    amount = args.amount
    needed = final_target - start_balance

    print(f"[+] Starting Wallet balance: {start_balance:.2f}")
    if args.earn is not None:
        print(f"[+] Top-up goal:             +{args.earn:.2f} (to {final_target:.2f})")
    else:
        print(f"[+] Final target balance:    {final_target:.2f}")

    if needed <= 0:
        print("[+] Target balance already reached; nothing to do.")
        result = {
            "success": True,
            "reason": "already at or above target",
            "starting_balance": start_balance,
            "target_balance": final_target,
            "final_balance": start_balance,
            "reward_amount": 0.0,
            "ads_launched": 0,
        }
        report = app.save_json(result, "reward-success")
        print(json.dumps(result, indent=2) if args.json else f"[+] Report: {report}")
        return 0

    ads_needed = math.ceil(needed / amount)
    print(f"[+] Need ~{ads_needed} ad(s) at {amount:g} each. Pipelining without waiting per-ad.")

    try:
        seen_keys = {n["key"] for n in app.get_gridee_wallet_notifications() if n["key"]}
    except Exception:
        seen_keys = set()

    state = {
        "seen_keys": seen_keys,
        "credited_points": 0.0,
        "credited_count": 0,
        "launches": [],          # timestamps of ads launched but not yet credited
        "last_credit_time": time.time(),
        "amount": amount,
        "needed": needed,
        "coords": {},
    }

    max_launches = args.max_cycles  # 0 == unlimited
    launched_total = 0
    last_status = 0.0
    overall_deadline = started_at + max(args.timeout, ads_needed * args.timeout)

    while state["credited_points"] < needed and time.time() < overall_deadline:
        now = time.time()
        pump_notifications(app, state, now)
        if state["credited_points"] >= needed:
            break

        state["launches"] = [t for t in state["launches"] if now - t < args.credit_deadline]
        pending = len(state["launches"])
        remaining_credits = math.ceil((needed - state["credited_points"]) / amount)

        if pending < remaining_credits and (max_launches == 0 or launched_total < max_launches):
            launched_total += 1
            print(
                f"[+] Ad {launched_total}: earned {state['credited_points']:g}/{needed:g}, "
                f"{pending} pending credit(s)."
            )
            if play_one_ad(app, args, state):
                state["launches"].append(time.time())
            else:
                print("[!] Ad did not open (no fill?); retrying shortly.")
                time.sleep(2)
        else:
            if max_launches and launched_total >= max_launches and pending == 0:
                print(f"[!] Reached --max-cycles limit ({max_launches}); stopping.")
                break
            if now - last_status >= 10:
                print(
                    f"[.] Waiting for {pending} pending reward(s) to credit "
                    f"({state['credited_points']:g}/{needed:g})."
                )
                last_status = now
            time.sleep(1.0)

    final_balance = None
    try:
        wallet = app.open_wallet(timeout=20)
        final_balance = app.read_balance(wallet)
    except Exception:
        pass
    if final_balance is None:
        final_balance = start_balance + state["credited_points"]

    duration = time.time() - started_at
    success = state["credited_points"] >= needed or final_balance >= final_target
    result = {
        "success": success,
        "reason": "target reached" if success else "stopped before target",
        "starting_balance": start_balance,
        "target_balance": final_target,
        "final_balance": final_balance,
        "reward_amount": final_balance - start_balance,
        "ads_launched": launched_total,
        "rewards_credited": state["credited_count"],
        "duration_seconds": round(duration, 2),
    }

    app.screenshot("reward-success" if success else "reward-timeout")
    report = app.save_json(result, "reward-success" if success else "reward-timeout")

    if args.json:
        print(json.dumps(result, indent=2))
    elif success:
        print(f"[+] Done: {start_balance:.2f} -> {final_balance:.2f} in {launched_total} ad(s).")
        print(f"[+] Report: {report}")
    else:
        print(f"[!] Stopped at {final_balance:.2f}; goal was {final_target:.2f}.")
        print(f"[!] Report: {report}")

    return 0 if success else 1


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()

    if args.command == "devices":
        return list_devices(args.adb, args.json)

    if args.command in {"auth", "api"}:
        try:
            return run_auth(args) if args.command == "auth" else run_api(args)
        except (ApiError, OSError) as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1

    cfg = Config(
        device=args.device,
        package=args.package,
        activity=args.activity,
        adb=args.adb,
        output=args.output,
        poll_interval=args.poll,
    )
    app = Gridee(cfg, verbose=args.verbose)

    try:
        if args.command == "config":
            data = {
                "device": cfg.device,
                "package": cfg.package,
                "activity": cfg.activity,
                "adb": cfg.adb,
                "output": str(cfg.output),
                "poll_interval": cfg.poll_interval,
            }
            print(json.dumps(data, indent=2))
            return 0

        if args.command == "scheduler" and args.scheduler_command == "build":
            return run_scheduler(app, args)

        app.verify_device()

        if args.command == "info":
            data = app.device_info()
            print(json.dumps(data, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in data.items()))
            return 0

        if args.command == "launch":
            app.launch()
            return 0

        if args.command == "wallet":
            app.launch()
            time.sleep(2)
            app.open_wallet()
            print("[+] Wallet opened")
            return 0

        if args.command == "balance":
            app.launch()
            time.sleep(2)
            root = app.open_wallet()
            balance = app.read_balance(root)
            if balance is None:
                raise RuntimeError("Could not read balance.")
            print(json.dumps({"balance": balance}) if args.json else f"{balance:.2f}")
            return 0

        if args.command == "screenshot":
            print(app.screenshot(args.name))
            return 0

        if args.command == "dump":
            root = app.dump_ui("manual")
            if root is None:
                raise RuntimeError("UI dump failed.")
            if args.list:
                print_nodes(app, root)
            else:
                print("[+] UI hierarchy saved")
            return 0

        if args.command == "tap":
            app.tap_xy(args.x, args.y)
            return 0

        if args.command == "click":
            app.fresh_tap(
                resource_id=args.id, text=args.text, desc=args.desc,
                name=args.id or args.text or args.desc, timeout=args.timeout
            )
            return 0

        if args.command == "wait":
            if args.wallet:
                app.open_wallet(timeout=args.timeout)
                print("[+] Wallet detected")
            else:
                app.wait_for_node(
                    resource_id=args.id, text=args.text, desc=args.desc,
                    timeout=args.timeout
                )
                print("[+] Element detected")
            return 0

        if args.command == "monitor":
            app.launch()
            time.sleep(2)
            root = app.open_wallet()
            initial = app.read_balance(root)
            last = initial
            deadline = None if args.timeout <= 0 else time.time() + args.timeout
            print(f"[+] Initial balance: {initial:.2f}" if initial is not None else "[+] Monitoring")
            while deadline is None or time.time() < deadline:
                root = app.dump_ui("monitor")
                if root is not None and app.is_wallet(root):
                    balance = app.read_balance(root)
                    if balance is not None and balance != last:
                        print(f"[+] Balance changed: {last} -> {balance}")
                        if args.until_change:
                            return 0
                        last = balance
                time.sleep(cfg.poll_interval)
            return 0

        if args.command == "reward":
            return run_reward(app, args)

        if args.command == "booking":
            return run_booking(app, args)

        if args.command == "scheduler":
            return run_scheduler(app, args)

        if args.command == "inspect":
            return inspect(app)

        if args.command == "back":
            app.adb("shell", "input", "keyevent", "KEYCODE_BACK")
            return 0

        if args.command == "home":
            app.adb("shell", "input", "keyevent", "KEYCODE_HOME")
            return 0

        parser.error("Unsupported command")
        return 2

    except KeyboardInterrupt:
        print("\n[!] Interrupted")
        return 130
    except (RuntimeError, TimeoutError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            app.adb("shell", "rm", "-f", app.remote_xml, check=False)
        except Exception:
            pass

        if args.command == "reward":
            try:
                original = getattr(app, "_original_stay_awake", None)
                if original is not None:
                    app.restore_stay_awake_setting(original)
                    print("[+] Restored previous device stay-awake setting.")
            except Exception:
                pass

            try:
                original_timeout = getattr(app, "_original_screen_timeout", None)
                if original_timeout:
                    app.restore_screen_off_timeout(original_timeout)
            except Exception:
                pass
