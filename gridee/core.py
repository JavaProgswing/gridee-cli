from __future__ import annotations

import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    device: str = "a2628a8c"
    package: str = "com.gridee.parking"
    activity: str = ".ui.auth.SplashActivity"
    adb: str = "adb"
    output: Path = Path("runs")
    poll_interval: float = 2.0
    dump_timeout: float = 8.0


@dataclass
class UiNode:
    index: int
    text: str
    desc: str
    resource_id: str
    class_name: str
    clickable: bool
    enabled: bool
    bounds: str


class Gridee:
    WALLET_TAB_ID = "com.gridee.parking:id/tab_wallet"
    BALANCE_ID = "com.gridee.parking:id/tv_balance_amount"
    EARN_BUTTON_ID = "com.gridee.parking:id/btn_watch_ad"
    CLAIM_BUTTON_ID = "com.gridee.parking:id/btn_primary"

    def __init__(self, config: Config, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self.config.output.mkdir(parents=True, exist_ok=True)
        self.remote_xml = "/sdcard/gridee-cli.xml"

    def adb(self, *args: str, binary: bool = False, check: bool = True, timeout: Optional[float] = None):
        cmd = [self.config.adb, "-s", self.config.device, *args]
        if self.verbose:
            print("[adb]", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=not binary,
                encoding=None if binary else "utf-8",
                errors=None if binary else "replace",
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"{self.config.adb!r} was not found in PATH.") from exc
        except subprocess.TimeoutExpired:
            return None

        if check and result.returncode != 0:
            out = result.stdout.decode(errors="replace") if binary else result.stdout
            err = result.stderr.decode(errors="replace") if binary else result.stderr
            raise RuntimeError(
                f"ADB command failed:\n{' '.join(cmd)}\nstdout:\n{out}\nstderr:\n{err}"
            )
        return result

    def verify_device(self) -> None:
        result = subprocess.run(
            [self.config.adb, "devices"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        states = {}
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                states[parts[0]] = parts[1]
        state = states.get(self.config.device)
        if state == "device":
            return
        if state == "unauthorized":
            raise RuntimeError("Unlock the phone and accept the USB debugging prompt.")
        raise RuntimeError(f"Device {self.config.device} is not ready.\n{result.stdout}")

    def launch(self) -> None:
        component = f"{self.config.package}/{self.config.activity}"
        result = self.adb("shell", "am", "start", "-n", component, check=False)
        output = "" if result is None else f"{result.stdout}\n{result.stderr}"
        if result is None or result.returncode != 0 or "Error" in output:
            self.adb(
                "shell", "monkey",
                "-p", self.config.package,
                "-c", "android.intent.category.LAUNCHER",
                "1",
            )

    def screenshot(self, label: str = "screen") -> Path:
        path = self.config.output / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.png"
        result = self.adb("exec-out", "screencap", "-p", binary=True)
        if result is None:
            raise RuntimeError("Screenshot command timed out.")
        path.write_bytes(result.stdout)
        return path

    @staticmethod
    def _extract_hierarchy(text: str) -> Optional[str]:
        """Pull the <hierarchy>...</hierarchy> XML out of a uiautomator dump blob."""
        start = text.find("<?xml")
        if start == -1:
            start = text.find("<hierarchy")
        end = text.rfind("</hierarchy>")
        if start == -1 or end == -1:
            return None
        return text[start:end + len("</hierarchy>")]

    def _dump_stream(self) -> Optional[str]:
        """Dump the UI straight to stdout, avoiding a remote file + pull."""
        result = self.adb(
            "exec-out", "uiautomator", "dump", "--compressed", "/dev/tty",
            binary=True,
            check=False,
            timeout=self.config.dump_timeout,
        )
        if result is None:
            return None
        text = result.stdout.decode("utf-8", errors="replace")
        return self._extract_hierarchy(text)

    def _dump_pull(self) -> Optional[str]:
        """Fallback: dump to a remote file and pull it back."""
        result = self.adb(
            "shell", "uiautomator", "dump", "--compressed", self.remote_xml,
            check=False,
            timeout=self.config.dump_timeout,
        )
        if result is None:
            return None
        output = f"{result.stdout}\n{result.stderr}".lower()
        if "dumped to" not in output:
            return None
        pull = self.adb(
            "exec-out", "cat", self.remote_xml,
            binary=True, check=False, timeout=10,
        )
        if pull is None or pull.returncode != 0:
            return None
        return self._extract_hierarchy(pull.stdout.decode("utf-8", errors="replace"))

    def dump_ui(self, label: str = "ui", retries: int = 4) -> Optional[ET.Element]:
        """Capture the UI hierarchy.

        ``uiautomator dump`` intermittently fails with "could not get idle
        state" while animations or ad WebViews keep the surface busy, so retry
        a few times and fall back from streaming to the pull method.
        """
        xml = None
        for attempt in range(max(1, retries)):
            xml = self._dump_stream() or self._dump_pull()
            if xml:
                break
            if attempt + 1 < retries:
                time.sleep(0.6)

        if not xml:
            return None

        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return None

        local = self.config.output / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.xml"
        try:
            local.write_text(xml, encoding="utf-8")
        except OSError:
            pass
        return root

    @staticmethod
    def find_node(
        root: ET.Element,
        resource_id: Optional[str] = None,
        text: Optional[str] = None,
        desc: Optional[str] = None,
    ) -> Optional[ET.Element]:
        for node in root.iter("node"):
            if resource_id is not None:
                rid = node.attrib.get("resource-id", "")
                if rid != resource_id and not rid.endswith("/" + resource_id):
                    continue
            if text is not None and node.attrib.get("text") != text:
                continue
            if desc is not None and node.attrib.get("content-desc") != desc:
                continue
            return node
        return None

    @staticmethod
    def parse_bounds(bounds: str) -> tuple[int, int, int, int]:
        values = tuple(map(int, bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")))
        if len(values) != 4:
            raise RuntimeError(f"Invalid bounds: {bounds!r}")
        return values  # type: ignore[return-value]

    def tap_node(self, node: ET.Element, name: str = "element") -> None:
        x1, y1, x2, y2 = self.parse_bounds(node.attrib.get("bounds", ""))
        x, y = (x1 + x2) // 2, (y1 + y2) // 2
        print(f"[+] Tapping {name} at ({x}, {y})")
        self.adb("shell", "input", "tap", str(x), str(y))

    def tap_xy(self, x: int, y: int) -> None:
        self.adb("shell", "input", "tap", str(x), str(y))

    def wait_for_node(
        self,
        *,
        resource_id: Optional[str] = None,
        text: Optional[str] = None,
        desc: Optional[str] = None,
        timeout: float = 30,
    ) -> tuple[ET.Element, ET.Element]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            root = self.dump_ui("wait")
            if root is not None:
                node = self.find_node(root, resource_id=resource_id, text=text, desc=desc)
                if node is not None:
                    return root, node
            time.sleep(self.config.poll_interval)
        raise TimeoutError("Timed out waiting for UI element.")

    def fresh_tap(
        self,
        *,
        resource_id: Optional[str] = None,
        text: Optional[str] = None,
        desc: Optional[str] = None,
        name: str = "element",
        timeout: float = 30,
    ) -> None:
        _, node = self.wait_for_node(
            resource_id=resource_id, text=text, desc=desc, timeout=timeout
        )
        if node.attrib.get("enabled", "true").lower() != "true":
            raise RuntimeError(f"{name} is disabled.")
        self.tap_node(node, name)

    def read_balance(self, root: ET.Element) -> Optional[float]:
        node = self.find_node(root, resource_id=self.BALANCE_ID)
        if node is None:
            return None
        raw = node.attrib.get("text", "").replace(",", "").strip()
        try:
            return float(raw)
        except ValueError:
            return None

    def is_wallet(self, root: ET.Element) -> bool:
        return (
            self.find_node(root, resource_id=self.WALLET_TAB_ID) is not None
            and self.find_node(root, resource_id=self.BALANCE_ID) is not None
        )

    def open_wallet(self, timeout: float = 40) -> ET.Element:
        deadline = time.time() + timeout
        while time.time() < deadline:
            root = self.dump_ui("wallet-open")
            if root is not None:
                if self.is_wallet(root):
                    return root
                wallet = self.find_node(root, resource_id=self.WALLET_TAB_ID)
                if wallet is not None:
                    self.tap_node(wallet, "Wallet tab")
                    time.sleep(2)
                    root = self.dump_ui("wallet")
                    if root is not None and self.is_wallet(root):
                        return root
            time.sleep(self.config.poll_interval)
        raise TimeoutError("Could not open Wallet.")

    def list_nodes(self, root: ET.Element) -> list[UiNode]:
        nodes: list[UiNode] = []
        for element in root.iter("node"):
            text = element.attrib.get("text", "").strip()
            desc = element.attrib.get("content-desc", "").strip()
            rid = element.attrib.get("resource-id", "").strip()
            clickable = element.attrib.get("clickable", "false").lower() == "true"
            if not (text or desc or rid or clickable):
                continue
            nodes.append(UiNode(
                index=len(nodes),
                text=text,
                desc=desc,
                resource_id=rid,
                class_name=element.attrib.get("class", ""),
                clickable=clickable,
                enabled=element.attrib.get("enabled", "false").lower() == "true",
                bounds=element.attrib.get("bounds", ""),
            ))
        return nodes

    def current_activity(self) -> str:
        """Return the top resumed activity component, e.g.
        'com.gridee.parking/.ui.main.MainContainerActivity' or the AdMob
        'com.gridee.parking/com.google.android.gms.ads.AdActivity'."""
        result = self.adb(
            "shell", "dumpsys", "activity", "activities", check=False, timeout=8
        )
        if result is None:
            return ""
        for line in result.stdout.splitlines():
            if "topResumedActivity" in line or "ResumedActivity:" in line:
                match = re.search(r"[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+", line)
                if match:
                    return match.group(0)
        return ""

    def is_ad_foreground(self) -> bool:
        """True while a rewarded/interstitial ad activity is on top."""
        act = self.current_activity().lower()
        return "adactivity" in act or "ads." in act or "unityads" in act

    def current_focus(self) -> str:
        result = self.adb("shell", "dumpsys", "window", check=False, timeout=8)
        if result is None:
            return "unknown"
        text = result.stdout
        for key in ("mCurrentFocus", "mFocusedWindow", "mFocusedApp"):
            for line in text.splitlines():
                if key in line:
                    return line.strip()
        return "unknown"

    def device_info(self) -> dict:
        def prop(name: str) -> str:
            result = self.adb("shell", "getprop", name, check=False, timeout=5)
            return "" if result is None else result.stdout.strip()

        size = self.adb("shell", "wm", "size", check=False, timeout=5)
        density = self.adb("shell", "wm", "density", check=False, timeout=5)
        pkg = self.adb(
            "shell", "dumpsys", "package", self.config.package,
            check=False, timeout=10
        )

        version_name = ""
        version_code = ""
        if pkg is not None:
            m = re.search(r"versionName=([^\s]+)", pkg.stdout)
            if m:
                version_name = m.group(1)
            m = re.search(r"versionCode=(\d+)", pkg.stdout)
            if m:
                version_code = m.group(1)

        return {
            "serial": self.config.device,
            "manufacturer": prop("ro.product.manufacturer"),
            "model": prop("ro.product.model"),
            "android": prop("ro.build.version.release"),
            "api": prop("ro.build.version.sdk"),
            "screen_size": "" if size is None else size.stdout.strip(),
            "density": "" if density is None else density.stdout.strip(),
            "package": self.config.package,
            "version_name": version_name,
            "version_code": version_code,
            "focus": self.current_focus(),
        }

    def get_stay_awake_setting(self) -> str:
        result = self.adb(
            "shell",
            "settings",
            "get",
            "global",
            "stay_on_while_plugged_in",
            check=False,
            timeout=5,
        )
        if result is None:
            return "0"
        return result.stdout.strip() or "0"

    def set_stay_awake(self, enabled: bool) -> None:
        # 3 = stay awake while plugged in over AC or USB.
        value = "3" if enabled else "0"
        self.adb(
            "shell",
            "settings",
            "put",
            "global",
            "stay_on_while_plugged_in",
            value,
            check=False,
            timeout=5,
        )

    def restore_stay_awake_setting(self, value: str) -> None:
        safe_value = value if value.strip().isdigit() else "0"
        self.adb(
            "shell",
            "settings",
            "put",
            "global",
            "stay_on_while_plugged_in",
            safe_value,
            check=False,
            timeout=5,
        )

    def wake_screen(self) -> None:
        self.adb(
            "shell",
            "input",
            "keyevent",
            "KEYCODE_WAKEUP",
            check=False,
            timeout=5,
        )
        # Best-effort dismissal of a non-secure keyguard so the app is
        # immediately interactive. No-op on secure locks or when unlocked.
        self.adb("shell", "wm", "dismiss-keyguard", check=False, timeout=5)

    def poke(self) -> None:
        """Reset the user-activity timer so the display does not dim.

        An injected key event counts as user activity; KEYCODE_WAKEUP is inert
        when the screen is already on, so it never navigates or types.
        """
        self.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP", check=False, timeout=5)

    def get_screen_off_timeout(self) -> str:
        result = self.adb(
            "shell", "settings", "get", "system", "screen_off_timeout",
            check=False, timeout=5,
        )
        if result is None:
            return ""
        return result.stdout.strip()

    def set_screen_off_timeout(self, millis: int) -> None:
        self.adb(
            "shell", "settings", "put", "system", "screen_off_timeout", str(millis),
            check=False, timeout=5,
        )

    def restore_screen_off_timeout(self, value: str) -> None:
        if value.strip().isdigit():
            self.adb(
                "shell", "settings", "put", "system", "screen_off_timeout", value.strip(),
                check=False, timeout=5,
            )

    def is_screen_on(self) -> bool:
        result = self.adb(
            "shell",
            "dumpsys",
            "power",
            check=False,
            timeout=8,
        )
        if result is None:
            return True

        output = result.stdout.lower()

        match = re.search(r"mwakefulness=(\w+)", output)
        if match:
            return match.group(1) == "awake"

        # Fallbacks for devices/ROMs that omit mWakefulness.
        if "display power: state=off" in output:
            return False
        if "mscreenstate=off" in output or "mscreenstate=doze" in output:
            return False
        if "mwakefulness=asleep" in output:
            return False
        return True

    def get_gridee_wallet_notifications(self) -> list[dict]:
        """
        Read active Android notifications and return Gridee wallet-update notices.

        This is a monitoring fallback only; it does not interact with or dismiss
        notifications.
        """
        result = self.adb(
            "shell",
            "dumpsys",
            "notification",
            "--noredact",
            check=False,
            timeout=12,
        )
        if result is None:
            return []

        text = result.stdout
        package = self.config.package.lower()
        records: list[dict] = []

        # Android dumpsys formatting differs across versions. Split around
        # NotificationRecord blocks, then inspect each block independently.
        blocks = re.split(r"(?=NotificationRecord\()", text)

        def field(block: str, *names: str) -> str:
            # Values look like: android.title=String (Wallet Updated : Ad Top-up)
            for name in names:
                match = re.search(
                    rf"{name}=(?:String\s*\()?\s*([^\r\n]+)",
                    block,
                    re.IGNORECASE,
                )
                if match:
                    value = match.group(1).strip()
                    if value.endswith(")"):
                        value = value[:-1].strip()
                    return value.strip("[]{}")
            return ""

        for block in blocks:
            lower = block.lower()
            if package not in lower:
                continue
            if "wallet updated" not in lower and "ad top-up" not in lower:
                continue

            title = field(block, r"android\.title", "title")
            body = field(block, r"android\.bigText", r"android\.text", "text")
            post_time = field(block, "postTime", "mCreationTimeMs", "when")

            key_match = re.search(r"\bkey=(\S+)", block)
            key = key_match.group(1) if key_match else ""

            amount = None
            amount_match = re.search(
                r"(\d+(?:\.\d+)?)\s+points?\s+added",
                f"{title} {body}",
                re.IGNORECASE,
            )
            if amount_match:
                try:
                    amount = float(amount_match.group(1))
                except ValueError:
                    amount = None

            records.append(
                {
                    "key": key,
                    "title": title or "Wallet Updated: Ad Top-up",
                    "text": body,
                    "amount": amount,
                    "post_time": post_time,
                }
            )

        return records

    def save_json(self, data: dict, label: str) -> Path:
        path = self.config.output / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path
