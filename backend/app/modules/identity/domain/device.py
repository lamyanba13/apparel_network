from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceMetadata:
    browser: str
    operating_system: str
    device_type: str
    platform: str


def parse_device(user_agent: str | None) -> DeviceMetadata:
    """Return conservative, normalized metadata without fingerprinting."""
    value = user_agent or ""
    lowered = value.lower()

    if "edg/" in lowered:
        browser = "Edge"
    elif "firefox/" in lowered:
        browser = "Firefox"
    elif "chrome/" in lowered or "crios/" in lowered:
        browser = "Chrome"
    elif "safari/" in lowered and "version/" in lowered:
        browser = "Safari"
    else:
        browser = "Unknown"

    if "android" in lowered:
        operating_system, platform = "Android", "Android"
    elif "iphone" in lowered or "ipad" in lowered:
        operating_system, platform = "iOS", "Apple mobile"
    elif "windows nt" in lowered:
        operating_system, platform = "Windows", "Windows"
    elif "macintosh" in lowered or "mac os x" in lowered:
        operating_system, platform = "macOS", "Apple desktop"
    elif "linux" in lowered:
        operating_system, platform = "Linux", "Linux"
    else:
        operating_system, platform = "Unknown", "Unknown"

    if any(marker in lowered for marker in ("bot", "crawler", "spider")):
        device_type = "bot"
    elif "ipad" in lowered or "tablet" in lowered:
        device_type = "tablet"
    elif any(marker in lowered for marker in ("mobile", "iphone", "android")):
        device_type = "mobile"
    elif value:
        device_type = "desktop"
    else:
        device_type = "unknown"
    return DeviceMetadata(browser, operating_system, device_type, platform)
