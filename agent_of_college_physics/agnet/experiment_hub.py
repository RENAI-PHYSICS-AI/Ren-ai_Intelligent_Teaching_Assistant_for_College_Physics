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
EXPERIMENT_GROUPS: dict[str, tuple[str, ...]] = {
    "力学实验": ("杨氏模量", "转动惯量", "粘滞系数测定"),
    "热学实验": (
        "固体比热容的测定",
        "温度传感器特性的测定",
        "固体热传导系数测定",
    ),
    "振动波动": ("声速测量", "李萨如图形"),
    "电磁实验": (
        "电子荷质比",
        "惠斯通电桥测电阻",
        "霍尔效应测磁场分布",
        "铁磁滞回线测定与观察",
    ),
    "光学实验": (
        "牛顿环",
        "双棱镜干涉",
        "薄透镜焦距的测定",
        "三棱镜折射率测定",
    ),
    "近代物理实验": ("光电效应", "弗兰克-赫兹"),
}
EXPERIMENT_DISPLAY_NAMES = {
    "双棱镜干涉": "双棱镜干涉测波长",
}
EXPERIMENT_CATEGORY_BY_NAME = {
    experiment_name: category
    for category, experiment_names in EXPERIMENT_GROUPS.items()
    for experiment_name in experiment_names
}
DEFAULT_EXPERIMENT = EXPERIMENT_GROUPS["力学实验"][0]


def normalize_experiment_selection(
    category: str | None,
    experiment_name: str | None,
) -> tuple[str, str]:
    """Return a valid category/experiment pair while preserving old sessions."""
    if category in EXPERIMENT_GROUPS:
        experiments = EXPERIMENT_GROUPS[category]
        if experiment_name in experiments:
            return category, experiment_name
        return category, experiments[0]
    if experiment_name in EXPERIMENT_CATEGORY_BY_NAME:
        return EXPERIMENT_CATEGORY_BY_NAME[experiment_name], experiment_name
    return EXPERIMENT_CATEGORY_BY_NAME[DEFAULT_EXPERIMENT], DEFAULT_EXPERIMENT


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

BIPRISM = ExperimentService(
    key="biprism",
    title="双棱镜干涉测钠黄光波长",
    project_dir=EXPERIMENT_ROOT / "biprism",
    web_path=EXPERIMENT_ROOT / "biprism" / "web.jl",
    port_env="PHYSICS_BIPRISM_PORT",
    default_port=9388,
    julia_host_env="BIPRISM_WEB_HOST",
    julia_port_env="BIPRISM_WEB_PORT",
    julia_proxy_env="BIPRISM_WEB_PROXY_URL",
    ready_event="biprism-wgl-ready",
    failed_event="biprism-wgl-failed",
    identity_marker="physics-experiment:biprism",
    root_marker="双棱镜干涉",
    height=740,
)

NEWTON_RINGS = ExperimentService(
    key="newton_rings",
    title="牛顿环等厚干涉实验",
    project_dir=EXPERIMENT_ROOT / "newton_rings",
    web_path=EXPERIMENT_ROOT / "newton_rings" / "web.jl",
    port_env="PHYSICS_NEWTON_RINGS_PORT",
    default_port=9389,
    julia_host_env="NEWTON_RINGS_WEB_HOST",
    julia_port_env="NEWTON_RINGS_WEB_PORT",
    julia_proxy_env="NEWTON_RINGS_WEB_PROXY_URL",
    ready_event="newton-rings-wgl-ready",
    failed_event="newton-rings-wgl-failed",
    identity_marker="physics-experiment:newton-rings",
    root_marker="牛顿环",
    height=740,
)

YOUNG_MODULUS = ExperimentService(
    key="young_modulus",
    title="杨氏模量测定实验",
    project_dir=EXPERIMENT_ROOT / "young_modulus",
    web_path=EXPERIMENT_ROOT / "young_modulus" / "web.jl",
    port_env="PHYSICS_YOUNG_MODULUS_PORT",
    default_port=9390,
    julia_host_env="YOUNG_MODULUS_WEB_HOST",
    julia_port_env="YOUNG_MODULUS_WEB_PORT",
    julia_proxy_env="YOUNG_MODULUS_WEB_PROXY_URL",
    ready_event="young-modulus-wgl-ready",
    failed_event="young-modulus-wgl-failed",
    identity_marker="physics-experiment:young-modulus",
    root_marker="杨氏模量",
    height=740,
)

ROTATIONAL_INERTIA = ExperimentService(
    key="rotational_inertia",
    title="转动惯量测定实验",
    project_dir=EXPERIMENT_ROOT / "rotational_inertia",
    web_path=EXPERIMENT_ROOT / "rotational_inertia" / "web.jl",
    port_env="PHYSICS_ROTATIONAL_INERTIA_PORT",
    default_port=9391,
    julia_host_env="ROTATIONAL_INERTIA_WEB_HOST",
    julia_port_env="ROTATIONAL_INERTIA_WEB_PORT",
    julia_proxy_env="ROTATIONAL_INERTIA_WEB_PROXY_URL",
    ready_event="rotational-inertia-wgl-ready",
    failed_event="rotational-inertia-wgl-failed",
    identity_marker="physics-experiment:rotational-inertia",
    root_marker="转动惯量",
    height=740,
)

VISCOSITY = ExperimentService(
    key="viscosity",
    title="粘滞系数测定实验",
    project_dir=EXPERIMENT_ROOT / "viscosity",
    web_path=EXPERIMENT_ROOT / "viscosity" / "web.jl",
    port_env="PHYSICS_VISCOSITY_PORT",
    default_port=9392,
    julia_host_env="VISCOSITY_WEB_HOST",
    julia_port_env="VISCOSITY_WEB_PORT",
    julia_proxy_env="VISCOSITY_WEB_PROXY_URL",
    ready_event="viscosity-wgl-ready",
    failed_event="viscosity-wgl-failed",
    identity_marker="physics-experiment:viscosity",
    root_marker="粘滞系数",
    height=740,
)

SPECIFIC_HEAT = ExperimentService(
    key="specific_heat",
    title="固体比热容的测定实验",
    project_dir=EXPERIMENT_ROOT / "specific_heat",
    web_path=EXPERIMENT_ROOT / "specific_heat" / "web.jl",
    port_env="PHYSICS_SPECIFIC_HEAT_PORT",
    default_port=9393,
    julia_host_env="SPECIFIC_HEAT_WEB_HOST",
    julia_port_env="SPECIFIC_HEAT_WEB_PORT",
    julia_proxy_env="SPECIFIC_HEAT_WEB_PROXY_URL",
    ready_event="specific-heat-wgl-ready",
    failed_event="specific-heat-wgl-failed",
    identity_marker="physics-experiment:specific-heat",
    root_marker="固体比热容",
    height=740,
)

FRANCK_HERTZ = ExperimentService(
    key="franck_hertz",
    title="弗兰克-赫兹实验",
    project_dir=EXPERIMENT_ROOT / "franck_hertz",
    web_path=EXPERIMENT_ROOT / "franck_hertz" / "web.jl",
    port_env="PHYSICS_FRANCK_HERTZ_PORT",
    default_port=9394,
    julia_host_env="FRANCK_HERTZ_WEB_HOST",
    julia_port_env="FRANCK_HERTZ_WEB_PORT",
    julia_proxy_env="FRANCK_HERTZ_WEB_PROXY_URL",
    ready_event="franck-hertz-wgl-ready",
    failed_event="franck-hertz-wgl-failed",
    identity_marker="physics-experiment:franck-hertz",
    root_marker="弗兰克-赫兹",
    height=740,
)

TEMPERATURE_SENSOR = ExperimentService(
    key="temperature_sensor",
    title="温度传感器特性的测定实验",
    project_dir=EXPERIMENT_ROOT / "temperature_sensor",
    web_path=EXPERIMENT_ROOT / "temperature_sensor" / "web.jl",
    port_env="PHYSICS_TEMPERATURE_SENSOR_PORT",
    default_port=9395,
    julia_host_env="TEMPERATURE_SENSOR_WEB_HOST",
    julia_port_env="TEMPERATURE_SENSOR_WEB_PORT",
    julia_proxy_env="TEMPERATURE_SENSOR_WEB_PROXY_URL",
    ready_event="temperature-sensor-wgl-ready",
    failed_event="temperature-sensor-wgl-failed",
    identity_marker="physics-experiment:temperature-sensor",
    root_marker="温度传感器",
    height=740,
)

WHEATSTONE_BRIDGE = ExperimentService(
    key="wheatstone_bridge",
    title="惠斯通电桥测电阻实验",
    project_dir=EXPERIMENT_ROOT / "wheatstone_bridge",
    web_path=EXPERIMENT_ROOT / "wheatstone_bridge" / "web.jl",
    port_env="PHYSICS_WHEATSTONE_BRIDGE_PORT",
    default_port=9396,
    julia_host_env="WHEATSTONE_BRIDGE_WEB_HOST",
    julia_port_env="WHEATSTONE_BRIDGE_WEB_PORT",
    julia_proxy_env="WHEATSTONE_BRIDGE_WEB_PROXY_URL",
    ready_event="wheatstone-bridge-wgl-ready",
    failed_event="wheatstone-bridge-wgl-failed",
    identity_marker="physics-experiment:wheatstone-bridge",
    root_marker="惠斯通电桥",
    height=740,
)

HALL_EFFECT = ExperimentService(
    key="hall_effect",
    title="霍尔效应测磁场分布实验",
    project_dir=EXPERIMENT_ROOT / "hall_effect",
    web_path=EXPERIMENT_ROOT / "hall_effect" / "web.jl",
    port_env="PHYSICS_HALL_EFFECT_PORT",
    default_port=9397,
    julia_host_env="HALL_EFFECT_WEB_HOST",
    julia_port_env="HALL_EFFECT_WEB_PORT",
    julia_proxy_env="HALL_EFFECT_WEB_PROXY_URL",
    ready_event="hall-effect-wgl-ready",
    failed_event="hall-effect-wgl-failed",
    identity_marker="physics-experiment:hall-effect",
    root_marker="霍尔效应",
    height=740,
)

MAGNETIC_HYSTERESIS = ExperimentService(
    key="magnetic_hysteresis",
    title="铁磁滞回线测定与观察实验",
    project_dir=EXPERIMENT_ROOT / "magnetic_hysteresis",
    web_path=EXPERIMENT_ROOT / "magnetic_hysteresis" / "web.jl",
    port_env="PHYSICS_MAGNETIC_HYSTERESIS_PORT",
    default_port=9398,
    julia_host_env="MAGNETIC_HYSTERESIS_WEB_HOST",
    julia_port_env="MAGNETIC_HYSTERESIS_WEB_PORT",
    julia_proxy_env="MAGNETIC_HYSTERESIS_WEB_PROXY_URL",
    ready_event="magnetic-hysteresis-wgl-ready",
    failed_event="magnetic-hysteresis-wgl-failed",
    identity_marker="physics-experiment:magnetic-hysteresis",
    root_marker="铁磁滞回线",
    height=740,
)

THIN_LENS_FOCAL = ExperimentService(
    key="thin_lens_focal",
    title="薄透镜焦距的测定实验",
    project_dir=EXPERIMENT_ROOT / "thin_lens_focal",
    web_path=EXPERIMENT_ROOT / "thin_lens_focal" / "web.jl",
    port_env="PHYSICS_THIN_LENS_FOCAL_PORT",
    default_port=9399,
    julia_host_env="THIN_LENS_FOCAL_WEB_HOST",
    julia_port_env="THIN_LENS_FOCAL_WEB_PORT",
    julia_proxy_env="THIN_LENS_FOCAL_WEB_PROXY_URL",
    ready_event="thin-lens-focal-wgl-ready",
    failed_event="thin-lens-focal-wgl-failed",
    identity_marker="physics-experiment:thin-lens-focal",
    root_marker="薄透镜焦距",
    height=740,
)

PRISM_REFRACTIVE_INDEX = ExperimentService(
    key="prism_refractive_index",
    title="三棱镜折射率测定实验",
    project_dir=EXPERIMENT_ROOT / "prism_refractive_index",
    web_path=EXPERIMENT_ROOT / "prism_refractive_index" / "web.jl",
    port_env="PHYSICS_PRISM_REFRACTIVE_INDEX_PORT",
    default_port=9400,
    julia_host_env="PRISM_REFRACTIVE_INDEX_WEB_HOST",
    julia_port_env="PRISM_REFRACTIVE_INDEX_WEB_PORT",
    julia_proxy_env="PRISM_REFRACTIVE_INDEX_WEB_PROXY_URL",
    ready_event="prism-refractive-index-wgl-ready",
    failed_event="prism-refractive-index-wgl-failed",
    identity_marker="physics-experiment:prism-refractive-index",
    root_marker="三棱镜折射率",
    height=740,
)

THERMAL_CONDUCTIVITY = ExperimentService(
    key="thermal_conductivity",
    title="固体热传导系数测定实验",
    project_dir=EXPERIMENT_ROOT / "thermal_conductivity",
    web_path=EXPERIMENT_ROOT / "thermal_conductivity" / "web.jl",
    port_env="PHYSICS_THERMAL_CONDUCTIVITY_PORT",
    default_port=9401,
    julia_host_env="THERMAL_CONDUCTIVITY_WEB_HOST",
    julia_port_env="THERMAL_CONDUCTIVITY_WEB_PORT",
    julia_proxy_env="THERMAL_CONDUCTIVITY_WEB_PROXY_URL",
    ready_event="thermal-conductivity-wgl-ready",
    failed_event="thermal-conductivity-wgl-failed",
    identity_marker="physics-experiment:thermal-conductivity",
    root_marker="固体热传导系数",
    height=740,
)

SERVICES = {
    service.key: service
    for service in (
        LISSAJOUS,
        SOUND_SPEED,
        ELECTRON_EM,
        PHOTOELECTRIC,
        BIPRISM,
        NEWTON_RINGS,
        YOUNG_MODULUS,
        ROTATIONAL_INERTIA,
        VISCOSITY,
        SPECIFIC_HEAT,
        FRANCK_HERTZ,
        TEMPERATURE_SENSOR,
        WHEATSTONE_BRIDGE,
        HALL_EFFECT,
        MAGNETIC_HYSTERESIS,
        THIN_LENS_FOCAL,
        PRISM_REFRACTIVE_INDEX,
        THERMAL_CONDUCTIVITY,
    )
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
    configured = os.getenv("PHYSICS_JULIA_EXE", "").strip()
    julia = configured or shutil.which("julia")
    if not julia:
        raise FileNotFoundError("未找到 Julia。请先安装 Julia 1.10，并确认 julia 命令可用。")

    prefix = [julia]
    channel = os.getenv("PHYSICS_JULIA_CHANNEL", "").strip().lstrip("+")
    if not configured and channel:
        prefix.append(f"+{channel}")
    elif not configured:
        # Juliaup may point the bare `julia` launcher at a newer release even
        # though the experiment manifests are resolved for Julia 1.10.10.
        # Prefer the already-installed compatible channel without changing
        # the user's global Juliaup default.  A standalone Julia executable
        # simply rejects this probe and falls back to its normal invocation.
        try:
            probe = subprocess.run(
                [julia, "+1.10.10", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            version_text = f"{probe.stdout}\n{probe.stderr}".lower()
            if probe.returncode == 0 and "julia version 1.10." in version_text:
                prefix.append("+1.10.10")
        except (OSError, subprocess.SubprocessError):
            pass

    command = [
        *prefix,
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

    selected_category, selected_name = normalize_experiment_selection(
        st.session_state.get("visual_experiment_category"),
        st.session_state.get("visual_experiment_name"),
    )
    st.session_state.visual_experiment_category = selected_category
    st.session_state.visual_experiment_name = selected_name

    category = st.segmented_control(
        "实验类别",
        list(EXPERIMENT_GROUPS),
        key="visual_experiment_category",
        width="stretch",
    ) or selected_category
    category_experiments = EXPERIMENT_GROUPS[category]
    if st.session_state.visual_experiment_name not in category_experiments:
        st.session_state.visual_experiment_name = category_experiments[0]
        st.rerun()

    selected = st.segmented_control(
        "选择实验",
        category_experiments,
        format_func=lambda name: EXPERIMENT_DISPLAY_NAMES.get(name, name),
        key="visual_experiment_name",
        width="stretch",
    ) or category_experiments[0]

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
    elif selected == "光电效应":
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
    elif selected == "双棱镜干涉":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>◇ 双棱镜干涉测钠黄光波长</h3>
              <p>依次研究分波阵面与虚光源、干涉条纹宽度、凸透镜二次成像，以及钠黄光波长拟合与不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "分波阵面与虚光源": "/geometry",
            "钠黄光干涉条纹": "/fringes",
            "二次成像测间距": "/separation",
            "波长拟合与误差": "/wavelength",
        }
        if "biprism_experiment_name" not in st.session_state:
            st.session_state.biprism_experiment_name = "分波阵面与虚光源"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="biprism_experiment_name",
            width="stretch",
        ) or "分波阵面与虚光源"
        _start_and_render(
            BIPRISM,
            routes[experiment_name],
            f"双棱镜干涉 · {experiment_name}",
        )
    elif selected == "牛顿环":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>◎ 牛顿环等厚干涉实验</h3>
              <p>使用 589.3 nm 钠黄光，依次研究半波损失与环纹形成、读数显微镜单向扫描、15 级逐差法，以及直径平方线性拟合与不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "等厚干涉与环纹": "/formation",
            "读数显微镜测量": "/measurement",
            "逐差法求曲率半径": "/difference",
            "线性拟合与误差": "/fit",
        }
        if "newton_rings_experiment_name" not in st.session_state:
            st.session_state.newton_rings_experiment_name = "等厚干涉与环纹"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="newton_rings_experiment_name",
            width="stretch",
        ) or "等厚干涉与环纹"
        _start_and_render(
            NEWTON_RINGS,
            routes[experiment_name],
            f"牛顿环 · {experiment_name}",
        )
    elif selected == "薄透镜焦距的测定":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>◉ 薄透镜焦距的测定实验</h3>
              <p>比较物距—像距法、自准直法和贝塞尔位移法，并通过多组读数拟合与不确定度传播评定焦距。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "物距—像距法": "/direct",
            "自准直法": "/autocollimation",
            "贝塞尔位移法": "/displacement",
            "拟合与不确定度": "/uncertainty",
        }
        if "thin_lens_focal_experiment_name" not in st.session_state:
            st.session_state.thin_lens_focal_experiment_name = "物距—像距法"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="thin_lens_focal_experiment_name",
            width="stretch",
        ) or "物距—像距法"
        _start_and_render(
            THIN_LENS_FOCAL,
            routes[experiment_name],
            f"薄透镜焦距的测定 · {experiment_name}",
        )
    elif selected == "三棱镜折射率测定":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>△ 三棱镜折射率测定实验</h3>
              <p>完成分光计调节、棱镜顶角测量、最小偏向角判定，并由不同谱线分析折射率、色散和不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "分光计调节": "/collimation",
            "棱镜顶角测量": "/apex",
            "最小偏向角法": "/minimum-deviation",
            "折射率、色散与不确定度": "/dispersion",
        }
        if "prism_refractive_index_experiment_name" not in st.session_state:
            st.session_state.prism_refractive_index_experiment_name = "分光计调节"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="prism_refractive_index_experiment_name",
            width="stretch",
        ) or "分光计调节"
        _start_and_render(
            PRISM_REFRACTIVE_INDEX,
            routes[experiment_name],
            f"三棱镜折射率测定 · {experiment_name}",
        )
    elif selected == "杨氏模量":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>↕ 杨氏模量测定实验</h3>
              <p>采用金属丝静态拉伸与光杠杆放大，依次研究微小伸长测量、加载与卸载、力—伸长线性拟合，以及杨氏模量和不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "光杠杆放大原理": "/principle",
            "加载与卸载读数": "/loading",
            "力—伸长线性拟合": "/fit",
            "模量与不确定度": "/uncertainty",
        }
        if "young_modulus_experiment_name" not in st.session_state:
            st.session_state.young_modulus_experiment_name = "光杠杆放大原理"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="young_modulus_experiment_name",
            width="stretch",
        ) or "光杠杆放大原理"
        _start_and_render(
            YOUNG_MODULUS,
            routes[experiment_name],
            f"杨氏模量 · {experiment_name}",
        )
    elif selected == "转动惯量":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>↻ 转动惯量测定实验</h3>
              <p>分别研究扭摆法、三线摆法、平行轴定理验证，以及转动惯量的线性拟合和不确定度评定。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "扭摆法测转动惯量": "/torsion",
            "三线摆法测转动惯量": "/trifilar",
            "平行轴定理验证": "/parallel-axis",
            "摆动周期拟合与不确定度": "/pendulum-fit",
        }
        if "rotational_inertia_experiment_name" not in st.session_state:
            st.session_state.rotational_inertia_experiment_name = "扭摆法测转动惯量"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="rotational_inertia_experiment_name",
            width="stretch",
        ) or "扭摆法测转动惯量"
        _start_and_render(
            ROTATIONAL_INERTIA,
            routes[experiment_name],
            f"转动惯量 · {experiment_name}",
        )
    elif selected == "粘滞系数测定":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>◉ 粘滞系数测定实验</h3>
              <p>采用落球法研究斯托克斯阻力与终端速度，评估计时区间、Faxén 管壁修正、雷诺数，并通过多球线性拟合求液体动力黏度及其不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "斯托克斯定律与受力平衡": "/stokes",
            "终端速度与落球计时": "/terminal",
            "容器壁面修正": "/correction",
            "多球拟合与不确定度": "/fit",
        }
        if "viscosity_experiment_name" not in st.session_state:
            st.session_state.viscosity_experiment_name = "斯托克斯定律与受力平衡"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="viscosity_experiment_name",
            width="stretch",
        ) or "斯托克斯定律与受力平衡"
        _start_and_render(
            VISCOSITY,
            routes[experiment_name],
            f"粘滞系数测定 · {experiment_name}",
        )
    elif selected == "固体比热容的测定":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>♨ 固体比热容的测定实验</h3>
              <p>综合研究混合法热量平衡、冷却修正、电热法能量输入，以及多组数据的线性拟合与不确定度评定。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "混合法与热量平衡": "/mixing",
            "冷却修正与热损失": "/cooling",
            "电热法与能量输入": "/electrical",
            "线性拟合与不确定度": "/fit",
        }
        if "specific_heat_experiment_name" not in st.session_state:
            st.session_state.specific_heat_experiment_name = "混合法与热量平衡"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="specific_heat_experiment_name",
            width="stretch",
        ) or "混合法与热量平衡"
        _start_and_render(
            SPECIFIC_HEAT,
            routes[experiment_name],
            f"固体比热容的测定 · {experiment_name}",
        )
    elif selected == "温度传感器特性的测定":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>🌡 温度传感器特性的测定实验</h3>
              <p>以 Pt100 为主线，研究静态标定、阶跃响应、测量电桥与导线补偿，以及滞后、拟合和不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "Pt100 静态标定与灵敏度": "/calibration",
            "阶跃响应与时间常数": "/response",
            "测量电桥、导线补偿与自热": "/bridge",
            "滞后、拟合与不确定度": "/uncertainty",
        }
        if "temperature_sensor_experiment_name" not in st.session_state:
            st.session_state.temperature_sensor_experiment_name = "Pt100 静态标定与灵敏度"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="temperature_sensor_experiment_name",
            width="stretch",
        ) or "Pt100 静态标定与灵敏度"
        _start_and_render(
            TEMPERATURE_SENSOR,
            routes[experiment_name],
            f"温度传感器特性的测定 · {experiment_name}",
        )
    elif selected == "固体热传导系数测定":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>▥ 固体热传导系数测定实验</h3>
              <p>从傅里叶定律出发，研究稳态导热、散热盘冷却修正、多工况线性拟合及热传导系数的不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "稳态导热与温度梯度": "/steady-state",
            "冷却曲线与散热修正": "/cooling",
            "多工况线性拟合": "/fit",
            "热传导系数与不确定度": "/uncertainty",
        }
        if "thermal_conductivity_experiment_name" not in st.session_state:
            st.session_state.thermal_conductivity_experiment_name = "稳态导热与温度梯度"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="thermal_conductivity_experiment_name",
            width="stretch",
        ) or "稳态导热与温度梯度"
        _start_and_render(
            THERMAL_CONDUCTIVITY,
            routes[experiment_name],
            f"固体热传导系数测定 · {experiment_name}",
        )
    elif selected == "惠斯通电桥测电阻":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>◇ 惠斯通电桥测电阻实验</h3>
              <p>从零电流平衡条件出发，练习粗调与细调，比较桥路灵敏度和不确定度，并用多比率测量检验线性关系。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "桥路原理与零电流平衡": "/principle",
            "粗调细调与平衡读数": "/balance",
            "灵敏度与不确定度": "/sensitivity",
            "多比率测量与线性拟合": "/fit",
        }
        if "wheatstone_bridge_experiment_name" not in st.session_state:
            st.session_state.wheatstone_bridge_experiment_name = "桥路原理与零电流平衡"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="wheatstone_bridge_experiment_name",
            width="stretch",
        ) or "桥路原理与零电流平衡"
        _start_and_render(
            WHEATSTONE_BRIDGE,
            routes[experiment_name],
            f"惠斯通电桥测电阻 · {experiment_name}",
        )
    elif selected == "霍尔效应测磁场分布":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>⊕ 霍尔效应测磁场分布实验</h3>
              <p>研究霍尔电压与磁场、电流和几何尺寸的关系，完成探头标定、沿轴扫描、线性拟合及不确定度评定。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "霍尔电压标定": "/calibration",
            "沿轴磁场分布扫描": "/scan",
            "线性拟合与残差": "/fit",
            "不确定度评定": "/uncertainty",
        }
        if "hall_effect_experiment_name" not in st.session_state:
            st.session_state.hall_effect_experiment_name = "霍尔电压标定"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="hall_effect_experiment_name",
            width="stretch",
        ) or "霍尔电压标定"
        _start_and_render(
            HALL_EFFECT,
            routes[experiment_name],
            f"霍尔效应测磁场分布 · {experiment_name}",
        )
    elif selected == "铁磁滞回线测定与观察":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>↔ 铁磁滞回线测定与观察实验</h3>
              <p>观察基本磁滞回线与特征量，理解示波器法和积分器标定，模拟交流退磁，并分析磁滞损耗和不确定度。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        routes = {
            "基本磁滞回线与特征量": "/loop",
            "示波器法与积分器标定": "/apparatus",
            "交流退磁与剩磁衰减": "/demagnetization",
            "损耗分离与不确定度": "/fit",
        }
        if "magnetic_hysteresis_experiment_name" not in st.session_state:
            st.session_state.magnetic_hysteresis_experiment_name = "基本磁滞回线与特征量"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="magnetic_hysteresis_experiment_name",
            width="stretch",
        ) or "基本磁滞回线与特征量"
        _start_and_render(
            MAGNETIC_HYSTERESIS,
            routes[experiment_name],
            f"铁磁滞回线测定与观察 · {experiment_name}",
        )
    elif selected == "弗兰克-赫兹":
        st.markdown(
            """
            <div class="experiment-summary">
              <h3>⚛ 弗兰克-赫兹实验</h3>
              <p>依次研究实验装置与电子—原子碰撞、周期性峰谷曲线、第一激发电势的数据分析，以及拟合与不确定度评定。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.warning(
            "本实验页仅作数值仿真。真实汞管实验涉及有毒汞蒸气、高温和高压"
            "（包括高温玻璃表面与高压电源），只能使用完好封装设备并按实验室规程操作。"
        )
        routes = {
            "实验装置与能级跃迁": "/apparatus",
            "周期性峰谷曲线": "/curve",
            "激发电势分析": "/analysis",
            "拟合与不确定度": "/uncertainty",
        }
        if "franck_hertz_experiment_name" not in st.session_state:
            st.session_state.franck_hertz_experiment_name = "实验装置与能级跃迁"
        experiment_name = st.segmented_control(
            "实验项目",
            list(routes),
            key="franck_hertz_experiment_name",
            width="stretch",
        ) or "实验装置与能级跃迁"
        _start_and_render(
            FRANCK_HERTZ,
            routes[experiment_name],
            f"弗兰克-赫兹 · {experiment_name}",
        )
    else:
        st.error("实验选择状态异常，请重新选择实验。")


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
