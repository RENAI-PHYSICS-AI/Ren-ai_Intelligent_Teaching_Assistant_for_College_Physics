from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from aiohttp import ClientConnectionError, ServerTimeoutError, web
from aiohttp.test_utils import make_mocked_request


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import gateway


def _request_with_peer(headers: dict[str, str], peer: str):
    transport = Mock()
    transport.get_extra_info.side_effect = lambda name, default=None: (
        (peer, 1234) if name == "peername" else default
    )
    return make_mocked_request("GET", "/", headers=headers, transport=transport)


def test_untrusted_client_cannot_spoof_forwarding_headers() -> None:
    request = _request_with_peer(
        {
            "Host": "public.example",
            "Forwarded": "for=attacker;proto=https",
            "X-Forwarded-For": "203.0.113.99",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-Prefix": "/evil",
        },
        "192.0.2.10",
    )

    headers = gateway.forward_headers(request)

    assert "Forwarded" not in headers
    assert headers["X-Forwarded-For"] == "192.0.2.10"
    assert headers["X-Forwarded-Proto"] == "http"
    assert headers["X-Forwarded-Host"] == "public.example"
    assert headers["X-Forwarded-Prefix"] == gateway.PUBLIC_PATH_PREFIX


def test_trusted_proxy_chain_is_reduced_to_canonical_client() -> None:
    request = _request_with_peer(
        {
            "Host": "internal",
            "X-Forwarded-For": "203.0.113.7, 198.51.100.4",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "physics.example",
            "X-Forwarded-Prefix": "/agent",
        },
        "127.0.0.1",
    )

    headers = gateway.forward_headers(request)

    assert headers["X-Forwarded-For"] == "198.51.100.4"
    assert headers["X-Forwarded-Proto"] == "https"
    assert headers["X-Forwarded-Host"] == "physics.example"
    assert headers["X-Forwarded-Prefix"] == "/agent"


def test_trusted_proxy_without_prefix_uses_configured_mount() -> None:
    request = _request_with_peer({"Host": "internal"}, "127.0.0.1")

    with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
        headers = gateway.forward_headers(request)

    assert headers["X-Forwarded-Prefix"] == "/agent"


class _ChunkedContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def iter_chunked(self, _size: int):
        for chunk in self.chunks:
            yield chunk


def test_streamed_request_has_a_cumulative_hard_limit() -> None:
    request = SimpleNamespace(content=_ChunkedContent([b"1234", b"5678"]))

    async def consume() -> None:
        with patch.object(gateway, "REQUEST_MAX_BYTES", 7):
            async for _ in gateway.limited_request_body(request):
                pass

    with pytest.raises(gateway.RequestBodyTooLarge):
        asyncio.run(consume())


class _FailingRequestContext:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def __aenter__(self):
        raise self.error

    async def __aexit__(self, *_args):
        return False


class _FailingSession:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def request(self, *_args, **_kwargs):
        return _FailingRequestContext(self.error)


def _proxy_request(error: Exception):
    return SimpleNamespace(
        headers={},
        content_length=0,
        can_read_body=False,
        content=_ChunkedContent([]),
        app={"client": _FailingSession(error)},
        method="GET",
        path="/health",
        query_string="",
        remote="192.0.2.1",
        scheme="http",
        host="physics.example",
        path_qs="/health",
    )


def test_upstream_timeout_and_connection_error_have_stable_gateway_statuses() -> None:
    with pytest.raises(web.HTTPGatewayTimeout):
        asyncio.run(gateway.http_proxy(_proxy_request(ServerTimeoutError())))
    with pytest.raises(web.HTTPBadGateway):
        asyncio.run(
            gateway.http_proxy(_proxy_request(ClientConnectionError("offline")))
        )
