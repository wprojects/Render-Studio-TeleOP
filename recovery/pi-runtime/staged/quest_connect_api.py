#!/usr/bin/env python3
"""Local HTTP API so Render Studio (and other LAN clients) can connect to DimOS Quest teleop.

Listens on http://0.0.0.0:8450 (no TLS) so callers do not hit the self-signed
8443 cert. WebXR still requires HTTPS on the Quest page itself.

Paste this in Render robotics configuration (single URL):
  http://<PI_LAN_IP>:8450/robotics/config

That JSON is a setup manifest: controls, menus, downloadable HUD/docs UIs,
and http://<PI_LAN_IP>:8450/robotics/bundle.zip.
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

HERE = Path(__file__).resolve().parent
DIMOS_ROOT = Path(os.environ.get("DIMOS_ROOT", HERE.parent)).expanduser().resolve()
SCHEMA = "render-studio-robotics/v1"
RENDER_DOCS = "https://render3d.app/getting-started.html#robotics-configuration"


def _load_robotics_setup():
    env = (os.environ.get("RENDER_STUDIO_TELEOP") or "").strip()
    candidates = []
    if env:
        candidates.append(Path(env).expanduser() / "robotics_setup.py")
    candidates.extend(
        [
            HERE.parents[1] / "Render-Studio-TeleOP" / "robotics_setup.py",
            HERE / "robotics_setup.py",
        ]
    )
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("robotics_setup", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules["robotics_setup"] = module
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError(
        "robotics_setup.py not found next to DimOS (expected sibling Render-Studio-TeleOP)"
    )


robotics_setup = _load_robotics_setup()
RoboticsContext = robotics_setup.RoboticsContext
SETUP_VERSION = robotics_setup.SETUP_VERSION
Y_MAP = robotics_setup.Y_MAP


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(DIMOS_ROOT / ".env")
_load_dotenv(DIMOS_ROOT.parent / "Render-Studio-TeleOP" / ".env")

TELEOP_HOST = os.environ.get("DIMOS_TELEOP_HOST") or os.environ.get("QUEST_HOST_IP") or "127.0.0.1"
TELEOP_PORT = int(os.environ.get("DIMOS_TELEOP_PORT", "8443"))
API_HOST = os.environ.get("DIMOS_CONNECT_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("DIMOS_CONNECT_API_PORT", "8450"))
VISER_PORT = int(os.environ.get("DIMOS_VISER_PORT", "8095"))

STATIC_DIR = DIMOS_ROOT / "dimos" / "teleop" / "quest" / "web" / "static"
CERT_PATH = DIMOS_ROOT / "assets" / "teleop_certs" / "cert.pem"
TRUST_HTML = STATIC_DIR / "trust.html"

app = FastAPI(title="DimOS Quest Connect API", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        "https://render3d.app",
        "https://www.render3d.app",
        "https://app.render3d.app",
    ],
    allow_origin_regex=(
        r"https://([a-z0-9-]+\.)*render3d\.app"
        r"|https?://(localhost|127\.0\.0\.1|"
        r"(\d{1,3}\.){3}\d{1,3})(:\d+)?"
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _is_loopback(host: str) -> bool:
    h = host.strip().lower().strip("[]")
    return h in ("", "0.0.0.0", "::", "127.0.0.1", "::1", "localhost")


def _detect_lan_ip() -> str:
    env = (os.environ.get("DIMOS_TELEOP_HOST") or os.environ.get("QUEST_HOST_IP") or "").strip()
    if env and not _is_loopback(env):
        return env
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("1.1.1.1", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not _is_loopback(ip):
            return ip
    except OSError:
        pass
    return env or TELEOP_HOST or "127.0.0.1"


def _hostname(request: Request) -> str:
    host = request.headers.get("host") or TELEOP_HOST
    if host.startswith("[") and "]" in host:
        host = host.split("]")[0] + "]"
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    if _is_loopback(host):
        return _detect_lan_ip()
    return host or _detect_lan_ip()


def _port_up(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def teleop_listening() -> bool:
    return _port_up(TELEOP_PORT)


def teleop_page_url(request: Request, autoconnect: bool = False) -> str:
    q = "?autoconnect=1" if autoconnect else ""
    return f"https://{_hostname(request)}:{TELEOP_PORT}/teleop{q}"


def teleop_url(request: Request) -> str:
    return teleop_page_url(request, autoconnect=True)


def trust_https_url(request: Request) -> str:
    return f"https://{_hostname(request)}:{TELEOP_PORT}/trust"


def _http_api(request: Request, path: str) -> str:
    return f"http://{_hostname(request)}:{API_PORT}{path}"


def _https_teleop(request: Request, path: str) -> str:
    return f"https://{_hostname(request)}:{TELEOP_PORT}{path}"


CTX = RoboticsContext(
    schema=SCHEMA,
    y_map=Y_MAP,
    render_docs=RENDER_DOCS,
    static_dir=STATIC_DIR,
    api_port=API_PORT,
    teleop_port=TELEOP_PORT,
    viser_port=VISER_PORT,
    hostname=_hostname,
    http_api=_http_api,
    https_teleop=_https_teleop,
    teleop_page_url=teleop_page_url,
    teleop_url=teleop_url,
    teleop_listening=teleop_listening,
    port_up=_port_up,
    trust_https_url=trust_https_url,
)

robotics_setup.attach_robotics_routes(app, CTX)


def _policy_store():
    from dimos.teleop.quest import policy_store

    return policy_store


def robotics_config(request: Request) -> dict[str, object]:
    cfg = robotics_setup.build_config(CTX, request)
    host = _hostname(request)
    policy = {
        "schema": "render-studio-policy/v1",
        "http": f"http://{host}:{API_PORT}/robotics/policy",
        "https": f"https://{host}:{TELEOP_PORT}/robotics/policy",
        "bind": f"http://{host}:{API_PORT}/robotics/policy/bind",
        "program": f"http://{host}:{API_PORT}/robotics/policy/program",
        "link_emote": f"https://{host}:{TELEOP_PORT}/robotics/policy/link-emote",
        "run": f"https://{host}:{TELEOP_PORT}/robotics/policy/run",
        "note": (
            "Mac Robotics Home POSTs the live MuJoCo deployment to /robotics/policy/bind. "
            "Agents read GET /robotics/policy. Physical run uses HTTPS /robotics/policy/run "
            "after guarded Home, only when a validated program is bound."
        ),
    }
    try:
        policy.update(_policy_store().status_payload())
    except Exception as error:  # noqa: BLE001 — discovery must still answer
        policy["ok"] = False
        policy["error"] = str(error)
    cfg["policy"] = policy
    cfg["policy_server"] = policy["http"]
    return cfg


def payload(request: Request, teleop_up: bool) -> dict[str, object]:
    cfg = robotics_config(request)
    cfg["ok"] = teleop_up
    cfg["teleop_up"] = teleop_up
    cfg["setup_version"] = SETUP_VERSION
    return cfg


def health_response(request: Request) -> JSONResponse:
    up = teleop_listening()
    body = payload(request, up)
    return JSONResponse(body, status_code=200 if up else 503)


@app.get("/")
@app.get("/health")
async def health(request: Request) -> JSONResponse:
    return health_response(request)


@app.get("/robotics")
@app.get("/robotics/config")
async def robotics(request: Request) -> JSONResponse:
    """Machine config for Render Studio robotics configuration. Always 200."""
    return JSONResponse(robotics_config(request))


@app.get("/robotics/policy")
async def robotics_policy_get() -> JSONResponse:
    """Agent + Mac discovery of the bound simulation deployment / runnable program."""
    return JSONResponse(_policy_store().status_payload())


@app.post("/robotics/policy/bind")
async def robotics_policy_bind(request: Request) -> JSONResponse:
    """Bind whatever MuJoCo scene Robotics Home currently has loaded (no motion)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    try:
        _policy_store().bind_deployment(body)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error), **_policy_store().status_payload()}, status_code=400)
    return JSONResponse({"ok": True, **_policy_store().status_payload()})


@app.post("/robotics/policy/program")
async def robotics_policy_program(request: Request) -> JSONResponse:
    """Upload a validated open-loop hardware program (joint trajectory)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    try:
        saved = _policy_store().save_program(body)
    except ValueError as error:
        return JSONResponse({"ok": False, "error": str(error), **_policy_store().status_payload()}, status_code=400)
    return JSONResponse({"ok": True, "saved": saved, **_policy_store().status_payload()})


def _wants_redirect(request: Request, redirect: bool) -> bool:
    if redirect:
        return True
    accept = request.headers.get("accept") or ""
    return "text/html" in accept and "application/json" not in accept.split(",")[0]


@app.api_route("/connect", methods=["GET", "POST"], response_model=None)
async def connect(request: Request, redirect: bool = False):
    up = teleop_listening()
    body = payload(request, up)
    if request.method == "GET" and _wants_redirect(request, redirect):
        return RedirectResponse(url=str(body["url"]), status_code=302)
    return JSONResponse(body, status_code=200 if up else 503)


@app.get("/teleop")
async def teleop_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(url=teleop_url(request), status_code=302)


@app.get("/trust", response_class=HTMLResponse)
async def trust() -> HTMLResponse:
    return HTMLResponse(TRUST_HTML.read_text())


@app.get("/cert.pem")
async def cert_pem() -> FileResponse:
    return FileResponse(
        CERT_PATH,
        media_type="application/x-pem-file",
        filename="dimos-teleop.pem",
    )


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="trust_static")


if __name__ == "__main__":
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")
