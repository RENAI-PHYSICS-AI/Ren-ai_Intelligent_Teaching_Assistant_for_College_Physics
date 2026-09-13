from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import analytics_db
import migrate_db
import storage


def test_concurrent_empty_database_initialization_is_lock_safe() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        for run_number in range(8):
            database = Path(temporary) / f"assistant-{run_number}.db"
            barrier = threading.Barrier(2)

            def initialize(function) -> None:
                barrier.wait(timeout=5)
                function()

            with (
                patch.object(storage, "DB_FILE", database),
                patch.object(analytics_db, "DB_PATH", str(database)),
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                futures = [
                    executor.submit(initialize, storage.init_db),
                    executor.submit(initialize, analytics_db.init_db),
                ]
                for future in futures:
                    future.result(timeout=30)

            with closing(sqlite3.connect(database)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            assert {"users", "messages", "interactions", "sessions"} <= tables


def test_analytics_init_closes_connection_when_migration_raises() -> None:
    connection = Mock()
    with (
        patch.object(analytics_db, "_get_conn", return_value=connection),
        patch.object(
            analytics_db,
            "_init_db_once",
            side_effect=RuntimeError("migration failed"),
        ),
    ):
        try:
            analytics_db.init_db()
        except RuntimeError as exc:
            assert str(exc) == "migration failed"
        else:
            raise AssertionError("migration error was not propagated")

    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_serial_migration_runs_storage_before_analytics() -> None:
    calls: list[str] = []
    with (
        patch.object(storage, "init_db", side_effect=lambda: calls.append("storage")),
        patch.object(analytics_db, "init_db", side_effect=lambda: calls.append("analytics")),
    ):
        migrate_db.migrate_database()
    assert calls == ["storage", "analytics"]


def test_cross_process_migration_lock_has_bounded_wait() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Path(temporary) / "assistant.db"
        marker = Path(temporary) / "locked"
        code = (
            "import sys,time; from pathlib import Path; "
            "from migrate_db import migration_lock; "
            "lock=migration_lock(Path(sys.argv[1]), timeout_seconds=5); "
            "lock.__enter__(); Path(sys.argv[2]).write_text('ready'); "
            "time.sleep(1); lock.__exit__(None,None,None)"
        )
        child = subprocess.Popen(
            [sys.executable, "-c", code, str(database), str(marker)],
            cwd=APP_DIR,
        )
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert marker.exists(), "child process did not acquire migration lock"

            started = time.monotonic()
            try:
                with migrate_db.migration_lock(database, timeout_seconds=0.15):
                    pass
            except TimeoutError:
                pass
            else:
                raise AssertionError("second process unexpectedly acquired migration lock")
            assert time.monotonic() - started < 1
        finally:
            child.wait(timeout=10)
        assert child.returncode == 0
        with migrate_db.migration_lock(database, timeout_seconds=1):
            pass


def test_column_alters_are_guarded_by_immediate_transactions() -> None:
    import inspect

    analytics_source = inspect.getsource(analytics_db._init_db_once)
    storage_source = inspect.getsource(storage._init_db_once)
    assert analytics_source.index('conn.execute("BEGIN IMMEDIATE")') < analytics_source.index(
        "_ensure_column("
    )
    assert storage_source.index('connection.execute("BEGIN IMMEDIATE")') < storage_source.index(
        'connection.execute(f"ALTER TABLE users ADD COLUMN'
    )
