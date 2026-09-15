#!/usr/bin/env python3
"""Local HTTP API so another site can Connect to DimOS Quest teleop.

Listens on http://0.0.0.0:8450 (no TLS) so callers do not hit the self-signed
8443 cert. WebXR still requires HTTPS on the Quest page itself.

Set DIMOS_ROOT to the DimOS checkout (default: sibling ../DimOS).
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

HERE = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE from .env without overriding a real environment."""
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


_load_dotenv(HERE / ".env")

TELEOP_HOST = os.environ.get("DIMOS_TELEOP_HOST") or os.environ.get("QUEST_HOST_IP") or "127.0.0.1"
TELEOP_PORT = int(os.environ.get("DIMOS_TELEOP_PORT", "8443"))
API_HOST = os.environ.get("DIMOS_CONNECT_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("DIMOS_CONNECT_API_PORT", "8450"))

DIMOS_ROOT = Path(os.environ.get("DIMOS_ROOT", HERE.parent / "DimOS")).expanduser().resolve()
STATIC_DIR = DIMOS_ROOT / "dimos" / "teleop" / "quest" / "web" / "static"
CERT_PATH = DIMOS_ROOT / "assets" / "teleop_certs" / "cert.pem"
TRUST_HTML = STATIC_DIR / "trust.html"

app = FastAPI(title="DimOS Quest Connect API", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _hostname(request: Request) -> str:
    host = request.headers.get("host") or TELEOP_HOST
    if host.startswith("[") and "]" in host:
        return host.split("]")[0] + "]"
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host or TELEOP_HOST


def teleop_url(request: Request) -> str:
    return f"https://{_hostname(request)}:{TELEOP_PORT}/teleop?autoconnect=1"


def trust_https_url(request: Request) -> str:
    return f"https://{_hostname(request)}:{TELEOP_PORT}/trust"


def payload(request: Request, teleop_up: bool) -> dict[str, object]:
    return {
        "ok": teleop_up,
        "teleop_up": teleop_up,
        "url": teleop_url(request),
        "trust_url": f"http://{_hostname(request)}:{API_PORT}/trust",
        "trust_https_url": trust_https_url(request),
    }


def teleop_listening() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", TELEOP_PORT)) == 0


def health_response(request: Request) -> JSONResponse:
    up = teleop_listening()
    return JSONResponse(payload(request, up), status_code=200 if up else 503)


@app.get("/")
@app.get("/health")
async def health(request: Request) -> JSONResponse:
    return health_response(request)


def _wants_redirect(request: Request, redirect: bool) -> bool:
    if redirect:
        return True
    accept = request.headers.get("accept") or ""
    return "text/html" in accept and "application/json" not in accept.split(",")[0]


@app.api_route("/connect", methods=["GET", "POST"])
async def connect(request: Request, redirect: bool = False) -> JSONResponse | RedirectResponse:
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
