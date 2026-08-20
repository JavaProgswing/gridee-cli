from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_android_helper_manifest_has_build_package():
    manifest = ET.parse(ROOT / "android-helper" / "AndroidManifest.xml").getroot()
    assert manifest.attrib["package"] == "com.yashasvi.grideescheduler"


def test_android_build_resolves_both_jdk_tools():
    script = (ROOT / "build_android_helper.ps1").read_text(encoding="utf-8")
    assert "$Javac" in script
    assert "$JarTool" in script
