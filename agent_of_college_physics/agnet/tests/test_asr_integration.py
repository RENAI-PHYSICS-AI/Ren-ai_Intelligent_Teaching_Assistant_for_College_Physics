from __future__ import annotations

import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import asr_service
import gateway


class AsrTextTests(unittest.TestCase):
    def test_physics_term_normalization(self) -> None:
        self.assertEqual(
            asr_service.normalize_physics_terms("落伦兹力和简协振动"),
            "洛伦兹力和简谐振动",
        )

    def test_segment_joining_preserves_chinese_and_spaces_english(self) -> None:
        self.assertEqual(asr_service.join_segments(["大学", "物理"]), "大学物理")
        self.assertEqual(asr_service.join_segments(["hello", "world"]), "hello world")
        self.assertEqual(asr_service.join_segments(["洛伦兹利", "方向"]), "洛伦兹力方向")


class GatewayRoutingTests(unittest.TestCase):
    def test_asr_health_route_strips_public_prefix(self) -> None:
        request = SimpleNamespace(path="/asr/health", query_string="")
        self.assertEqual(gateway.upstream_url(request), f"{gateway.ASR_UPSTREAM}/health")

    def test_asr_websocket_route_keeps_query(self) -> None:
        request = SimpleNamespace(path="/asr/ws", query_string="attempt=7")
        self.assertEqual(
            gateway.upstream_url(request),
            f"{gateway.ASR_UPSTREAM}/ws?attempt=7",
        )

    def test_https_gateway_strips_public_agent_prefix(self) -> None:
        request = SimpleNamespace(path="/agent/asr/health", query_string="")
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(gateway.upstream_url(request), f"{gateway.ASR_UPSTREAM}/health")


class VoiceInputLayoutTests(unittest.TestCase):
    def test_microphone_portal_is_inserted_before_chat_submit(self) -> None:
        source = (APP_DIR / "voice_input.py").read_text(encoding="utf-8")
        self.assertIn("actions.insertBefore(button, submit)", source)
        self.assertIn('[data-testid="stChatInputSubmitButton"]', source)
        self.assertNotIn("const root = component.parentElement", source)

    def test_microphone_portal_replaces_previous_controller(self) -> None:
        source = (APP_DIR / "voice_input.py").read_text(encoding="utf-8")
        self.assertIn("window[controllerKey] = {instanceId, dispose}", source)
        self.assertIn("previousController.dispose()", source)
        self.assertIn("if (disposed) return", source)
        self.assertIn("return dispose", source)
        self.assertLess(
            source.index("previousController.dispose()"),
            source.index("const button = document.createElement('button')"),
        )
        for cleanup in (
            "portalObserver.disconnect()",
            "window.cancelAnimationFrame(portalFrame)",
            "recorderNode.port.onmessage = null",
            "button.remove()",
            "popover.remove()",
        ):
            self.assertIn(cleanup, source)

    def test_disposed_audio_start_releases_acquired_microphone(self) -> None:
        source = (APP_DIR / "voice_input.py").read_text(encoding="utf-8")
        self.assertIn("const acquiredStream = await navigator.mediaDevices.getUserMedia", source)
        self.assertIn("acquiredStream.getTracks().forEach((track) => track.stop())", source)
        self.assertGreaterEqual(source.count("if (disposed)"), 8)
        self.assertIn("if (data.disabled || disposed) return", source)
        self.assertIn("if (disposed || !recording || stopping) return", source)

    def test_legacy_microphones_are_retired_without_reinsertion(self) -> None:
        source = (APP_DIR / "voice_input.py").read_text(encoding="utf-8")
        self.assertIn("physics-voice-retired-portals", source)
        self.assertIn("retirementBin.appendChild(node)", source)
        self.assertIn("retireDuplicatePortals()", source)
        self.assertIn("&& !duplicateVisible", source)


class OriginTests(unittest.TestCase):
    def test_same_origin_uses_forwarded_public_host(self) -> None:
        websocket = SimpleNamespace(
            headers={
                "origin": "https://physics.example.edu",
                "x-forwarded-host": "physics.example.edu",
                "x-forwarded-proto": "https",
                "host": "127.0.0.1:8604",
            }
        )
        self.assertTrue(asr_service.same_origin(websocket))

    def test_cross_origin_is_rejected(self) -> None:
        websocket = SimpleNamespace(
            headers={
                "origin": "https://untrusted.example",
                "x-forwarded-host": "physics.example.edu",
            }
        )
        self.assertFalse(asr_service.same_origin(websocket))

    def test_configured_public_origin_keeps_nonstandard_proxy_port(self) -> None:
        websocket = SimpleNamespace(
            headers={
                "origin": "http://192.168.222.147:1234",
                "x-forwarded-host": "192.168.222.147",
                "x-forwarded-proto": "http",
                "host": "127.0.0.1:8604",
            }
        )
        with patch.dict(
            "os.environ",
            {"PHYSICS_PUBLIC_BASE_URL": "http://192.168.222.147:1234/agent/"},
        ):
            self.assertTrue(asr_service.same_origin(websocket))

    def test_missing_origin_is_rejected_by_default(self) -> None:
        websocket = SimpleNamespace(headers={"host": "127.0.0.1:8604"})
        self.assertFalse(asr_service.same_origin(websocket))


class SchedulerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_resolves_waiting_decoder(self) -> None:
        class SlowRecognizer:
            @staticmethod
            def decode_streams(_streams) -> None:
                time.sleep(0.1)

        scheduler = asr_service.DecodeScheduler(SlowRecognizer())
        await scheduler.start()
        waiter = asyncio.create_task(scheduler.decode(object()))
        await asyncio.sleep(0.02)
        await scheduler.close()
        self.assertTrue(waiter.done())
        with self.assertRaises(asyncio.CancelledError):
            await waiter


if __name__ == "__main__":
    unittest.main()
