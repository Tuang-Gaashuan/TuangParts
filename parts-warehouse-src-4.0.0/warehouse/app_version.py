# -*- coding: utf-8 -*-
"""Application release identity and GitHub Release update checks."""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen


VERSION = "4.0.2"
RELEASES_URL = "https://api.github.com/repos/Tuang-Gaashuan/TuangParts/releases/latest"


def _version_tuple(value: str) -> tuple[int, ...]:
    """Parse stable release tags such as v4.0.1 without external packages."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", (value or "").strip())
    if not match:
        raise ValueError("GitHub 返回的版本标签格式无效")
    return tuple(int(part) for part in match.group(1).split("."))


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    length = max(len(left), len(right))
    left += (0,) * (length - len(left))
    right += (0,) * (length - len(right))
    return (left > right) - (left < right)


def check_latest_release(timeout: int = 12) -> dict:
    """Fetch the public latest GitHub Release and compare it with this build."""
    request = Request(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "TuangParts-update-check"},
    )
    with urlopen(request, timeout=timeout) as response:
        latest = json.load(response)

    tag = str(latest.get("tag_name") or "")
    comparison = _compare(_version_tuple(tag), _version_tuple(VERSION))
    assets = []
    for asset in latest.get("assets", []):
        name = str(asset.get("name") or "")
        if name.lower().endswith((".exe", ".zip")):
            assets.append({
                "name": name,
                "url": str(asset.get("browser_download_url") or ""),
                "size": int(asset.get("size") or 0),
                "sha256": str(asset.get("digest") or "").removeprefix("sha256:"),
            })
    return {
        "current_version": VERSION,
        "latest_version": tag.removeprefix("v"),
        "has_update": comparison > 0,
        "is_newer_than_release": comparison < 0,
        "published_at": latest.get("published_at") or "",
        "release_url": latest.get("html_url") or "",
        "release_notes": latest.get("body") or "",
        "assets": assets,
    }
