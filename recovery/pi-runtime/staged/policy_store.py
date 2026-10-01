# Copyright 2026 Dimensional Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Persist the Mac simulation deployment + validated hardware policy programs.

Render Studio binds whatever MuJoCo scene is loaded on Robotics Home. A scene
alone never moves the robot. A program becomes runnable only after it is
explicitly uploaded (or linked from an accepted VR recording) with OpenArm
joint names and timed positions — the same shape as emote playback.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any

from dimos.constants import DIMOS_PROJECT_ROOT

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_LOCK = threading.RLock()
SCHEMA = "render-studio-policy/v1"


def policy_dir() -> Path:
    path = DIMOS_PROJECT_ROOT / "user_data" / "policy"
    path.mkdir(parents=True, exist_ok=True)
    return path


def programs_dir() -> Path:
    path = policy_dir() / "programs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deployment_path() -> Path:
    return policy_dir() / "deployment.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def read_deployment() -> dict[str, Any] | None:
    with _LOCK:
        return _read_json(_deployment_path())


def clear_deployment() -> None:
    with _LOCK:
        path = _deployment_path()
        if path.exists():
            path.unlink()


def bind_deployment(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Store the Mac MuJoCo deployment draft. Does not authorize motion."""
    body = raw if isinstance(raw, dict) else {}
    scene = str(body.get("scene") or body.get("sourcePath") or "").strip()
    source_path = str(body.get("sourcePath") or scene).strip()
    if not source_path:
        raise ValueError("deployment requires scene or sourcePath from the Mac simulation")
    program_id = str(body.get("programId") or body.get("program_id") or "").strip()
    if program_id and not _SAFE_ID.match(program_id):
        raise ValueError(f"unsafe program id {program_id!r}")
    deployment = {
        "schema": SCHEMA,
        "bound_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": str(body.get("engine") or "mujoco").strip() or "mujoco",
        "scene": scene or source_path,
        "label": str(body.get("label") or scene or source_path).strip(),
        "sourcePath": source_path,
        "projectId": str(body.get("projectId") or body.get("project_id") or "").strip(),
        "hardwareTarget": str(body.get("hardwareTarget") or body.get("hardware_target") or "").strip(),
        "simUrl": str(body.get("simUrl") or body.get("sim_url") or "").strip(),
        "runId": str(body.get("runId") or body.get("run_id") or "").strip(),
        "programId": program_id,
        "macHost": str(body.get("macHost") or body.get("mac_host") or "").strip(),
        "notes": str(body.get("notes") or "").strip(),
    }
    with _LOCK:
        _write_json(_deployment_path(), deployment)
    return deployment


def list_programs() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with _LOCK:
        paths = sorted(programs_dir().glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths:
            payload = _read_json(path)
            if not payload:
                continue
            program_id = str(payload.get("id") or path.stem)
            items.append(
                {
                    "id": program_id,
                    "name": str(payload.get("name") or program_id),
                    "validated": bool(payload.get("validated")),
                    "scene": str(payload.get("scene") or ""),
                    "samples": len(payload.get("positions") or []),
                    "source": str(payload.get("source") or "upload"),
                    "kind": str(payload.get("kind") or "trajectory"),
                    "checkpoint": str(payload.get("checkpoint") or ""),
                    "action_schema": str(payload.get("action_schema") or "openarm_joint_position_v1"),
                    "required_cameras": list(payload.get("required_cameras") or []),
                    "blockers": list(payload.get("blockers") or []),
                }
            )
    return items


def load_program(program_id: str) -> dict[str, Any] | None:
    if not _SAFE_ID.match(str(program_id)):
        return None
    with _LOCK:
        return _read_json(programs_dir() / f"{program_id}.json")


def save_program(raw: dict[str, Any] | None) -> dict[str, Any]:
    body = raw if isinstance(raw, dict) else {}
    program_id = str(body.get("id") or "").strip() or time.strftime("%Y%m%d_%H%M%S")
    if not _SAFE_ID.match(program_id):
        raise ValueError(f"unsafe program id {program_id!r}")
    names = [str(name) for name in body.get("joint_names") or []]
    positions = list(body.get("positions") or [])
    times = list(body.get("times") or [])
    if not names or not positions:
        raise ValueError("program requires joint_names and positions")
    width = len(names)
    for row in positions:
        if not isinstance(row, list) or len(row) != width:
            raise ValueError(f"each positions row must have {width} values matching joint_names")
    if times and len(times) != len(positions):
        raise ValueError("times length must match positions length when provided")
    flat = [float(value) for row in positions for value in row]
    if not all(math.isfinite(value) for value in flat):
        raise ValueError("program positions must be finite")
    start_positions = [float(value) for value in body.get("start_positions") or []]
    if start_positions and len(start_positions) != width:
        raise ValueError(f"start_positions must have {width} values matching joint_names")
    if not all(math.isfinite(value) for value in start_positions):
        raise ValueError("start_positions must be finite")
    parsed_times = [float(value) for value in times] if times else [index / 50.0 for index in range(len(positions))]
    if not all(math.isfinite(value) and value >= 0 for value in parsed_times):
        raise ValueError("program times must be finite and non-negative")
    if any(right <= left for left, right in zip(parsed_times, parsed_times[1:])):
        raise ValueError("program times must increase strictly")
    validated = body.get("validated") is True
    program = {
        "id": program_id,
        "name": str(body.get("name") or program_id).strip() or program_id,
        "validated": bool(validated),
        "scene": str(body.get("scene") or "").strip(),
        "source": str(body.get("source") or "upload").strip() or "upload",
        "kind": str(body.get("kind") or "trajectory").strip() or "trajectory",
        "checkpoint": str(body.get("checkpoint") or "").strip(),
        "revision": str(body.get("revision") or "").strip(),
        "action_schema": str(body.get("action_schema") or "openarm_joint_position_v1").strip(),
        "required_cameras": [str(value) for value in body.get("required_cameras") or []],
        "blockers": [str(value) for value in body.get("blockers") or []],
        "start_positions": start_positions,
        "joint_names": names,
        "times": parsed_times,
        "positions": [[float(value) for value in row] for row in positions],
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _LOCK:
        _write_json(programs_dir() / f"{program_id}.json", program)
        deployment = _read_json(_deployment_path()) or {}
        deployment["programId"] = program_id
        deployment["schema"] = SCHEMA
        deployment["bound_at"] = deployment.get("bound_at") or program["saved_at"]
        if not deployment.get("scene") and program["scene"]:
            deployment["scene"] = program["scene"]
            deployment["sourcePath"] = deployment.get("sourcePath") or program["scene"]
            deployment["label"] = deployment.get("label") or program["name"]
        _write_json(_deployment_path(), deployment)
    return {
        "id": program_id,
        "name": program["name"],
        "validated": program["validated"],
        "samples": len(program["positions"]),
        "scene": program["scene"],
    }


def link_emote_program(emote: dict[str, Any], *, scene: str = "") -> dict[str, Any]:
    """Promote an accepted VR recording into a validated hardware policy program."""
    emote_id = str(emote.get("id") or "").strip()
    if not emote_id:
        raise ValueError("emote id required")
    return save_program(
        {
            "id": f"emote_{emote_id}",
            "name": str(emote.get("name") or emote_id),
            "validated": True,
            "scene": scene,
            "source": f"emote:{emote_id}",
            "joint_names": list(emote.get("joint_names") or []),
            "times": list(emote.get("times") or []),
            "positions": list(emote.get("positions") or []),
        }
    )


def status_payload() -> dict[str, Any]:
    with _LOCK:
        deployment = _read_json(_deployment_path())
        programs = list_programs()
    program_id = str((deployment or {}).get("programId") or "")
    program = load_program(program_id) if program_id else None
    runnable = bool(program and program.get("validated") and program.get("positions") and not program.get("blockers"))
    return {
        "schema": SCHEMA,
        "ok": True,
        "bound": deployment is not None,
        "runnable": runnable,
        "deployment": deployment,
        "program": None
        if not program
        else {
            "id": program.get("id"),
            "name": program.get("name"),
            "validated": bool(program.get("validated")),
            "scene": program.get("scene") or "",
            "samples": len(program.get("positions") or []),
            "source": program.get("source") or "",
            "kind": program.get("kind") or "trajectory",
            "checkpoint": program.get("checkpoint") or "",
            "action_schema": program.get("action_schema") or "openarm_joint_position_v1",
            "required_cameras": list(program.get("required_cameras") or []),
            "blockers": list(program.get("blockers") or []),
        },
        "programs": programs,
        "note": (
            "Bound MuJoCo deployment is visible to agents and Robotics Home. "
            "Physical motion requires a validated hardware program (uploaded trajectory "
            "or linked VR recording), then POST /robotics/policy/run after guarded Home."
        ),
    }
