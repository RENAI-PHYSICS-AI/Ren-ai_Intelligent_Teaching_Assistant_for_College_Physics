from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import shutil
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from config import APP_DIR


DB_FILE = APP_DIR / "data" / "assistant.db"
DB_BUSY_TIMEOUT_MS = 5_000
DB_INIT_ATTEMPTS = 4
USERNAME_RE = re.compile(r"^[\w\-\u4e00-\u9fff]{3,32}$")
ARTIFACT_MAX_COUNT = 8
ARTIFACT_MAX_ITEM_BYTES = 8 * 1024**2
ARTIFACT_MAX_TOTAL_BYTES = 16 * 1024**2
UPLOAD_MAX_ITEM_BYTES = 20 * 1024**2
UPLOAD_MAX_COUNT = 6
UPLOAD_MAX_TOTAL_BYTES = 40 * 1024**2
USER_BLOB_DAILY_STORED_BYTES = 128 * 1024**2
USER_BLOB_TOTAL_STORED_BYTES = 512 * 1024**2
USER_BLOB_DAILY_MESSAGE_LIMIT = 30
MESSAGE_MAX_CONTENT_BYTES = 512 * 1024
MESSAGE_MAX_VISUALIZATION_BYTES = 2 * 1024**2
USER_MESSAGE_DAILY_LIMIT = 500
GLOBAL_MESSAGE_DAILY_STORED_BYTES = 2 * 1024**3
DATABASE_MAX_BYTES = 8 * 1024**3
DATABASE_MIN_FREE_BYTES = 512 * 1024**2
REGISTRATION_CLIENT_WINDOW_LIMIT = 3
REGISTRATION_CLIENT_DAILY_LIMIT = 8
REGISTRATION_GLOBAL_WINDOW_LIMIT = 100
REGISTRATION_GLOBAL_DAILY_LIMIT = 500
REGISTRATION_WINDOW_SECONDS = 10 * 60
REGISTRATION_DAY_SECONDS = 24 * 60 * 60
LOGIN_FAILURE_LIMIT = 8
LOGIN_ACCOUNT_FAILURE_LIMIT = 16
LOGIN_CLIENT_FAILURE_LIMIT = 64
LOGIN_WINDOW_SECONDS = 5 * 60
LOGIN_LOCK_SECONDS = 5 * 60
PASSWORD_MAX_UTF8_BYTES = 256
ARTIFACT_ALLOWED_MIMES = {
    ".tex": frozenset({"text/x-tex", "application/x-tex"}),
    ".pdf": frozenset({"application/pdf"}),
    ".zip": frozenset({"application/zip"}),
}


class LoginRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        super().__init__(f"登录尝试过于频繁，请在 {self.retry_after_seconds} 秒后重试。")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=DB_BUSY_TIMEOUT_MS / 1000)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


_MESSAGE_STORED_BYTES_SQL = """
    length(CAST(content AS BLOB))
    + length(CAST(images_json AS BLOB))
    + length(CAST(visualizations_json AS BLOB))
    + length(CAST(artifacts_json AS BLOB))
"""


def _rebuild_storage_usage(connection: sqlite3.Connection) -> None:
    """Reconcile the compact quota ledger after migrations or deletions."""
    day_key = datetime.now().date().isoformat()
    rows = connection.execute(
        f"""SELECT user_id,
                   COALESCE(SUM({_MESSAGE_STORED_BYTES_SQL}), 0) AS stored_bytes,
                   COALESCE(SUM(CASE WHEN date(created_at, 'localtime')=date('now', 'localtime')
                                     THEN {_MESSAGE_STORED_BYTES_SQL} ELSE 0 END), 0) AS daily_bytes,
                   COALESCE(SUM(CASE WHEN date(created_at, 'localtime')=date('now', 'localtime')
                                     THEN 1 ELSE 0 END), 0) AS daily_count,
                   COALESCE(SUM(CASE WHEN date(created_at, 'localtime')=date('now', 'localtime')
                                          AND (images_json<>'[]' OR artifacts_json<>'[]')
                                     THEN 1 ELSE 0 END), 0) AS daily_blob_count
            FROM messages GROUP BY user_id"""
    ).fetchall()
    connection.execute("DELETE FROM storage_usage")
    totals = [0, 0, 0, 0]
    for row in rows:
        values = [
            int(row["stored_bytes"]),
            int(row["daily_bytes"]),
            int(row["daily_count"]),
            int(row["daily_blob_count"]),
        ]
        totals = [left + right for left, right in zip(totals, values)]
        connection.execute(
            """INSERT INTO storage_usage
               (scope, stored_bytes, daily_bytes, daily_count, daily_blob_count, day_key)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (f"user:{int(row['user_id'])}", *values, day_key),
        )
    connection.execute(
        """INSERT INTO storage_usage
           (scope, stored_bytes, daily_bytes, daily_count, daily_blob_count, day_key)
           VALUES ('global', ?, ?, ?, ?, ?)""",
        (*totals, day_key),
    )


def _current_usage(
    connection: sqlite3.Connection,
    scope: str,
    day_key: str,
) -> sqlite3.Row:
    connection.execute(
        """INSERT INTO storage_usage
           (scope, stored_bytes, daily_bytes, daily_count, daily_blob_count, day_key)
           VALUES (?, 0, 0, 0, 0, ?)
           ON CONFLICT(scope) DO NOTHING""",
        (scope, day_key),
    )
    connection.execute(
        """UPDATE storage_usage
           SET daily_bytes=0, daily_count=0, daily_blob_count=0, day_key=?
           WHERE scope=? AND day_key<>?""",
        (day_key, scope, day_key),
    )
    return connection.execute(
        """SELECT stored_bytes, daily_bytes, daily_count, daily_blob_count
           FROM storage_usage WHERE scope=?""",
        (scope,),
    ).fetchone()


def _init_db_once() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT,
                identity_type TEXT,
                institutional_id TEXT,
                real_name TEXT,
                identity_verified INTEGER DEFAULT 0,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                password_salt TEXT,
                role TEXT DEFAULT 'student',
                teacher_approval_status TEXT NOT NULL DEFAULT 'not_required',
                teacher_approval_reviewed_at TEXT,
                session_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT,
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                agent_mode TEXT NOT NULL DEFAULT 'assistant',
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                images_json TEXT NOT NULL DEFAULT '[]',
                visualizations_json TEXT NOT NULL DEFAULT '[]',
                artifacts_json TEXT NOT NULL DEFAULT '[]',
                interaction_id INTEGER,
                parent_message_id INTEGER,
                quoted_message_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_user_id
            ON messages(user_id, id);
            CREATE TABLE IF NOT EXISTS login_rate_limits (
                throttle_key TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL,
                window_started REAL NOT NULL,
                locked_until REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS registration_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_key TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_registration_events_client_time
            ON registration_events(client_key, created_at);
            CREATE TABLE IF NOT EXISTS storage_usage (
                scope TEXT PRIMARY KEY,
                stored_bytes INTEGER NOT NULL DEFAULT 0,
                daily_bytes INTEGER NOT NULL DEFAULT 0,
                daily_count INTEGER NOT NULL DEFAULT 0,
                daily_blob_count INTEGER NOT NULL DEFAULT 0,
                day_key TEXT NOT NULL
            );
            """
        )
        # Hold a write reservation across column discovery and ALTER so two
        # service processes cannot both act on the same stale schema snapshot.
        connection.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        additions = {
            "display_name": "TEXT", "identity_type": "TEXT", "institutional_id": "TEXT",
            "real_name": "TEXT", "identity_verified": "INTEGER DEFAULT 0",
            "password_salt": "TEXT", "role": "TEXT DEFAULT 'student'",
            "teacher_approval_status": "TEXT NOT NULL DEFAULT 'not_required'",
            "teacher_approval_reviewed_at": "TEXT",
            "session_version": "INTEGER NOT NULL DEFAULT 1",
            "last_login": "TEXT", "is_active": "INTEGER DEFAULT 1",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        connection.execute("UPDATE users SET display_name=username WHERE display_name IS NULL OR display_name='' ")
        connection.execute("UPDATE users SET password_salt=salt WHERE password_salt IS NULL OR password_salt='' ")
        connection.execute("UPDATE users SET role='student' WHERE role IS NULL OR role='' ")
        connection.execute(
            """UPDATE users SET teacher_approval_status='approved'
               WHERE identity_type='teacher' AND role IN ('teacher', 'admin')
                 AND teacher_approval_status='not_required'"""
        )
        connection.execute(
            """UPDATE users SET teacher_approval_status='pending'
               WHERE identity_type='teacher' AND COALESCE(identity_verified, 0)=1
                 AND role NOT IN ('teacher', 'admin')
                 AND teacher_approval_status='not_required'"""
        )
        connection.execute("UPDATE users SET is_active=1 WHERE is_active IS NULL")
        connection.execute(
            "UPDATE users SET session_version=1 WHERE session_version IS NULL OR session_version<1"
        )
        message_columns = {row["name"] for row in connection.execute("PRAGMA table_info(messages)")}
        if "interaction_id" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN interaction_id INTEGER")
        if "parent_message_id" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN parent_message_id INTEGER")
        if "quoted_message_id" not in message_columns:
            connection.execute("ALTER TABLE messages ADD COLUMN quoted_message_id INTEGER")
        if "agent_mode" not in message_columns:
            connection.execute(
                "ALTER TABLE messages ADD COLUMN agent_mode "
                "TEXT NOT NULL DEFAULT 'assistant'"
            )
        if "artifacts_json" not in message_columns:
            connection.execute(
                "ALTER TABLE messages ADD COLUMN artifacts_json "
                "TEXT NOT NULL DEFAULT '[]'"
            )
        connection.execute(
            "UPDATE messages SET agent_mode='assistant' "
            "WHERE agent_mode IS NULL OR TRIM(agent_mode)=''"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user_mode_id "
            "ON messages(user_id, agent_mode, id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_parent_id "
            "ON messages(user_id, agent_mode, parent_message_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_quoted_id "
            "ON messages(user_id, agent_mode, quoted_message_id)"
        )
        if connection.execute(
            "SELECT 1 FROM storage_usage WHERE scope='global'"
        ).fetchone() is None:
            _rebuild_storage_usage(connection)
        row_bytes = _MESSAGE_STORED_BYTES_SQL
        new_row_bytes = row_bytes
        old_row_bytes = row_bytes
        for column in ("content", "images_json", "visualizations_json", "artifacts_json"):
            new_row_bytes = new_row_bytes.replace(column, f"NEW.{column}")
            old_row_bytes = old_row_bytes.replace(column, f"OLD.{column}")
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_messages_usage_insert
                AFTER INSERT ON messages
                BEGIN
                  INSERT INTO storage_usage
                    (scope, stored_bytes, daily_bytes, daily_count, daily_blob_count, day_key)
                  VALUES
                    ('global', {new_row_bytes}, {new_row_bytes}, 1,
                     CASE WHEN NEW.images_json<>'[]' OR NEW.artifacts_json<>'[]' THEN 1 ELSE 0 END,
                     date('now', 'localtime'))
                  ON CONFLICT(scope) DO UPDATE SET
                    stored_bytes=storage_usage.stored_bytes+excluded.stored_bytes,
                    daily_bytes=CASE WHEN storage_usage.day_key=excluded.day_key
                                     THEN storage_usage.daily_bytes+excluded.daily_bytes
                                     ELSE excluded.daily_bytes END,
                    daily_count=CASE WHEN storage_usage.day_key=excluded.day_key
                                     THEN storage_usage.daily_count+1 ELSE 1 END,
                    daily_blob_count=CASE WHEN storage_usage.day_key=excluded.day_key
                                     THEN storage_usage.daily_blob_count+excluded.daily_blob_count
                                     ELSE excluded.daily_blob_count END,
                    day_key=excluded.day_key;
                  INSERT INTO storage_usage
                    (scope, stored_bytes, daily_bytes, daily_count, daily_blob_count, day_key)
                  VALUES
                    ('user:' || NEW.user_id, {new_row_bytes}, {new_row_bytes}, 1,
                     CASE WHEN NEW.images_json<>'[]' OR NEW.artifacts_json<>'[]' THEN 1 ELSE 0 END,
                     date('now', 'localtime'))
                  ON CONFLICT(scope) DO UPDATE SET
                    stored_bytes=storage_usage.stored_bytes+excluded.stored_bytes,
                    daily_bytes=CASE WHEN storage_usage.day_key=excluded.day_key
                                     THEN storage_usage.daily_bytes+excluded.daily_bytes
                                     ELSE excluded.daily_bytes END,
                    daily_count=CASE WHEN storage_usage.day_key=excluded.day_key
                                     THEN storage_usage.daily_count+1 ELSE 1 END,
                    daily_blob_count=CASE WHEN storage_usage.day_key=excluded.day_key
                                     THEN storage_usage.daily_blob_count+excluded.daily_blob_count
                                     ELSE excluded.daily_blob_count END,
                    day_key=excluded.day_key;
                END"""
        )
        connection.execute(
            f"""CREATE TRIGGER IF NOT EXISTS trg_messages_usage_delete
                AFTER DELETE ON messages
                BEGIN
                  UPDATE storage_usage SET
                    stored_bytes=MAX(0, stored_bytes-({old_row_bytes})),
                    daily_bytes=CASE WHEN day_key=date('now', 'localtime')
                                          AND date(OLD.created_at, 'localtime')=day_key
                                     THEN MAX(0, daily_bytes-({old_row_bytes})) ELSE daily_bytes END,
                    daily_count=CASE WHEN day_key=date('now', 'localtime')
                                          AND date(OLD.created_at, 'localtime')=day_key
                                     THEN MAX(0, daily_count-1) ELSE daily_count END,
                    daily_blob_count=CASE WHEN day_key=date('now', 'localtime')
                                          AND date(OLD.created_at, 'localtime')=day_key
                                          AND (OLD.images_json<>'[]' OR OLD.artifacts_json<>'[]')
                                     THEN MAX(0, daily_blob_count-1) ELSE daily_blob_count END
                  WHERE scope IN ('global', 'user:' || OLD.user_id);
                END"""
        )


def init_db() -> None:
    """Apply idempotent schema migrations with bounded lock retries."""
    for attempt in range(DB_INIT_ATTEMPTS):
        try:
            _init_db_once()
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).casefold()
            locked = "database is locked" in message or "database table is locked" in message
            if not locked or attempt + 1 >= DB_INIT_ATTEMPTS:
                raise
            time.sleep(min(0.4, 0.05 * (2 ** attempt)))


def _password_hash(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return digest.hex()


def _password_exceeds_byte_limit(password: str) -> bool:
    """Bound password hashing work without materializing attacker-sized UTF-8."""
    try:
        encoded_prefix = password[: PASSWORD_MAX_UTF8_BYTES + 1].encode("utf-8")
    except UnicodeEncodeError:
        return True
    return len(encoded_prefix) > PASSWORD_MAX_UTF8_BYTES


def _reserve_registration_attempt(client_key: str) -> bool:
    now = time.time()
    hashed_client = hashlib.sha256(
        str(client_key or "unknown")[:256].casefold().encode("utf-8", errors="replace")
    ).hexdigest()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM registration_events WHERE created_at<?",
            (now - REGISTRATION_DAY_SECONDS,),
        )
        client_window = connection.execute(
            "SELECT COUNT(*) FROM registration_events WHERE client_key=? AND created_at>=?",
            (hashed_client, now - REGISTRATION_WINDOW_SECONDS),
        ).fetchone()[0]
        client_day = connection.execute(
            "SELECT COUNT(*) FROM registration_events WHERE client_key=? AND created_at>=?",
            (hashed_client, now - REGISTRATION_DAY_SECONDS),
        ).fetchone()[0]
        global_window = connection.execute(
            "SELECT COUNT(*) FROM registration_events WHERE created_at>=?",
            (now - REGISTRATION_WINDOW_SECONDS,),
        ).fetchone()[0]
        global_day = connection.execute(
            "SELECT COUNT(*) FROM registration_events WHERE created_at>=?",
            (now - REGISTRATION_DAY_SECONDS,),
        ).fetchone()[0]
        allowed = (
            int(client_window) < REGISTRATION_CLIENT_WINDOW_LIMIT
            and int(client_day) < REGISTRATION_CLIENT_DAILY_LIMIT
            and int(global_window) < REGISTRATION_GLOBAL_WINDOW_LIMIT
            and int(global_day) < REGISTRATION_GLOBAL_DAILY_LIMIT
        )
        if allowed:
            connection.execute(
                "INSERT INTO registration_events(client_key, created_at) VALUES (?, ?)",
                (hashed_client, now),
            )
        return allowed


def create_user(
    username: str,
    password: str,
    client_key: str = "unknown",
) -> tuple[int | None, str]:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        return None, "用户名需为3–32位中文、字母、数字、下划线或连字符。"
    if len(password) < 8:
        return None, "密码至少需要8个字符。"
    if _password_exceeds_byte_limit(password):
        return None, "密码不能超过256字节。"
    if not _reserve_registration_attempt(client_key):
        return None, "注册请求过于频繁，请稍后再试。"
    try:
        with _connect() as connection:
            username_conflict = connection.execute(
                "SELECT 1 FROM users WHERE username=? LIMIT 1", (username,)
            ).fetchone()
            if username_conflict:
                return None, "该用户名已存在。"
            alias_conflict = connection.execute(
                """SELECT 1 FROM users
                   WHERE COALESCE(is_active, 1) = 1
                     AND COALESCE(identity_verified, 0) = 1
                     AND institutional_id = ?
                   LIMIT 1""",
                (username,),
            ).fetchone()
            if alias_conflict:
                return None, "该用户名已作为学号或工号绑定其他账号。"
            roster_table = connection.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type='table' AND name='identity_roster'"""
            ).fetchone()
            if roster_table:
                roster_conflict = connection.execute(
                    """SELECT 1 FROM identity_roster
                       WHERE is_active=1 AND institutional_id=?
                       LIMIT 1""",
                    (username,),
                ).fetchone()
                if roster_conflict:
                    return None, "该用户名是名册中的学号或工号，请另设用户名后使用编号登录。"
            salt = secrets.token_bytes(16)
            password_hash = _password_hash(password, salt)
            cursor = connection.execute(
                """INSERT INTO users
                   (username, display_name, password_hash, salt, password_salt, role, is_active)
                   VALUES (?, ?, ?, ?, ?, 'student', 1)""",
                (username, username, password_hash, salt.hex(), salt.hex()),
            )
            return int(cursor.lastrowid), "注册成功。"
    except sqlite3.IntegrityError:
        return None, "该用户名已存在。"


def _scoped_login_throttle_key(scope: str, *parts: str) -> str:
    normalized = [str(part or "unknown")[:256].casefold() for part in parts]
    material = "\0".join((scope, *normalized))
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()


def _login_throttle_key(username: str, client_key: str) -> str:
    """Backward-compatible pair bucket used by older callers and tests."""
    return _scoped_login_throttle_key("pair", client_key, username)


def _check_login_throttle(throttle_key: str, now: float) -> None:
    with _connect() as connection:
        row = connection.execute(
            """SELECT failure_count, window_started, locked_until
               FROM login_rate_limits WHERE throttle_key=?""",
            (throttle_key,),
        ).fetchone()
        if not row:
            return
        if float(row["locked_until"] or 0) > now:
            raise LoginRateLimited(int(float(row["locked_until"]) - now + 0.999))
        if now - float(row["window_started"]) > LOGIN_WINDOW_SECONDS:
            connection.execute(
                "DELETE FROM login_rate_limits WHERE throttle_key=?",
                (throttle_key,),
            )


def _record_login_failure(
    throttle_key: str,
    now: float,
    failure_limit: int | None = None,
) -> None:
    if failure_limit is None:
        failure_limit = LOGIN_FAILURE_LIMIT
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT failure_count, window_started
               FROM login_rate_limits WHERE throttle_key=?""",
            (throttle_key,),
        ).fetchone()
        if not row or now - float(row["window_started"]) > LOGIN_WINDOW_SECONDS:
            failure_count = 1
            window_started = now
        else:
            failure_count = int(row["failure_count"]) + 1
            window_started = float(row["window_started"])
        locked_until = now + LOGIN_LOCK_SECONDS if failure_count >= failure_limit else 0
        connection.execute(
            """INSERT INTO login_rate_limits
               (throttle_key, failure_count, window_started, locked_until, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(throttle_key) DO UPDATE SET
                   failure_count=excluded.failure_count,
                   window_started=excluded.window_started,
                   locked_until=excluded.locked_until,
                   updated_at=excluded.updated_at""",
            (throttle_key, failure_count, window_started, locked_until, now),
        )
        connection.execute(
            "DELETE FROM login_rate_limits WHERE updated_at<?",
            (now - 24 * 60 * 60,),
        )


def authenticate(
    username: str,
    password: str,
    client_key: str = "unknown",
) -> tuple[int | None, str | None]:
    login_name = username.strip()
    now = time.time()
    throttle_key = _login_throttle_key(login_name, client_key)
    client_throttle_key = _scoped_login_throttle_key("client", client_key)
    _check_login_throttle(throttle_key, now)
    _check_login_throttle(client_throttle_key, now)
    with _connect() as connection:
        rows = connection.execute(
            """SELECT id, username, password_hash, salt FROM users
               WHERE COALESCE(is_active, 1) = 1
                 AND (
                     username = ?
                     OR (
                         COALESCE(identity_verified, 0) = 1
                         AND institutional_id = ?
                     )
                 )
               ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END, id""",
            (login_name, login_name, login_name),
        ).fetchall()
    account_throttle_key = None
    if len(rows) == 1:
        account_throttle_key = _scoped_login_throttle_key(
            "account", str(rows[0]["username"])
        )
        _check_login_throttle(account_throttle_key, now)
    if _password_exceeds_byte_limit(password):
        # Treat oversized credentials exactly like an ordinary failed login,
        # while never allowing them to reach the expensive PBKDF operation.
        _record_login_failure(throttle_key, now)
        _record_login_failure(
            client_throttle_key, now, LOGIN_CLIENT_FAILURE_LIMIT
        )
        if account_throttle_key is not None:
            _record_login_failure(
                account_throttle_key, now, LOGIN_ACCOUNT_FAILURE_LIMIT
            )
        return None, None
    if len(rows) != 1:
        # Match the expensive password path so account existence is not exposed
        # through a large timing difference.
        _password_hash(password, bytes(16))
        _record_login_failure(throttle_key, now)
        _record_login_failure(
            client_throttle_key, now, LOGIN_CLIENT_FAILURE_LIMIT
        )
        return None, None
    row = rows[0]
    candidate = _password_hash(password, bytes.fromhex(row["salt"]))
    if not hmac.compare_digest(candidate, row["password_hash"]):
        _record_login_failure(throttle_key, now)
        _record_login_failure(
            client_throttle_key, now, LOGIN_CLIENT_FAILURE_LIMIT
        )
        _record_login_failure(
            account_throttle_key, now, LOGIN_ACCOUNT_FAILURE_LIMIT
        )
        return None, None
    with _connect() as connection:
        connection.execute(
            "DELETE FROM login_rate_limits WHERE throttle_key IN (?, ?)",
            (throttle_key, account_throttle_key),
        )
        connection.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), row["id"]),
        )
    return int(row["id"]), str(row["username"])


def _serialize_images(images: list[dict]) -> str:
    if not isinstance(images, list):
        raise ValueError("附件列表格式无效。")
    if len(images) > UPLOAD_MAX_COUNT:
        raise ValueError(f"一次最多上传 {UPLOAD_MAX_COUNT} 个附件。")
    serializable = []
    total_bytes = 0
    for image in images:
        if not isinstance(image, dict):
            raise ValueError("附件格式无效。")
        data = image.get("data", b"")
        if isinstance(data, str):
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError("附件数据不是有效的 Base64。") from exc
        else:
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise ValueError("附件 data 必须是字节数据。")
            raw = bytes(data)
        if len(raw) > UPLOAD_MAX_ITEM_BYTES:
            raise ValueError("单个附件超过 20 MB 限制。")
        total_bytes += len(raw)
        if total_bytes > UPLOAD_MAX_TOTAL_BYTES:
            raise ValueError("附件总大小超过 40 MB 限制。")
        encoded = base64.b64encode(raw).decode("ascii")
        serializable.append({
            "data": encoded,
            "mime": image.get("mime", "image/png"),
            "name": image.get("name", "image.png"),
        })
    return json.dumps(serializable, ensure_ascii=False)


def _deserialize_images(raw: str, include_data: bool = True) -> list[dict]:
    images = []
    for image in json.loads(raw or "[]"):
        item = {key: value for key, value in image.items() if key != "data"}
        if include_data:
            try:
                item["data"] = base64.b64decode(image.get("data", ""))
            except (ValueError, TypeError):
                item["data"] = b""
        images.append(item)
    return images


def _artifact_metadata(artifact: dict) -> tuple[str, str, str]:
    if not isinstance(artifact, dict):
        raise ValueError("考试产物必须是字典。")
    name = str(artifact.get("name", "")).strip()
    if (
        not name
        or len(name) > 160
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 for character in name)
    ):
        raise ValueError("考试产物文件名无效。")
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    mime = str(artifact.get("mime", "")).strip().lower()
    if suffix not in ARTIFACT_ALLOWED_MIMES or mime not in ARTIFACT_ALLOWED_MIMES[suffix]:
        raise ValueError("考试产物仅允许 UTF-8 TeX、PDF 或 ZIP 文件。")
    return name, mime, suffix


def _artifact_payload(artifact: dict, suffix: str) -> bytes:
    data = artifact.get("data", b"")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("考试产物 data 必须是字节数据。")
    payload = bytes(data)
    if not payload:
        raise ValueError("考试产物不能为空。")
    if len(payload) > ARTIFACT_MAX_ITEM_BYTES:
        raise ValueError("单个考试产物超过大小限制。")
    if suffix == ".pdf":
        if not payload.startswith(b"%PDF-"):
            raise ValueError("PDF 产物格式无效。")
    elif suffix == ".zip":
        if not payload.startswith((b"PK\x03\x04", b"PK\x05\x06")):
            raise ValueError("ZIP 产物格式无效。")
    else:
        if b"\x00" in payload:
            raise ValueError("TeX 产物包含无效字节。")
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("TeX 产物必须使用 UTF-8 编码。") from exc
    return payload


def _serialize_artifacts(artifacts: list[dict]) -> str:
    if not isinstance(artifacts, list):
        raise ValueError("考试产物必须使用列表传入。")
    if not artifacts:
        return "[]"
    if len(artifacts) > ARTIFACT_MAX_COUNT:
        raise ValueError("考试产物数量超过限制。")

    serializable: list[dict] = []
    seen_names: set[str] = set()
    total_bytes = 0
    for artifact in artifacts:
        name, mime, suffix = _artifact_metadata(artifact)
        name_key = name.casefold()
        if name_key in seen_names:
            raise ValueError("考试产物文件名不能重复。")
        payload = _artifact_payload(artifact, suffix)
        total_bytes += len(payload)
        if total_bytes > ARTIFACT_MAX_TOTAL_BYTES:
            raise ValueError("考试产物总大小超过限制。")
        serializable.append({
            "name": name,
            "mime": mime,
            "data": base64.b64encode(payload).decode("ascii"),
        })
        seen_names.add(name_key)
    return json.dumps(serializable, ensure_ascii=False, separators=(",", ":"))


def _deserialize_artifacts(raw: str) -> list[dict]:
    try:
        records = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(records, list) or len(records) > ARTIFACT_MAX_COUNT:
        return []

    artifacts: list[dict] = []
    seen_names: set[str] = set()
    total_bytes = 0
    for record in records:
        try:
            name, mime, suffix = _artifact_metadata(record)
            name_key = name.casefold()
            if name_key in seen_names:
                continue
            encoded = record.get("data", "")
            if not isinstance(encoded, str):
                continue
            # Reject oversized database values before allocating their decoded form.
            if len(encoded) > ((ARTIFACT_MAX_ITEM_BYTES + 2) // 3) * 4 + 4:
                continue
            payload = base64.b64decode(encoded, validate=True)
            validated = _artifact_payload({"data": payload}, suffix)
            total_bytes += len(validated)
            if total_bytes > ARTIFACT_MAX_TOTAL_BYTES:
                return []
        except (ValueError, TypeError):
            continue
        artifacts.append({"name": name, "mime": mime, "data": validated})
        seen_names.add(name_key)
    return artifacts


def image_data_url(image: dict) -> str:
    """Return a self-contained raster image URL for proxy-safe chat rendering."""
    data = image.get("data", b"")
    if isinstance(data, str):
        if data.startswith("data:"):
            header, separator, encoded = data.partition(",")
            if (not separator or header not in {
                "data:image/png;base64", "data:image/jpeg;base64",
                "data:image/webp;base64",
            }):
                return ""
            data = encoded
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, TypeError):
            return ""
    else:
        try:
            raw = bytes(data)
        except (TypeError, ValueError):
            return ""
    if not raw or len(raw) > 20 * 1024**2:
        return ""

    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        return ""
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def pdf_attachment_data(attachment: dict) -> bytes:
    """Return validated PDF bytes for a chat upload, or ``b""`` when invalid.

    Uploaded files are persisted in ``images_json`` for backward compatibility.
    This helper deliberately validates the signature again before the bytes are
    offered to the browser as a download, so a misleading MIME type cannot turn
    an arbitrary upload into a PDF attachment.
    """
    data = attachment.get("data", b"")
    if isinstance(data, str):
        if data.startswith("data:"):
            header, separator, encoded = data.partition(",")
            if not separator or header != "data:application/pdf;base64":
                return b""
            data = encoded
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, TypeError):
            return b""
    else:
        try:
            raw = bytes(data)
        except (TypeError, ValueError):
            return b""
    if not raw or len(raw) > UPLOAD_MAX_ITEM_BYTES or not raw.startswith(b"%PDF-"):
        return b""
    return raw


def _normalize_agent_mode(agent_mode: str) -> str:
    mode = str(agent_mode or "").strip()
    if not mode:
        raise ValueError("agent_mode 不能为空。")
    return mode


def save_message(user_id: int, message: dict, agent_mode: str = "assistant") -> int:
    mode = _normalize_agent_mode(agent_mode)
    content = str(message.get("content", ""))
    if len(content.encode("utf-8")) > MESSAGE_MAX_CONTENT_BYTES:
        raise ValueError("单条消息正文超过保存上限。")
    artifacts_json = _serialize_artifacts(message.get("artifacts", []))
    images_json = _serialize_images(message.get("images", []))
    visualizations_json = json.dumps(
        message.get("visualizations", []), ensure_ascii=False
    )
    if len(visualizations_json.encode("utf-8")) > MESSAGE_MAX_VISUALIZATION_BYTES:
        raise ValueError("单条消息的可视化数据超过保存上限。")
    stored_row_bytes = sum(
        len(value.encode("utf-8"))
        for value in (content, images_json, visualizations_json, artifacts_json)
    )
    has_stored_blobs = images_json != "[]" or artifacts_json != "[]"
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(DB_FILE.parent).free < DATABASE_MIN_FREE_BYTES + stored_row_bytes * 2:
        raise ValueError("服务器剩余磁盘空间不足，当前消息未保存。")
    with _connect() as connection:
        # Serialize quota checks with the insert so concurrent tabs cannot
        # reserve the same remaining per-account or global capacity.
        connection.execute("BEGIN IMMEDIATE")
        day_key = datetime.now().date().isoformat()
        usage = _current_usage(connection, f"user:{int(user_id)}", day_key)
        global_usage = _current_usage(connection, "global", day_key)
        if int(usage["stored_bytes"]) + stored_row_bytes > USER_BLOB_TOTAL_STORED_BYTES:
            raise ValueError("该账号保存的对话与文件已达到总容量上限，请先删除旧对话。")
        if int(usage["daily_bytes"]) + stored_row_bytes > USER_BLOB_DAILY_STORED_BYTES:
            raise ValueError("该账号今日保存的对话与文件已达到容量上限，请明日再试。")
        if int(usage["daily_count"]) >= USER_MESSAGE_DAILY_LIMIT:
            raise ValueError("该账号今日保存的消息次数已达到上限。")
        if has_stored_blobs and int(usage["daily_blob_count"]) >= USER_BLOB_DAILY_MESSAGE_LIMIT:
            raise ValueError("该账号今日含附件或文件的消息次数已达到上限。")
        if int(global_usage["daily_bytes"]) + stored_row_bytes > GLOBAL_MESSAGE_DAILY_STORED_BYTES:
            raise ValueError("服务器今日保存容量已达到上限，请稍后再试。")
        if int(global_usage["stored_bytes"]) + stored_row_bytes > DATABASE_MAX_BYTES:
            raise ValueError("服务器历史数据库已达到容量上限，请联系管理员清理。")
        quoted_message_id = message.get("quoted_message_id")
        if quoted_message_id is not None:
            try:
                quoted_message_id = int(quoted_message_id)
            except (TypeError, ValueError):
                quoted_message_id = None
        if quoted_message_id is not None:
            owned_reference = connection.execute(
                """SELECT 1 FROM messages
                   WHERE id = ? AND user_id = ? AND agent_mode = ?
                     AND role = 'assistant'""",
                (quoted_message_id, int(user_id), mode),
            ).fetchone()
            if owned_reference is None:
                quoted_message_id = None
        cursor = connection.execute(
            """
            INSERT INTO messages(
                user_id, agent_mode, role, content, images_json, visualizations_json,
                artifacts_json, interaction_id, parent_message_id, quoted_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                mode,
                message["role"],
                content,
                images_json,
                visualizations_json,
                artifacts_json,
                message.get("interaction_id"),
                message.get("parent_message_id"),
                quoted_message_id,
            ),
        )
        message_id = int(cursor.lastrowid)
        return message_id


def load_messages(
    user_id: int,
    include_image_data: bool = True,
    agent_mode: str = "assistant",
) -> list[dict]:
    mode = _normalize_agent_mode(agent_mode)
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT m.id, m.agent_mode, m.role, m.content, m.images_json,
                   m.visualizations_json, m.artifacts_json, m.interaction_id,
                   m.parent_message_id, m.quoted_message_id, m.created_at,
                   (SELECT substr(q.content, 1, 361) FROM messages AS q
                    WHERE q.id = m.quoted_message_id AND q.user_id = m.user_id
                      AND q.agent_mode = m.agent_mode AND q.role = 'assistant')
                   AS quoted_preview
            FROM messages AS m
            WHERE m.user_id = ? AND m.agent_mode = ? ORDER BY m.id
            """,
            (user_id, mode),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "agent_mode": row["agent_mode"],
            "role": row["role"],
            "content": row["content"],
            "images": _deserialize_images(row["images_json"], include_image_data),
            "visualizations": json.loads(row["visualizations_json"] or "[]"),
            "artifacts": _deserialize_artifacts(row["artifacts_json"]),
            "interaction_id": row["interaction_id"],
            "parent_message_id": row["parent_message_id"],
            "quoted_message_id": row["quoted_message_id"],
            "_quoted_preview": row["quoted_preview"] or "",
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def load_messages_page(
    user_id: int,
    *,
    before_id: int | None = None,
    limit: int = 8,
    agent_mode: str = "assistant",
) -> tuple[list[dict], bool]:
    """Load one newest-first database page and return it in chat order."""
    mode = _normalize_agent_mode(agent_mode)
    page_size = max(1, min(int(limit), 100))
    parameters: list[int | str] = [int(user_id), mode]
    before_clause = ""
    if before_id is not None:
        before_clause = "AND id < ?"
        parameters.append(int(before_id))
    parameters.append(page_size + 1)
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT m.id, m.agent_mode, m.role, m.content, m.visualizations_json,
                   m.interaction_id, m.parent_message_id, m.quoted_message_id,
                   m.created_at,
                   (SELECT substr(q.content, 1, 361) FROM messages AS q
                    WHERE q.id = m.quoted_message_id AND q.user_id = m.user_id
                      AND q.agent_mode = m.agent_mode AND q.role = 'assistant')
                   AS quoted_preview,
                   CASE WHEN COALESCE(TRIM(m.images_json), '[]') <> '[]'
                        THEN 1 ELSE 0 END AS has_images,
                   CASE WHEN COALESCE(TRIM(m.artifacts_json), '[]') <> '[]'
                        THEN 1 ELSE 0 END AS has_artifacts
            FROM messages AS m
            WHERE m.user_id = ? AND m.agent_mode = ? {before_clause}
            ORDER BY m.id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    has_more = len(rows) > page_size
    selected = rows[:page_size]
    messages = [
        {
            "id": row["id"],
            "agent_mode": row["agent_mode"],
            "role": row["role"],
            "content": row["content"],
            "images": [],
            "_has_images": bool(row["has_images"]),
            "visualizations": json.loads(row["visualizations_json"] or "[]"),
            "artifacts": [],
            "_has_artifacts": bool(row["has_artifacts"]),
            "interaction_id": row["interaction_id"],
            "parent_message_id": row["parent_message_id"],
            "quoted_message_id": row["quoted_message_id"],
            "_quoted_preview": row["quoted_preview"] or "",
            "created_at": row["created_at"],
        }
        for row in reversed(selected)
    ]
    return messages, has_more


def load_message_images(
    user_id: int,
    message_id: int,
    agent_mode: str = "assistant",
) -> list[dict]:
    """Decode attachments for one visible message only."""
    mode = _normalize_agent_mode(agent_mode)
    with _connect() as connection:
        row = connection.execute(
            """SELECT images_json FROM messages
               WHERE id = ? AND user_id = ? AND agent_mode = ?""",
            (int(message_id), int(user_id), mode),
        ).fetchone()
    if row is None:
        return []
    return _deserialize_images(row["images_json"])


def load_message_artifacts(
    user_id: int,
    message_id: int,
    agent_mode: str = "assistant",
) -> list[dict]:
    """Decode generated TeX/PDF files for one owned, visible message only."""
    mode = _normalize_agent_mode(agent_mode)
    with _connect() as connection:
        row = connection.execute(
            """SELECT artifacts_json FROM messages
               WHERE id = ? AND user_id = ? AND agent_mode = ?""",
            (int(message_id), int(user_id), mode),
        ).fetchone()
    if row is None:
        return []
    return _deserialize_artifacts(row["artifacts_json"])


def load_message_reference(
    user_id: int,
    message_id: int,
    agent_mode: str = "assistant",
    *,
    include_artifacts: bool = False,
) -> dict | None:
    """Load one owned assistant answer for an explicit history reference."""
    mode = _normalize_agent_mode(agent_mode)
    artifact_projection = (
        "artifacts_json" if include_artifacts else "'[]' AS artifacts_json"
    )
    with _connect() as connection:
        row = connection.execute(
            f"""SELECT id, content, {artifact_projection}, created_at
                FROM messages
                WHERE id = ? AND user_id = ? AND agent_mode = ?
                  AND role = 'assistant'""",
            (int(message_id), int(user_id), mode),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "role": "assistant",
        "content": str(row["content"] or ""),
        "artifacts": _deserialize_artifacts(row["artifacts_json"]),
        "created_at": row["created_at"],
        "agent_mode": mode,
    }


def load_context_messages(
    user_id: int,
    *,
    before_id: int | None = None,
    limit: int = 80,
    agent_mode: str = "assistant",
    include_artifacts: bool = False,
) -> list[dict]:
    """Load recent model context, optionally including prior editable TeX sources."""
    mode = _normalize_agent_mode(agent_mode)
    context_limit = max(2, min(int(limit), 200))
    parameters: list[int | str] = [int(user_id), mode]
    before_clause = ""
    if before_id is not None:
        before_clause = "AND id < ?"
        parameters.append(int(before_id))
    parameters.append(context_limit)
    artifact_projection = (
        "artifacts_json" if include_artifacts else "'[]' AS artifacts_json"
    )
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT role, content, {artifact_projection}
            FROM messages
            WHERE user_id = ? AND agent_mode = ? {before_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    messages = []
    for row in reversed(rows):
        content = str(row["content"] or "")
        if include_artifacts and row["role"] == "assistant":
            tex_sections = []
            for artifact in _deserialize_artifacts(row["artifacts_json"]):
                if not str(artifact.get("name", "")).lower().endswith(".tex"):
                    continue
                try:
                    source = artifact["data"].decode("utf-8")
                except (KeyError, AttributeError, UnicodeDecodeError):
                    continue
                tex_sections.append(
                    f"[上一轮可编辑 TeX 文件：{artifact['name']}]\n"
                    f"```latex\n{source}\n```"
                )
            if tex_sections:
                content = content.rstrip() + "\n\n" + "\n\n".join(tex_sections)
        messages.append({"role": row["role"], "content": content})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


def delete_message(
    user_id: int,
    message_id: int,
    agent_mode: str = "assistant",
) -> bool:
    mode = _normalize_agent_mode(agent_mode)
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM messages WHERE id = ? AND user_id = ? AND agent_mode = ?",
            (message_id, user_id, mode),
        )
        return cursor.rowcount > 0


def _existing_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    if not exists:
        return set()
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _delete_linked_analytics(
    connection: sqlite3.Connection,
    user_id: int,
    agent_mode: str,
    *,
    interaction_ids: list[int] | None = None,
    legacy_questions: list[str] | None = None,
    clear_mode: bool = False,
) -> None:
    """Delete analytics owned by a conversation while sharing its transaction."""
    interaction_columns = _existing_table_columns(connection, "interactions")
    if not interaction_columns or "user_id" not in interaction_columns:
        return

    owned_ids: list[int]
    if clear_mode:
        mode_filter = " AND agent_mode=?" if "agent_mode" in interaction_columns else ""
        params: tuple = (user_id, agent_mode) if mode_filter else (user_id,)
        owned_ids = [
            int(row["id"])
            for row in connection.execute(
                f"SELECT id FROM interactions WHERE user_id=?{mode_filter}",
                params,
            ).fetchall()
        ]
    else:
        candidates = sorted({int(value) for value in (interaction_ids or []) if value})
        owned_ids = []
        if candidates:
            placeholders = ",".join("?" for _ in candidates)
            mode_filter = " AND agent_mode=?" if "agent_mode" in interaction_columns else ""
            params = (user_id, *candidates, agent_mode) if mode_filter else (user_id, *candidates)
            owned_ids = [
                int(row["id"])
                for row in connection.execute(
                    f"""SELECT id FROM interactions
                        WHERE user_id=? AND id IN ({placeholders}){mode_filter}""",
                    params,
                ).fetchall()
            ]

    affected_sessions: list[str] = []
    if owned_ids and "session_id" in interaction_columns:
        placeholders = ",".join("?" for _ in owned_ids)
        affected_sessions = [
            str(row["session_id"])
            for row in connection.execute(
                f"SELECT DISTINCT session_id FROM interactions WHERE id IN ({placeholders})",
                owned_ids,
            ).fetchall()
            if row["session_id"]
        ]

    feedback_columns = _existing_table_columns(connection, "feedback")
    if owned_ids:
        placeholders = ",".join("?" for _ in owned_ids)
        if "interaction_id" in feedback_columns:
            connection.execute(
                f"DELETE FROM feedback WHERE interaction_id IN ({placeholders})",
                owned_ids,
            )
    if clear_mode and "user_id" in feedback_columns:
        connection.execute(
            "DELETE FROM feedback WHERE user_id=? AND interaction_id IS NULL",
            (user_id,),
        )

    error_columns = _existing_table_columns(connection, "error_log")
    if "user_id" in error_columns:
        if clear_mode:
            if "agent_mode" in error_columns:
                connection.execute(
                    """DELETE FROM error_log
                       WHERE user_id=? AND (agent_mode=? OR agent_mode IS NULL)""",
                    (user_id, agent_mode),
                )
            else:
                # Old rows have no mode marker. Removing all of this user's old
                # error details is the only privacy-safe legacy behavior.
                connection.execute("DELETE FROM error_log WHERE user_id=?", (user_id,))
        else:
            predicates = []
            params: list[object] = [user_id]
            if owned_ids and "interaction_id" in error_columns:
                placeholders = ",".join("?" for _ in owned_ids)
                predicates.append(f"interaction_id IN ({placeholders})")
                params.extend(owned_ids)
            questions = sorted({str(value) for value in (legacy_questions or []) if value})
            if questions and "question" in error_columns:
                placeholders = ",".join("?" for _ in questions)
                legacy_predicate = f"question IN ({placeholders})"
                if "interaction_id" in error_columns:
                    legacy_predicate = f"(interaction_id IS NULL AND {legacy_predicate})"
                predicates.append(legacy_predicate)
                params.extend(questions)
            if predicates:
                mode_guard = ""
                if "agent_mode" in error_columns:
                    mode_guard = " AND (agent_mode=? OR agent_mode IS NULL)"
                    params.append(agent_mode)
                connection.execute(
                    f"DELETE FROM error_log WHERE user_id=? AND ({' OR '.join(predicates)}){mode_guard}",
                    params,
                )

    if owned_ids:
        placeholders = ",".join("?" for _ in owned_ids)
        connection.execute(
            f"DELETE FROM interactions WHERE id IN ({placeholders})",
            owned_ids,
        )
    if affected_sessions and _existing_table_columns(connection, "sessions"):
        for session_id in affected_sessions:
            remaining = connection.execute(
                """SELECT COUNT(*) AS questions,
                          COALESCE(SUM(tokens_input), 0) AS tokens_input,
                          COALESCE(SUM(tokens_output), 0) AS tokens_output
                   FROM interactions WHERE session_id=?""",
                (session_id,),
            ).fetchone()
            errors = connection.execute(
                "SELECT COUNT(*) AS errors FROM error_log WHERE session_id=?",
                (session_id,),
            ).fetchone()
            connection.execute(
                """UPDATE sessions
                   SET total_questions=?, total_errors=?,
                       total_tokens_input=?, total_tokens_output=?
                   WHERE session_id=?""",
                (
                    int(remaining["questions"]),
                    int(errors["errors"]),
                    int(remaining["tokens_input"]),
                    int(remaining["tokens_output"]),
                    session_id,
                ),
            )


def delete_unanswered_question(
    user_id: int,
    question_message_id: int,
    agent_mode: str = "assistant",
) -> bool:
    """Delete one user question only when no stored answer belongs to it."""
    user_id = int(user_id)
    question_message_id = int(question_message_id)
    mode = _normalize_agent_mode(agent_mode)
    if user_id <= 0 or question_message_id <= 0:
        return False

    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        question = connection.execute(
            """SELECT id, role FROM messages
               WHERE id = ? AND user_id = ? AND agent_mode = ?""",
            (question_message_id, user_id, mode),
        ).fetchone()
        if question is None or question["role"] != "user":
            return False

        linked_answer = connection.execute(
            """
            SELECT 1 FROM messages
            WHERE user_id = ? AND agent_mode = ?
              AND role = 'assistant' AND parent_message_id = ?
            LIMIT 1
            """,
            (user_id, mode, question_message_id),
        ).fetchone()
        if linked_answer is not None:
            return False

        # Legacy answers may not have parent_message_id. Treat the immediately
        # following unlinked assistant row as this question's answer.
        next_message = connection.execute(
            """
            SELECT role, parent_message_id FROM messages
            WHERE user_id = ? AND agent_mode = ? AND id > ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (user_id, mode, question_message_id),
        ).fetchone()
        if (
            next_message is not None
            and next_message["role"] == "assistant"
            and next_message["parent_message_id"] is None
        ):
            return False

        cursor = connection.execute(
            """DELETE FROM messages
               WHERE id = ? AND user_id = ? AND agent_mode = ? AND role = 'user'""",
            (question_message_id, user_id, mode),
        )
        return cursor.rowcount == 1


def delete_answer_turn(
    user_id: int,
    assistant_message_id: int,
    agent_mode: str = "assistant",
) -> tuple[int, ...]:
    """Delete an answer and its explicitly linked question as one history turn.

    The ownership and role checks are performed inside the same write transaction.
    Returning the deleted database IDs lets the UI remove exactly the same messages
    from its paged in-memory view. Legacy rows without an explicit link fall back to
    the immediately preceding message for the same user.
    """
    user_id = int(user_id)
    assistant_message_id = int(assistant_message_id)
    mode = _normalize_agent_mode(agent_mode)
    if user_id <= 0 or assistant_message_id <= 0:
        return ()

    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        answer = connection.execute(
            """SELECT id, role, content, interaction_id, parent_message_id FROM messages
               WHERE id = ? AND user_id = ? AND agent_mode = ?""",
            (assistant_message_id, user_id, mode),
        ).fetchone()
        if answer is None or answer["role"] != "assistant":
            return ()

        previous = None
        if answer["parent_message_id"] is not None:
            previous = connection.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE id = ? AND user_id = ? AND agent_mode = ? AND id < ?
                """,
                (int(answer["parent_message_id"]), user_id, mode, assistant_message_id),
            ).fetchone()
        else:
            # Legacy rows predate explicit pairing. Their best recoverable link is
            # the immediately preceding message belonging to the same user.
            previous = connection.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE user_id = ? AND agent_mode = ? AND id < ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id, mode, assistant_message_id),
            ).fetchone()
        deleted_ids = [assistant_message_id]
        if previous is not None and previous["role"] == "user":
            deleted_ids.insert(0, int(previous["id"]))

        placeholders = ",".join("?" for _ in deleted_ids)
        cursor = connection.execute(
            f"""DELETE FROM messages
                WHERE user_id = ? AND agent_mode = ? AND id IN ({placeholders})""",
            (user_id, mode, *deleted_ids),
        )
        if cursor.rowcount != len(deleted_ids):
            raise RuntimeError("对话轮次删除不完整，事务已回滚。")
        interaction_ids = []
        if answer["interaction_id"]:
            interaction_ids.append(int(answer["interaction_id"]))
        elif previous is not None and previous["role"] == "user":
            interaction_columns = _existing_table_columns(connection, "interactions")
            if {"user_id", "question", "answer"}.issubset(interaction_columns):
                mode_filter = " AND agent_mode=?" if "agent_mode" in interaction_columns else ""
                params = (
                    (user_id, previous["content"], answer["content"], mode)
                    if mode_filter
                    else (user_id, previous["content"], answer["content"])
                )
                legacy_interaction = connection.execute(
                    f"""SELECT id FROM interactions
                        WHERE user_id=? AND question=? AND answer=?{mode_filter}
                        ORDER BY id DESC LIMIT 1""",
                    params,
                ).fetchone()
                if legacy_interaction:
                    interaction_ids.append(int(legacy_interaction["id"]))
        _delete_linked_analytics(
            connection,
            user_id,
            mode,
            interaction_ids=interaction_ids,
            legacy_questions=(
                [str(previous["content"])]
                if previous is not None and previous["role"] == "user"
                else []
            ),
        )
        return tuple(deleted_ids)


def clear_messages(user_id: int, agent_mode: str = "assistant") -> None:
    mode = _normalize_agent_mode(agent_mode)
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM messages WHERE user_id = ? AND agent_mode = ?",
            (user_id, mode),
        )
        _delete_linked_analytics(
            connection,
            int(user_id),
            mode,
            clear_mode=True,
        )


def messages_to_markdown(messages: list[dict], username: str) -> str:
    lines = [
        "# 大学物理智能助教对话记录",
        "",
        f"- 用户：{username}",
        f"- 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
    ]
    for index, message in enumerate(messages, 1):
        speaker = "用户" if message.get("role") == "user" else "智能助教"
        lines.extend([f"## {index}. {speaker}", ""])
        if message.get("created_at"):
            lines.extend([f"> 时间：{message['created_at']}", ""])
        if message.get("quoted_message_id") is not None:
            lines.extend([
                f"> 引用历史回答：消息 #{int(message['quoted_message_id'])}",
                "",
            ])
        for image in message.get("images", []):
            lines.append(f"> 附图：{image.get('name', 'image.png')}")
        if message.get("images"):
            lines.append("")
        artifact_names = [
            str(artifact.get("name", "")).strip()
            for artifact in message.get("artifacts", [])
            if isinstance(artifact, dict) and str(artifact.get("name", "")).strip()
        ]
        for name in artifact_names:
            lines.append(f"> 生成文件：{name}")
        if artifact_names:
            lines.append("")
        lines.extend([message.get("content", ""), ""])
        if message.get("visualizations"):
            lines.extend([
                "<details><summary>可视化配置</summary>", "", "```json",
                json.dumps(message["visualizations"], ensure_ascii=False, indent=2),
                "```", "", "</details>", "",
            ])
        lines.extend(["---", ""])
    return "\n".join(lines)
