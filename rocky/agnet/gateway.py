from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


STREAMLIT_UPSTREAM = os.getenv("PHYSICS_STREAMLIT_UPSTREAM", "http://127.0.0.1:8502")
ADMIN_UPSTREAM = os.getenv("PHYSICS_ADMIN_UPSTREAM", "http://127.0.0.1:8603")
ADMIN_PATHS = {
    "/admin-login",
    "/analytics",
    "/identity-roster",
    "/identity-roster/excel",
}
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


def upstream_url(request: web.Request) -> str:
    if request.path == "/rocky-health/admin":
        return f"{ADMIN_UPSTREAM}/health"
    base = ADMIN_UPSTREAM if request.path in ADMIN_PATHS else STREAMLIT_UPSTREAM
    return f"{base}{request.rel_url}"


def forward_headers(request: web.Request) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP and not key.lower().startswith("sec-websocket-")
    }
    peer = request.remote or ""
    previous = request.headers.get("X-Forwarded-For", "")
    headers["X-Forwarded-For"] = ", ".join(value for value in (previous, peer) if value)
    headers["X-Forwarded-Proto"] = request.scheme
    headers["X-Forwarded-Host"] = request.host
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
        elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
            break


async def websocket_proxy(request: web.Request) -> web.WebSocketResponse:
    browser = web.WebSocketResponse(autoping=True, heartbeat=30)
    await browser.prepare(request)
    session: ClientSession = request.app["client"]
    headers = forward_headers(request)
    protocols = [item.strip() for item in request.headers.get("Sec-WebSocket-Protocol", "").split(",") if item.strip()]
    try:
        async with session.ws_connect(
            upstream_url(request), headers=headers, protocols=protocols, autoping=True, heartbeat=30
        ) as upstream:
            browser_to_upstream = asyncio.create_task(copy_websocket(browser, upstream))
            upstream_to_browser = asyncio.create_task(copy_websocket(upstream, browser))
            done, pending = await asyncio.wait(
                {browser_to_upstream, upstream_to_browser}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
    except Exception:
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
        headers = {key: value for key, value in upstream.headers.items() if key.lower() not in HOP_BY_HOP}
        response = web.StreamResponse(status=upstream.status, reason=upstream.reason, headers=headers)
        await response.prepare(request)
        async for chunk in upstream.content.iter_chunked(64 * 1024):
            await response.write(chunk)
        await response.write_eof()
        return response


def create_app() -> web.Application:
    app = web.Application(client_max_size=25 * 1024**2)

    async def store_session(app: web.Application):
        async with ClientSession(timeout=ClientTimeout(total=None, connect=30, sock_read=None)) as session:
            app["client"] = session
            yield

    app.cleanup_ctx.append(store_session)
    app.router.add_route("*", "/{path:.*}", http_proxy)
    return app


if __name__ == "__main__":
    web.run_app(
        create_app(),
        host=os.getenv("PHYSICS_GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("PHYSICS_GATEWAY_PORT", "8501")),
        print=lambda *_: None,
    )
