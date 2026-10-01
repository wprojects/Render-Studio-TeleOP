"""Render Studio robotics setup pack: controls, menus, downloadable UIs, zip.

Used by connect_api.py (this repo) and DimOS scripts/quest_connect_api.py.
Serve over HTTP :8450 so Render can fetch assets without the self-signed :8443 cert.
Live WebXR passthrough stays on https://<LAN>:8443/teleop.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

SETUP_VERSION = "1.0.2"
Y_MAP = "tap_pause_hold3_kill"
Y_HOLD_MS = 3000
Y_TAP_MAX_MS = 350
Y_HOLD_SHOW_MS = 300

DISCORD_INVITE = "https://discord.gg/kaPZRCk9c"
DISCORD_INVITE_WEB = "https://discord.com/invite/kaPZRCk9c"
X_HANDLE = "A1_Proejcts"
X_URL = "https://x.com/A1_Proejcts"
GITHUB_URL = "https://github.com/wprojects/Render-Studio-TeleOP"
RENDER_DOCS = "https://render3d.app/getting-started.html#robotics-configuration"

DOCS_TABS = [
    {"id": "intro", "title": "Intro"},
    {"id": "controls", "title": "Controls"},
    {"id": "connect", "title": "Connect"},
    {"id": "arms", "title": "Arms/CAN"},
    {"id": "trouble", "title": "Troubleshooting"},
    {"id": "render", "title": "Render Studio"},
]
DOCS_SEARCH_CHIPS = ["Y", "pause", "cancel", "reset", "record", "CAN", "cert", "Discord"]
DOCS_PAGES = {
    "intro": {
        "keywords": ["intro", "how to", "teleop", "start", "y", "pause", "cancel", "reset", "follow"],
        "lines": [
            "How to use TeleOP",
            "Tap Y: pause arms in place and pause headset/controller follow (original DimOS pause — MIT/gravity hold).",
            "Tap Y again: resume follow from the current pose (no slam). After a 3s kill, tap Y is a fresh calibrate — same as first enable.",
            "Hold Y 3 seconds: spinning “Canceling arms” in the visor. Completing the hold kills teleop and resets the session. Next Y is a fresh instance.",
            "Release before 3s: cancel the kill. Stay paused if you had started holding.",
            "A record/save · B discard while recording · X emotes · triggers pinch-to-close from rest 0.5.",
            "Trust the cert once, then open https://<LAN>:8443/teleop in Quest Browser.",
        ],
    },
    "controls": {
        "keywords": ["controls", "y", "pause", "cancel", "reset", "hold", "a", "b", "x", "trigger", "gripper", "emote"],
        "lines": [
            "Y tap from ON: pause arms where they are + stop follow (HOLD).",
            "Y tap from HOLD: resume follow from the current pose.",
            "Y tap from OFF: start follow / calibrate like a new session.",
            "Hold Y ≥ 0.3s: visor spinner “Canceling arms” (controller Y ring too).",
            "Hold Y 3s: kill arms + full session reset. HUD TELEOP = OFF. Next Y = fresh instance.",
            "Not a Dora all-zero slow-home. Hold Y does not drive joints to a canned rest pose.",
            "Release 0.3–3s: no kill. Stay HOLD if pause had started; stay OFF if you never armed.",
            "A: record / save. B: discard while recording. X: emote picker.",
            "Triggers: pinch-to-close from rest 0.5. Left decreasing_position, right increasing_position.",
            "Do not use Hold X+A (old DimOS deadman). Grip the HUD to move it.",
        ],
    },
    "connect": {
        "keywords": ["connect", "cert", "https", "quest", "url", "autoconnect", "8443", "8450", "trust", "config", "bundle"],
        "lines": [
            "Paste in Render: http://<LAN>:8450/robotics/config",
            "That JSON is a setup manifest: controls, menus, HUD/docs UI, and /robotics/bundle.zip.",
            "Quest page: https://<LAN>:8443/teleop  (WebXR needs HTTPS).",
            "Autoconnect: https://<LAN>:8443/teleop?autoconnect=1",
            "Accept the self-signed certificate once (Advanced / Proceed).",
            "If the cert warning loops, open http://<LAN>:8450/trust then return to /teleop.",
            "Connect API: http://<LAN>:8450  GET/POST /connect, cert helper /trust.",
            "Use Quest Browser, not a desktop tab. Same LAN as the Pi.",
        ],
    },
    "arms": {
        "keywords": ["arms", "can", "can0", "can1", "can-fd", "left", "right", "peak", "fd"],
        "lines": [
            "can0 = right arm. can1 = left arm.",
            "Peak PCAN-USB Pro FD, CAN-FD 1M/5M only.",
            "Never run dimos hardware can setup (that is classic 1M).",
            "If arms are swapped, swap the two CLI flags only — not the buses.",
            "systemd unit: dimos-teleop-quest-openarm (Restart=always).",
        ],
    },
    "trouble": {
        "keywords": ["trouble", "cert", "offline", "can", "browser", "systemd", "viser", "8095"],
        "lines": [
            "NET::ERR_CERT: accept the 8443 cert once, or use :8450/trust.",
            "Arms never enable: buses must be CAN-FD 1M/5M. can0=right, can1=left.",
            "Works on laptop, not Quest: open Quest Browser, not desktop Chrome.",
            "Service: sudo systemctl status dimos-teleop-quest-openarm",
            "Viser 3D on a laptop: http://<LAN>:8095  (DISPLAY=:0 on the Pi).",
            "Hard-reload Quest Browser after a teleop.js?v= change.",
        ],
    },
    "render": {
        "keywords": ["render", "studio", "ip", "robotics", "configuration", "vis", "bundle", "download"],
        "lines": [
            "Paste http://<LAN>:8450/robotics/config in Render Studio robotics configuration.",
            "Render should download controls + every in-headset UI from that manifest (or /robotics/bundle.zip) and wire menus — not only open a URL.",
            "Source of truth: render3d.app/getting-started.html#robotics-configuration",
            "Find the Pi IP: hostname -I | awk '{print $1}'",
            "Quest stays on https://<LAN>:8443/teleop. Asset download is HTTP :8450 so the self-signed cert is not required for setup files.",
        ],
    },
}

SOCIAL_LINKS = [
    {
        "id": "discord",
        "label": "Discord",
        "url": DISCORD_INVITE,
        "url_web": DISCORD_INVITE_WEB,
        "deep_link": "discord://discord.com/invite/kaPZRCk9c",
    },
    {"id": "x", "label": X_HANDLE, "url": X_URL},
    {"id": "github", "label": "GitHub", "url": GITHUB_URL},
    {"id": "render", "label": "Render docs", "url": RENDER_DOCS},
]


@dataclass
class RoboticsContext:
    schema: str
    y_map: str
    render_docs: str
    static_dir: Path
    api_port: int
    teleop_port: int
    viser_port: int
    hostname: Callable[[Request], str]
    http_api: Callable[[Request, str], str]
    https_teleop: Callable[[Request, str], str]
    teleop_page_url: Callable[[Request, bool], str]
    teleop_url: Callable[[Request], str]
    teleop_listening: Callable[[], bool]
    port_up: Callable[[int], bool]
    trust_https_url: Callable[[Request], str]


def _json_bytes(obj: object) -> bytes:
    return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")


def _media(path: str) -> str:
    if path.endswith(".html"):
        return "text/html; charset=utf-8"
    if path.endswith(".css"):
        return "text/css; charset=utf-8"
    if path.endswith(".js"):
        return "text/javascript; charset=utf-8"
    if path.endswith(".json"):
        return "application/json; charset=utf-8"
    if path.endswith(".md"):
        return "text/markdown; charset=utf-8"
    if path.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"


def _lan_host(ctx: RoboticsContext, request: Request) -> str:
    return ctx.hostname(request)


def _fill_lan(text: str, host: str) -> str:
    return text.replace("<LAN>", host)


def xr_standard_gamepad() -> dict[str, object]:
    return {
        "mapping": "xr-standard",
        "axes": {
            "0": {"id": "thumbstick_x", "label": "Thumbstick X"},
            "1": {"id": "thumbstick_y", "label": "Thumbstick Y"},
            "2": {"id": "trigger_analog", "label": "Trigger analog"},
            "3": {"id": "grip_analog", "label": "Grip analog"},
        },
        "buttons": {
            "0": {"id": "trigger", "label": "Trigger"},
            "1": {"id": "grip", "label": "Grip / squeeze"},
            "2": {"id": "touchpad", "label": "Touchpad"},
            "3": {"id": "thumbstick_press", "label": "Thumbstick press"},
            "4": {
                "id": "primary",
                "label": "Primary",
                "left": "X",
                "right": "A",
            },
            "5": {
                "id": "secondary",
                "label": "Secondary",
                "left": "Y",
                "right": "B",
            },
            "6": {"id": "menu", "label": "Menu"},
        },
        "frame_id": "left | right",
    }


def actions_spec() -> dict[str, object]:
    return {
        "pause": {
            "id": "pause",
            "label": "Pause in place",
            "http": {"method": "POST", "path": "/teleop/y", "body": {"action": "tap"}},
            "when": "TELEOP ON (armed follow)",
            "result": "HOLD — arms stay where they are (MIT/gravity hold); headset follow stops.",
        },
        "resume": {
            "id": "resume",
            "label": "Resume follow",
            "http": {"method": "POST", "path": "/teleop/y", "body": {"action": "tap"}},
            "when": "TELEOP HOLD, or OFF for a fresh enable",
            "result": "Follow from the current pose (no slam). After session_reset, tap is a fresh calibrate.",
        },
        "session_reset": {
            "id": "session_reset",
            "label": "Kill + fresh-session reset",
            "http": {"method": "POST", "path": "/teleop/y", "body": {"action": "session_reset"}},
            "when": "Hold Y ≥ 3s (Canceling arms overlay completes)",
            "result": (
                "Kill teleop and reset the session. HUD TELEOP = OFF. "
                "Next Y tap is a new instance. NOT a Dora all-zero slow-home."
            ),
            "aliases": ["kill", "reset"],
            "hold_ms": Y_HOLD_MS,
        },
        "kill": {
            "id": "kill",
            "label": "KILL / disable software motion",
            "http": {"method": "POST", "path": "/robotics/kill", "body": {"source": "robotics_home"}},
            "when": "Render Studio emergency button; no teleop page or controller session required",
            "result": (
                "Cancel teleop follow, pending engagement, homing, and emote playback; "
                "publish the driver safe command. Motors safe-hold; physical E-stop removes power."
            ),
            "required_ack": {"armed": False, "homing": False, "pending_arm": False, "playing": False},
        },
        "home_robot": {
            "id": "home_robot",
            "label": "Home Robot · Arms Down",
            "http": {"method": "POST", "path": "/robotics/home", "body": {"pose": "arms_down", "both_arms": True, "speed_scale": 0.15}},
            "when": "Workspace is clear and calibration/joint-limit checks pass",
            "result": "Slow guarded physical home; teleop and emotes remain disabled.",
        },
        "recover_home": {
            "id": "recover_home",
            "label": "Recover → Home",
            "http": {"method": "POST", "path": "/robotics/recover-home", "body": {"pose": "arms_down", "both_arms": True, "speed_scale": 0.15}},
            "when": "After a software KILL and an explicit clear-workspace confirmation",
            "result": "Runs guarded physical home without enabling controller follow.",
        },
        "record": {
            "id": "record",
            "label": "Record / save a take",
            "input": "A (right primary)",
        },
        "discard": {
            "id": "discard",
            "label": "Discard while recording",
            "input": "B (right secondary)",
        },
        "emote_picker": {
            "id": "emote_picker",
            "label": "Open / close emote picker",
            "input": "X (left primary)",
            "http": {
                "list": {"method": "GET", "path": "/emotes"},
                "play": {"method": "POST", "path": "/emote/play"},
                "accept": {"method": "POST", "path": "/emote/accept"},
                "discard": {"method": "POST", "path": "/emote/discard"},
            },
        },
        "gripper_pinch": {
            "id": "gripper_pinch",
            "label": "Pinch-to-close gripper",
            "input": "Triggers (analog + button 0)",
            "rest": 0.5,
            "note": "Half open at rest, not fully spread. Left decreasing_position, right increasing_position.",
        },
    }


def controls_payload(ctx: RoboticsContext, request: Request) -> dict[str, object]:
    host = _lan_host(ctx, request)
    ws = f"wss://{host}:{ctx.teleop_port}/ws"
    y_https = ctx.https_teleop(request, "/teleop/y")
    return {
        "schema": ctx.schema,
        "kind": "controls",
        "id": "controls",
        "version": SETUP_VERSION,
        "host": host,
        "gamepad": "xr-standard",
        "xr_standard": xr_standard_gamepad(),
        "y_map": ctx.y_map,
        "y": {
            "tap": (
                "pause/resume in place. ON→HOLD pause; HOLD→resume follow; "
                "OFF→fresh enable/calibrate."
            ),
            "tap_max_ms": Y_TAP_MAX_MS,
            "hold_ms": Y_HOLD_MS,
            "hold_overlay_ms": Y_HOLD_SHOW_MS,
            "hold": (
                "kill teleop + fresh-session reset (Canceling arms spinner). "
                "NOT the old Dora all-zero slow-home."
            ),
            "release_before_hold": "cancel the kill; stay HOLD if pause already started",
            "http": {
                "method": "POST",
                "url": y_https,
                "body_tap": {"action": "tap"},
                "body_reset": {"action": "session_reset"},
            },
        },
        "note": (
            "Direct LAN wss://<LAN>:8443/ws. Binary LCM PoseStamped+Joy is one pose "
            "client (usually /teleop). Render Studio may open a second /ws and send JSON "
            "Y ({type:\"y\",action:\"tap\"}) without stealing poses. mock=false hello "
            "means real OpenArm, not a local mock gamepad."
        ),
        "websocket": {
            "url": ws,
            "protocol": (
                "binary DimOS LCM PoseStamped + Joy (~80 Hz) and JSON control "
                "({type:\"y\", action:\"tap\"|\"session_reset\"})"
            ),
            "single_client": False,
            "pose_client_exclusive": True,
            "json_control": True,
            "mock": False,
            "hardware": "openarm_damiao",
            "hello": {
                "type": "hello",
                "mock": False,
                "hardware": "openarm_damiao",
                "y_map": ctx.y_map,
            },
            "y": {
                "text": {"type": "y", "action": "tap"},
                "text_reset": {"type": "y", "action": "session_reset"},
            },
            "owner": "Quest /teleop (poses) + Render Studio (JSON Y) on the same /ws",
        },
        "stream": ws,
        "http_backups": {
            "y": {
                "method": "POST",
                "url": y_https,
                "body": {"action": "tap | session_reset | kill"},
            },
            "emotes": {"method": "GET", "url": ctx.https_teleop(request, "/emotes")},
            "emote_play": {"method": "POST", "url": ctx.https_teleop(request, "/emote/play")},
            "emote_accept": {"method": "POST", "url": ctx.https_teleop(request, "/emote/accept")},
            "emote_discard": {"method": "POST", "url": ctx.https_teleop(request, "/emote/discard")},
        },
        "actions": actions_spec(),
        "bindings": [
            {
                "hand": "left",
                "button": "Y",
                "xr_button": 5,
                "event": "tap",
                "action": "pause",
                "when": "armed",
            },
            {
                "hand": "left",
                "button": "Y",
                "xr_button": 5,
                "event": "tap",
                "action": "resume",
                "when": "holding or off",
            },
            {
                "hand": "left",
                "button": "Y",
                "xr_button": 5,
                "event": "hold",
                "hold_ms": Y_HOLD_MS,
                "action": "session_reset",
                "ui": "y_hold",
                "overlay": "Canceling arms",
            },
            {
                "hand": "left",
                "button": "X",
                "xr_button": 4,
                "event": "tap",
                "action": "emote_picker",
                "ui": "emote",
            },
            {
                "hand": "right",
                "button": "A",
                "xr_button": 4,
                "event": "tap",
                "action": "record",
            },
            {
                "hand": "right",
                "button": "B",
                "xr_button": 5,
                "event": "tap",
                "action": "discard",
                "when": "recording",
            },
            {
                "hand": "both",
                "button": "trigger",
                "xr_button": 0,
                "event": "analog",
                "action": "gripper_pinch",
            },
            {
                "hand": "both",
                "button": "grip",
                "xr_button": 1,
                "event": "squeeze",
                "action": "grab_panel",
                "targets": ["hud", "docs"],
            },
        ],
        "left": {
            "Y": {
                "tap": "pause/resume in place (ON→HOLD, HOLD→resume, OFF→fresh enable)",
                "hold_ms": Y_HOLD_MS,
                "hold": (
                    "kill + fresh-session reset. Visor overlay “Canceling arms”. "
                    "NOT a Dora all-zero slow-home."
                ),
            },
            "X": "emote picker",
            "trigger": "pinch-to-close gripper (rest 0.5)",
            "grip": "grab HUD / docs panel",
        },
        "right": {
            "A": "record / save a take",
            "B": "discard while recording",
            "trigger": "pinch-to-close gripper (rest 0.5)",
            "grip": "grab HUD / docs panel",
        },
        "do_not_use": "Hold X+A (old DimOS deadman). Do not treat Y-hold as Dora slow-home.",
        "buttons": button_map_summary(),
    }


def button_map_summary() -> dict[str, object]:
    return {
        "gamepad": "xr-standard",
        "y_map": Y_MAP,
        "note": (
            "LAN wss://<LAN>:8443/ws accepts Render Studio JSON Y alongside the "
            "Quest WebXR pose client. Do not fall back to a mock gamepad when hello.mock is false."
        ),
        "joy": xr_standard_gamepad(),
        "left": {
            "Y": {
                "tap": "pause/resume in place (ON→HOLD, HOLD→resume, OFF→fresh enable)",
                "hold_ms": Y_HOLD_MS,
                "hold": (
                    "kill + fresh-session reset (“Canceling arms”). "
                    "NOT a Dora all-zero slow-home."
                ),
            },
            "X": "emote picker",
            "trigger": "pinch-to-close gripper (rest 0.5)",
            "grip": "grab HUD / docs panel",
        },
        "right": {
            "A": "record / save a take",
            "B": "discard while recording",
            "trigger": "pinch-to-close gripper (rest 0.5)",
            "grip": "grab HUD / docs panel",
        },
        "do_not_use": "Hold X+A (old DimOS deadman)",
        "actions": list(actions_spec().keys()),
    }


def menus_payload(ctx: RoboticsContext, request: Request) -> dict[str, object]:
    host = _lan_host(ctx, request)
    base = ctx.http_api(request, "/robotics")
    return {
        "schema": ctx.schema,
        "kind": "menu",
        "id": "menus",
        "version": SETUP_VERSION,
        "host": host,
        "note": (
            "Full in-headset menu wiring from DimOS teleop.js. Render should install "
            "these panels and bindings, not iframe the Quest page."
        ),
        "root": {
            "id": "hud",
            "type": "panel",
            "title": "Collection HUD",
            "open_on": "session_start",
            "ui": f"{base}/ui/hud",
            "grab": {
                "input": "grip",
                "xr_button": 1,
                "hands": ["left", "right"],
                "ray": True,
                "distance_m": 0.28,
                "hint": "grip HUD to move · release to place",
            },
            "items": [
                {
                    "id": "docs-icon",
                    "type": "icon",
                    "label": "Docs ?",
                    "placement": "hud-top-right",
                    "rect_px": {"x": 882, "y": 18, "w": 54, "h": 54},
                    "opens": "docs",
                    "input": "trigger_tap",
                }
            ],
            "chips": [
                {"id": "teleop", "label": "TELEOP", "values": ["OFF", "HOLD", "ON", "HOMING", "WAIT", "PLAY"]},
                {"id": "state", "label": "STATE", "values": ["READY", "RECORDING", "OFFLINE"]},
                {"id": "take", "label": "TAKE"},
                {"id": "elapsed", "label": "ELAPSED"},
                {"id": "saved", "label": "SAVED"},
                {"id": "discarded", "label": "DISCARDED"},
                {"id": "last_action", "label": "LAST ACTION"},
            ],
            "footer": "grip HUD to move  ·  tap Y pause  ·  hold Y 3s cancel  ·  A record  ·  B discard  ·  X emotes",
        },
        "panels": {
            "docs": {
                "id": "docs",
                "type": "panel",
                "title": "TeleOP docs",
                "open_from": "hud.docs-icon",
                "ui": f"{base}/ui/docs",
                "close": {"id": "close", "input": "trigger_tap", "label": "×"},
                "grab": {"input": "grip", "xr_button": 1, "ray": True, "distance_m": 0.28},
                "header": {
                    "title": "TeleOP docs",
                    "links": [
                        {**link, "opens": "external"}
                        for link in SOCIAL_LINKS
                        if link["id"] != "render"
                    ],
                },
                "tabs": DOCS_TABS,
                "search": {
                    "chips": DOCS_SEARCH_CHIPS,
                    "input": "chip_toggle",
                    "placeholder": "Search topics — tap a chip",
                },
                "pages": DOCS_PAGES,
                "footer": {
                    "id": "link-render",
                    "label": "Render docs: render3d.app  ·  tap footer to open",
                    "url": ctx.render_docs,
                },
                "hint": "grip to move · trigger taps",
            },
            "y_hold": {
                "id": "y_hold",
                "type": "overlay",
                "title": "Canceling arms",
                "ui": f"{base}/ui/y_hold",
                "show_when": "Y held ≥ 300ms",
                "complete_ms": Y_HOLD_MS,
                "label": "Canceling arms",
                "complete_label": "Reset",
                "action": "session_reset",
                "note": "Spinner + controller Y ring. Completing the hold is kill + session reset, not slow-home.",
            },
            "emote": {
                "id": "emote",
                "type": "popup",
                "title": "Emotes",
                "open_from": "X.tap",
                "ui": f"{base}/ui/emote",
                "nav": "left stick up/down",
                "play": "A",
                "close": "X tap again",
            },
            "confirm": {
                "id": "confirm",
                "type": "popup",
                "title": "Add this take as an emote?",
                "open_from": "record_saved",
                "ui": f"{base}/ui/confirm",
                "accept": {"label": "Add emote", "input": "A", "http": "POST /emote/accept"},
                "discard": {"label": "Don't add", "input": "B", "http": "POST /emote/discard"},
            },
            "hand_chip": {
                "id": "hand_chip",
                "type": "overlay",
                "title": "Right-hand A/B chip",
                "ui": f"{base}/ui/hand_chip",
                "shows": "A Record/Save · B Discard while recording",
            },
        },
        "bindings": [
            {
                "from": "hud.docs-icon",
                "event": "trigger_tap",
                "action": "open",
                "target": "docs",
            },
            {"from": "docs.close", "event": "trigger_tap", "action": "close", "target": "docs"},
            {"from": "docs.tab-*", "event": "trigger_tap", "action": "select_tab", "target": "docs"},
            {"from": "docs.chip-*", "event": "trigger_tap", "action": "toggle_search", "target": "docs"},
            {
                "from": "docs.link-discord",
                "event": "trigger_tap",
                "action": "open_url",
                "url": DISCORD_INVITE,
            },
            {"from": "docs.link-x", "event": "trigger_tap", "action": "open_url", "url": X_URL},
            {
                "from": "docs.link-github",
                "event": "trigger_tap",
                "action": "open_url",
                "url": GITHUB_URL,
            },
            {
                "from": "docs.link-render",
                "event": "trigger_tap",
                "action": "open_url",
                "url": ctx.render_docs,
            },
            {
                "from": "left.Y",
                "event": "hold",
                "action": "show",
                "target": "y_hold",
            },
            {
                "from": "left.X",
                "event": "tap",
                "action": "toggle",
                "target": "emote",
            },
        ],
        "social": SOCIAL_LINKS,
        "load_order": [
            "controls.json",
            "menus.json",
            "ui/panels.css",
            "ui/setup.js",
            "ui/hud.html",
            "ui/docs.html",
            "ui/y_hold.html",
            "ui/emote.html",
            "ui/confirm.html",
        ],
    }


def hud_three_spec() -> dict[str, object]:
    return {
        "kind": "world-locked-card",
        "engine_hint": "canvas-texture-quad",
        "size_m": {"width": 0.38, "height": 0.38 * 400 / 960},
        "canvas_px": {"width": 960, "height": 400},
        "seed": {"forward_m": 0.50, "left_m": 0.32, "down_m": 0.04},
        "grab": {"grip_button": 1, "distance_m": 0.28, "ray": True},
        "style": {
            "fill": "rgba(4, 9, 17, 0.88)",
            "radius_px": 22,
            "stroke": "rgba(188, 210, 235, 0.35)",
            "stroke_hover": "#ffcc00",
            "stroke_grab": "#22c55e",
        },
        "chips": [
            {"id": "teleop", "label": "TELEOP"},
            {"id": "state", "label": "STATE"},
            {"id": "take", "label": "TAKE"},
            {"id": "elapsed", "label": "ELAPSED"},
            {"id": "saved", "label": "SAVED"},
            {"id": "discarded", "label": "DISCARDED"},
            {"id": "last_action", "label": "LAST ACTION"},
        ],
        "icons": [
            {
                "id": "docs",
                "label": "Docs ?",
                "opens": "docs",
                "rect_px": {"x": 882, "y": 18, "w": 54, "h": 54},
            }
        ],
    }


def ui_modules(ctx: RoboticsContext, request: Request) -> list[dict[str, object]]:
    api = ctx.http_api
    return [
        {
            "id": "hud",
            "kind": "ui",
            "title": "Main HUD card",
            "url": api(request, "/robotics/ui/hud"),
            "path": "ui/hud.html",
            "json": api(request, "/robotics/ui/hud.json"),
            "media_type": "text/html",
        },
        {
            "id": "docs",
            "kind": "ui",
            "title": "Docs window (tabs, search, Discord / X / GitHub)",
            "url": api(request, "/robotics/ui/docs"),
            "path": "ui/docs.html",
            "media_type": "text/html",
        },
        {
            "id": "y_hold",
            "kind": "ui",
            "title": "Hold-Y Canceling arms spinner",
            "url": api(request, "/robotics/ui/y_hold"),
            "path": "ui/y_hold.html",
            "media_type": "text/html",
        },
        {
            "id": "emote",
            "kind": "ui",
            "title": "Emote picker",
            "url": api(request, "/robotics/ui/emote"),
            "path": "ui/emote.html",
            "media_type": "text/html",
        },
        {
            "id": "confirm",
            "kind": "ui",
            "title": "Add-emote / record popup",
            "url": api(request, "/robotics/ui/confirm"),
            "path": "ui/confirm.html",
            "media_type": "text/html",
        },
        {
            "id": "hand_chip",
            "kind": "ui",
            "title": "Right-hand A/B chip",
            "url": api(request, "/robotics/ui/hand_chip"),
            "path": "ui/hand_chip.html",
            "media_type": "text/html",
        },
        {
            "id": "entry",
            "kind": "ui",
            "title": "Setup entry (load order preview)",
            "url": api(request, "/robotics/ui/index"),
            "path": "ui/index.html",
            "media_type": "text/html",
        },
        {
            "id": "setup_js",
            "kind": "script",
            "title": "setup.js",
            "url": api(request, "/robotics/assets/ui/setup.js"),
            "path": "ui/setup.js",
            "media_type": "text/javascript",
        },
        {
            "id": "panels_css",
            "kind": "style",
            "title": "panels.css",
            "url": api(request, "/robotics/assets/ui/panels.css"),
            "path": "ui/panels.css",
            "media_type": "text/css",
        },
        {
            "id": "source_js",
            "kind": "ui-source",
            "title": "Live teleop.js (WebXR, not for iframe)",
            "url": api(request, "/robotics/assets/ui/source/teleop.js"),
            "path": "ui/source/teleop.js",
            "media_type": "text/javascript",
        },
        {
            "id": "source_css",
            "kind": "ui-source",
            "title": "Live teleop.css",
            "url": api(request, "/robotics/assets/ui/source/teleop.css"),
            "path": "ui/source/teleop.css",
            "media_type": "text/css",
        },
        {
            "id": "source_html",
            "kind": "ui-source",
            "title": "Live Quest index.html",
            "url": api(request, "/robotics/assets/ui/source/index.html"),
            "path": "ui/source/index.html",
            "media_type": "text/html",
        },
    ]


def setup_asset_list(ctx: RoboticsContext, request: Request) -> list[dict[str, object]]:
    api = ctx.http_api
    assets = [
        {
            "id": "hud",
            "kind": "ui",
            "url": api(request, "/robotics/ui/hud"),
            "path": "ui/hud.html",
        },
        {
            "id": "docs",
            "kind": "ui",
            "url": api(request, "/robotics/ui/docs"),
            "path": "ui/docs.html",
        },
        {
            "id": "y_hold",
            "kind": "ui",
            "url": api(request, "/robotics/ui/y_hold"),
            "path": "ui/y_hold.html",
        },
        {
            "id": "emote",
            "kind": "ui",
            "url": api(request, "/robotics/ui/emote"),
            "path": "ui/emote.html",
        },
        {
            "id": "confirm",
            "kind": "ui",
            "url": api(request, "/robotics/ui/confirm"),
            "path": "ui/confirm.html",
        },
        {
            "id": "controls",
            "kind": "controls",
            "url": api(request, "/robotics/controls"),
            "path": "controls.json",
        },
        {
            "id": "menus",
            "kind": "menu",
            "url": api(request, "/robotics/menus"),
            "path": "menus.json",
        },
        {
            "id": "setup_js",
            "kind": "script",
            "url": api(request, "/robotics/assets/ui/setup.js"),
            "path": "ui/setup.js",
        },
        {
            "id": "panels_css",
            "kind": "style",
            "url": api(request, "/robotics/assets/ui/panels.css"),
            "path": "ui/panels.css",
        },
    ]
    return assets


def setup_payload(ctx: RoboticsContext, request: Request) -> dict[str, object]:
    return {
        "version": SETUP_VERSION,
        "schema": ctx.schema,
        "download": ctx.http_api(request, "/robotics/bundle.zip"),
        "assets_root": ctx.http_api(request, "/robotics/assets/"),
        "load_order": [
            "manifest.json",
            "controls.json",
            "menus.json",
            "ui/setup.js",
            "ui/panels.css",
            "ui/hud.html",
            "ui/docs.html",
            "ui/y_hold.html",
            "ui/emote.html",
            "ui/confirm.html",
        ],
        "apply": (
            "Download the zip (or each asset). Bind action ids from controls.json. "
            "Mount panels from menus.json (docs icon → docs, Y-hold overlay, emote/confirm). "
            "Live passthrough remains https://<LAN>:8443/teleop — do not iframe it."
        ),
        "assets": setup_asset_list(ctx, request),
    }


def ui_payload(ctx: RoboticsContext, request: Request) -> dict[str, object]:
    modules = ui_modules(ctx, request)
    return {
        "schema": ctx.schema,
        "kind": "ui-manifest",
        "version": SETUP_VERSION,
        "host": _lan_host(ctx, request),
        "passthrough_ui": ctx.teleop_page_url(request, False),
        "ui": ctx.teleop_page_url(request, False),
        "autoconnect": ctx.teleop_url(request),
        "embed": {
            "iframe": False,
            "reason": (
                "Quest immersive-ar / passthrough WebXR must run as a full-page "
                "document, not inside an iframe from render3d.app. Download HUD/docs "
                "HTML from this API and mount them in Render; keep live tracking on :8443."
            ),
        },
        "docs": ctx.render_docs,
        "modules": modules,
        "setup_js": ctx.http_api(request, "/robotics/assets/ui/setup.js"),
        "css": ctx.http_api(request, "/robotics/assets/ui/panels.css"),
    }


def controllers_payload(ctx: RoboticsContext, request: Request) -> dict[str, object]:
    """Compact controllers object kept on /robotics/config for older clients."""
    full = controls_payload(ctx, request)
    return {
        "stream": full["stream"],
        "websocket": full["websocket"]["url"],
        "protocol": full["websocket"]["protocol"],
        "single_client": False,
        "mock": False,
        "json_control": True,
        "http_backups": full["http_backups"],
        "buttons": full["buttons"],
        "y_map": ctx.y_map,
        "actions": list(full["actions"].keys()),
        "full": ctx.http_api(request, "/robotics/controls"),
    }


def build_config(ctx: RoboticsContext, request: Request) -> dict[str, object]:
    host = _lan_host(ctx, request)
    up = ctx.teleop_listening()
    visor = f"http://{host}:{ctx.viser_port}"
    ui = ui_payload(ctx, request)
    controllers = controllers_payload(ctx, request)
    setup = setup_payload(ctx, request)
    return {
        "ok": up,
        "teleop_up": up,
        "schema": ctx.schema,
        "kind": "dimos-quest-openarm",
        "mock": False,
        "hardware": "openarm_damiao",
        "host": host,
        "paste_url": ctx.http_api(request, "/robotics/config"),
        "docs": ctx.render_docs,
        "url": ctx.teleop_url(request),
        "ui": ui["ui"],
        "passthrough_ui": ui["passthrough_ui"],
        "autoconnect": ui["autoconnect"],
        "embed": ui["embed"],
        "websocket": controllers["websocket"],
        "controllers": controllers,
        "y_map": ctx.y_map,
        "trust": ctx.http_api(request, "/trust"),
        "trust_url": ctx.http_api(request, "/trust"),
        "trust_https_url": ctx.trust_https_url(request),
        "cert": ctx.http_api(request, "/cert.pem"),
        "viser": visor,
        "visor": visor,
        "viser_up": ctx.port_up(ctx.viser_port),
        "ports": {
            "discovery_http": ctx.api_port,
            "teleop_https": ctx.teleop_port,
            "viser_http": ctx.viser_port,
        },
        "setup": setup,
        "controls_summary": {
            "gamepad": "xr-standard",
            "y": "tap pause/resume in place · hold 3s session_reset (not slow-home)",
            "actions": list(actions_spec().keys()),
            "url": ctx.http_api(request, "/robotics/controls"),
        },
        "ui_summary": {
            "panels": ["hud", "docs", "y_hold", "emote", "confirm"],
            "menus": ctx.http_api(request, "/robotics/menus"),
            "download": setup["download"],
        },
    }


def _panel_html(title: str, body: str, *, base_href: str = "", extra_head: str = "") -> str:
    base = f'<base href="{base_href}">' if base_href else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{base}
<link rel="stylesheet" href="panels.css">
{extra_head}
</head>
<body class="rs-teleop">
{body}
</body>
</html>
"""


def panels_css() -> str:
    return """/* DimOS Quest teleop panels — downloadable HUD / docs for Render */
:root {
  --bg: rgba(4, 9, 17, 0.94);
  --card: rgba(6, 12, 22, 0.94);
  --ink: #f4f7fb;
  --muted: #9aa8b8;
  --line: rgba(188, 210, 235, 0.35);
  --gold: #ffcc00;
  --green: #63d6a3;
  --warn: #f6b94d;
  --danger: #ff6b6b;
  --ok: #7ee787;
}
* { box-sizing: border-box; }
html, body.rs-teleop {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #05070c;
  color: var(--ink);
}
.rs-card {
  background: var(--bg);
  border: 3px solid var(--line);
  border-radius: 22px;
  padding: 16px 18px 14px;
  max-width: 960px;
}
.rs-card.grabbing { border-color: #22c55e; }
.rs-card:hover { border-color: var(--gold); }
.rs-hud { width: min(960px, 100%); }
.rs-chips {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.rs-chips.row3 { grid-template-columns: repeat(3, 1fr); margin-top: 10px; }
.rs-chip {
  background: rgba(255,255,255,0.06);
  border-radius: 14px;
  padding: 10px 12px 12px;
  min-height: 78px;
}
.rs-chip .k { display: block; color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.rs-chip .v { display: block; margin-top: 6px; font-size: 28px; font-weight: 700; }
.rs-hud-head { display: flex; gap: 10px; align-items: flex-start; }
.rs-hud-head .rs-chips { flex: 1; }
.rs-docs-icon {
  width: 54px; height: 54px; border-radius: 14px;
  border: 2px solid var(--line);
  background: rgba(255,255,255,0.08);
  color: var(--ink);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-decoration: none; font-weight: 700; font-size: 12px; line-height: 1.15;
  flex: 0 0 54px;
}
.rs-docs-icon:hover { border-color: var(--gold); background: rgba(255,204,0,0.28); }
.rs-foot { color: var(--muted); font-size: 14px; font-weight: 600; margin: 14px 4px 4px; }
.rs-docs header { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.rs-docs h1 { font-size: 22px; margin: 0; }
.rs-social { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
.rs-social a, .rs-tab, .rs-chip-btn, .rs-btn {
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none; color: var(--ink); font-weight: 700;
  border-radius: 12px; border: 0; cursor: pointer;
}
.rs-social a {
  background: rgba(255,255,255,0.08); padding: 12px 16px; min-width: 120px;
}
.rs-social a:hover { background: rgba(255,204,0,0.28); color: #fff; }
.rs-close {
  width: 48px; height: 40px; border-radius: 10px; background: rgba(255,255,255,0.08);
  color: var(--ink); font-size: 22px; border: 0; cursor: pointer;
}
.rs-close:hover { background: #b45309; }
.rs-tabs { display: flex; gap: 6px; margin: 8px 0 10px; flex-wrap: wrap; }
.rs-tab { flex: 1; min-height: 40px; padding: 8px; background: rgba(255,255,255,0.06); }
.rs-tab[aria-selected="true"] { background: #1f7a4d; }
.rs-search-label { color: var(--muted); font-size: 14px; margin: 6px 0; }
.rs-chips-row { display: flex; flex-wrap: wrap; gap: 8px; }
.rs-chip-btn { padding: 8px 14px; background: rgba(255,255,255,0.08); }
.rs-chip-btn[aria-pressed="true"] { background: #b45309; }
.rs-page { min-height: 220px; padding: 8px 4px 24px; }
.rs-page p { margin: 0 0 8px; line-height: 1.45; color: var(--ink); }
.rs-hold {
  width: min(640px, 100%); min-height: 420px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: rgba(8,10,18,0.42); border-radius: 50%;
}
.rs-spinner {
  width: 220px; height: 220px; border-radius: 50%;
  border: 16px solid rgba(255,255,255,0.18);
  border-top-color: var(--warn);
  animation: rs-spin 0.9s linear infinite;
}
.rs-hold.done .rs-spinner { border-top-color: var(--green); }
.rs-hold-label { margin-top: 28px; font-size: 28px; font-weight: 700; }
@keyframes rs-spin { to { transform: rotate(360deg); } }
.rs-emote, .rs-confirm { width: min(768px, 100%); }
.rs-emote h2 { color: var(--ok); margin: 0 0 6px; }
.rs-row { padding: 14px 16px; margin: 6px 0; border-radius: 10px; background: rgba(255,255,255,0.04); }
.rs-row.sel { outline: 3px solid var(--ok); background: rgba(126,231,135,0.18); }
.rs-btns { display: flex; gap: 16px; margin-top: 18px; }
.rs-btn { min-height: 88px; flex: 1; font-size: 22px; }
.rs-btn.accept { background: #1f7a4d; color: #fff; }
.rs-btn.skip { background: #7c4a12; color: #fff; }
.rs-entry section { margin: 24px auto; }
"""


def setup_js(ctx: RoboticsContext, request: Request) -> str:
    host = _lan_host(ctx, request)
    config_url = ctx.http_api(request, "/robotics/config")
    return f"""/* Render robotics setup entry — load order and mount helpers.
 * Live WebXR passthrough is still https://{host}:{ctx.teleop_port}/teleop (do not iframe).
 * Asset download is HTTP :{ctx.api_port}.
 */
(function (root) {{
  const SETUP_VERSION = {json.dumps(SETUP_VERSION)};
  const PASTE_URL = {json.dumps(config_url)};
  const LOAD_ORDER = [
    "manifest.json",
    "controls.json",
    "menus.json",
    "ui/panels.css",
    "ui/setup.js",
    "ui/hud.html",
    "ui/docs.html",
    "ui/y_hold.html",
    "ui/emote.html",
    "ui/confirm.html",
    "ui/hud.json"
  ];
  const ACTION_IDS = {json.dumps(list(actions_spec().keys()))};

  async function fetchJson(url) {{
    const res = await fetch(url, {{ cache: "no-store" }});
    if (!res.ok) throw new Error(url + " " + res.status);
    return res.json();
  }}
  async function fetchText(url) {{
    const res = await fetch(url, {{ cache: "no-store" }});
    if (!res.ok) throw new Error(url + " " + res.status);
    return res.text();
  }}
  function assetMap(setup) {{
    const out = {{}};
    for (const asset of (setup && setup.assets) || []) out[asset.id] = asset;
    return out;
  }}
  async function downloadAndSetup(configUrl) {{
    const config = await fetchJson(configUrl || PASTE_URL);
    const setup = config.setup || {{}};
    const byId = assetMap(setup);
    const controls = byId.controls ? await fetchJson(byId.controls.url) : null;
    const menus = byId.menus ? await fetchJson(byId.menus.url) : null;
    return {{
      config,
      setup,
      controls,
      menus,
      byId,
      loadOrder: LOAD_ORDER,
      actionIds: (controls && controls.actions) ? Object.keys(controls.actions) : ACTION_IDS,
    }};
  }}
  async function mountPanel(hostEl, moduleUrl) {{
    if (!hostEl) throw new Error("mountPanel needs a host element");
    hostEl.innerHTML = await fetchText(moduleUrl);
    const docsIcon = hostEl.querySelector("[data-opens='docs']");
    const docs = document.querySelector("[data-panel='docs']");
    if (docsIcon && docs) {{
      docsIcon.addEventListener("click", function (event) {{
        event.preventDefault();
        docs.hidden = false;
      }});
    }}
  }}
  function bindMenus(menus) {{
    if (!menus) return [];
    return (menus.bindings || []).map(function (row) {{
      return {{
        from: row.from,
        event: row.event,
        action: row.action,
        target: row.target || null,
        url: row.url || null,
      }};
    }});
  }}
  root.RenderRoboticsSetup = {{
    version: SETUP_VERSION,
    pasteUrl: PASTE_URL,
    loadOrder: LOAD_ORDER,
    actionIds: ACTION_IDS,
    downloadAndSetup,
    mountPanel,
    bindMenus,
  }};
}})(typeof window !== "undefined" ? window : globalThis);
"""


def readme_setup(ctx: RoboticsContext, request: Request) -> str:
    host = _lan_host(ctx, request)
    paste = ctx.http_api(request, "/robotics/config")
    zip_url = ctx.http_api(request, "/robotics/bundle.zip")
    teleop = ctx.teleop_page_url(request, False)
    return f"""# DimOS Quest robotics setup bundle

Paste this URL in Render Studio robotics configuration:

`{paste}`

Or download this zip: `{zip_url}`

## What Render should do

1. Fetch `{paste}` (always HTTP :{ctx.api_port}, no self-signed cert).
2. Read `setup.assets` and either download `{zip_url}` **or** each asset URL.
3. Apply **controls.json** — xr-standard gamepad, action ids (`pause`, `resume`, `session_reset`, `record`, `discard`, `emote_picker`, `gripper_pinch`), HTTP backups, WS notes.
4. Apply **menus.json** — HUD docs icon → docs panel, tabs, search chips, Discord / X / GitHub, Y-hold overlay, emote + confirm popups, grip-to-drag.
5. Mount HTML in `ui/` (or rebuild from `ui/hud.json` as a Three.js world-locked card).
6. Run `ui/setup.js` (`RenderRoboticsSetup.downloadAndSetup`) for load order.

Live WebXR passthrough is **not** in this zip as a thing to iframe:

`{teleop}`

Quest Browser still needs HTTPS :{ctx.teleop_port}. Pose LCM is one binary client; Render Studio may send JSON Y on a second `/ws`.

## Y button (do not use old Dora slow-home)

- **Tap** = pause/resume in place.
- **Hold ≥ 3s** = kill + fresh-session reset (`session_reset`). Overlay label: “Canceling arms”.
- This is **not** a Dora all-zero home of all 7 joints.

## Load order

See `manifest.json` → `load_order` and `ui/setup.js`.

## Social (docs header)

- Discord {DISCORD_INVITE}
- X {X_HANDLE} {X_URL}
- GitHub {GITHUB_URL}

## Curl

```bash
LAN={host}
curl -sS "http://${{LAN}}:{ctx.api_port}/robotics/config"
curl -sS "http://${{LAN}}:{ctx.api_port}/robotics/controls"
curl -sS "http://${{LAN}}:{ctx.api_port}/robotics/menus"
curl -sS -o dimos-robotics-setup.zip "http://${{LAN}}:{ctx.api_port}/robotics/bundle.zip"
unzip -l dimos-robotics-setup.zip
```
"""


def hud_html(base_href: str) -> str:
    body = """
<article class="rs-card rs-hud" data-panel="hud">
  <div class="rs-hud-head">
    <div class="rs-chips">
      <div class="rs-chip"><span class="k">TELEOP</span><span class="v" style="color:#ff6b6b">OFF</span></div>
      <div class="rs-chip"><span class="k">STATE</span><span class="v" style="color:#63d6a3">READY</span></div>
      <div class="rs-chip"><span class="k">TAKE</span><span class="v">001</span></div>
      <div class="rs-chip"><span class="k">ELAPSED</span><span class="v">00:00</span></div>
    </div>
    <a class="rs-docs-icon" href="docs.html" data-opens="docs" title="Open docs">Docs<br>?</a>
  </div>
  <div class="rs-chips row3">
    <div class="rs-chip"><span class="k">SAVED</span><span class="v" style="color:#8de2bd">000</span></div>
    <div class="rs-chip"><span class="k">DISCARDED</span><span class="v" style="color:#f7c66d">000</span></div>
    <div class="rs-chip"><span class="k">LAST ACTION</span><span class="v">NONE</span></div>
  </div>
  <p class="rs-foot">grip HUD to move  ·  tap Y pause  ·  hold Y 3s cancel  ·  A record  ·  B discard  ·  X emotes</p>
</article>
<script type="application/json" id="robotics-module">{"id":"hud","opens":{"docs-icon":"docs"}}</script>
"""
    return _panel_html("TeleOP HUD", body, base_href=base_href)


def docs_html(base_href: str, host: str) -> str:
    tabs = "".join(
        f'<button class="rs-tab" data-tab="{t["id"]}" aria-selected="{"true" if t["id"]=="intro" else "false"}">{t["title"]}</button>'
        for t in DOCS_TABS
    )
    chips = "".join(
        f'<button class="rs-chip-btn" data-chip="{c}" aria-pressed="false">{c}</button>'
        for c in DOCS_SEARCH_CHIPS
    )
    pages = []
    for tab_id, page in DOCS_PAGES.items():
        paras = "".join(f"<p>{_fill_lan(line, host)}</p>" for line in page["lines"])
        hidden = "" if tab_id == "intro" else " hidden"
        pages.append(
            f'<article class="rs-page" data-page="{tab_id}" data-keywords="{" ".join(page["keywords"])}"{hidden}>{paras}</article>'
        )
    social = f"""
    <nav class="rs-social" aria-label="Social">
      <a href="{DISCORD_INVITE}" target="_blank" rel="noopener">Discord</a>
      <a href="{X_URL}" target="_blank" rel="noopener">{X_HANDLE}</a>
      <a href="{GITHUB_URL}" target="_blank" rel="noopener">GitHub</a>
    </nav>
    """
    body = f"""
<article class="rs-card rs-docs" data-panel="docs">
  <header>
    <h1>TeleOP docs</h1>
    <button class="rs-close" type="button" data-close="docs" aria-label="Close">×</button>
  </header>
  {social}
  <nav class="rs-tabs" aria-label="Docs tabs">{tabs}</nav>
  <p class="rs-search-label">Search topics — tap a chip</p>
  <div class="rs-chips-row">{chips}</div>
  {"".join(pages)}
  <p class="rs-foot"><a href="{RENDER_DOCS}" target="_blank" rel="noopener">Render docs: render3d.app · tap footer to open</a>
  · grip to move · trigger taps</p>
</article>
<script>
(function () {{
  const root = document.currentScript.parentElement;
  const tabs = root.querySelectorAll("[data-tab]");
  const pages = root.querySelectorAll("[data-page]");
  const chips = root.querySelectorAll("[data-chip]");
  function show(id) {{
    pages.forEach(function (p) {{ p.hidden = p.getAttribute("data-page") !== id; }});
    tabs.forEach(function (t) {{ t.setAttribute("aria-selected", t.getAttribute("data-tab") === id ? "true" : "false"); }});
  }}
  tabs.forEach(function (t) {{ t.addEventListener("click", function () {{ show(t.getAttribute("data-tab")); }}); }});
  chips.forEach(function (c) {{
    c.addEventListener("click", function () {{
      const on = c.getAttribute("aria-pressed") === "true";
      chips.forEach(function (x) {{ x.setAttribute("aria-pressed", "false"); }});
      if (on) {{ c.setAttribute("aria-pressed", "false"); show("intro"); return; }}
      c.setAttribute("aria-pressed", "true");
      const q = c.getAttribute("data-chip").toLowerCase();
      let first = null;
      pages.forEach(function (p) {{
        const hit = (p.getAttribute("data-keywords") || "").toLowerCase().indexOf(q) >= 0;
        if (hit && !first) first = p.getAttribute("data-page");
      }});
      if (first) show(first);
    }});
  }});
}})();
</script>
"""
    return _panel_html("TeleOP docs", body, base_href=base_href)


def y_hold_html(base_href: str) -> str:
    body = """
<article class="rs-hold" data-panel="y_hold" data-action="session_reset">
  <div class="rs-spinner" aria-hidden="true"></div>
  <p class="rs-hold-label">Canceling arms</p>
</article>
<p class="rs-foot">Hold Y 3s → session_reset (kill + fresh session). Not a Dora slow-home.</p>
"""
    return _panel_html("Canceling arms", body, base_href=base_href)


def emote_html(base_href: str) -> str:
    body = """
<article class="rs-card rs-emote" data-panel="emote">
  <h2>Emotes</h2>
  <p class="rs-foot">tap X  ·  stick ↕  ·  A play</p>
  <div class="rs-row">no takes yet</div>
</article>
"""
    return _panel_html("Emotes", body, base_href=base_href)


def confirm_html(base_href: str) -> str:
    body = """
<article class="rs-card rs-confirm" data-panel="confirm">
  <h2 style="text-align:center">Add this take as an emote?</h2>
  <p class="rs-foot" style="text-align:center">saved take</p>
  <div class="rs-btns">
    <button class="rs-btn accept" type="button" data-action="emote_accept">Add emote</button>
    <button class="rs-btn skip" type="button" data-action="emote_discard">Don't add</button>
  </div>
  <p class="rs-foot" style="text-align:center">A add  ·  B skip  ·  click a button</p>
</article>
"""
    return _panel_html("Add emote?", body, base_href=base_href)


def hand_chip_html(base_href: str) -> str:
    body = """
<article class="rs-card" data-panel="hand_chip" style="width:min(384px,100%)">
  <p style="margin:8px 0;font-weight:700;color:#7ee787">A  Record</p>
  <p class="rs-foot">While recording: A Save · B Discard</p>
</article>
"""
    return _panel_html("Hand chip", body, base_href=base_href)


def index_html(ctx: RoboticsContext, request: Request, base_href: str) -> str:
    host = _lan_host(ctx, request)
    paste = ctx.http_api(request, "/robotics/config")
    extra = '<script src="setup.js"></script>'
    inner = (
        hud_html("").split('<body class="rs-teleop">', 1)[-1].rsplit("</body>", 1)[0]
        + docs_html("", host).split('<body class="rs-teleop">', 1)[-1].rsplit("</body>", 1)[0]
        + y_hold_html("").split('<body class="rs-teleop">', 1)[-1].rsplit("</body>", 1)[0]
        + emote_html("").split('<body class="rs-teleop">', 1)[-1].rsplit("</body>", 1)[0]
        + confirm_html("").split('<body class="rs-teleop">', 1)[-1].rsplit("</body>", 1)[0]
    )
    body = f"""
<main class="rs-entry">
  <h1>DimOS robotics setup</h1>
  <p>Paste URL: <code>{paste}</code></p>
  <p>Use <code>RenderRoboticsSetup.downloadAndSetup()</code> in setup.js. Do not iframe the Quest page.</p>
  {inner}
</main>
"""
    return _panel_html("Robotics setup", body, base_href=base_href, extra_head=extra)


def _source_files(ctx: RoboticsContext) -> dict[str, tuple[bytes, str]]:
    out: dict[str, tuple[bytes, str]] = {}
    mapping = {
        "ui/source/teleop.js": "teleop.js",
        "ui/source/teleop.css": "teleop.css",
        "ui/source/index.html": "index.html",
    }
    for zip_path, name in mapping.items():
        src = ctx.static_dir / name
        if src.is_file():
            out[zip_path] = (src.read_bytes(), _media(zip_path))
    return out


def manifest_doc(ctx: RoboticsContext, request: Request) -> dict[str, object]:
    setup = setup_payload(ctx, request)
    return {
        **setup,
        "kind": "setup-manifest",
        "host": _lan_host(ctx, request),
        "paste_url": ctx.http_api(request, "/robotics/config"),
        "passthrough_ui": ctx.teleop_page_url(request, False),
    }


def bundle_files(ctx: RoboticsContext, request: Request, *, relative_html: bool) -> dict[str, tuple[bytes, str]]:
    host = _lan_host(ctx, request)
    base = "" if relative_html else ctx.http_api(request, "/robotics/assets/ui/")
    files: dict[str, tuple[bytes, str]] = {
        "manifest.json": (_json_bytes(manifest_doc(ctx, request)), _media("manifest.json")),
        "controls.json": (_json_bytes(controls_payload(ctx, request)), _media("controls.json")),
        "menus.json": (_json_bytes(menus_payload(ctx, request)), _media("menus.json")),
        "README-setup.md": (_fill_lan(readme_setup(ctx, request), host).encode("utf-8"), _media("README.md")),
        "ui/panels.css": (panels_css().encode("utf-8"), _media("panels.css")),
        "ui/setup.js": (setup_js(ctx, request).encode("utf-8"), _media("setup.js")),
        "ui/hud.html": (hud_html(base).encode("utf-8"), _media("hud.html")),
        "ui/hud.json": (_json_bytes(hud_three_spec()), _media("hud.json")),
        "ui/docs.html": (docs_html(base, host).encode("utf-8"), _media("docs.html")),
        "ui/y_hold.html": (y_hold_html(base).encode("utf-8"), _media("y_hold.html")),
        "ui/emote.html": (emote_html(base).encode("utf-8"), _media("emote.html")),
        "ui/confirm.html": (confirm_html(base).encode("utf-8"), _media("confirm.html")),
        "ui/hand_chip.html": (hand_chip_html(base).encode("utf-8"), _media("hand_chip.html")),
        "ui/index.html": (index_html(ctx, request, base).encode("utf-8"), _media("index.html")),
    }
    files.update(_source_files(ctx))
    return files


def build_zip(ctx: RoboticsContext, request: Request) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, (data, _media_type) in bundle_files(ctx, request, relative_html=True).items():
            zf.writestr(path, data)
    return buf.getvalue()


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }


def _file_response(path: str, data: bytes, media_type: str) -> Response:
    headers = _cors_headers()
    filename = path.rsplit("/", 1)[-1]
    headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return Response(content=data, media_type=media_type, headers=headers)


UI_ID_TO_PATH = {
    "hud": "ui/hud.html",
    "docs": "ui/docs.html",
    "y_hold": "ui/y_hold.html",
    "y-hold": "ui/y_hold.html",
    "canceling": "ui/y_hold.html",
    "emote": "ui/emote.html",
    "confirm": "ui/confirm.html",
    "hand_chip": "ui/hand_chip.html",
    "hand-chip": "ui/hand_chip.html",
    "index": "ui/index.html",
    "entry": "ui/index.html",
    "setup": "ui/setup.js",
    "setup.js": "ui/setup.js",
    "css": "ui/panels.css",
    "panels": "ui/panels.css",
    "hud.json": "ui/hud.json",
    "source": "ui/source/index.html",
}


def attach_robotics_routes(app: FastAPI, ctx: RoboticsContext) -> None:
    def files_http(request: Request) -> dict[str, tuple[bytes, str]]:
        return bundle_files(ctx, request, relative_html=False)

    @app.get("/robotics/setup")
    async def robotics_setup_ep(request: Request) -> JSONResponse:
        body = setup_payload(ctx, request)
        body["schema"] = ctx.schema
        return JSONResponse(body)

    @app.get("/robotics/controls")
    async def robotics_controls(request: Request) -> JSONResponse:
        return JSONResponse(controls_payload(ctx, request))

    @app.get("/robotics/controllers")
    async def robotics_controllers(request: Request) -> JSONResponse:
        body = controllers_payload(ctx, request)
        body["schema"] = ctx.schema
        body["host"] = _lan_host(ctx, request)
        return JSONResponse(body)

    @app.get("/robotics/menus")
    async def robotics_menus(request: Request) -> JSONResponse:
        return JSONResponse(menus_payload(ctx, request))

    @app.get("/robotics/ui/manifest")
    @app.get("/robotics/ui")
    async def robotics_ui(request: Request) -> JSONResponse:
        return JSONResponse(ui_payload(ctx, request))

    @app.get("/robotics/ui/{uid}")
    async def robotics_ui_id(uid: str, request: Request) -> Response:
        key = uid.strip()
        path = UI_ID_TO_PATH.get(key) or UI_ID_TO_PATH.get(key.replace("-", "_"))
        if not path:
            # allow hud.json style
            guess = f"ui/{key}" if "/" not in key else key
            files = files_http(request)
            if guess not in files:
                raise HTTPException(status_code=404, detail=f"unknown ui id: {uid}")
            data, media = files[guess]
            return _file_response(guess, data, media)
        files = files_http(request)
        if path not in files:
            raise HTTPException(status_code=404, detail=f"missing ui file: {path}")
        data, media = files[path]
        return _file_response(path, data, media)

    @app.get("/robotics/assets")
    async def robotics_assets_index(request: Request) -> JSONResponse:
        listing = []
        for path, (data, media) in files_http(request).items():
            listing.append(
                {
                    "path": path,
                    "url": ctx.http_api(request, "/robotics/assets/" + quote(path, safe="/")),
                    "bytes": len(data),
                    "media_type": media,
                }
            )
        return JSONResponse(
            {
                "schema": ctx.schema,
                "download": ctx.http_api(request, "/robotics/bundle.zip"),
                "files": listing,
            }
        )

    @app.get("/robotics/assets/{path:path}")
    async def robotics_asset(path: str, request: Request) -> Response:
        files = files_http(request)
        if path not in files:
            raise HTTPException(status_code=404, detail=f"unknown asset: {path}")
        data, media = files[path]
        return _file_response(path, data, media)

    @app.get("/robotics/bundle.zip")
    @app.get("/robotics/bundle")
    async def robotics_bundle(request: Request) -> Response:
        data = build_zip(ctx, request)
        headers = _cors_headers()
        headers["Content-Disposition"] = 'attachment; filename="dimos-robotics-setup.zip"'
        return Response(content=data, media_type="application/zip", headers=headers)
