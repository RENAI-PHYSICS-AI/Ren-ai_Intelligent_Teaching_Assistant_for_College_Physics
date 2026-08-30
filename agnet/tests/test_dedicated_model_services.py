from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
ROCKY_DIR = APP_DIR.parent
if not (ROCKY_DIR / "manage.sh").is_file():
    ROCKY_DIR = APP_DIR.parent / "agent_of_college_physics"


def _read(name: str) -> str:
    return (APP_DIR / name).read_text(encoding="utf-8")


def test_mimo_service_is_private_resident_and_bound_to_numa0() -> None:
    unit = _read("mimo-vl-avx2.service")
    env = _read("mimo-vl-avx2.env.example")
    assert "Restart=always" in unit
    assert "--no-mmap" in unit
    assert "--no-direct-io" in unit
    assert "--mmproj ${MIMO_VL_MMPROJ_PATH}" in unit
    assert "--physcpubind=${MIMO_VL_CPU_LIST}" in unit
    assert "--membind=${MIMO_VL_NUMA_NODE}" in unit
    assert "--numa numactl" not in unit
    assert "--api-key" not in unit
    assert "MIMO_VL_HOST=127.0.0.1" in env
    assert "MIMO_VL_PORT=1237" in env
    assert "MIMO_VL_CTX_SIZE=128000" in env
    assert "MIMO_VL_PARALLEL=4" in env
    assert "MIMO_VL_NUMA_NODE=0" in env
    assert "MIMO_VL_CPU_LIST=0-127" in env


def test_deepseek_service_is_one_megatoken_and_bound_to_numa1() -> None:
    unit = _read("deepseek-avx512.service")
    env = _read("deepseek-avx512.env.example")
    assert "Restart=always" in unit
    assert "--load-mode dio" in unit
    assert "--physcpubind=${DEEPSEEK_AVX512_CPU_LIST}" in unit
    assert "--membind=${DEEPSEEK_AVX512_NUMA_NODE}" in unit
    assert "--numa numactl" not in unit
    assert "--api-key" not in unit
    assert "DEEPSEEK_AVX512_CTX_SIZE=1048576" in env
    assert "DEEPSEEK_AVX512_PARALLEL=1" in env
    assert "DEEPSEEK_AVX512_NUMA_NODE=1" in env
    assert "DEEPSEEK_AVX512_CPU_LIST=128-255" in env


def test_manage_starts_units_and_checks_two_authenticated_model_apis() -> None:
    manage = (ROCKY_DIR / "manage.sh").read_text(encoding="utf-8")
    env = (ROCKY_DIR / "physics-assistant.env.example").read_text(encoding="utf-8")
    assert 'PHYSICS_BASE_URL:-http://127.0.0.1:1237/v1' in manage
    assert 'PHYSICS_EXAM_BASE_URL:-http://127.0.0.1:1236/v1' in manage
    assert 'PHYSICS_MODEL_STARTUP_TIMEOUT_SECONDS:-1800' in manage
    assert "systemctl --user start mimo-vl-avx2.service deepseek-avx512.service" in manage
    assert 'headers["Authorization"] = f"Bearer {api_key}"' in manage
    start_body = manage.split("start_all() {", 1)[1].split("stop_one() {", 1)[0]
    assert "ensure_model_apis" in start_body
    assert "ensure_local_llms" not in start_body
    assert "PHYSICS_BASE_URL=http://127.0.0.1:1237/v1" in env
    assert "PHYSICS_EXAM_CONTEXT_WINDOW=1048576" in env
    assert "PHYSICS_USE_LEGACY_LM_STUDIO=0" in env
