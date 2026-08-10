from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_DIR = Path(__file__).resolve().parent
MODEL_REVISION = "8e40c43232a1c5c66c82111efc5820d3accca11b"
MODEL_REPOSITORY = "csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en"
MODEL_BASE_URL = (
    f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}"
)
MODEL_FILES = {
    "encoder.int8.onnx": {
        "source": "encoder.int8.onnx",
        "sha256": "81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a",
        "size": 165_462_184,
    },
    "decoder.int8.onnx": {
        "source": "decoder.int8.onnx",
        "sha256": "f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f",
        "size": 71_664_561,
    },
    "tokens.txt": {
        "source": "tokens.txt",
        "sha256": "59aba8873a2ed1e122c25fee421e25f283b63290efbde85c1f01a853d83cb6e6",
        "size": 75_756,
    },
}


def default_model_dir() -> Path:
    configured = os.getenv("PHYSICS_ASR_MODEL_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return APP_DIR / "runtime" / "asr" / "paraformer-zh-streaming"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_file(path: Path, expected: dict[str, object]) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == int(expected["size"])
        and file_sha256(path) == str(expected["sha256"])
    )


def download_file(url: str, destination: Path, expected: dict[str, object]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.download")
    expected_size = int(expected["size"])
    if partial.is_file() and partial.stat().st_size > expected_size:
        partial.unlink()
    last_error: Exception | None = None
    for attempt in range(1, 9):
        try:
            offset = partial.stat().st_size if partial.is_file() else 0
            headers = {"User-Agent": "physics-assistant-asr/1.0"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = Request(url, headers=headers)
            with urlopen(request, timeout=90) as response:
                resumed = offset > 0 and getattr(response, "status", 200) == 206
                if offset and not resumed:
                    offset = 0
                mode = "ab" if resumed else "wb"
                with partial.open(mode) as temporary:
                    received = offset
                    last_percent = -1
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        temporary.write(chunk)
                        received += len(chunk)
                        percent = int(received * 100 / max(expected_size, 1))
                        if percent >= last_percent + 10:
                            print(f"  {destination.name}: {percent}%", flush=True)
                            last_percent = percent
            if not valid_file(partial, expected):
                raise RuntimeError(f"{destination.name} 的大小或 SHA-256 校验失败")
            os.replace(partial, destination)
            return
        except (HTTPError, URLError, OSError, RuntimeError) as exc:
            last_error = exc
            if partial.is_file() and partial.stat().st_size == expected_size:
                if valid_file(partial, expected):
                    os.replace(partial, destination)
                    return
                partial.unlink()
            if attempt < 8:
                print(f"  下载中断，准备断点续传（{attempt}/8）：{exc}", flush=True)
                time.sleep(min(attempt * 2, 10))
    raise RuntimeError(f"下载 {destination.name} 失败：{last_error}")


def ensure_model(model_dir: Path) -> None:
    model_dir = model_dir.resolve()
    model_dir.mkdir(parents=True, exist_ok=True)
    for filename, expected in MODEL_FILES.items():
        destination = model_dir / filename
        if valid_file(destination, expected):
            print(f"已存在并通过校验：{destination}")
            continue
        source_name = str(expected["source"])
        print(f"正在下载 {filename}（INT8）……")
        download_file(f"{MODEL_BASE_URL}/{source_name}", destination, expected)
        print(f"下载完成：{destination}")

    metadata = model_dir / "MODEL_SOURCE.txt"
    metadata.write_text(
        "Paraformer-zh-streaming INT8\n"
        f"Sherpa-ONNX model: https://huggingface.co/{MODEL_REPOSITORY}\n"
        "Converted from: https://www.modelscope.cn/models/damo/"
        "speech_paraformer_asr_nat-zh-cn-16k-common-vocab8404-online\n"
        f"Revision: {MODEL_REVISION}\n"
        "License: Apache-2.0\n",
        encoding="utf-8",
    )
    print(f"Paraformer 流式模型已就绪：{model_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="下载并校验 Paraformer 流式 INT8 模型")
    parser.add_argument("--model-dir", type=Path, default=default_model_dir())
    parser.add_argument("--check", action="store_true", help="仅检查，不下载")
    args = parser.parse_args()
    if args.check:
        missing = [
            filename for filename, expected in MODEL_FILES.items()
            if not valid_file(args.model_dir / filename, expected)
        ]
        if missing:
            print("缺少或校验失败：" + "、".join(missing), file=sys.stderr)
            return 1
        print(f"模型文件校验通过：{args.model_dir.resolve()}")
        return 0
    ensure_model(args.model_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
