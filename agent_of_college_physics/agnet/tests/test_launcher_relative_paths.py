"""Portable launcher regression tests; never install or start real services."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


APP_DIR = Path(__file__).resolve().parents[1]
ROCKY_DIR = APP_DIR.parent
if not (ROCKY_DIR / "manage.sh").is_file():
    ROCKY_DIR = APP_DIR.parent / "agent_of_college_physics"


def _bash() -> str:
    executable = shutil.which("bash")
    if not executable and os.name == "nt":
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parents[1] / "bin" / "bash.exe"
            if candidate.is_file():
                executable = str(candidate)
    if not executable:
        pytest.skip("Bash is required to execute the Linux launcher helper")
    return executable


def _run_helper(tmp_path: Path, script: str, **variables: str) -> list[str]:
    # An unrelated cwd must not determine configured paths.
    env = os.environ.copy()
    env.update(variables)
    result = subprocess.run(
        [_bash(), "--noprofile", "--norc", "-c", script, "test-paths", str(APP_DIR / "launcher_paths.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return result.stdout.splitlines()


@pytest.mark.parametrize("variable", [
    "PHYSICS_EXAM_MATERIALS_DIR", "PHYSICS_ASR_MODEL_DIR", "PHYSICS_TEX_CACHE_DIR",
    "PHYSICS_CJK_FONT", "PHYSICS_GATEWAY_TLS_CERT", "PHYSICS_GATEWAY_TLS_KEY",
    "PHYSICS_CA_BUNDLE", "PHYSICS_SOUND_SPEED_OUTPUT_DIR",
])
def test_configured_paths_use_release_root(tmp_path: Path, variable: str) -> None:
    lines = _run_helper(
        tmp_path,
        'set -eu; source "$1"; physics_resolve_launcher_paths "/release directory"; '
        'printf "%s\\n" "${!TEST_VARIABLE}"',
        TEST_VARIABLE=variable,
        **{variable: "./assets/path with spaces"},
    )
    assert lines == ["/release directory/assets/path with spaces"]


@pytest.mark.parametrize("variable", ["PHYSICS_JULIA_EXE", "PHYSICS_TEX_COMPILER", "PHYSICS_LMS_BIN"])
@pytest.mark.parametrize("value, expected", [
    ("compiler", "compiler"),
    ("./bin/compiler", "/release directory/bin/compiler"),
    ("/external/bin/compiler", "/external/bin/compiler"),
])
def test_executable_paths_preserve_path_lookup_and_absolute_overrides(
    tmp_path: Path, variable: str, value: str, expected: str
) -> None:
    lines = _run_helper(
        tmp_path,
        'set -eu; source "$1"; physics_resolve_launcher_paths "/release directory"; '
        'printf "%s\\n" "${!TEST_VARIABLE}"',
        TEST_VARIABLE=variable,
        **{variable: value},
    )
    assert lines == [expected]


@pytest.mark.parametrize("value, expected", [
    ("depot:/shared/depot:", "/release/depot:/shared/depot:"),
    (":depot::", ":/release/depot::"),
])
def test_julia_depot_list_keeps_empty_entry_semantics(tmp_path: Path, value: str, expected: str) -> None:
    lines = _run_helper(
        tmp_path,
        'set -eu; source "$1"; physics_resolve_launcher_paths /release; printf "%s\\n" "$JULIA_DEPOT_PATH"',
        JULIA_DEPOT_PATH=value,
    )
    assert lines == [expected]


def test_user_paths_and_unset_variables_are_preserved(tmp_path: Path) -> None:
    lines = _run_helper(
        tmp_path,
        'set -eu; source "$1"; unset PHYSICS_CJK_FONT; physics_resolve_launcher_paths /release; '
        'printf "%s\\n" "$HOME" "$PHYSICS_CA_BUNDLE" "${PHYSICS_CJK_FONT-unset}"',
        PHYSICS_CA_BUNDLE="~/certs/ca.pem",
    )
    assert lines[1:] == [f"{lines[0]}/certs/ca.pem", "unset"]


@pytest.mark.parametrize("stem, installer", [
    ("deepseek-avx512", "install_deepseek_avx512_service.sh"),
    ("mimo-vl-avx2", "install_mimo_vl_avx2_service.sh"),
])
def test_model_services_and_preflight_share_home_path_base(tmp_path: Path, stem: str, installer: str) -> None:
    unit = (APP_DIR / f"{stem}.service").read_text(encoding="utf-8")
    source = (APP_DIR / installer).read_text(encoding="utf-8")
    assert "WorkingDirectory=%h" in unit
    assert 'cd -- "$HOME"' in source
    assert source.index('cd -- "$HOME"') < source.index('server_help=')
    # --check is explicitly static: it never writes units/config or starts models.
    subprocess.run(
        [_bash(), str(APP_DIR / installer), "--check"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_release_launchers_resolve_before_start_and_bundle_relative_julia_link() -> None:
    manage = (ROCKY_DIR / "manage.sh").read_text(encoding="utf-8")
    install = (ROCKY_DIR / "install.sh").read_text(encoding="utf-8")
    assert manage.index('physics_resolve_launcher_paths "$APP_ROOT"') < manage.index("start_one() {")
    assert install.count('physics_resolve_launcher_paths "$APP_ROOT"') == 2
    assert 'has_admin="$("$APP_ROOT/agnet/.venv/bin/python" -c' in install
    assert 'ln -sfn "../julia-${JULIA_VERSION}/bin/julia" "$RUNTIME_ROOT/bin/julia"' in install
    tectonic = (APP_DIR / "install_tectonic.sh").read_text(encoding="utf-8")
    assert 'PHYSICS_TECTONIC_ARCHIVE="${PROJECT_DIR}/${PHYSICS_TECTONIC_ARCHIVE#./}"' in tectonic
