from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import package_rocky_release


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
    )


def _release_repository(tmp_path: Path) -> Path:
    release = tmp_path / "agent_of_college_physics"
    (release / "agnet").mkdir(parents=True)
    (release / "install.sh").write_bytes(b"#!/usr/bin/env bash\necho ready\n")
    (release / "agnet" / "app.py").write_bytes(b"VALUE = 1\n")
    (release / "local-secret.txt").write_bytes(b"must not be packaged\n")
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "add", "agent_of_college_physics/install.sh")
    _git(tmp_path, "add", "agent_of_college_physics/agnet/app.py")
    _git(tmp_path, "update-index", "--chmod=+x", "agent_of_college_physics/install.sh")
    return tmp_path


def test_archive_uses_tracked_allowlist_and_is_deterministic(tmp_path: Path) -> None:
    repo = _release_repository(tmp_path)
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    count, _total_bytes = package_rocky_release.create_archive(repo, first)
    package_rocky_release.create_archive(repo, second)

    assert count == 2
    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    with tarfile.open(first, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        assert set(members) == {
            "agent_of_college_physics/agnet/app.py",
            "agent_of_college_physics/install.sh",
        }
        assert members["agent_of_college_physics/install.sh"].mode == 0o755
        assert archive.extractfile("agent_of_college_physics/agnet/app.py").read() == b"VALUE = 1\n"


def test_packaging_refuses_unhydrated_lfs_pointer(tmp_path: Path) -> None:
    repo = _release_repository(tmp_path)
    pointer = repo / "agent_of_college_physics" / "asset.bin"
    pointer.write_bytes(
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:0123456789abcdef\nsize 1234\n"
    )
    _git(repo, "add", "agent_of_college_physics/asset.bin")

    entries = package_rocky_release.tracked_release_files(repo)
    with pytest.raises(package_rocky_release.PackagingError, match="git lfs pull"):
        package_rocky_release.validate_hydrated_files(entries)
