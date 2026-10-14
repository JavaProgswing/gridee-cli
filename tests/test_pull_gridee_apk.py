from tools.pull_gridee_apk import (
    parse_devices,
    parse_package_metadata,
    parse_package_paths,
    safe_version,
    select_device,
)


def test_parse_and_select_single_online_device():
    devices = parse_devices(
        """List of devices attached
a2628a8c               device product:CPH2573IN model:CPH2573 transport_id:1
"""
    )
    assert devices == [
        {
            "serial": "a2628a8c",
            "state": "device",
            "product": "CPH2573IN",
            "model": "CPH2573",
            "transport_id": "1",
        }
    ]
    assert select_device(devices, None)["serial"] == "a2628a8c"


def test_parse_split_package_paths():
    assert parse_package_paths(
        """package:/data/app/example/base.apk
package:/data/app/example/split_config.arm64_v8a.apk
"""
    ) == [
        "/data/app/example/base.apk",
        "/data/app/example/split_config.arm64_v8a.apk",
    ]


def test_parse_package_metadata_and_safe_version():
    metadata = parse_package_metadata(
        """versionCode=77 minSdk=26 targetSdk=35
versionName=1.76 beta
firstInstallTime=2026-08-01 10:00:00
lastUpdateTime=2026-10-07 12:00:00
"""
    )
    assert metadata["versionCode"] == 77
    assert metadata["versionName"] == "1.76"
    assert metadata["lastUpdateTime"] == "2026-10-07 12:00:00"
    assert safe_version("1.76 beta") == "1.76-beta"
