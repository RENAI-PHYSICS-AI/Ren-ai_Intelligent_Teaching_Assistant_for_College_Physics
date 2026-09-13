#!/usr/bin/env python3
"""Package the tracked Rocky snapshot from a hydrated Git-LFS worktree."""

from __future__ import annotations

import argparse
import gzip
import os
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIRECTORY = Path("agent_of_college_physics")
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"
SUPPORTED_GIT_MODES = {"100644": 0o644, "100755": 0o755}


class PackagingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TrackedFile:
    relative_path: Path
    source_path: Path
    archive_mode: int


def _git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PackagingError(detail or "Git command failed")
    return result.stdout


def tracked_release_files(repo: Path) -> list[TrackedFile]:
    repo = repo.resolve()
    release_root = (repo / RELEASE_DIRECTORY).resolve()
    output = _git(
        repo,
        "ls-files",
        "--stage",
        "-z",
        "--",
        RELEASE_DIRECTORY.as_posix(),
    )
    entries: list[TrackedFile] = []
    for record in output.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, _object_id, stage = metadata.decode("ascii").split()
            relative = Path(encoded_path.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise PackagingError("Cannot parse the tracked-file allowlist") from exc
        if stage != "0":
            raise PackagingError(f"Unmerged Git index entry: {relative.as_posix()}")
        if mode not in SUPPORTED_GIT_MODES:
            raise PackagingError(
                f"Unsupported tracked entry mode {mode}: {relative.as_posix()}"
            )
        source = repo / relative
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(release_root)
        except (FileNotFoundError, ValueError) as exc:
            raise PackagingError(
                f"Tracked release file is missing or escapes the release tree: "
                f"{relative.as_posix()}"
            ) from exc
        if not resolved.is_file():
            raise PackagingError(f"Tracked release entry is not a file: {relative.as_posix()}")
        entries.append(
            TrackedFile(
                relative_path=relative,
                source_path=resolved,
                archive_mode=SUPPORTED_GIT_MODES[mode],
            )
        )
    if not entries:
        raise PackagingError("No tracked Rocky release files were found")
    return sorted(entries, key=lambda entry: entry.relative_path.as_posix())


def _is_lfs_pointer(path: Path) -> bool:
    with path.open("rb") as handle:
        header = handle.read(256).replace(b"\r\n", b"\n")
    return header.startswith(LFS_POINTER_PREFIX)


def validate_hydrated_files(entries: list[TrackedFile]) -> None:
    pointers = [
        entry.relative_path.as_posix()
        for entry in entries
        if _is_lfs_pointer(entry.source_path)
    ]
    if not pointers:
        return
    preview = "\n".join(f"  - {path}" for path in pointers[:20])
    if len(pointers) > 20:
        preview += f"\n  - ... and {len(pointers) - 20} more"
    raise PackagingError(
        "Git-LFS pointer files remain in the Rocky worktree. Run `git lfs pull` "
        f"before packaging:\n{preview}"
    )


def _write_archive(entries: list[TrackedFile], destination: Path) -> None:
    with destination.open("wb") as raw_output:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_output,
            mtime=0,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w|",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for entry in entries:
                    stat = entry.source_path.stat()
                    info = tarfile.TarInfo(entry.relative_path.as_posix())
                    info.size = stat.st_size
                    info.mode = entry.archive_mode
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    with entry.source_path.open("rb") as source:
                        archive.addfile(info, source)


def create_archive(repo: Path, output: Path) -> tuple[int, int]:
    repo = repo.resolve()
    output = output.resolve()
    release_root = (repo / RELEASE_DIRECTORY).resolve()
    try:
        output.relative_to(release_root)
    except ValueError:
        pass
    else:
        raise PackagingError("The release archive must be outside the Rocky release tree")

    entries = tracked_release_files(repo)
    validate_hydrated_files(entries)
    total_bytes = sum(entry.source_path.stat().st_size for entry in entries)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _write_archive(entries, temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return len(entries), total_bytes


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        type=Path,
        default=REPOSITORY_ROOT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("rocky-physics-assistant.tar.gz"),
        help="archive destination (default: rocky-physics-assistant.tar.gz)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate the tracked allowlist and LFS hydration without writing an archive",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        entries = tracked_release_files(args.repository)
        validate_hydrated_files(entries)
        total_bytes = sum(entry.source_path.stat().st_size for entry in entries)
        if args.check_only:
            print(
                f"Rocky release check passed: {len(entries)} tracked files, "
                f"{total_bytes} hydrated bytes."
            )
            return 0
        count, total_bytes = create_archive(args.repository, args.output)
    except PackagingError as exc:
        print(f"Rocky release packaging failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Created {args.output.resolve()} from {count} tracked files "
        f"({total_bytes} source bytes)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
