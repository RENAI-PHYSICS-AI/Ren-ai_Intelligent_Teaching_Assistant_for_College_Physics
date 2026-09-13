"""Run all SQLite schema migrations serially before services are spawned."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

import analytics_db
import storage


LOCK_TIMEOUT_DEFAULT_SECONDS = 30.0
LOCK_TIMEOUT_MIN_SECONDS = 0.1
LOCK_TIMEOUT_MAX_SECONDS = 120.0


def _lock_timeout_seconds(value: float | str | None = None) -> float:
    raw = value if value is not None else os.getenv(
        "PHYSICS_DB_MIGRATION_LOCK_TIMEOUT_SECONDS",
        str(LOCK_TIMEOUT_DEFAULT_SECONDS),
    )
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        parsed = LOCK_TIMEOUT_DEFAULT_SECONDS
    return min(LOCK_TIMEOUT_MAX_SECONDS, max(LOCK_TIMEOUT_MIN_SECONDS, parsed))


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, OSError):
        return False


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def migration_lock(
    database_path: Path | str | None = None,
    *,
    timeout_seconds: float | str | None = None,
) -> Iterator[Path]:
    database = Path(database_path or storage.DB_FILE)
    database.parent.mkdir(parents=True, exist_ok=True)
    lock_path = database.with_name(database.name + ".migration.lock")
    deadline = time.monotonic() + _lock_timeout_seconds(timeout_seconds)
    with lock_path.open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        acquired = False
        while not acquired:
            acquired = _try_lock(handle)
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"等待数据库迁移锁超时：{lock_path}")
            time.sleep(0.05)
        try:
            yield lock_path
        finally:
            _unlock(handle)


def migrate_database(database_path: Path | str | None = None) -> None:
    database = Path(database_path) if database_path is not None else Path(storage.DB_FILE)
    if database_path is not None:
        storage.DB_FILE = database
        analytics_db.DB_PATH = str(database)
    with migration_lock(database):
        storage.init_db()
        analytics_db.init_db()


if __name__ == "__main__":
    migrate_database()
