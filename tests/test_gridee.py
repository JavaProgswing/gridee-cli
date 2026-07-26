"""Unit tests for Gridee CLI parsing, UI classification, and dump handling.

These tests are device-free: they exercise pure XML/string logic and argument
parsing. Run with: python -m pytest
"""
from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from gridee.core import Config, Gridee
from gridee.cli import make_parser, activity_state


def make_app() -> Gridee:
    return Gridee(Config(output=Path(tempfile.mkdtemp(prefix="gridee-test-"))))


def node(**attrs: str) -> str:
    body = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f"<node {body}></node>"


def hierarchy(*nodes: str) -> ET.Element:
    xml = "<hierarchy rotation=\"0\">" + "".join(nodes) + "</hierarchy>"
    return ET.fromstring(xml)


WALLET_XML = hierarchy(
    node(**{"resource-id": "com.gridee.parking:id/tab_wallet", "class": "android.widget.FrameLayout"}),
    node(**{"resource-id": "com.gridee.parking:id/tv_balance_amount", "text": "190.00",
            "content-desc": "Balance 190.00 Gridee coins"}),
)


def test_is_wallet_true():
    assert make_app().is_wallet(WALLET_XML) is True


def test_is_wallet_false_when_balance_missing():
    root = hierarchy(node(**{"resource-id": "com.gridee.parking:id/tab_wallet"}))
    assert make_app().is_wallet(root) is False


def test_read_balance_plain():
    assert make_app().read_balance(WALLET_XML) == 190.0


def test_read_balance_with_thousands_separator():
    root = hierarchy(
        node(**{"resource-id": "com.gridee.parking:id/tv_balance_amount", "text": "1,234.50"}),
    )
    assert make_app().read_balance(root) == 1234.5


def test_read_balance_missing_returns_none():
    root = hierarchy(node(**{"resource-id": "other", "text": "x"}))
    assert make_app().read_balance(root) is None


def test_read_balance_non_numeric_returns_none():
    root = hierarchy(
        node(**{"resource-id": "com.gridee.parking:id/tv_balance_amount", "text": "--"}),
    )
    assert make_app().read_balance(root) is None


def test_extract_hierarchy_strips_trailing_marker():
    blob = (
        "<?xml version='1.0'?><hierarchy rotation=\"0\">"
        "<node text=\"x\"></node></hierarchy>"
        "UI hierchary dumped to: /dev/tty"
    )
    xml = Gridee._extract_hierarchy(blob)
    assert xml.endswith("</hierarchy>")
    assert "dumped to" not in xml
    ET.fromstring(xml)


def test_extract_hierarchy_without_xml_decl():
    blob = "junk<hierarchy><node/></hierarchy>trailing"
    xml = Gridee._extract_hierarchy(blob)
    assert xml == "<hierarchy><node/></hierarchy>"


def test_extract_hierarchy_returns_none_on_error_blob():
    assert Gridee._extract_hierarchy("ERROR: could not get idle state.") is None

class _FakeResult:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.returncode = 0


@pytest.mark.parametrize(
    "dump,expected",
    [
        ("mWakefulness=Awake\n", True),
        ("mWakefulness=Dozing\n", False),   # always-on display -> needs wake
        ("mWakefulness=Asleep\n", False),
        ("mWakefulness=Dreaming\n", False),
        ("Display Power: state=OFF\n", False),
        ("mScreenState=DOZE\n", False),
        ("some unrelated output\n", True),   # no signal -> assume on
    ],
)
def test_is_screen_on_parsing(monkeypatch, dump, expected):
    app = make_app()
    monkeypatch.setattr(app, "adb", lambda *a, **k: _FakeResult(dump))
    assert app.is_screen_on() is expected


def test_is_screen_on_defaults_true_when_dump_fails():
    app = make_app()
    app.adb = lambda *a, **k: None  # simulate timeout
    assert app.is_screen_on() is True


_NOTIF_DUMP = """
NotificationRecord(0x0551a311: pkg=com.gridee.parking user=UserHandle{0} id=504494995 tag=null importance=4 key=0|com.gridee.parking|504494995|null|10379: Notification(channel=gridee_live_updates_v2)
      key=0|com.gridee.parking|504494995|null|10379
                android.title=String (Wallet Updated : Ad Top-up)
                android.text=String (10.0 points added to your wallet.)
                android.bigText=String (10.0 points added to your wallet.)
NotificationRecord(0x0f2a085e: pkg=com.gridee.parking user=UserHandle{0} id=469459915 tag=null importance=4 key=0|com.gridee.parking|469459915|null|10379: Notification(channel=gridee_live_updates_v2)
      key=0|com.gridee.parking|469459915|null|10379
                android.title=String (Wallet Updated : Ad Top-up)
                android.text=String (10.0 points added to your wallet.)
NotificationRecord(0x99: pkg=com.other.app id=1 key=0|com.other.app|1|null|1: Notification()
                android.title=String (Something else)
"""


def test_notifications_parse_and_keys():
    app = make_app()
    app.adb = lambda *a, **k: _FakeResult(_NOTIF_DUMP)
    notes = app.get_gridee_wallet_notifications()
    assert len(notes) == 2  # only gridee wallet notifications
    keys = {n["key"] for n in notes}
    assert len(keys) == 2   # unique per credit
    assert all(n["amount"] == 10.0 for n in notes)
    assert all("Wallet Updated" in n["title"] for n in notes)
    assert all(")" not in n["title"] for n in notes)  # String(...) unwrapped


def test_notifications_empty_when_none():
    app = make_app()
    app.adb = lambda *a, **k: None
    assert app.get_gridee_wallet_notifications() == []

_AD_ACTIVITIES = "  topResumedActivity=ActivityRecord{abc u0 com.gridee.parking/com.google.android.gms.ads.AdActivity t9}\n"
_MAIN_ACTIVITIES = "  topResumedActivity=ActivityRecord{abc u0 com.gridee.parking/.ui.main.MainContainerActivity t9}\n"


def test_current_activity_parses_component():
    app = make_app()
    app.adb = lambda *a, **k: _FakeResult(_MAIN_ACTIVITIES)
    assert app.current_activity() == "com.gridee.parking/.ui.main.MainContainerActivity"


def test_is_ad_foreground_true_for_admob():
    app = make_app()
    app.adb = lambda *a, **k: _FakeResult(_AD_ACTIVITIES)
    assert app.is_ad_foreground() is True


def test_is_ad_foreground_false_for_main():
    app = make_app()
    app.adb = lambda *a, **k: _FakeResult(_MAIN_ACTIVITIES)
    assert app.is_ad_foreground() is False


def _activities(component):
    return f"  topResumedActivity=ActivityRecord{{x u0 {component} t1}}\n"


@pytest.mark.parametrize(
    "component,expected",
    [
        ("com.gridee.parking/.ui.main.MainContainerActivity", "wallet"),
        ("com.gridee.parking/com.google.android.gms.ads.AdActivity", "ad"),
        ("com.gridee.parking/.ui.auth.SplashActivity", "gridee_other"),
        ("com.android.vending/com.google.android.finsky.MainActivity", "stray"),
        ("com.android.chrome/org.chromium.chrome.browser.ChromeTabbedActivity", "stray"),
    ],
)
def test_activity_state_classification(component, expected):
    app = make_app()
    app.adb = lambda *a, **k: _FakeResult(_activities(component))
    assert activity_state(app) == expected


def test_activity_state_unknown_when_empty():
    app = make_app()
    app.adb = lambda *a, **k: _FakeResult("no activity line here\n")
    assert activity_state(app) == "unknown"


def test_reward_target_flag():
    args = make_parser().parse_args(["reward", "--target", "200"])
    assert args.command == "reward"
    assert args.target == 200.0
    assert args.max_cycles == 0
    assert args.amount == 10.0


def test_reward_defaults():
    args = make_parser().parse_args(["reward"])
    assert args.target is None
    assert args.earn is None
    assert args.poke_interval == 20.0
    assert args.ad_open_timeout == 25.0
    assert args.credit_deadline == 60.0
    assert args.timeout == 240.0


def test_reward_earn_flag():
    args = make_parser().parse_args(["reward", "--earn", "50"])
    assert args.earn == 50.0
    assert args.target is None


def test_reward_target_and_earn_mutually_exclusive():
    with pytest.raises(SystemExit):
        make_parser().parse_args(["reward", "--target", "200", "--earn", "50"])


def test_removed_flags_rejected():
    for flag in ("--refresh-wallet", "--no-enter", "--manual-recover"):
        with pytest.raises(SystemExit):
            make_parser().parse_args(["reward", flag])


def test_goal_monitor_removed():
    with pytest.raises(SystemExit):
        make_parser().parse_args(["goal-monitor", "--target", "50"])
