from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.gridee_apk_audit import DEFAULT_API_CLASS, audit, find_apkanalyzer, markdown


DEFAULT_PACKAGE = "com.gridee.parking"
REPO_ROOT = Path(__file__).resolve().parents[1]


def find_adb(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("adb") or shutil.which("adb.exe")
    if found:
        candidates.append(Path(found))
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.getenv(variable):
            candidates.append(Path(os.environ[variable]) / "platform-tools" / "adb.exe")
    if os.getenv("LOCALAPPDATA"):
        candidates.append(
            Path(os.environ["LOCALAPPDATA"])
            / "Android"
            / "Sdk"
            / "platform-tools"
            / "adb.exe"
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "adb was not found. Pass --adb or install Android SDK platform-tools."
    )


def run(tool: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        [str(tool), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(arguments[:3])} failed: {detail}")
    return result.stdout.strip()


def parse_devices(value: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices"):
            continue
        columns = re.split(r"\s+", line, maxsplit=1)
        if len(columns) != 2:
            continue
        serial, remainder = columns
        parts = remainder.split()
        state = parts[0]
        details = {"serial": serial, "state": state}
        for item in parts[1:]:
            if ":" in item:
                key, content = item.split(":", 1)
                details[key] = content
        devices.append(details)
    return devices


def select_device(devices: list[dict[str, str]], requested: str | None) -> dict[str, str]:
    if requested:
        match = next((item for item in devices if item["serial"] == requested), None)
        if match is None:
            raise RuntimeError(f"ADB device {requested!r} is not connected.")
        if match["state"] != "device":
            raise RuntimeError(
                f"ADB device {requested!r} is {match['state']}; unlock it and authorize USB debugging."
            )
        return match
    online = [item for item in devices if item["state"] == "device"]
    if not online:
        states = ", ".join(f"{item['serial']}={item['state']}" for item in devices)
        suffix = f" Found: {states}." if states else ""
        raise RuntimeError(
            "No authorized ADB device is available. Unlock the phone, enable USB "
            f"debugging, and accept the computer authorization prompt.{suffix}"
        )
    if len(online) > 1:
        serials = ", ".join(item["serial"] for item in online)
        raise RuntimeError(f"Multiple ADB devices are connected ({serials}); pass --serial.")
    return online[0]


def adb_args(serial: str, *arguments: str) -> tuple[str, ...]:
    return ("-s", serial, *arguments)


def parse_package_paths(value: str) -> list[str]:
    paths: list[str] = []
    for line in value.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            path = line.removeprefix("package:").strip()
            if path:
                paths.append(path)
    return list(dict.fromkeys(paths))


def parse_package_metadata(value: str) -> dict[str, Any]:
    version_name = re.search(r"\bversionName=([^\s]+)", value)
    version_code = re.search(r"\bversionCode=(\d+)", value)
    first_install = re.search(r"\bfirstInstallTime=([^\r\n]+)", value)
    last_update = re.search(r"\blastUpdateTime=([^\r\n]+)", value)
    return {
        "versionName": version_name.group(1) if version_name else "unknown",
        "versionCode": int(version_code.group(1)) if version_code else None,
        "firstInstallTime": first_install.group(1).strip() if first_install else None,
        "lastUpdateTime": last_update.group(1).strip() if last_update else None,
    }


def safe_version(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return cleaned or "unknown"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pull_apks(
    adb: Path,
    serial: str,
    package: str,
    output_root: Path,
) -> dict[str, Any]:
    paths = parse_package_paths(
        run(adb, *adb_args(serial, "shell", "pm", "path", package))
    )
    if not paths:
        raise RuntimeError(f"Package {package!r} is not installed on {serial}.")
    metadata = parse_package_metadata(
        run(adb, *adb_args(serial, "shell", "dumpsys", "package", package))
    )
    version = safe_version(str(metadata["versionName"]))
    target = output_root / f"gridee-{version}-device"
    target.mkdir(parents=True, exist_ok=True)

    pulled: list[dict[str, str]] = []
    used_names: set[str] = set()
    for index, remote in enumerate(paths):
        name = PurePosixPath(remote).name or f"split-{index}.apk"
        if name in used_names:
            name = f"{index}-{name}"
        used_names.add(name)
        local = target / name
        run(adb, *adb_args(serial, "pull", remote, str(local)))
        pulled.append(
            {
                "devicePath": remote,
                "localPath": str(local.resolve()),
                "sha256": sha256(local),
            }
        )

    base = next(
        (
            Path(item["localPath"])
            for item in pulled
            if PurePosixPath(item["devicePath"]).name == "base.apk"
        ),
        Path(pulled[0]["localPath"]),
    )
    return {
        "package": package,
        "device": serial,
        **metadata,
        "baseApk": str(base),
        "apks": pulled,
    }


def write_audit(
    result: dict[str, Any],
    apkanalyzer: Path,
    output_root: Path,
    docs_root: Path,
    api_classes: list[str] | None = None,
) -> None:
    version = safe_version(str(result["versionName"]))
    candidates = api_classes or [DEFAULT_API_CLASS, "mf.c"]
    failures: list[str] = []
    report: dict[str, Any] | None = None
    for api_class in candidates:
        try:
            candidate = audit(Path(result["baseApk"]), apkanalyzer, [api_class])
        except RuntimeError as exc:
            failures.append(f"{api_class}: {exc}")
            continue
        if candidate["endpointCount"]:
            report = candidate
            break
        failures.append(f"{api_class}: no Retrofit endpoints found")
    if report is None:
        raise RuntimeError("Could not locate the Retrofit API interface. " + "; ".join(failures))
    json_path = output_root / f"gridee-{version}-endpoints.json"
    markdown_path = docs_root / f"ENDPOINTS_{version}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown(report), encoding="utf-8")
    result["audit"] = {
        "endpointCount": report["endpointCount"],
        "json": str(json_path.resolve()),
        "markdown": str(markdown_path.resolve()),
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pull the installed Gridee APK set from ADB and audit its Retrofit API."
    )
    parser.add_argument("--adb", help="Path to adb.exe.")
    parser.add_argument("--serial", help="ADB device serial (required when multiple are online).")
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--apkanalyzer", help="Path to apkanalyzer or apkanalyzer.bat.")
    parser.add_argument(
        "--api-class",
        action="append",
        dest="api_classes",
        help="Retrofit interface to inspect; repeat for multiple interfaces.",
    )
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "analysis")
    parser.add_argument("--docs-root", type=Path, default=REPO_ROOT / "docs")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Also run the slower Retrofit/model audit after pulling the APK.",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Deprecated compatibility flag; pulling without --audit is already the default.",
    )
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        adb = find_adb(args.adb)
        device = select_device(parse_devices(run(adb, "devices", "-l")), args.serial)
        result = pull_apks(
            adb,
            device["serial"],
            args.package,
            args.output_root.resolve(),
        )
        result["deviceDetails"] = device
        if args.audit and not args.skip_audit:
            write_audit(
                result,
                find_apkanalyzer(args.apkanalyzer),
                args.output_root.resolve(),
                args.docs_root.resolve(),
                args.api_classes,
            )
        version = safe_version(str(result["versionName"]))
        summary = args.output_root.resolve() / f"gridee-{version}-device.json"
        summary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(
            f"Pulled Gridee {result['versionName']} (code {result['versionCode']}) "
            f"from {device['serial']}"
        )
        print(f"Base APK: {result['baseApk']}")
        if result.get("audit"):
            print(
                f"Audit: {result['audit']['endpointCount']} endpoints -> "
                f"{result['audit']['markdown']}"
            )
        print(f"Manifest: {summary}")
    except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
