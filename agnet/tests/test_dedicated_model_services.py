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


def test_rocky_installer_is_reproducible_and_bootstraps_an_empty_database() -> None:
    install = (ROCKY_DIR / "install.sh").read_text(encoding="utf-8")
    env = (ROCKY_DIR / "physics-assistant.env.example").read_text(encoding="utf-8")
    required_block = install.split("for required in", 1)[1].split("; do", 1)[0]

    assert 'UV_VERSION="0.12.5"' in install
    assert 'https://astral.sh/uv/${UV_VERSION}/install.sh' in install
    assert '"$UV_BIN" --version' in install
    assert 'bash "$APP_ROOT/agnet/install_tectonic.sh"' in install
    assert "agnet/data/assistant.db" not in required_block
    assert '"$APP_ROOT/agnet/.venv/bin/python" "$APP_ROOT/agnet/migrate_db.py"' in install
    assert 'set_config_value PHYSICS_GATEWAY_HOST "127.0.0.1"' in install
    assert 'set_config_value PHYSICS_GATEWAY_HTTPS_HOST "$legacy_gateway_host"' in install
    assert "PHYSICS_GATEWAY_HOST=127.0.0.1" in env
    assert "PHYSICS_EXAM_SOURCE_PASSWORDS=" in env
    assert "PHYSICS_PDF_PASSWORDS=" in env


def test_every_launcher_migrates_before_services_and_separates_https_binding() -> None:
    install = (ROCKY_DIR / "install.sh").read_text(encoding="utf-8")
    manage = (ROCKY_DIR / "manage.sh").read_text(encoding="utf-8")
    setup_https = (ROCKY_DIR / "setup_https.sh").read_text(encoding="utf-8")
    env = (ROCKY_DIR / "physics-assistant.env.example").read_text(encoding="utf-8")
    windows_start = (ROCKY_DIR.parent / "agnet" / "start_all.ps1").read_text(encoding="utf-8")
    manage_start = manage.split("start_all() {", 1)[1].split("stop_one() {", 1)[0]

    assert manage_start.index("run_db_migrations") < manage_start.index("start_one admin")
    assert windows_start.index("migrate_db.py") < windows_start.index("Start-Process")
    assert install.index("migrate_db.py") < install.index('"$APP_ROOT/manage.sh" restart')
    assert "PHYSICS_GATEWAY_HOST=127.0.0.1" in env
    assert "PHYSICS_GATEWAY_HTTPS_HOST=" in env
    assert 'PHYSICS_GATEWAY_HOST="127.0.0.1"' in manage
    assert 'PHYSICS_GATEWAY_HOST="$PHYSICS_GATEWAY_HTTPS_HOST"' in manage
    assert 'https_probe_host_for_bind "$PHYSICS_GATEWAY_HTTPS_HOST"' in manage
    assert '""|0.0.0.0) printf' in manage
    assert '::) printf' in manage
    assert "*:*) printf '[%s]'" in manage
    assert 'set_env_value PHYSICS_GATEWAY_HOST "127.0.0.1"' in setup_https
    assert 'set_env_value PHYSICS_GATEWAY_HTTPS_HOST "$HTTPS_LISTEN_HOST"' in setup_https
    assert "PHYSICS_MODEL_QUEUE_MAX_WAITERS=16" in env
    assert "PHYSICS_MODEL_QUEUE_TIMEOUT_SECONDS=900" in env
    assert "PHYSICS_DB_MIGRATION_LOCK_TIMEOUT_SECONDS=30" in env
