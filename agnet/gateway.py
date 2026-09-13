from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import ssl
from collections.abc import AsyncIterator

from aiohttp import ClientError, ClientSession, ClientTimeout, ServerTimeoutError, WSMsgType, web
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
REQUEST_MAX_BYTES = max(
    1,
    min(int(os.getenv("PHYSICS_GATEWAY_MAX_REQUEST_MB", "25")), 256),
) * 1024**2
UPSTREAM_CONNECT_TIMEOUT = max(
    1.0,
    min(float(os.getenv("PHYSICS_GATEWAY_CONNECT_TIMEOUT_SECONDS", "10")), 120.0),
)
UPSTREAM_READ_TIMEOUT = max(
    5.0,
    min(float(os.getenv("PHYSICS_GATEWAY_READ_TIMEOUT_SECONDS", "300")), 3600.0),
)


def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    raw = os.getenv("PHYSICS_GATEWAY_TRUSTED_PROXIES", "127.0.0.1/32,::1/128")
    networks = []
    for value in raw.split(","):
        try:
            networks.append(ipaddress.ip_network(value.strip(), strict=False))
        except ValueError:
            LOGGER.warning("Ignoring invalid trusted proxy network: %s", value.strip())
    return tuple(networks)


TRUSTED_PROXY_NETWORKS = _trusted_proxy_networks()
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
    "/experiments/gas-gamma": os.getenv("PHYSICS_GAS_GAMMA_UPSTREAM", "http://127.0.0.1:9402"),
    "/experiments/grating-interference": os.getenv("PHYSICS_GRATING_INTERFERENCE_UPSTREAM", "http://127.0.0.1:9403"),
    "/experiments/light-polarization": os.getenv("PHYSICS_LIGHT_POLARIZATION_UPSTREAM", "http://127.0.0.1:9404"),
    "/experiments/michelson-wavelength": os.getenv("PHYSICS_MICHELSON_WAVELENGTH_UPSTREAM", "http://127.0.0.1:9405"),
}
ADMIN_PATHS = {
    "/admin-login",
    "/admin-logout",
    "/analytics",
    "/identity-roster",
    "/identity-roster/excel",
    "/session-login",
    "/session-logout",
    "/teacher-approvals",
}


def is_admin_path(path: str) -> bool:
    return (
        path in ADMIN_PATHS
        or path.startswith("/identity-roster/")
        or path.startswith("/teacher-approvals/")
    )
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
    forwarding_headers = {
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-prefix",
        "x-forwarded-proto",
    }
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP
        and key.lower() not in forwarding_headers
        and not key.lower().startswith("sec-websocket-")
    }
    peer = _valid_ip(request.remote)
    peer_is_trusted = bool(peer and _ip_in_trusted_networks(peer))
    forwarded_ips = (
        _valid_forwarded_ips(request.headers.get("X-Forwarded-For", ""))
        if peer_is_trusted
        else []
    )
    headers["X-Forwarded-For"] = _canonical_client_ip(peer, forwarded_ips)

    supplied_proto = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
    headers["X-Forwarded-Proto"] = (
        supplied_proto
        if peer_is_trusted and supplied_proto in {"http", "https", "ws", "wss"}
        else request.scheme
    )
    supplied_host = request.headers.get("X-Forwarded-Host", "").split(",", 1)[0].strip()
    headers["X-Forwarded-Host"] = (
        supplied_host
        if peer_is_trusted and _safe_forwarded_host(supplied_host)
        else request.host
    )
    # Preserve the public mount point for upstream redirects.  The outer
    # reverse proxy may already have stripped /agent before this gateway sees
    # the request, so the configured prefix is the authoritative fallback.
    supplied_prefix = request.headers.get("X-Forwarded-Prefix", "").split(",", 1)[0].strip()
    headers["X-Forwarded-Prefix"] = (
        supplied_prefix
        if peer_is_trusted
        and supplied_prefix
        and _safe_forwarded_prefix(supplied_prefix)
        else PUBLIC_PATH_PREFIX
    )
    return headers


def _valid_ip(value: str | None) -> str:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return ""


def _ip_in_trusted_networks(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return any(address.version == network.version and address in network for network in TRUSTED_PROXY_NETWORKS)


def _valid_forwarded_ips(raw_value: str) -> list[str]:
    values = []
    for item in raw_value.split(","):
        parsed = _valid_ip(item)
        if parsed:
            values.append(parsed)
    return values[-32:]


def _canonical_client_ip(peer: str, forwarded_ips: list[str]) -> str:
    chain = [*forwarded_ips, *([peer] if peer else [])]
    while chain and _ip_in_trusted_networks(chain[-1]):
        chain.pop()
    return chain[-1] if chain else (forwarded_ips[0] if forwarded_ips else peer)


def _safe_forwarded_host(value: str) -> bool:
    return bool(value) and len(value) <= 255 and not any(
        character in value for character in "\r\n/\\"
    )


def _safe_forwarded_prefix(value: str) -> bool:
    return (
        bool(value)
        and (
            value.startswith("/")
            and not value.startswith("//")
            and len(value) <= 128
            and all(character.isalnum() or character in "/_-" for character in value)
        )
    )


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


class RequestBodyTooLarge(Exception):
    def __init__(self, actual_size: int):
        super().__init__(f"request body exceeds {REQUEST_MAX_BYTES} bytes")
        self.actual_size = actual_size


async def limited_request_body(request: web.Request) -> AsyncIterator[bytes]:
    total = 0
    async for chunk in request.content.iter_chunked(64 * 1024):
        total += len(chunk)
        if total > REQUEST_MAX_BYTES:
            raise RequestBodyTooLarge(total)
        yield chunk


def _caused_by(error: BaseException, expected_type: type[BaseException]) -> BaseException | None:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, expected_type):
            return current
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return None


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

    content_length = request.content_length
    if content_length is not None and content_length > REQUEST_MAX_BYTES:
        raise web.HTTPRequestEntityTooLarge(
            max_size=REQUEST_MAX_BYTES,
            actual_size=content_length,
        )

    session: ClientSession = request.app["client"]
    response: web.StreamResponse | None = None
    request_body = limited_request_body(request) if request.can_read_body else None
    try:
        async with session.request(
            request.method,
            upstream_url(request),
            headers=forward_headers(request),
            data=request_body,
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
    except Exception as exc:
        oversized = _caused_by(exc, RequestBodyTooLarge)
        if oversized is not None and response is None:
            raise web.HTTPRequestEntityTooLarge(
                max_size=REQUEST_MAX_BYTES,
                actual_size=oversized.actual_size,
            ) from exc
        if response is not None:
            LOGGER.warning("HTTP upstream stream interrupted: %s", request.path_qs)
            response.force_close()
            return response
        if isinstance(exc, (asyncio.TimeoutError, ServerTimeoutError)):
            LOGGER.warning("HTTP upstream timed out: %s", request.path_qs)
            raise web.HTTPGatewayTimeout(text="Upstream service timed out.") from exc
        if isinstance(exc, (ClientError, OSError)):
            LOGGER.warning("HTTP upstream unavailable: %s", request.path_qs)
            raise web.HTTPBadGateway(text="Upstream service is unavailable.") from exc
        raise


def create_app() -> web.Application:
    app = web.Application(client_max_size=REQUEST_MAX_BYTES)

    async def store_session(app: web.Application):
        async with ClientSession(
            timeout=ClientTimeout(
                total=None,
                connect=UPSTREAM_CONNECT_TIMEOUT,
                sock_connect=UPSTREAM_CONNECT_TIMEOUT,
                sock_read=UPSTREAM_READ_TIMEOUT,
            )
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
