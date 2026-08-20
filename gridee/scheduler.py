from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .core import Gridee


HELPER_PACKAGE = "com.yashasvi.grideescheduler"
RECEIVER = f"{HELPER_PACKAGE}/.ConfigReceiver"
ACTION_PREFIX = "com.yashasvi.grideescheduler"


def parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date/time must be ISO-8601, for example 2026-08-21T04:59:55") from exc


def broadcast(app: Gridee, action: str, *extras: str) -> str:
    result = app.adb(
        "shell",
        "am",
        "broadcast",
        "-a",
        f"{ACTION_PREFIX}.{action}",
        "-n",
        RECEIVER,
        *extras,
    )
    return "" if result is None else result.stdout.strip()


def run_scheduler(app: Gridee, args: Any) -> int:
    if args.scheduler_command == "build":
        root = Path(__file__).resolve().parent.parent
        script = root / "build_android_helper.ps1"
        shell = "powershell.exe" if os.name == "nt" else "pwsh"
        command = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        if args.android_sdk:
            command.extend(["-AndroidSdk", args.android_sdk])
        if args.build_tools_version:
            command.extend(["-BuildToolsVersion", args.build_tools_version])
        return subprocess.run(command, check=False).returncode

    if args.scheduler_command == "install":
        apk = Path(args.apk)
        if not apk.is_file():
            raise RuntimeError(f"Scheduler APK not found: {apk}; run 'gridee scheduler build' first.")
        result = app.adb("install", "-r", str(apk))
        if result is not None:
            print(result.stdout.strip())
        return 0

    if args.scheduler_command == "enable":
        app.adb("shell", "am", "start", "-a", "android.settings.ACCESSIBILITY_SETTINGS")
        print("Enable 'Gridee booking scheduler' on the device.")
        return 0

    if args.scheduler_command == "schedule":
        trigger = args.at
        if trigger <= datetime.now(trigger.tzinfo):
            raise RuntimeError("--at must be in the future.")
        extras = [
            "--el", "triggerAt", str(int(trigger.timestamp() * 1000)),
            "--es", "venue", args.venue,
            "--es", "start", args.start,
            "--es", "end", args.end,
            "--es", "date", args.date or "",
            "--ez", "execute", str(args.execute).lower(),
            "--ef", "threshold", str(args.venue_threshold),
        ]
        print(broadcast(app, "CONFIGURE", *extras))
        return 0

    if args.scheduler_command == "status":
        print(broadcast(app, "STATUS"))
        return 0

    if args.scheduler_command == "cancel":
        print(broadcast(app, "CANCEL"))
        return 0

    raise RuntimeError(f"Unsupported scheduler command: {args.scheduler_command}")
