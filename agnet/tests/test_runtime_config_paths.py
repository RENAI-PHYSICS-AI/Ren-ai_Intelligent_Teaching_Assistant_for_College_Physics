from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import asr_service
import build_teacher_exam_kb
import config
import download_asr_model
import exam_artifacts
import experiment_hub
import gateway
import llm
import visualization


@pytest.fixture
def relocated_runtime(tmp_path, monkeypatch):
    app_dir = tmp_path / "project" / "agnet"
    launch_dir = tmp_path / "unrelated-launch-directory"
    app_dir.mkdir(parents=True)
    launch_dir.mkdir()
    monkeypatch.setattr(config, "APP_DIR", app_dir)
    monkeypatch.chdir(launch_dir)
    return app_dir


def test_app_path_resolves_relative_parent_absolute_and_home_paths(
    relocated_runtime, tmp_path, monkeypatch
):
    app_dir = relocated_runtime
    assert config.resolve_app_path("data/example.txt") == app_dir / "data" / "example.txt"
    assert config.resolve_app_path("../考试素材") == app_dir.parent / "考试素材"
    external = tmp_path / "external" / "model"
    assert config.resolve_app_path(external) == external
    # expanduser uses the OS home environment.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    assert config.resolve_app_path("~/models") == tmp_path / "home" / "models"


def test_relative_exam_corpus_and_asr_model_ignore_launch_directory(
    relocated_runtime, monkeypatch
):
    monkeypatch.setenv("PHYSICS_EXAM_MATERIALS_DIR", "../考试素材")
    monkeypatch.setenv("PHYSICS_ASR_MODEL_DIR", "runtime/asr/custom")
    assert config._exam_materials_dir() == relocated_runtime.parent / "考试素材"
    expected = relocated_runtime / "runtime" / "asr" / "custom"
    assert asr_service.model_directory() == expected
    assert download_asr_model.default_model_dir() == expected


def test_absolute_asr_model_configuration_remains_supported(
    relocated_runtime, tmp_path, monkeypatch
):
    external = tmp_path / "external-model"
    monkeypatch.setenv("PHYSICS_ASR_MODEL_DIR", str(external))
    assert asr_service.model_directory() == external
    assert download_asr_model.default_model_dir() == external


def test_relative_font_and_ca_bundle_ignore_launch_directory(
    relocated_runtime, monkeypatch
):
    font = relocated_runtime / "assets" / "font.ttf"
    font.parent.mkdir()
    font.write_bytes(b"font fixture")
    certificate = relocated_runtime / "certs" / "ca.pem"
    certificate.parent.mkdir()
    certificate.write_text("certificate fixture", encoding="utf-8")
    monkeypatch.setenv("PHYSICS_CJK_FONT", "assets/font.ttf")
    monkeypatch.setenv("PHYSICS_CA_BUNDLE", "certs/ca.pem")
    assert visualization._cjk_font_path() == font
    assert llm._request_verify() == str(certificate)


def test_relative_gateway_tls_paths_ignore_launch_directory(
    relocated_runtime, monkeypatch
):
    context = Mock()
    monkeypatch.setattr(gateway.ssl, "SSLContext", Mock(return_value=context))
    monkeypatch.setenv("PHYSICS_GATEWAY_TLS_CERT", "certs/site.crt")
    monkeypatch.setenv("PHYSICS_GATEWAY_TLS_KEY", "certs/site.key")
    assert gateway.tls_context() is context
    context.load_cert_chain.assert_called_once_with(
        str(relocated_runtime / "certs" / "site.crt"),
        str(relocated_runtime / "certs" / "site.key"),
    )


def test_relative_tex_cache_ignores_launch_directory(
    relocated_runtime, tmp_path, monkeypatch
):
    workdir = tmp_path / "compile-job"
    workdir.mkdir()
    monkeypatch.setenv("PHYSICS_TEX_CACHE_DIR", "../.runtime/tectonic-cache")
    environment = exam_artifacts._tex_environment(workdir)
    expected = relocated_runtime.parent / ".runtime" / "tectonic-cache"
    assert environment["XDG_CACHE_HOME"] == str(expected)
    assert expected.is_dir()


def test_explicit_relative_compiler_ignores_launch_directory(
    relocated_runtime, monkeypatch
):
    compiler = relocated_runtime / "bin" / "tectonic"
    compiler.parent.mkdir()
    compiler.write_bytes(b"compiler fixture")
    compiler.chmod(0o755)
    monkeypatch.setenv("PHYSICS_TEX_COMPILER", "bin/tectonic")
    assert exam_artifacts.find_tex_compiler() == compiler


def test_bare_compiler_uses_path_not_launch_directory(
    relocated_runtime, tmp_path, monkeypatch
):
    Path("xelatex").write_bytes(b"must not be selected from cwd")
    Path("xelatex").chmod(0o755)
    executable = tmp_path / "system-bin" / "xelatex"
    which = Mock(return_value=str(executable))
    monkeypatch.setattr(exam_artifacts.shutil, "which", which)
    assert exam_artifacts.find_tex_compiler("xelatex") == executable
    which.assert_called_once_with("xelatex")


def test_missing_explicit_compiler_does_not_fall_back_to_launch_directory(
    relocated_runtime, monkeypatch
):
    compiler = Path("bin") / "tectonic"
    compiler.parent.mkdir()
    compiler.write_bytes(b"must not be selected from cwd")
    compiler.chmod(0o755)
    which = Mock()
    monkeypatch.setattr(exam_artifacts.shutil, "which", which)
    assert exam_artifacts.find_tex_compiler("bin/tectonic") is None
    which.assert_not_called()


@pytest.mark.parametrize("release_directory", ["project", "repo/agent_of_college_physics"])
@pytest.mark.parametrize("exam_at_parent", [False, True])
def test_private_manifest_source_roots_are_portable_for_both_layouts(
    tmp_path, monkeypatch, release_directory, exam_at_parent
):
    project_root = tmp_path / release_directory
    materials = project_root / "教学素材"
    private = materials / "教师专用" / "教研考试"
    exams = (project_root.parent if exam_at_parent else project_root) / "考试素材"
    private.mkdir(parents=True)
    exams.mkdir()
    output = project_root / "agnet" / "knowledge_base" / "private" / "teacher_exam.jsonl"
    manifest_file = output.with_name("teacher_exam.manifest.json")
    for name, value in {
        "PROJECT_ROOT": project_root,
        "MATERIALS_DIR": materials,
        "EXAM_MATERIALS_DIR": exams,
        "TEACHER_EXAM_MATERIALS_DIR": private,
        "TEACHER_EXAM_KB_FILE": output,
        "TEACHER_EXAM_KB_MANIFEST_FILE": manifest_file,
        "TEACHER_EXAM_TEMPLATE_FILE": exams / "missing-template.tex",
    }.items():
        monkeypatch.setattr(build_teacher_exam_kb, name, value)
    monkeypatch.setattr(build_teacher_exam_kb, "_passwords", lambda: ())
    manifest = build_teacher_exam_kb.build()
    expected = ["考试素材", "教学素材/教师专用/教研考试"]
    assert manifest["source_roots_base"] == "logical"
    assert manifest["source_roots"] == expected
    assert all(not Path(value).is_absolute() for value in manifest["source_roots"])
    assert json.loads(manifest_file.read_text(encoding="utf-8")) == manifest


def test_relative_julia_executable_uses_app_directory(relocated_runtime, monkeypatch):
    monkeypatch.setenv("PHYSICS_JULIA_EXE", "../tools/Julia bin/julia")
    probe = Mock()
    monkeypatch.setattr(experiment_hub.subprocess, "run", probe)
    command = experiment_hub._julia_command(experiment_hub.NEWTON_RINGS)
    assert command[0] == str(relocated_runtime.parent / "tools" / "Julia bin" / "julia")
    probe.assert_not_called()


def test_bare_julia_executable_is_looked_up_on_path(relocated_runtime, tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSICS_JULIA_EXE", "julia-custom")
    executable = tmp_path / "system-bin" / "julia-custom"
    which = Mock(return_value=str(executable))
    monkeypatch.setattr(experiment_hub.shutil, "which", which)
    command = experiment_hub._julia_command(experiment_hub.NEWTON_RINGS)
    assert command[0] == str(executable)
    which.assert_called_once_with("julia-custom")


def test_relative_julia_path_lookup_is_resolved_before_changing_cwd(
    relocated_runtime, monkeypatch
):
    monkeypatch.setenv("PHYSICS_JULIA_EXE", "julia-custom")
    relative = str(Path("path-tools") / "julia")
    monkeypatch.setattr(experiment_hub.shutil, "which", Mock(return_value=relative))
    command = experiment_hub._julia_command(experiment_hub.NEWTON_RINGS)
    assert command[0] == str(Path(relative).resolve())


def test_missing_bare_julia_executable_fails_without_launch(relocated_runtime, monkeypatch):
    monkeypatch.setenv("PHYSICS_JULIA_EXE", "julia-missing")
    monkeypatch.setattr(experiment_hub.shutil, "which", Mock(return_value=None))
    with pytest.raises(FileNotFoundError):
        experiment_hub._julia_command(experiment_hub.NEWTON_RINGS)


@pytest.mark.parametrize("depots", [
    ["relative-depot", "", "second-depot", ""],
    ["", "relative-depot", "", ""],
    [""],
])
def test_julia_environment_resolves_resources_and_preserves_empty_depots(
    relocated_runtime, tmp_path, monkeypatch, depots
):
    monkeypatch.setenv("PHYSICS_CJK_FONT", "assets/font.ttf")
    monkeypatch.setenv("PHYSICS_SOUND_SPEED_OUTPUT_DIR", "runtime/sound-speed-output")
    absolute = tmp_path / "external-depot"
    configured = [*depots, str(absolute)]
    monkeypatch.setenv("JULIA_DEPOT_PATH", os.pathsep.join(configured))
    environment = experiment_hub._julia_environment()
    assert environment["PHYSICS_CJK_FONT"] == str(relocated_runtime / "assets" / "font.ttf")
    assert environment["PHYSICS_SOUND_SPEED_OUTPUT_DIR"] == str(
        relocated_runtime / "runtime" / "sound-speed-output"
    )
    assert environment["JULIA_DEPOT_PATH"] == os.pathsep.join([
        *(str(relocated_runtime / value) if value else "" for value in depots),
        str(absolute),
    ])
    assert os.environ["JULIA_DEPOT_PATH"] == os.pathsep.join(configured)


def test_julia_environment_preserves_unset_and_empty_resources(relocated_runtime, monkeypatch):
    monkeypatch.delenv("PHYSICS_CJK_FONT", raising=False)
    monkeypatch.delenv("JULIA_DEPOT_PATH", raising=False)
    monkeypatch.setenv("PHYSICS_SOUND_SPEED_OUTPUT_DIR", "")
    environment = experiment_hub._julia_environment()
    assert "PHYSICS_CJK_FONT" not in environment
    assert "JULIA_DEPOT_PATH" not in environment
    assert environment["PHYSICS_SOUND_SPEED_OUTPUT_DIR"] == ""
    monkeypatch.setenv("JULIA_DEPOT_PATH", "")
    assert experiment_hub._julia_environment()["JULIA_DEPOT_PATH"] == ""


def test_julia_launch_receives_normalized_environment_without_starting_service(
    relocated_runtime, monkeypatch
):
    project = relocated_runtime / "experiments" / "fixture"
    project.mkdir(parents=True)
    web_path = project / "web.jl"
    web_path.write_text("# fixture", encoding="utf-8")
    (project / "Project.toml").write_text("[deps]", encoding="utf-8")
    service = replace(experiment_hub.NEWTON_RINGS, project_dir=project, web_path=web_path)
    monkeypatch.setattr(experiment_hub, "RUNTIME_DIR", relocated_runtime / "runtime" / "experiments")
    monkeypatch.setattr(experiment_hub, "_processes", {})
    monkeypatch.setattr(experiment_hub, "_logs", {})
    monkeypatch.setattr(experiment_hub, "service_ready", Mock(return_value=False))
    popen = Mock()
    monkeypatch.setattr(experiment_hub.subprocess, "Popen", popen)
    monkeypatch.setenv("PHYSICS_JULIA_EXE", "bin/julia")
    monkeypatch.setenv("PHYSICS_CJK_FONT", "assets/font.ttf")
    monkeypatch.setenv("PHYSICS_SOUND_SPEED_OUTPUT_DIR", "runtime/sound-speed-output")
    monkeypatch.setenv("JULIA_DEPOT_PATH", "depot" + os.pathsep)
    try:
        assert experiment_hub.launch_service(service) is popen.return_value
        arguments, keywords = popen.call_args
        assert arguments[0][0] == str(relocated_runtime / "bin" / "julia")
        assert keywords["cwd"] == project
        assert keywords["env"]["PHYSICS_CJK_FONT"] == str(relocated_runtime / "assets" / "font.ttf")
        assert keywords["env"]["PHYSICS_SOUND_SPEED_OUTPUT_DIR"] == str(
            relocated_runtime / "runtime" / "sound-speed-output"
        )
        assert keywords["env"]["JULIA_DEPOT_PATH"] == str(relocated_runtime / "depot") + os.pathsep
    finally:
        for handle in experiment_hub._logs.values():
            handle.close()
