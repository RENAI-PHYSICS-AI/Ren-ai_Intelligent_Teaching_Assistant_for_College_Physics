from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse


LOGGER = logging.getLogger("physics_asr")
APP_DIR = Path(__file__).resolve().parent
SAMPLE_RATE = 16_000
MAX_CHUNK_BYTES = 256 * 1024


def integer_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))


def boolean_setting(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def model_directory() -> Path:
    configured = os.getenv("PHYSICS_ASR_MODEL_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (APP_DIR / "runtime" / "asr" / "paraformer-zh-streaming").resolve()


def model_paths() -> tuple[Path, Path, Path]:
    root = model_directory()
    return root / "tokens.txt", root / "encoder.int8.onnx", root / "decoder.int8.onnx"


def build_recognizer():
    import sherpa_onnx

    tokens, encoder, decoder = model_paths()
    missing = [str(path) for path in (tokens, encoder, decoder) if not path.is_file()]
    if missing:
        raise FileNotFoundError("Paraformer 模型文件缺失：" + "、".join(missing))
    return sherpa_onnx.OnlineRecognizer.from_paraformer(
        tokens=str(tokens),
        encoder=str(encoder),
        decoder=str(decoder),
        num_threads=integer_setting("PHYSICS_ASR_THREADS", 4, 1, 64),
        sample_rate=SAMPLE_RATE,
        feature_dim=80,
        # The browser explicitly sends ``finish`` when the learner stops.
        # Avoid resetting Paraformer at pauses inside a single question; doing
        # so noticeably harms mixed Chinese/English physics terms.
        enable_endpoint_detection=False,
        rule1_min_trailing_silence=2.4,
        rule2_min_trailing_silence=1.2,
        rule3_min_utterance_length=20.0,
        decoding_method="greedy_search",
        provider="cpu",
    )


PHYSICS_TERM_FIXES = {
    "洛伦兹利": "洛伦兹力",
    "落伦兹力": "洛伦兹力",
    "楞次定率": "楞次定律",
    "麦克斯伟": "麦克斯韦",
    "德布罗义": "德布罗意",
    "简协振动": "简谐振动",
    "波尔半经": "玻尔半径",
}


def normalize_physics_terms(text: str) -> str:
    normalized = text.strip()
    for incorrect, correct in PHYSICS_TERM_FIXES.items():
        normalized = normalized.replace(incorrect, correct)
    return normalized


def join_segments(segments: list[str], current: str = "") -> str:
    parts = [normalize_physics_terms(item) for item in [*segments, current] if item.strip()]
    if not parts:
        return ""
    result = parts[0]
    for part in parts[1:]:
        needs_space = (
            result[-1:].isascii() and result[-1:].isalnum()
            and part[:1].isascii() and part[:1].isalnum()
        )
        result += (" " if needs_space else "") + part
    return result


class DecodeScheduler:
    def __init__(self, recognizer) -> None:
        self.recognizer = recognizer
        self.queue: asyncio.Queue[tuple[object, asyncio.Future]] = asyncio.Queue(maxsize=64)
        self.max_batch_size = integer_setting("PHYSICS_ASR_BATCH_SIZE", 4, 1, 16)
        self.max_wait_seconds = integer_setting("PHYSICS_ASR_BATCH_WAIT_MS", 8, 0, 100) / 1000
        self.task: asyncio.Task | None = None

    async def start(self) -> None:
        self.task = asyncio.create_task(self._consume(), name="paraformer-decode-batcher")

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        while not self.queue.empty():
            try:
                _, future = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not future.done():
                future.cancel()
            self.queue.task_done()

    async def decode(self, stream) -> None:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self.queue.put((stream, future))
        await future

    async def _consume(self) -> None:
        while True:
            first = await self.queue.get()
            batch = [first]
            deadline = asyncio.get_running_loop().time() + self.max_wait_seconds
            while len(batch) < self.max_batch_size:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.queue.get(), remaining))
                except asyncio.TimeoutError:
                    break
            try:
                await asyncio.to_thread(
                    self.recognizer.decode_streams,
                    [stream for stream, _ in batch],
                )
            except asyncio.CancelledError:
                for _, future in batch:
                    if not future.done():
                        future.cancel()
                raise
            except Exception as exc:
                for _, future in batch:
                    if not future.done():
                        future.set_exception(exc)
            else:
                for _, future in batch:
                    if not future.done():
                        future.set_result(None)
            finally:
                for _ in batch:
                    self.queue.task_done()


class ServiceState:
    recognizer = None
    scheduler: DecodeScheduler | None = None
    load_error = "服务尚未初始化"
    active_connections = 0
    connection_lock: asyncio.Lock | None = None


STATE = ServiceState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    STATE.recognizer = None
    STATE.scheduler = None
    STATE.active_connections = 0
    STATE.connection_lock = asyncio.Lock()
    try:
        STATE.recognizer = await asyncio.to_thread(build_recognizer)
        STATE.scheduler = DecodeScheduler(STATE.recognizer)
        await STATE.scheduler.start()
        STATE.load_error = ""
        LOGGER.info("Paraformer 流式识别模型加载完成：%s", model_directory())
    except Exception as exc:
        STATE.load_error = str(exc)
        LOGGER.exception("Paraformer 流式识别模型加载失败")
    try:
        yield
    finally:
        if STATE.scheduler is not None:
            await STATE.scheduler.close()
        STATE.scheduler = None
        STATE.recognizer = None


app = FastAPI(title="大学物理智能助教语音识别", lifespan=lifespan)


@app.get("/health")
async def health():
    ready = (
        STATE.recognizer is not None
        and STATE.scheduler is not None
        and STATE.scheduler.task is not None
        and not STATE.scheduler.task.done()
    )
    payload = {
        "ok": ready,
        "engine": "sherpa-onnx",
        "model": "Paraformer-zh-streaming INT8",
        "sample_rate": SAMPLE_RATE,
        "active_connections": STATE.active_connections,
    }
    if not ready:
        payload["error"] = "Paraformer 语音模型尚未就绪"
    return JSONResponse(payload, status_code=200 if ready else 503)


def same_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin", "").strip()
    if not origin:
        return boolean_setting("PHYSICS_ASR_ALLOW_MISSING_ORIGIN", False)

    def origin_identity(value: str, fallback_scheme: str = "") -> tuple[str, str, int] | None:
        try:
            parsed = urlsplit(value if "://" in value else f"//{value}")
            scheme = (parsed.scheme or fallback_scheme).lower()
            hostname = (parsed.hostname or "").lower()
            if scheme not in {"http", "https"} or not hostname:
                return None
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError:
            return None
        return scheme, hostname, port

    actual_origin = origin_identity(origin)
    if actual_origin is None:
        return False

    # The outer reverse proxy may forward ``Host`` without its non-standard
    # public port.  The configured public URL is authoritative in that case.
    configured_public_url = os.getenv("PHYSICS_PUBLIC_BASE_URL", "").strip()
    configured_origin = origin_identity(configured_public_url) if configured_public_url else None
    if configured_origin is not None and actual_origin == configured_origin:
        return True

    forwarded_host = websocket.headers.get("x-forwarded-host") or websocket.headers.get("host", "")
    forwarded_proto = (
        websocket.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
        or "http"
    )
    request_origin = origin_identity(forwarded_host, fallback_scheme=forwarded_proto)
    return actual_origin == request_origin


async def acquire_connection() -> bool:
    assert STATE.connection_lock is not None
    maximum = integer_setting("PHYSICS_ASR_MAX_CONNECTIONS", 4, 1, 32)
    async with STATE.connection_lock:
        if STATE.active_connections >= maximum:
            return False
        STATE.active_connections += 1
        return True


async def release_connection() -> None:
    assert STATE.connection_lock is not None
    async with STATE.connection_lock:
        STATE.active_connections = max(0, STATE.active_connections - 1)


async def decode_ready(stream) -> None:
    assert STATE.recognizer is not None and STATE.scheduler is not None
    while STATE.recognizer.is_ready(stream):
        await STATE.scheduler.decode(stream)


async def finalize_stream(stream) -> str:
    assert STATE.recognizer is not None
    padding = np.zeros(int(SAMPLE_RATE * 0.35), dtype=np.float32)
    stream.accept_waveform(SAMPLE_RATE, padding)
    stream.input_finished()
    await decode_ready(stream)
    return STATE.recognizer.get_result(stream)


@app.websocket("/ws")
async def recognize(websocket: WebSocket) -> None:
    await websocket.accept()
    if STATE.recognizer is None or STATE.scheduler is None:
        await websocket.send_json({"type": "error", "message": "语音识别服务尚未就绪"})
        await websocket.close(code=1013)
        return
    if not same_origin(websocket):
        await websocket.send_json({"type": "error", "message": "只允许同源语音连接"})
        await websocket.close(code=1008)
        return
    if not await acquire_connection():
        await websocket.send_json({"type": "error", "message": "语音识别服务繁忙，请稍后重试"})
        await websocket.close(code=1013)
        return

    try:
        stream = STATE.recognizer.create_stream()
        committed: list[str] = []
        last_sent = ""
        total_samples = 0
        maximum_seconds = integer_setting("PHYSICS_ASR_MAX_AUDIO_SECONDS", 180, 10, 900)
        maximum_samples = maximum_seconds * SAMPLE_RATE
        idle_timeout = integer_setting("PHYSICS_ASR_IDLE_TIMEOUT_SECONDS", 20, 5, 120)
        loop = asyncio.get_running_loop()
        connected_at = loop.time()
        hard_deadline = connected_at + maximum_seconds + 30
        started = False
        await websocket.send_json({
            "type": "ready", "sample_rate": SAMPLE_RATE,
            "model": "Paraformer-zh-streaming INT8",
        })
        while True:
            remaining = hard_deadline - loop.time()
            if remaining <= 0:
                await websocket.send_json({"type": "error", "message": "语音连接已超过最长时间"})
                await websocket.close(code=1008)
                return
            receive_timeout = min(float(idle_timeout), remaining, 10.0 if not started else remaining)
            try:
                message = await asyncio.wait_for(websocket.receive(), receive_timeout)
            except asyncio.TimeoutError:
                message_text = "等待录音开始超时" if not started else "语音连接空闲超时"
                await websocket.send_json({"type": "error", "message": message_text})
                await websocket.close(code=1008)
                return
            if message.get("type") == "websocket.disconnect":
                return
            text_message = message.get("text")
            if text_message is not None:
                if len(text_message.encode("utf-8")) > 4096:
                    await websocket.send_json({"type": "error", "message": "控制消息过大"})
                    await websocket.close(code=1009)
                    return
                if text_message == "Done":
                    break
                try:
                    command = json.loads(text_message)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "无效的控制消息"})
                    continue
                if not isinstance(command, dict):
                    await websocket.send_json({"type": "error", "message": "控制消息必须是对象"})
                    continue
                command_type = command.get("type")
                if command_type == "start":
                    if started:
                        await websocket.send_json({"type": "error", "message": "录音已经开始"})
                        continue
                    if command.get("sample_rate") != SAMPLE_RATE or command.get("format") != "pcm_f32le":
                        await websocket.send_json({"type": "error", "message": "仅支持 16 kHz Float32 单声道 PCM"})
                        await websocket.close(code=1003)
                        return
                    started = True
                elif command_type in {"finish", "stop"}:
                    break
                elif command_type == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json({"type": "error", "message": "不支持的控制命令"})
                continue

            audio_bytes = message.get("bytes")
            if not audio_bytes:
                continue
            if not started:
                await websocket.send_json({"type": "error", "message": "请先发送 start 控制消息"})
                continue
            if len(audio_bytes) > MAX_CHUNK_BYTES or len(audio_bytes) % 4:
                await websocket.send_json({"type": "error", "message": "音频分块格式无效"})
                continue
            samples = np.frombuffer(audio_bytes, dtype="<f4")
            if not np.isfinite(samples).all():
                await websocket.send_json({"type": "error", "message": "音频包含无效采样值"})
                continue
            total_samples += samples.size
            if total_samples > maximum_samples:
                await websocket.send_json({"type": "error", "message": "单次录音时间已达上限"})
                break
            stream.accept_waveform(SAMPLE_RATE, np.clip(samples, -1.0, 1.0))
            await decode_ready(stream)
            current = STATE.recognizer.get_result(stream)
            aggregate = join_segments(committed, current)
            endpoint = STATE.recognizer.is_endpoint(stream)
            if endpoint:
                normalized = normalize_physics_terms(current)
                if normalized:
                    committed.append(normalized)
                STATE.recognizer.reset(stream)
                aggregate = join_segments(committed)
            if aggregate != last_sent:
                await websocket.send_json({
                    "type": "partial", "text": aggregate, "is_endpoint": endpoint,
                })
                last_sent = aggregate

        tail = await finalize_stream(stream)
        final_text = join_segments(committed, tail)
        await websocket.send_json({
            "type": "final", "id": uuid.uuid4().hex, "text": final_text,
        })
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        pass
    except Exception:
        LOGGER.exception("语音识别连接异常")
        try:
            await websocket.send_json({"type": "error", "message": "语音识别发生内部错误"})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        await release_connection()
