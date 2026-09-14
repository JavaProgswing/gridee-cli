from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_android_helper_manifest_has_build_package():
    manifest = ET.parse(ROOT / "android-helper" / "AndroidManifest.xml").getroot()
    assert manifest.attrib["package"] == "com.yashasvi.grideescheduler"
    namespace = {"android": "http://schemas.android.com/apk/res/android"}
    packages = manifest.findall("./queries/package")
    assert any(node.attrib[f"{{{namespace['android']}}}name"] == "com.gridee.parking"
               for node in packages)


def test_android_build_resolves_both_jdk_tools():
    script = (ROOT / "build_android_helper.ps1").read_text(encoding="utf-8")
    assert "$Javac" in script
    assert "$JarTool" in script


def test_android_helper_daily_schedule_separates_pending_and_running_state():
    java = ROOT / "android-helper" / "java" / "com" / "yashasvi" / "grideescheduler"
    scheduler = (java / "Scheduler.java").read_text(encoding="utf-8")
    alarm = (java / "AlarmReceiver.java").read_text(encoding="utf-8")
    service = (java / "BookingAccessibilityService.java").read_text(encoding="utf-8")
    assert "nextDailyTrigger" in scheduler
    assert 'putBoolean("running", true)' in alarm
    assert 'getBoolean("running", false)' in service


def test_scheduler_daily_cli_flag():
    from gridee.cli import make_parser

    args = make_parser().parse_args(
        ["scheduler", "schedule", "--at", "2026-08-21T05:00:00", "--daily", "--execute"]
    )
    assert args.daily is True
    assert args.execute is True


def test_scheduler_broadcast_quotes_values_with_spaces():
    from types import SimpleNamespace

    from gridee.scheduler import broadcast

    class FakeApp:
        args = ()

        def adb(self, *args):
            self.args = args
            return SimpleNamespace(stdout="ok")

    app = FakeApp()
    assert broadcast(app, "CONFIGURE", "--es", "venue", "Tech Park Avenue") == "ok"
    assert app.args[0] == "shell"
    assert "'Tech Park Avenue'" in app.args[1]


def test_scheduler_simulate_cli_command():
    from gridee.cli import make_parser

    assert make_parser().parse_args(["scheduler", "simulate"]).scheduler_command == "simulate"
