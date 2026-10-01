"""Persistent OpenArm recordings accepted as replayable emotes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from dimos.constants import DIMOS_PROJECT_ROOT

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def _root() -> Path:
    path = DIMOS_PROJECT_ROOT / "user_data" / "emotes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_emote_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _path(emote_id: str) -> Path | None:
    value = str(emote_id).strip()
    if not _SAFE_ID.fullmatch(value):
        return None
    return _root() / f"{value}.json"


def save_emote(payload: dict[str, Any]) -> dict[str, Any]:
    emote_id = str(payload.get("id") or new_emote_id())
    path = _path(emote_id)
    if path is None:
        raise ValueError("invalid emote id")
    value = {**payload, "id": emote_id}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return value


def load_emote(emote_id: str) -> dict[str, Any] | None:
    path = _path(emote_id)
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def list_emotes() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(_root().glob("*.json"), reverse=True):
        value = load_emote(path.stem)
        if value is not None:
            items.append(value)
    return items
