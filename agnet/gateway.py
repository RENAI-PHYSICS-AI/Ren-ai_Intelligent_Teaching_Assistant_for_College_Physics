from __future__ import annotations

import asyncio
import logging
import os
import ssl
from collections.abc import AsyncIterator

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from multidict import CIMultiDict


LOGGER = logging.getLogger("physics_gateway")
STREAMLIT_UPSTREAM = os.getenv("PHYSICS_STREAMLIT_UPSTREAM", "http://127.0.0.1:8502")
ADMIN_UPSTREAM = os.getenv("PHYSICS_ADMIN_UPSTREAM", "http://127.0.0.1:8603")
ASR_UPSTREAM = os.getenv("PHYSICS_ASR_UPSTREAM", "http://127.0.0.1:8604")
PUBLIC_PATH_PREFIX = "/" + os.getenv("PHYSICS_GATEWAY_PUBLIC_PREFIX", "").strip("/")
if PUBLIC_PATH_PREFIX == "/":
    PUBLIC_PATH_PREFIX = ""
WEBSOCKET_MAX_MESSAGE_SIZE = max(
    4,
    int(os.getenv("PHYSICS_WEBSOCKET_MAX_MESSAGE_MB", "64")),
) * 1024**2
EXPERIMENT_UPSTREAMS = {
    "/experiments/lissajous": os.getenv(
        "PHYSICS_LISSAJOUS_UPSTREAM", "http://127.0.0.1:9384"
    ),
    "/experiments/sound-speed": os.getenv(
        "PHYSICS_SOUND_SPEED_UPSTREAM", "http://127.0.0.1:9385"
    ),
    "/experiments/electron-em": os.getenv(
        "PHYSICS_ELECTRON_EM_UPSTREAM", "http://127.0.0.1:9386"
    ),
    "/experiments/photoelectric": os.getenv(
        "PHYSICS_PHOTOELECTRIC_UPSTREAM", "http://127.0.0.1:9387"
    ),
    "/experiments/biprism": os.getenv(
        "PHYSICS_BIPRISM_UPSTREAM", "http://127.0.0.1:9388"
    ),
    "/experiments/newton-rings": os.getenv(
        "PHYSICS_NEWTON_RINGS_UPSTREAM", "http://127.0.0.1:9389"
    ),
    "/experiments/young-modulus": os.getenv(
        "PHYSICS_YOUNG_MODULUS_UPSTREAM", "http://127.0.0.1:9390"
    ),
    "/experiments/rotational-inertia": os.getenv(
        "PHYSICS_ROTATIONAL_INERTIA_UPSTREAM", "http://127.0.0.1:9391"
    ),
    "/experiments/viscosity": os.getenv(
        "PHYSICS_VISCOSITY_UPSTREAM", "http://127.0.0.1:9392"
    ),
    "/experiments/specific-heat": os.getenv(
        "PHYSICS_SPECIFIC_HEAT_UPSTREAM", "http://127.0.0.1:9393"
    ),
    "/experiments/franck-hertz": os.getenv(
        "PHYSICS_FRANCK_HERTZ_UPSTREAM", "http://127.0.0.1:9394"
    ),
    "/experiments/temperature-sensor": os.getenv(
        "PHYSICS_TEMPERATURE_SENSOR_UPSTREAM", "http://127.0.0.1:9395"
    ),
    "/experiments/wheatstone-bridge": os.getenv(
        "PHYSICS_WHEATSTONE_BRIDGE_UPSTREAM", "http://127.0.0.1:9396"
    ),
    "/experiments/hall-effect": os.getenv(
        "PHYSICS_HALL_EFFECT_UPSTREAM", "http://127.0.0.1:9397"
    ),
    "/experiments/magnetic-hysteresis": os.getenv(
        "PHYSICS_MAGNETIC_HYSTERESIS_UPSTREAM", "http://127.0.0.1:9398"
    ),
    "/experiments/thin-lens-focal": os.getenv(
        "PHYSICS_THIN_LENS_FOCAL_UPSTREAM", "http://127.0.0.1:9399"
    ),
    "/experiments/prism-refractive-index": os.getenv(
        "PHYSICS_PRISM_REFRACTIVE_INDEX_UPSTREAM", "http://127.0.0.1:9400"
    ),
    "/experiments/thermal-conductivity": os.getenv(
        "PHYSICS_THERMAL_CONDUCTIVITY_UPSTREAM", "http://127.0.0.1:9401"
    ),
}
ADMIN_PATHS = {
    "/admin-login",
    "/admin-logout",
    "/analytics",
    "/identity-roster",
    "/identity-roster/excel",
    "/session-login",
    "/session-logout",
}


def is_admin_path(path: str) -> bool:
    return path in ADMIN_PATHS or path.startswith("/identity-roster/")
HOP_BY_HOP = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def upstream_path(request: web.Request) -> str:
    path = request.path
    if PUBLIC_PATH_PREFIX and (path == PUBLIC_PATH_PREFIX or path.startswith(f"{PUBLIC_PATH_PREFIX}/")):
        return path[len(PUBLIC_PATH_PREFIX):] or "/"
    return path


def upstream_url(request: web.Request) -> str:
    path = upstream_path(request)
    query = f"?{request.query_string}" if request.query_string else ""
    if path == "/asr" or path.startswith("/asr/"):
        suffix = path[len("/asr"):] or "/"
        return f"{ASR_UPSTREAM}{suffix}{query}"
    for prefix, base in EXPERIMENT_UPSTREAMS.items():
        if path == prefix or path.startswith(f"{prefix}/"):
            suffix = path[len(prefix):] or "/"
            return f"{base}{suffix}{query}"
    if path == "/agent-health/admin":
        return f"{ADMIN_UPSTREAM}/health"
    base = ADMIN_UPSTREAM if is_admin_path(path) else STREAMLIT_UPSTREAM
    return f"{base}{path}{query}"


def forward_headers(request: web.Request) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP and not key.lower().startswith("sec-websocket-")
    }
    peer = request.remote or ""
    previous = request.headers.get("X-Forwarded-For", "")
    headers["X-Forwarded-For"] = ", ".join(value for value in (previous, peer) if value)
    headers["X-Forwarded-Proto"] = (
        request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip()
        or request.scheme
    )
    headers["X-Forwarded-Host"] = (
        request.headers.get("X-Forwarded-Host", "").split(",", 1)[0].strip()
        or request.host
    )
    # Preserve the public mount point for upstream redirects.  The outer
    # reverse proxy may already have stripped /agent before this gateway sees
    # the request, so the configured prefix is the authoritative fallback.
    headers["X-Forwarded-Prefix"] = (
        request.headers.get("X-Forwarded-Prefix", "").split(",", 1)[0].strip()
        or PUBLIC_PATH_PREFIX
    )
    return headers


def forward_response_headers(upstream_headers) -> CIMultiDict[str]:
    """Preserve repeatable response headers such as Set-Cookie."""
    headers: CIMultiDict[str] = CIMultiDict()
    for key, value in upstream_headers.items():
        if key.lower() not in HOP_BY_HOP:
            headers.add(key, value)
    return headers


async def copy_websocket(source, destination) -> None:
    async for message in source:
        if message.type == WSMsgType.TEXT:
            await destination.send_str(message.data)
        elif message.type == WSMsgType.BINARY:
            await destination.send_bytes(message.data)
        elif message.type == WSMsgType.PING:
            await destination.ping(message.data)
        elif message.type == WSMsgType.PONG:
            await destination.pong(message.data)
        elif message.type == WSMsgType.CLOSE:
            reason = message.extra.encode("utf-8", errors="replace") if message.extra else b""
            await destination.close(code=message.data or 1000, message=reason)
            break
        elif message.type == WSMsgType.ERROR:
            await destination.close(code=1011, message=b"websocket proxy error")
            break
        elif message.type == WSMsgType.CLOSED:
            break


async def websocket_proxy(request: web.Request) -> web.WebSocketResponse:
    protocols = [
        item.strip()
        for item in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
        if item.strip()
    ]
    # Streamlit requires the `streamlit` subprotocol to be acknowledged by
    # the browser-facing socket. Preparing a protocol-less socket leaves the
    # frontend indefinitely on its skeleton screen when accessed over LAN.
    browser = web.WebSocketResponse(
        protocols=protocols,
        autoping=True,
        heartbeat=30,
        max_msg_size=WEBSOCKET_MAX_MESSAGE_SIZE,
    )
    await browser.prepare(request)
    session: ClientSession = request.app["client"]
    headers = forward_headers(request)
    try:
        async with session.ws_connect(
            upstream_url(request), headers=headers, protocols=protocols,
            autoping=True, heartbeat=30,
            max_msg_size=WEBSOCKET_MAX_MESSAGE_SIZE,
        ) as upstream:
            browser_to_upstream = asyncio.create_task(copy_websocket(browser, upstream))
            upstream_to_browser = asyncio.create_task(copy_websocket(upstream, browser))
            done, pending = await asyncio.wait(
                {browser_to_upstream, upstream_to_browser},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
    except Exception:
        LOGGER.exception("WebSocket upstream failed: %s", request.path_qs)
        await browser.close(code=1011, message=b"upstream unavailable")
    return browser


async def http_proxy(request: web.Request) -> web.StreamResponse:
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await websocket_proxy(request)

    session: ClientSession = request.app["client"]
    body: AsyncIterator[bytes] | bytes = request.content.iter_chunked(64 * 1024)
    async with session.request(
        request.method,
        upstream_url(request),
        headers=forward_headers(request),
        data=body,
        allow_redirects=False,
    ) as upstream:
        response = web.StreamResponse(
            status=upstream.status,
            reason=upstream.reason,
            headers=forward_response_headers(upstream.headers),
        )
        await response.prepare(request)
        async for chunk in upstream.content.iter_chunked(64 * 1024):
            await response.write(chunk)
        await response.write_eof()
        return response


def create_app() -> web.Application:
    app = web.Application(client_max_size=25 * 1024**2)

    async def store_session(app: web.Application):
        async with ClientSession(
            timeout=ClientTimeout(total=None, connect=30, sock_read=None)
        ) as session:
            app["client"] = session
            yield

    app.cleanup_ctx.append(store_session)
    app.router.add_route("*", "/{path:.*}", http_proxy)
    return app


def tls_context() -> ssl.SSLContext | None:
    certificate = os.getenv("PHYSICS_GATEWAY_TLS_CERT", "").strip()
    private_key = os.getenv("PHYSICS_GATEWAY_TLS_KEY", "").strip()
    if not certificate and not private_key:
        return None
    if not certificate or not private_key:
        raise RuntimeError("HTTPS 网关必须同时配置证书和私钥")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate, private_key)
    return context


if __name__ == "__main__":
    web.run_app(
        create_app(),
        host=os.getenv("PHYSICS_GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("PHYSICS_GATEWAY_PORT", "8501")),
        ssl_context=tls_context(),
        print=lambda *_: None,
    )
