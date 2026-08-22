from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

import streamlit as st

from config import APP_DIR


EXPERIMENT_ROOT = APP_DIR / "experiments"
RUNTIME_DIR = APP_DIR / "runtime" / "experiments"


@dataclass(frozen=True)
class ExperimentService:
    key: str
    title: str
    project_dir: Path
    web_path: Path
    port_env: str
    default_port: int
    julia_host_env: str
    julia_port_env: str
    julia_proxy_env: str
    ready_event: str
    failed_event: str
    identity_marker: str
    root_marker: str
    height: int


LISSAJOUS = ExperimentService(
    key="lissajous",
    title="李萨如图形综合实验",
    project_dir=EXPERIMENT_ROOT / "lissajous",
    web_path=EXPERIMENT_ROOT / "lissajous" / "web.jl",
    port_env="PHYSICS_LISSAJOUS_PORT",
    default_port=9384,
    julia_host_env="LISSAJOUS_WEB_HOST",
    julia_port_env="LISSAJOUS_WEB_PORT",
    julia_proxy_env="LISSAJOUS_WEB_PROXY_URL",
    ready_event="lissajous-wgl-ready",
    failed_event="lissajous-wgl-failed",
    identity_marker="physics-experiment:lissajous",
    root_marker="李萨如图形",
    height=800,
)

SOUND_SPEED = ExperimentService(
    key="sound_speed",
    title="声速四种测量方法综合实验",
    project_dir=EXPERIMENT_ROOT / "sound_speed",
    web_path=EXPERIMENT_ROOT / "sound_speed" / "web.jl",
    port_env="PHYSICS_SOUND_SPEED_PORT",
    default_port=9385,
    julia_host_env="SOUND_SPEED_WEB_HOST",
    julia_port_env="SOUND_SPEED_WEB_PORT",
    julia_proxy_env="SOUND_SPEED_WEB_PROXY_URL",
    ready_event="sound-speed-wgl-ready",
    failed_event="sound-speed-wgl-failed",
    identity_marker="physics-experiment:sound-speed",
    root_marker="声速测量",
    height=740,
)

ELECTRON_EM = ExperimentService(
    key="electron_em",
    title="电子荷质比可视化实验",
    project_dir=EXPERIMENT_ROOT / "electron_em",
    web_path=EXPERIMENT_ROOT / "electron_em" / "web.jl",
    port_env="PHYSICS_ELECTRON_EM_PORT",
    default_port=9386,
    julia_host_env="ELECTRON_EM_WEB_HOST",
    julia_port_env="ELECTRON_EM_WEB_PORT",
    julia_proxy_env="ELECTRON_EM_WEB_PROXY_URL",
    ready_event="electron-em-wgl-ready",
    failed_event="electron-em-wgl-failed",
    identity_marker="physics-experiment:electron-em",
    root_marker="电子荷质比",
    height=740,
)

PHOTOELECTRIC = ExperimentService(
    key="photoelectric",
    title="光电效应可视化实验",
    project_dir=EXPERIMENT_ROOT / "photoelectric",
    web_path=EXPERIMENT_ROOT / "photoelectric" / "web.jl",
    port_env="PHYSICS_PHOTOELECTRIC_PORT",
    default_port=9387,
    julia_host_env="PHOTOELECTRIC_WEB_HOST",
    julia_port_env="PHOTOELECTRIC_WEB_PORT",
    julia_proxy_env="PHOTOELECTRIC_WEB_PROXY_URL",
    ready_event="photoelectric-wgl-ready",
    failed_event="photoelectric-wgl-failed",
    identity_marker="physics-experiment:photoelectric",
    root_marker="光电效应",
    height=740,
)

SERVICES = {
    service.key: service
    for service in (LISSAJOUS, SOUND_SPEED, ELECTRON_EM, PHOTOELECTRIC)
}
_processes: dict[str, subprocess.Popen] = {}
_logs: dict[str, IO[str]] = {}
_locks = {key: threading.Lock() for key in SERVICES}


def service_port(service: ExperimentService) -> int:
    raw_value = os.getenv(service.port_env, str(service.default_port)).strip()
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{service.port_env} 必须是有效端口号。") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{service.port_env} 必须位于 1 到 65535 之间。")
    return port


def service_proxy_url(service: ExperimentService) -> str:
    """Return the browser-visible Bonito base URL for this experiment."""
    public_base = os.getenv("PHYSICS_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not public_base:
        return "."
    slug = service.key.replace("_", "-")
    return f"{public_base}/experiments/{slug}/"


def public_path_prefix() -> str:
    """Return the path portion used by a same-origin reverse-proxy deployment."""
    public_base = os.getenv("PHYSICS_PUBLIC_BASE_URL", "").strip()
    if not public_base:
        return ""
    parsed = urlsplit(public_base)
    path = parsed.path if parsed.scheme or parsed.netloc else public_base
    normalized = "/" + path.strip("/")
    return "" if normalized == "/" else normalized


def service_browser_path(service: ExperimentService, route: str = "/") -> str:
    """Build the iframe path while preserving an outer proxy prefix such as /agent."""
    slug = service.key.replace("_", "-")
    normalized_route = "/" + route.lstrip("/")
    return f"{public_path_prefix()}/experiments/{slug}{normalized_route}"


def service_ready(service: ExperimentService, timeout: float = 0.45) -> bool:
    port = service_port(service)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            pass
    except OSError:
        return False

    # Verify the process identity as well as the port. The root-page fallback
    # keeps compatibility with an already-running pre-healthcheck experiment.
    markers = (
        ("/__physics_health__", service.identity_marker),
        ("/", service.root_marker),
    )
    for path, marker in markers:
        try:
            with urlopen(f"http://127.0.0.1:{port}{path}", timeout=max(timeout, 0.8)) as response:
                body = response.read(512_000).decode("utf-8", errors="ignore")
            if marker in body:
                return True
        except (HTTPError, URLError, OSError, TimeoutError):
            continue
    return False


def _julia_command(service: ExperimentService) -> list[str]:
    julia = os.getenv("PHYSICS_JULIA_EXE", "").strip() or shutil.which("julia")
    if not julia:
        raise FileNotFoundError("未找到 Julia。请先安装 Julia 1.10，并确认 julia 命令可用。")
    command = [
        julia,
        f"--project={service.project_dir}",
        str(service.web_path),
    ]
    if os.getenv("PHYSICS_EXPERIMENT_INSTANTIATE", "false").lower() not in {
        "1",
        "true",
        "yes",
    }:
        command.append("--no-instantiate")
    return command


def _log_tail(service: ExperimentService, limit: int = 1800) -> str:
    path = RUNTIME_DIR / f"{service.key}.log"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:].strip()
    except OSError:
        return ""


def launch_service(service: ExperimentService) -> subprocess.Popen | None:
    if service_ready(service):
        return _processes.get(service.key)
    process = _processes.get(service.key)
    if process is not None and process.poll() is None:
        return process
    if not service.web_path.exists() or not (service.project_dir / "Project.toml").exists():
        raise FileNotFoundError(f"实验文件不完整：{service.project_dir}")

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    old_log = _logs.pop(service.key, None)
    if old_log is not None:
        old_log.close()
    log_handle = (RUNTIME_DIR / f"{service.key}.log").open(
        "a", encoding="utf-8", buffering=1
    )
    environment = os.environ.copy()
    # Experiments are private upstreams. Browsers reach them only through the
    # same-origin /experiments/... routes on the main 8501 gateway.
    environment[service.julia_host_env] = "127.0.0.1"
    environment[service.julia_port_env] = str(service_port(service))
    environment[service.julia_proxy_env] = service_proxy_url(service)

    creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    creation_flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        _julia_command(service),
        cwd=service.project_dir,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
    )
    _logs[service.key] = log_handle
    _processes[service.key] = process
    return process


def ensure_service(service: ExperimentService, timeout: float = 90.0) -> None:
    with _locks[service.key]:
        process = launch_service(service)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if service_ready(service):
                return
            if process is not None and process.poll() is not None:
                detail = _log_tail(service)
                suffix = f"\n\n日志末尾：\n{detail}" if detail else ""
                raise RuntimeError(f"{service.title}启动失败。{suffix}")
            time.sleep(0.4)
        raise TimeoutError(f"{service.title}启动超时，请稍后重试。")


def _stop_managed_services() -> None:
    for process in _processes.values():
        if process.poll() is None:
            process.terminate()
    for handle in _logs.values():
        try:
            handle.close()
        except OSError:
            pass


atexit.register(_stop_managed_services)


def render_experiment_frame(
    service: ExperimentService,
    route: str = "/",
    title: str | None = None,
) -> None:
    settings = json.dumps(
        {
            "path": service_browser_path(service, route),
            "title": title or service.title,
            "readyEvent": service.ready_event,
            "failedEvent": service.failed_event,
        },
        ensure_ascii=False,
    )
    st.iframe(
        _EMBED_HTML.replace("__SETTINGS__", settings),
        height=service.height,
        width="stretch",
    )


def _start_and_render(
    service: ExperimentService,
    route: str = "/",
    title: str | None = None,
) -> None:
    try:
        if not service_ready(service):
            with st.spinner(f"正在启动{service.title}，首次加载可能需要一些时间……"):
                ensure_service(service)
        render_experiment_frame(service, route, title)
    except Exception as exc:
        st.error(str(exc))
        st.caption(
            "实验依赖 Julia 1.10、Bonito 和 WGLMakie。首次部署可按项目说明完成依赖初始化后重试。"
        )


def render_experiment_hub() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width:1280px}
        .experiment-intro {max-width:940px;margin:.15rem auto .7rem;text-align:center}
        .experiment-intro h2 {font-size:1.55rem;margin:.1rem 0 .25rem;color:inherit}
        .experiment-intro p {margin:0;opacity:.72;line-height:1.65}
        .experiment-summary {margin:.65rem 0 .45rem;padding:.75rem 1rem;border-radius:12px;
          border:1px solid rgba(112,137,158,.25);background:rgba(87,119,146,.07)}
        .experiment-summary h3 {font-size:1.08rem;margin:0 0 .2rem;color:inherit}
        .experiment-summary p {font-size:.9rem;margin:0;opacity:.76;line-height:1.55}
        </style>
        <div class="experiment-intro">
          <h2>可视化实验</h2>
          <p>调节实验参数，实时观察物理量、波形与轨迹之间的联系。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "visual_experiment_name" not in st.session_state:
        st.session_state.visual_experiment_name = "李萨如图形"
    selected = st.segmented_control(
        "选择实验",
        ["李萨如图形", "声速测量", "电子荷质比", "光电效应"],
        key="visual_experiment_name",
        width="stretch",
    ) or "李萨如图形"

    if selected == "李萨如图形":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>〽 李萨如图形综合实验</h3>
              <p>合成两个正交简谐振动，比较相位差、振幅比、频率比和微小失谐对轨迹的影响。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "相位差": "/phase",
            "振幅比": "/amplitude",
            "有理频率比": "/ratio",
            "频率失谐": "/detune",
        }
        if "lissajous_experiment_name" not in st.session_state:
            st.session_state.lissajous_experiment_name = "相位差"
        experiment_name = st.segmented_control(
            "实验变量",
            list(routes),
            key="lissajous_experiment_name",
            width="stretch",
        ) or "相位差"
        _start_and_render(
            LISSAJOUS,
            routes[experiment_name],
            f"李萨如图形 · {experiment_name}",
        )
    elif selected == "声速测量":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>∿ 声速四种测量方法综合实验</h3>
              <p>分别研究回声法、双麦克风时差法、示波器相位差法和驻波法，并比较误差来源。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "回声法": "/echo",
            "双麦克风时差法": "/dual",
            "示波器相位差法": "/phase",
            "驻波法": "/standing",
        }
        if "sound_speed_experiment_name" not in st.session_state:
            st.session_state.sound_speed_experiment_name = "回声法"
        experiment_name = st.segmented_control(
            "实验方法",
            list(routes),
            key="sound_speed_experiment_name",
            width="stretch",
        ) or "回声法"
        _start_and_render(
            SOUND_SPEED,
            routes[experiment_name],
            f"声速测量 · {experiment_name}",
        )
    elif selected == "电子荷质比":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>⊖ 电子荷质比可视化实验</h3>
              <p>分别研究电子束圆轨道、亥姆霍兹线圈磁场、纵向磁聚焦与汤姆孙交叉电磁场测量。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "电子束圆轨道": "/circular",
            "亥姆霍兹磁场标定": "/helmholtz",
            "纵向磁聚焦": "/focus",
            "汤姆孙交叉场": "/thomson",
        }
        if "electron_em_experiment_name" not in st.session_state:
            st.session_state.electron_em_experiment_name = "电子束圆轨道"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="electron_em_experiment_name",
            width="stretch",
        ) or "电子束圆轨道"
        _start_and_render(
            ELECTRON_EM,
            routes[experiment_name],
            f"电子荷质比 · {experiment_name}",
        )
    else:
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>☀ 光电效应可视化实验</h3>
              <p>分别研究光电管伏安特性、普朗克常量线性拟合、截止频率与光强规律，以及遏止电压判读和系统误差。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "光电管伏安特性": "/iv",
            "普朗克常量拟合": "/planck",
            "截止频率与光强": "/threshold",
            "遏止电压判读": "/uncertainty",
        }
        if "photoelectric_experiment_name" not in st.session_state:
            st.session_state.photoelectric_experiment_name = "光电管伏安特性"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="photoelectric_experiment_name",
            width="stretch",
        ) or "光电管伏安特性"
        _start_and_render(
            PHOTOELECTRIC,
            routes[experiment_name],
            f"光电效应 · {experiment_name}",
        )


_EMBED_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  * { box-sizing:border-box; }
  html,body { margin:0; overflow:hidden; background:transparent;
    font-family:system-ui,"Microsoft YaHei",sans-serif; }
  .stage { position:relative; width:100%; height:100vh; min-height:0;
    overflow:hidden; background:#0b0f14; border:1px solid #27313d; border-radius:10px; }
  iframe { display:block; width:100%; height:100%; border:0; background:#0b0f14; }
  .loading { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
    flex-direction:column; gap:14px; color:#d7e1eb; background:#0b0f14; transition:opacity .25s ease; }
  .loading.hidden { opacity:0; pointer-events:none; }
  .spinner { width:42px; height:42px; border-radius:50%; border:5px solid rgba(255,255,255,.15);
    border-top-color:#48b7d4; animation:spin .9s linear infinite; }
  .title { font-size:18px; font-weight:700; }
  .detail { max-width:620px; color:#91a3b5; font-size:14px; line-height:1.6; text-align:center; }
  .detail.error { color:#ff9d9d; }
  button { display:none; min-height:36px; padding:0 16px; border:1px solid #496176; border-radius:8px;
    background:#1d3346; color:#eef5fa; font:inherit; cursor:pointer; }
  button.visible { display:block; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style>
</head>
<body>
<main class="stage">
  <iframe id="experiment" title="交互式大学物理实验"></iframe>
  <div class="loading" id="loading">
    <div class="spinner" id="spinner"></div>
    <div class="title" id="title"></div>
    <div class="detail" id="detail">正在连接实验服务并初始化 WebGL 图形……</div>
    <button id="retry">重新连接</button>
  </div>
</main>
<script>
(() => {
  const settings = __SETTINGS__;
  const frame = document.getElementById('experiment');
  const loading = document.getElementById('loading');
  const title = document.getElementById('title');
  const detail = document.getElementById('detail');
  const retry = document.getElementById('retry');
  const spinner = document.getElementById('spinner');
  let timeout = 0;
  title.textContent = `正在加载${settings.title}`;

  const experimentUrl = () => settings.path;
  const showReady = () => {
    window.clearTimeout(timeout);
    loading.classList.add('hidden');
  };
  const showError = message => {
    window.clearTimeout(timeout);
    spinner.style.display = 'none';
    title.textContent = `${settings.title}暂时无法显示`;
    detail.textContent = message || '内嵌实验服务暂时不可用，请稍后重新连接。';
    detail.classList.add('error');
    retry.classList.add('visible');
  };
  const connect = () => {
    spinner.style.display = '';
    detail.classList.remove('error');
    detail.textContent = '正在连接实验服务并初始化 WebGL 图形……';
    retry.classList.remove('visible');
    frame.src = experimentUrl() + `?attempt=${Date.now()}`;
    timeout = window.setTimeout(
      () => showError('实验初始化时间较长。可以稍后重新连接，或查看实验运行日志。'),
      90000
    );
  };
  window.addEventListener('message', event => {
    if (event.source !== frame.contentWindow || !event.data) return;
    if (event.data.type === settings.readyEvent) showReady();
    if (event.data.type === settings.failedEvent) showError(event.data.detail);
  });
  frame.addEventListener('error', () => showError('浏览器无法连接实验服务。'));
  retry.addEventListener('click', connect);
  connect();
})();
</script>
</body>
</html>
"""
