"""Read the Pi camera publisher and expose policy camera roles."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

CAMERA_BASE = "http://127.0.0.1:8001"
REQUIRED_ACT_ROLES = ("top", "wrist_left", "wrist_right")
_CACHE: tuple[float, dict[str, Any]] | None = None


def _json(path: str) -> dict[str, Any]:
    with urlopen(f"{CAMERA_BASE}{path}", timeout=0.4) as response:
        payload = json.load(response)
    return payload if isinstance(payload, dict) else {}


def status_payload(*, refresh: bool = False) -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    if not refresh and _CACHE and now - _CACHE[0] < 1.0:
        return dict(_CACHE[1])
    try:
        wrist = _json("/api/robotics/hand-cam/status")
    except (OSError, TimeoutError, URLError, ValueError, json.JSONDecodeError) as error:
        wrist = {"ok": False, "left": {}, "right": {}, "reason": str(error)[:160]}
    try:
        zed = _json("/api/robotics/zed/status")
    except (OSError, TimeoutError, URLError, ValueError, json.JSONDecodeError) as error:
        zed = {"ok": False, "live": False, "reason": str(error)[:160]}
    roles = {
        "top": {
            "live": zed.get("live") is True,
            "url": "/api/robotics/zed.jpg",
            "reason": str(zed.get("reason") or ("" if zed.get("live") else "top camera unavailable")),
        },
        "wrist_left": {
            "live": (wrist.get("left") or {}).get("live") is True,
            "url": "/api/robotics/hand-cam/left.jpg",
            "reason": str((wrist.get("left") or {}).get("reason") or ""),
        },
        "wrist_right": {
            "live": (wrist.get("right") or {}).get("live") is True,
            "url": "/api/robotics/hand-cam/right.jpg",
            "reason": str((wrist.get("right") or {}).get("reason") or ""),
        },
    }
    missing = [role for role in REQUIRED_ACT_ROLES if not roles[role]["live"]]
    payload = {
        "ok": True,
        "schema": "render-studio-policy-cameras/v1",
        "base": CAMERA_BASE,
        "roles": roles,
        "required": list(REQUIRED_ACT_ROLES),
        "ready": not missing,
        "missing": missing,
    }
    _CACHE = (now, payload)
    return dict(payload)
