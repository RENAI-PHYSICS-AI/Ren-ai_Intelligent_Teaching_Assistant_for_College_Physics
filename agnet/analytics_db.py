"""大学物理智能助教的用户、问答、反馈与学情分析数据库。"""
import sqlite3
import json
import logging
import time
import uuid
import hashlib
import secrets as py_secrets
from datetime import datetime
from config import APP_DIR

DB_PATH = str(APP_DIR / "data" / "assistant.db")
DB_BUSY_TIMEOUT_MS = 5_000
DB_INIT_ATTEMPTS = 4

# Analytics must never be an unbounded duplicate of conversation storage.
# Anonymous payloads are deliberately much smaller because no account quota can
# be applied to them; authenticated payloads still have a finite persistence cap.
ANONYMOUS_QUESTION_MAX_BYTES = 4 * 1024
ANONYMOUS_ANSWER_MAX_BYTES = 16 * 1024
AUTHENTICATED_QUESTION_MAX_BYTES = 64 * 1024
AUTHENTICATED_ANSWER_MAX_BYTES = 256 * 1024
ANONYMOUS_ERROR_MESSAGE_MAX_BYTES = 4 * 1024
ANONYMOUS_TRACEBACK_MAX_BYTES = 8 * 1024
AUTHENTICATED_ERROR_MESSAGE_MAX_BYTES = 16 * 1024
AUTHENTICATED_TRACEBACK_MAX_BYTES = 64 * 1024
ANONYMOUS_METADATA_MAX_BYTES = 8 * 1024
AUTHENTICATED_METADATA_MAX_BYTES = 32 * 1024
ANONYMOUS_FEEDBACK_MAX_BYTES = 2 * 1024
AUTHENTICATED_FEEDBACK_MAX_BYTES = 8 * 1024
ANALYTICS_IDENTIFIER_MAX_BYTES = 512

_TRUNCATION_SUFFIX = "\n[内容已截断]"
_LOGGER = logging.getLogger(__name__)
_RECOVERABLE_SQLITE_CODES = {
    getattr(sqlite3, "SQLITE_BUSY", 5),
    getattr(sqlite3, "SQLITE_LOCKED", 6),
    getattr(sqlite3, "SQLITE_FULL", 13),
}


def _database_is_locked(exc: BaseException) -> bool:
    message = str(exc).casefold()
    return "database is locked" in message or "database table is locked" in message


def _is_recoverable_analytics_write_error(exc: BaseException) -> bool:
    """Return whether a best-effort analytics write may safely be dropped."""
    error_code = getattr(exc, "sqlite_errorcode", None)
    if isinstance(error_code, int) and (error_code & 0xFF) in _RECOVERABLE_SQLITE_CODES:
        return True
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in (
            "database is locked",
            "database table is locked",
            "database is busy",
            "database or disk is full",
            "database is full",
        )
    )


def _truncate_utf8(value, max_bytes):
    """Bound persisted text by UTF-8 bytes without cutting a code point."""
    if value is None:
        return None
    text = str(value)
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    suffix = _TRUNCATION_SUFFIX.encode("utf-8")
    if max_bytes <= len(suffix):
        return suffix[:max_bytes].decode("utf-8", errors="ignore")
    prefix = encoded[: max_bytes - len(suffix)].decode("utf-8", errors="ignore")
    return prefix + _TRUNCATION_SUFFIX


def _analytics_payload_limit(user_id, anonymous_limit, authenticated_limit):
    return authenticated_limit if user_id else anonymous_limit


def _bounded_json(value, max_bytes):
    if not value:
        return None
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    encoded = serialized.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return serialized
    # Preserve valid JSON so dashboard readers never have to parse a cut token.
    return json.dumps(
        {"truncated": True, "original_bytes": len(encoded)},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _rollback_quietly(conn):
    if conn is None:
        return
    try:
        conn.rollback()
    except sqlite3.Error:
        pass


def _close_quietly(conn):
    if conn is None:
        return
    try:
        conn.close()
    except sqlite3.Error:
        pass


def _run_analytics_write(operation_name, operation, fallback=None):
    """Commit one best-effort analytics write and always release its connection."""
    conn = None
    try:
        conn = _get_conn()
        result = operation(conn)
        conn.commit()
        return result
    except Exception as exc:
        _rollback_quietly(conn)
        if isinstance(exc, sqlite3.Error) and _is_recoverable_analytics_write_error(exc):
            # Do not include exception text: it may contain a database path.
            _LOGGER.warning(
                "Analytics write '%s' skipped because SQLite is busy or full.",
                operation_name,
            )
            return fallback
        raise
    finally:
        _close_quietly(conn)


def _get_conn():
    (APP_DIR / "data").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=DB_BUSY_TIMEOUT_MS / 1000)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except Exception:
        conn.close()
        raise


def _hash_password(password, salt=None):
    if salt is None:
        salt = py_secrets.token_hex(16)
    try:
        salt_bytes = bytes.fromhex(salt)
    except ValueError:
        salt_bytes = salt.encode("utf-8")
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        240_000,
    ).hex()
    return salt, hashed


def _ensure_column(conn, table, column, definition):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _init_db_once(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT,
            identity_type TEXT,
            institutional_id TEXT,
            real_name TEXT,
            identity_verified INTEGER DEFAULT 0,
            salt TEXT,
            password_salt TEXT,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            teacher_approval_status TEXT NOT NULL DEFAULT 'not_required',
            teacher_approval_reviewed_at TEXT,
            session_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS identity_roster (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_type TEXT NOT NULL,
            institutional_id TEXT NOT NULL,
            real_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            bound_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            bound_at TEXT,
            UNIQUE(identity_type, institutional_id),
            FOREIGN KEY (bound_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent_mode TEXT NOT NULL DEFAULT 'assistant',
            timestamp TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT,
            chapter TEXT,
            provider TEXT,
            model TEXT,
            tokens_input INTEGER DEFAULT 0,
            tokens_output INTEGER DEFAULT 0,
            response_time_ms INTEGER DEFAULT 0,
            error TEXT,
            feedback TEXT,
            rag_chunks_used TEXT,
            question_length INTEGER DEFAULT 0,
            answer_length INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            start_time TEXT NOT NULL,
            end_time TEXT,
            total_questions INTEGER DEFAULT 0,
            total_errors INTEGER DEFAULT 0,
            total_tokens_input INTEGER DEFAULT 0,
            total_tokens_output INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            timestamp TEXT NOT NULL,
            question TEXT,
            error_type TEXT,
            error_message TEXT,
            traceback TEXT,
            interaction_id INTEGER,
            agent_mode TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interaction_id INTEGER,
            session_id TEXT,
            timestamp TEXT NOT NULL,
            rating TEXT NOT NULL,
            comment TEXT,
            FOREIGN KEY (interaction_id) REFERENCES interactions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_interactions_session ON interactions(session_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_chapter ON interactions(chapter);
        CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp);
        CREATE INDEX IF NOT EXISTS idx_errors_timestamp ON error_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
    """)
    # Serialize schema inspection and ALTER statements.  Without this write
    # reservation, two fresh processes can both observe a missing column and
    # then race to add it.
    conn.execute("BEGIN IMMEDIATE")
    _ensure_column(conn, "sessions", "user_id", "INTEGER")
    _ensure_column(conn, "sessions", "last_seen", "TEXT")
    _ensure_column(conn, "interactions", "user_id", "INTEGER")
    _ensure_column(conn, "interactions", "timing_details", "TEXT")
    _ensure_column(
        conn,
        "interactions",
        "agent_mode",
        "TEXT NOT NULL DEFAULT 'assistant'",
    )
    _ensure_column(conn, "error_log", "user_id", "INTEGER")
    _ensure_column(conn, "error_log", "interaction_id", "INTEGER")
    _ensure_column(conn, "error_log", "agent_mode", "TEXT")
    _ensure_column(conn, "feedback", "user_id", "INTEGER")
    _ensure_column(conn, "users", "identity_type", "TEXT")
    _ensure_column(conn, "users", "institutional_id", "TEXT")
    _ensure_column(conn, "users", "real_name", "TEXT")
    _ensure_column(conn, "users", "identity_verified", "INTEGER DEFAULT 0")
    _ensure_column(conn, "users", "display_name", "TEXT")
    _ensure_column(conn, "users", "salt", "TEXT")
    _ensure_column(conn, "users", "password_salt", "TEXT")
    _ensure_column(conn, "users", "role", "TEXT DEFAULT 'student'")
    _ensure_column(
        conn,
        "users",
        "teacher_approval_status",
        "TEXT NOT NULL DEFAULT 'not_required'",
    )
    _ensure_column(conn, "users", "teacher_approval_reviewed_at", "TEXT")
    _ensure_column(conn, "users", "session_version", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(conn, "users", "last_login", "TEXT")
    _ensure_column(conn, "users", "is_active", "INTEGER DEFAULT 1")
    # Compatibility with accounts created by the original lightweight user system.
    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "salt" in user_columns:
        conn.execute("UPDATE users SET password_salt=salt WHERE password_salt IS NULL OR password_salt='' ")
        conn.execute("UPDATE users SET salt=password_salt WHERE salt IS NULL OR salt='' ")
    conn.execute("UPDATE users SET display_name=username WHERE display_name IS NULL OR display_name='' ")
    conn.execute("UPDATE users SET role='student' WHERE role IS NULL OR role='' ")
    # Existing verified teacher accounts predate the approval workflow and are
    # grandfathered in. Newly claimed teacher identities are stored as pending.
    conn.execute(
        """UPDATE users SET teacher_approval_status='approved'
           WHERE identity_type='teacher' AND role IN ('teacher', 'admin')
             AND teacher_approval_status='not_required'"""
    )
    conn.execute(
        """UPDATE users SET teacher_approval_status='pending'
           WHERE identity_type='teacher' AND COALESCE(identity_verified, 0)=1
             AND role NOT IN ('teacher', 'admin')
             AND teacher_approval_status='not_required'"""
    )
    conn.execute("UPDATE users SET is_active=1 WHERE is_active IS NULL")
    conn.execute("UPDATE users SET session_version=1 WHERE session_version IS NULL OR session_version<1")
    conn.execute(
        "UPDATE interactions SET agent_mode='assistant' "
        "WHERE agent_mode IS NULL OR TRIM(agent_mode)=''"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_roster_identity ON identity_roster(identity_type, institutional_id)")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_users_verified_identity
           ON users(identity_type, institutional_id)
           WHERE institutional_id IS NOT NULL AND TRIM(institutional_id) <> ''"""
    )
    # One-time compatibility migration: turn existing saved chat pairs into
    # analytics interactions and retain the link for per-answer feedback.
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "messages" in tables:
        message_columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
        if "interaction_id" in message_columns:
            agent_mode_select = (
                "agent_mode" if "agent_mode" in message_columns
                else "'assistant' AS agent_mode"
            )
            rows = conn.execute(
                f"""SELECT id, user_id, agent_mode, role, content, created_at,
                           interaction_id
                    FROM (
                        SELECT id, user_id, {agent_mode_select}, role, content,
                               created_at, interaction_id
                        FROM messages
                    )
                    ORDER BY user_id, agent_mode, id"""
            ).fetchall()
            pending_questions = {}
            migrated_counts = {}
            for message in rows:
                user_id = message["user_id"]
                agent_mode = str(message["agent_mode"] or "assistant").strip() or "assistant"
                pending_key = (user_id, agent_mode)
                if message["role"] == "user":
                    pending_questions[pending_key] = message
                    continue
                question = pending_questions.pop(pending_key, None)
                if not question or message["interaction_id"]:
                    continue
                session_id = f"legacy_user_{user_id}"
                conn.execute(
                    """INSERT OR IGNORE INTO sessions
                       (session_id, start_time, end_time, last_seen, user_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session_id, question["created_at"], message["created_at"], message["created_at"], user_id),
                )
                cursor = conn.execute(
                    """INSERT INTO interactions
                       (session_id, agent_mode, timestamp, question, answer,
                        chapter, provider, model,
                        tokens_input, tokens_output, response_time_ms, question_length,
                        answer_length, user_id)
                       VALUES (?, ?, ?, ?, ?, '历史记录', 'legacy', '历史导入',
                               ?, ?, 0, ?, ?, ?)""",
                    (session_id, agent_mode, message["created_at"],
                     question["content"], message["content"],
                     max(1, len(question["content"]) // 4), max(1, len(message["content"]) // 4),
                     len(question["content"]), len(message["content"]), user_id),
                )
                conn.execute(
                    "UPDATE messages SET interaction_id=? WHERE id=?",
                    (cursor.lastrowid, message["id"]),
                )
                migrated_counts[session_id] = migrated_counts.get(session_id, 0) + 1
            for session_id, count in migrated_counts.items():
                conn.execute(
                    "UPDATE sessions SET total_questions=? WHERE session_id=?",
                    (count, session_id),
                )
    conn.commit()


def init_db():
    """Apply idempotent schema migrations with bounded lock retries."""
    for attempt in range(DB_INIT_ATTEMPTS):
        conn = None
        try:
            conn = _get_conn()
            _init_db_once(conn)
            return
        except sqlite3.OperationalError as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            if not _database_is_locked(exc) or attempt + 1 >= DB_INIT_ATTEMPTS:
                raise
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            raise
        finally:
            if conn is not None:
                conn.close()
        time.sleep(min(0.4, 0.05 * (2 ** attempt)))


def _normalize_real_name(value):
    return "".join((value or "").split())


def _username_conflicts_with_verified_id(conn, username, exclude_user_id=None):
    params = [str(username or "").strip()]
    exclusion = ""
    if exclude_user_id is not None:
        exclusion = " AND id<>?"
        params.append(int(exclude_user_id))
    return conn.execute(
        f"""SELECT 1 FROM users
            WHERE is_active=1 AND COALESCE(identity_verified, 0)=1
              AND institutional_id=?{exclusion}
            LIMIT 1""",
        params,
    ).fetchone() is not None


def _institutional_id_conflicts_with_account(conn, institutional_id, exclude_user_id=None):
    params = [str(institutional_id or "").strip(), str(institutional_id or "").strip()]
    exclusion = ""
    if exclude_user_id is not None:
        exclusion = " AND id<>?"
        params.append(int(exclude_user_id))
    return conn.execute(
        f"""SELECT 1 FROM users
            WHERE is_active=1
              AND (username=? OR (COALESCE(identity_verified, 0)=1 AND institutional_id=?))
              {exclusion}
            LIMIT 1""",
        params,
    ).fetchone() is not None


def _username_conflicts_with_roster_id(conn, username):
    return conn.execute(
        """SELECT 1 FROM identity_roster
           WHERE is_active=1 AND institutional_id=?
           LIMIT 1""",
        (str(username or "").strip(),),
    ).fetchone() is not None


def upsert_identity_roster(entries):
    """Add or update unbound student/teacher identities from the admin page."""
    conn = _get_conn()
    result = {"added": 0, "updated": 0, "unchanged": 0, "errors": []}
    now = datetime.now().isoformat()
    try:
        for index, entry in enumerate(entries, start=1):
            identity_type = str(entry.get("identity_type", "")).strip().lower()
            institutional_id = str(entry.get("institutional_id", "")).strip()
            real_name = str(entry.get("real_name", "")).strip()
            if identity_type not in {"student", "teacher"}:
                result["errors"].append(f"第 {index} 行身份类型无效")
                continue
            if not institutional_id or not real_name:
                result["errors"].append(f"第 {index} 行编号或姓名为空")
                continue
            if len(institutional_id) > 64 or len(real_name) > 64:
                result["errors"].append(f"第 {index} 行编号或姓名过长")
                continue

            cross_type = conn.execute(
                """SELECT identity_type FROM identity_roster
                   WHERE institutional_id=? AND identity_type<>? AND is_active=1
                   LIMIT 1""",
                (institutional_id, identity_type),
            ).fetchone()
            if cross_type:
                result["errors"].append(f"第 {index} 行编号已用于另一身份类型")
                continue

            existing = conn.execute(
                """SELECT id, real_name, bound_user_id FROM identity_roster
                   WHERE identity_type=? AND institutional_id=?""",
                (identity_type, institutional_id),
            ).fetchone()
            username_conflict = conn.execute(
                """SELECT id FROM users
                   WHERE is_active=1 AND username=?
                   LIMIT 1""",
                (institutional_id,),
            ).fetchone()
            if username_conflict and (
                not existing or existing["bound_user_id"] != username_conflict["id"]
            ):
                result["errors"].append(f"第 {index} 行编号与现有用户名冲突")
                continue
            if existing and existing["bound_user_id"]:
                if _normalize_real_name(existing["real_name"]) != _normalize_real_name(real_name):
                    result["errors"].append(f"第 {index} 行编号已绑定，不能修改姓名")
                else:
                    result["unchanged"] += 1
                continue
            if existing:
                conn.execute(
                    """UPDATE identity_roster SET real_name=?, is_active=1, updated_at=?
                       WHERE id=?""",
                    (real_name, now, existing["id"]),
                )
                result["updated"] += 1
            else:
                conn.execute(
                    """INSERT INTO identity_roster
                       (identity_type, institutional_id, real_name, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (identity_type, institutional_id, real_name, now, now),
                )
                result["added"] += 1
        conn.commit()
    finally:
        conn.close()
    return result


def update_identity_roster_entry(roster_id, identity_type, institutional_id, real_name):
    """Edit one unbound roster entry and return a small result object."""
    identity_type = str(identity_type or "").strip().lower()
    institutional_id = str(institutional_id or "").strip()
    real_name = str(real_name or "").strip()
    if identity_type not in {"student", "teacher"} or not institutional_id or not real_name:
        raise ValueError("身份类型、编号和姓名不能为空")
    if len(institutional_id) > 64 or len(real_name) > 64:
        raise ValueError("编号或姓名过长")
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT bound_user_id FROM identity_roster WHERE id=? AND is_active=1",
            (int(roster_id),),
        ).fetchone()
        if not row:
            raise LookupError("名册记录不存在")
        if row["bound_user_id"]:
            raise PermissionError("已绑定账号的名册记录不能修改")
        username_conflict = conn.execute(
            "SELECT id FROM users WHERE is_active=1 AND username=? LIMIT 1",
            (institutional_id,),
        ).fetchone()
        if username_conflict:
            raise ValueError("该学号或工号与现有用户名冲突")
        duplicate = conn.execute(
            "SELECT id FROM identity_roster WHERE institutional_id=? AND id<>? AND is_active=1",
            (institutional_id, int(roster_id)),
        ).fetchone()
        if duplicate:
            raise ValueError("该学号或工号已经存在")
        conn.execute(
            "UPDATE identity_roster SET identity_type=?, institutional_id=?, real_name=?, is_active=1, updated_at=? WHERE id=?",
            (identity_type, institutional_id, real_name, datetime.now().isoformat(), int(roster_id)),
        )
        conn.commit()
        return {"updated": True}
    finally:
        conn.close()


def delete_identity_roster_entry(roster_id):
    """Delete one unbound roster entry; bound identities are protected."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT bound_user_id FROM identity_roster WHERE id=? AND is_active=1",
            (int(roster_id),),
        ).fetchone()
        if not row:
            raise LookupError("名册记录不存在")
        if row["bound_user_id"]:
            raise PermissionError("已绑定账号的名册记录不能删除")
        conn.execute("DELETE FROM identity_roster WHERE id=?", (int(roster_id),))
        conn.commit()
        return {"deleted": True}
    finally:
        conn.close()


def get_identity_roster_stats(limit=1000):
    conn = _get_conn()
    counts = conn.execute(
        """SELECT identity_type, COUNT(*) AS total,
                  SUM(CASE WHEN bound_user_id IS NOT NULL THEN 1 ELSE 0 END) AS bound
           FROM identity_roster WHERE is_active=1 GROUP BY identity_type"""
    ).fetchall()
    rows = conn.execute(
        """SELECT r.id, r.identity_type, r.institutional_id, r.real_name, r.is_active,
                  r.bound_at, u.username, u.teacher_approval_status
           FROM identity_roster r
           LEFT JOIN users u ON u.id = r.bound_user_id
           ORDER BY r.identity_type, r.institutional_id
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    summary = {
        "student_total": 0,
        "student_bound": 0,
        "teacher_total": 0,
        "teacher_bound": 0,
        "teacher_pending": 0,
    }
    for row in counts:
        prefix = row["identity_type"]
        if prefix in {"student", "teacher"}:
            summary[f"{prefix}_total"] = int(row["total"] or 0)
            summary[f"{prefix}_bound"] = int(row["bound"] or 0)
    summary["list"] = [dict(row) for row in rows]
    summary["teacher_pending"] = sum(
        1
        for row in rows
        if row["identity_type"] == "teacher"
        and row["teacher_approval_status"] == "pending"
    )
    return summary


def create_user(username, password, display_name="", identity_type="", institutional_id="", real_name=""):
    username = (username or "").strip()
    display_name = (display_name or "").strip() or username
    identity_type = (identity_type or "").strip().lower()
    institutional_id = (institutional_id or "").strip()
    real_name = (real_name or "").strip()
    wants_identity_binding = bool(identity_type or institutional_id or real_name)
    if not username:
        raise ValueError("用户名不能为空")
    if len(username) < 3:
        raise ValueError("用户名至少需要 3 个字符")
    if not password or len(password) < 6:
        raise ValueError("密码至少需要 6 个字符")
    if wants_identity_binding:
        if identity_type not in {"student", "teacher"}:
            raise ValueError("请选择学生或教师身份")
        if not institutional_id:
            raise ValueError("学号或工号不能为空")
        if not real_name:
            raise ValueError("姓名不能为空")

    salt, password_hash = _hash_password(password)
    conn = _get_conn()
    try:
        if _username_conflicts_with_verified_id(conn, username):
            raise ValueError("该用户名已作为学号或工号绑定其他账号")
        if (
            _username_conflicts_with_roster_id(conn, username)
            and (not wants_identity_binding or username != institutional_id)
        ):
            raise ValueError("该用户名是名册中的学号或工号，请另设用户名后使用编号登录")
        if not wants_identity_binding:
            cur = conn.execute(
                """INSERT INTO users
                   (username, display_name, identity_verified, salt, password_salt,
                    password_hash, role, created_at)
                   VALUES (?, ?, 0, ?, ?, ?, 'student', ?)""",
                (username, display_name, salt, salt, password_hash, datetime.now().isoformat()),
            )
            conn.commit()
            user_id = cur.lastrowid
            return get_user_by_id(user_id)

        if _institutional_id_conflicts_with_account(conn, institutional_id):
            raise ValueError("该学号或工号与其他账号的登录标识冲突")
        roster = conn.execute(
            """SELECT id, real_name, bound_user_id FROM identity_roster
               WHERE identity_type=? AND institutional_id=? AND is_active=1""",
            (identity_type, institutional_id),
        ).fetchone()
        identity_label = "学号" if identity_type == "student" else "工号"
        if not roster:
            raise ValueError(f"{identity_label}不在有效名册中")
        if _normalize_real_name(roster["real_name"]) != _normalize_real_name(real_name):
            raise ValueError(f"姓名与{identity_label}不匹配")
        if roster["bound_user_id"]:
            raise ValueError(f"该{identity_label}已经绑定账号")

        role = "student"
        approval_status = "pending" if identity_type == "teacher" else "not_required"
        display_name = real_name
        cur = conn.execute(
            """INSERT INTO users
                (username, display_name, identity_type, institutional_id, real_name,
                 identity_verified, salt, password_salt, password_hash, role,
                 teacher_approval_status, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
            (username, display_name, identity_type, institutional_id, real_name,
             salt, salt, password_hash, role, approval_status, datetime.now().isoformat()),
        )
        user_id = cur.lastrowid
        conn.execute(
            """UPDATE identity_roster SET bound_user_id=?, bound_at=?, updated_at=?
               WHERE id=? AND bound_user_id IS NULL""",
            (user_id, datetime.now().isoformat(), datetime.now().isoformat(), roster["id"]),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("用户名或学号/工号已被注册")
    except ValueError:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_user_by_id(user_id)


def ensure_admin_user(username, password, display_name="管理员", update_password=False):
    """Create the configured administrator account without storing plaintext credentials."""
    username = (username or "").strip()
    password = password or ""
    display_name = (display_name or "").strip() or username
    if not username or len(username) < 3:
        raise ValueError("管理员用户名无效")
    if len(password) < 12:
        raise ValueError("管理员凭据长度不足")

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, role, display_name, is_active FROM users WHERE username=?",
            (username,),
        ).fetchone()
        if _username_conflicts_with_verified_id(
            conn, username, row["id"] if row else None
        ):
            raise ValueError("管理员用户名已作为学号或工号绑定其他账号")
        if _username_conflicts_with_roster_id(conn, username):
            raise ValueError("管理员用户名不能使用名册中的学号或工号")
        if row:
            if row["role"] != "admin":
                raise ValueError("管理员用户名已被普通用户占用")
            if update_password:
                salt, password_hash = _hash_password(password)
                conn.execute(
                    """UPDATE users SET display_name=?, is_active=1, salt=?,
                              password_salt=?, password_hash=?,
                              session_version=COALESCE(session_version, 1)+1
                       WHERE id=?""",
                    (display_name, salt, salt, password_hash, row["id"]),
                )
                conn.commit()
            elif row["display_name"] != display_name or not row["is_active"]:
                conn.execute(
                    "UPDATE users SET display_name=?, is_active=1 WHERE id=?",
                    (display_name, row["id"]),
                )
                conn.commit()
            return get_user_by_id(row["id"])

        salt, password_hash = _hash_password(password)
        cur = conn.execute(
            """INSERT INTO users
                (username, display_name, identity_verified, salt, password_salt,
                 password_hash, role, created_at, is_active)
                VALUES (?, ?, 0, ?, ?, ?, 'admin', ?, 1)""",
            (username, display_name, salt, salt, password_hash, datetime.now().isoformat()),
        )
        conn.commit()
        return get_user_by_id(cur.lastrowid)
    finally:
        conn.close()


def get_user_by_username(username):
    conn = _get_conn()
    row = conn.execute(
        """SELECT id, username, display_name, role, identity_type, institutional_id,
                  real_name, identity_verified, teacher_approval_status,
                  teacher_approval_reviewed_at, session_version,
                  created_at, last_login, is_active
           FROM users WHERE username=?""",
        ((username or "").strip(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def bind_user_identity(
    user_id,
    identity_type,
    institutional_id,
    real_name,
    *,
    allow_teacher_claim=False,
):
    """Bind an existing account to one active roster identity."""
    identity_type = (identity_type or "").strip().lower()
    institutional_id = (institutional_id or "").strip()
    real_name = (real_name or "").strip()
    if not user_id:
        raise ValueError("用户账号无效")
    if identity_type not in {"student", "teacher"}:
        raise ValueError("请选择学生或教师身份")
    if identity_type == "teacher" and not allow_teacher_claim:
        raise ValueError("教师账号由管理员预置；如需绑定，请联系管理员核验。")
    if not institutional_id or not real_name:
        raise ValueError("学号或工号、姓名不能为空")

    conn = _get_conn()
    try:
        user = conn.execute(
            "SELECT id, identity_verified FROM users WHERE id=? AND is_active=1",
            (user_id,),
        ).fetchone()
        if not user:
            raise ValueError("用户账号不存在或已停用")
        if user["identity_verified"]:
            raise ValueError("该账号已经完成身份核验")

        if _institutional_id_conflicts_with_account(conn, institutional_id, user_id):
            raise ValueError("该学号或工号与其他账号的登录标识冲突")

        roster = conn.execute(
            """SELECT id, real_name, bound_user_id FROM identity_roster
               WHERE identity_type=? AND institutional_id=? AND is_active=1""",
            (identity_type, institutional_id),
        ).fetchone()
        identity_label = "学号" if identity_type == "student" else "工号"
        if not roster:
            raise ValueError(f"{identity_label}不在有效名册中")
        if _normalize_real_name(roster["real_name"]) != _normalize_real_name(real_name):
            raise ValueError(f"姓名与{identity_label}不匹配")
        if roster["bound_user_id"] and roster["bound_user_id"] != user_id:
            raise ValueError(f"该{identity_label}已经绑定其他账号")

        role = "student"
        approval_status = "pending" if identity_type == "teacher" else "not_required"
        now = datetime.now().isoformat()
        conn.execute(
            """UPDATE users SET display_name=?, identity_type=?, institutional_id=?,
                      real_name=?, identity_verified=1, role=?,
                      teacher_approval_status=?, teacher_approval_reviewed_at=NULL
               WHERE id=?""",
            (
                real_name,
                identity_type,
                institutional_id,
                real_name,
                role,
                approval_status,
                user_id,
            ),
        )
        conn.execute(
            """UPDATE identity_roster SET bound_user_id=?, bound_at=?, updated_at=?
               WHERE id=? AND (bound_user_id IS NULL OR bound_user_id=?)""",
            (user_id, now, now, roster["id"], user_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("该学号或工号已经绑定其他账号")
    except ValueError:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_user_by_id(user_id)


def get_pending_teacher_approvals(limit=500):
    """Return verified teacher claims that still need an administrator decision."""
    safe_limit = max(1, min(int(limit), 1000))
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, username, display_name, institutional_id, real_name,
                  created_at, teacher_approval_status
           FROM users
           WHERE is_active=1 AND identity_type='teacher'
             AND COALESCE(identity_verified, 0)=1
             AND teacher_approval_status='pending'
           ORDER BY created_at, id
           LIMIT ?""",
        (safe_limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def review_teacher_approval(user_id, decision):
    """Approve or reject one verified teacher claim in a single transaction."""
    normalized = str(decision or "").strip().lower()
    if normalized not in {"approve", "reject"}:
        raise ValueError("审批结果必须为 approve 或 reject")
    try:
        requested_user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("用户账号无效") from exc

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        account = conn.execute(
            """SELECT id, role, identity_type, institutional_id,
                      identity_verified, is_active, teacher_approval_status
               FROM users WHERE id=?""",
            (requested_user_id,),
        ).fetchone()
        if not account:
            raise LookupError("待审批账号不存在")
        if (
            not account["is_active"]
            or account["identity_type"] != "teacher"
            or not account["identity_verified"]
        ):
            raise ValueError("该账号不是有效的教师身份申请")
        if account["role"] == "admin":
            raise PermissionError("管理员账号不能通过教师审批接口变更")
        if account["teacher_approval_status"] != "pending":
            raise ValueError("该教师身份申请已经处理，不能重复审批")

        next_status = "approved" if normalized == "approve" else "rejected"
        next_role = "teacher" if normalized == "approve" else "student"
        now = datetime.now().isoformat()
        if normalized == "reject":
            # Release the roster identity so a mistaken or fraudulent claim does
            # not permanently prevent the real teacher from binding it.
            conn.execute(
                """UPDATE identity_roster
                   SET bound_user_id=NULL, bound_at=NULL, updated_at=?
                   WHERE bound_user_id=? AND identity_type='teacher'""",
                (now, requested_user_id),
            )
        conn.execute(
            """UPDATE users
               SET role=?, teacher_approval_status=?,
                   teacher_approval_reviewed_at=?,
                   session_version=session_version + ?,
                   identity_type=CASE WHEN ?='rejected' THEN NULL ELSE identity_type END,
                   institutional_id=CASE WHEN ?='rejected' THEN NULL ELSE institutional_id END,
                   real_name=CASE WHEN ?='rejected' THEN NULL ELSE real_name END,
                   identity_verified=CASE WHEN ?='rejected' THEN 0 ELSE identity_verified END
               WHERE id=? AND teacher_approval_status='pending'""",
            (
                next_role,
                next_status,
                now,
                1 if normalized == "reject" else 0,
                next_status,
                next_status,
                next_status,
                next_status,
                requested_user_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_user_by_id(requested_user_id)


def provision_unbound_teacher_accounts(initial_password):
    """Create and bind one account per active, unbound teacher roster row.

    The operation is all-or-nothing.  Each account uses its institutional ID
    as the canonical username and receives an independently salted password
    hash, even though the supplied initial password is shared.
    """
    initial_password = initial_password or ""
    if len(initial_password) < 8:
        raise ValueError("教师初始密码至少需要 8 个字符")

    conn = _get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        roster_rows = conn.execute(
            """SELECT id, institutional_id, real_name
               FROM identity_roster
               WHERE identity_type='teacher' AND is_active=1
                 AND bound_user_id IS NULL
               ORDER BY institutional_id"""
        ).fetchall()

        # Complete every conflict check before writing the first account so a
        # stale username or alias cannot leave a partially provisioned class.
        for roster in roster_rows:
            institutional_id = str(roster["institutional_id"] or "").strip()
            if not institutional_id:
                raise ValueError("教师名册中存在空工号")
            username_conflict = conn.execute(
                "SELECT id FROM users WHERE username=? LIMIT 1",
                (institutional_id,),
            ).fetchone()
            if username_conflict:
                raise ValueError(f"工号 {institutional_id} 已被用作用户名")
            if _institutional_id_conflicts_with_account(conn, institutional_id):
                raise ValueError(f"工号 {institutional_id} 与现有登录标识冲突")

        created = []
        now = datetime.now().isoformat()
        for roster in roster_rows:
            institutional_id = str(roster["institutional_id"]).strip()
            real_name = str(roster["real_name"] or "").strip()
            salt, password_hash = _hash_password(initial_password)
            cursor = conn.execute(
                """INSERT INTO users
                   (username, display_name, identity_type, institutional_id,
                    real_name, identity_verified, salt, password_salt,
                    password_hash, role, teacher_approval_status, created_at, is_active)
                   VALUES (?, ?, 'teacher', ?, ?, 1, ?, ?, ?, 'teacher',
                           'approved', ?, 1)""",
                (
                    institutional_id,
                    real_name or institutional_id,
                    institutional_id,
                    real_name,
                    salt,
                    salt,
                    password_hash,
                    now,
                ),
            )
            user_id = int(cursor.lastrowid)
            update = conn.execute(
                """UPDATE identity_roster
                   SET bound_user_id=?, bound_at=?, updated_at=?
                   WHERE id=? AND bound_user_id IS NULL""",
                (user_id, now, now, int(roster["id"])),
            )
            if update.rowcount != 1:
                raise RuntimeError(f"工号 {institutional_id} 的名册绑定状态已变化")
            created.append(
                {
                    "user_id": user_id,
                    "username": institutional_id,
                    "institutional_id": institutional_id,
                    "real_name": real_name,
                }
            )
        conn.commit()
        return created
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def authenticate_user(username, password):
    login_name = (username or "").strip()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM users
           WHERE is_active=1
             AND (
                 username=?
                 OR (COALESCE(identity_verified, 0)=1 AND institutional_id=?)
             )
           ORDER BY CASE WHEN username=? THEN 0 ELSE 1 END, id""",
        (login_name, login_name, login_name),
    ).fetchall()
    if len(rows) != 1:
        conn.close()
        return None
    row = rows[0]
    _, password_hash = _hash_password(password or "", row["password_salt"])
    if not py_secrets.compare_digest(password_hash, row["password_hash"]):
        conn.close()
        return None
    conn.execute(
        "UPDATE users SET last_login=? WHERE id=?",
        (datetime.now().isoformat(), row["id"]),
    )
    conn.commit()
    conn.close()
    return get_user_by_id(row["id"])


def get_user_by_id(user_id):
    conn = _get_conn()
    row = conn.execute(
        """SELECT id, username, display_name, role, identity_type, institutional_id,
                  real_name, identity_verified, teacher_approval_status,
                  teacher_approval_reviewed_at, session_version,
                  created_at, last_login, is_active
           FROM users WHERE id=?""",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def start_session(user_id=None):
    sid = datetime.now().strftime("ses_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    now = datetime.now().isoformat()

    def write(conn):
        conn.execute(
            "INSERT INTO sessions (session_id, start_time, last_seen, user_id) VALUES (?, ?, ?, ?)",
            (sid, now, now, user_id),
        )
        return True

    # Keep returning the server-generated id if analytics is temporarily
    # unavailable. Callers can continue the user request, while later logging
    # attempts remain correlated by the same id.
    _run_analytics_write("start_session", write, fallback=False)
    return sid


def touch_session(session_id):
    if not session_id:
        return False
    bounded_session_id = _truncate_utf8(session_id, ANALYTICS_IDENTIFIER_MAX_BYTES)

    def write(conn):
        cursor = conn.execute(
            "UPDATE sessions SET last_seen=? WHERE session_id=? AND end_time IS NULL",
            (datetime.now().isoformat(), bounded_session_id),
        )
        return cursor.rowcount > 0

    return _run_analytics_write("touch_session", write, fallback=False)


def get_active_session_count(active_minutes=5):
    conn = _get_conn()
    cutoff = datetime.fromtimestamp(time.time() - active_minutes * 60).isoformat()
    count = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE end_time IS NULL AND COALESCE(last_seen, start_time) >= ?",
        (cutoff,),
    ).fetchone()[0]
    conn.close()
    return count


def end_session(session_id, total_q, total_err, ti, to):
    if not session_id:
        return False
    bounded_session_id = _truncate_utf8(session_id, ANALYTICS_IDENTIFIER_MAX_BYTES)

    def write(conn):
        cursor = conn.execute(
            """UPDATE sessions SET end_time=?, total_questions=?, total_errors=?,
               total_tokens_input=?, total_tokens_output=?
               WHERE session_id=?""",
            (datetime.now().isoformat(), total_q, total_err, ti, to, bounded_session_id),
        )
        return cursor.rowcount > 0

    return _run_analytics_write("end_session", write, fallback=False)


def log_interaction(session_id, question, answer, chapter, provider, model,
                    tokens_input, tokens_output, response_time_ms, error=None,
                    rag_chunks=None, user_id=None, request_timing=None,
                    agent_mode="assistant"):
    agent_mode = _truncate_utf8(
        str(agent_mode or "").strip(),
        ANALYTICS_IDENTIFIER_MAX_BYTES,
    )
    if not agent_mode:
        raise ValueError("agent_mode 不能为空。")
    question_text = "" if question is None else str(question)
    answer_text = None if answer is None else str(answer)
    question_length = len(question_text)
    answer_length = len(answer_text) if answer_text else 0
    question_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_QUESTION_MAX_BYTES,
        AUTHENTICATED_QUESTION_MAX_BYTES,
    )
    answer_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_ANSWER_MAX_BYTES,
        AUTHENTICATED_ANSWER_MAX_BYTES,
    )
    error_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_ERROR_MESSAGE_MAX_BYTES,
        AUTHENTICATED_ERROR_MESSAGE_MAX_BYTES,
    )
    metadata_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_METADATA_MAX_BYTES,
        AUTHENTICATED_METADATA_MAX_BYTES,
    )
    timing_details = None
    if request_timing:
        timing_details = _bounded_json(
            {key: round(float(value) * 1000, 1) for key, value in request_timing.items()},
            metadata_limit,
        )

    values = (
        _truncate_utf8(session_id or "", ANALYTICS_IDENTIFIER_MAX_BYTES),
        agent_mode,
        datetime.now().isoformat(),
        _truncate_utf8(question_text, question_limit),
        _truncate_utf8(answer_text, answer_limit),
        _truncate_utf8(chapter, ANALYTICS_IDENTIFIER_MAX_BYTES),
        _truncate_utf8(provider, ANALYTICS_IDENTIFIER_MAX_BYTES),
        _truncate_utf8(model, ANALYTICS_IDENTIFIER_MAX_BYTES),
        tokens_input,
        tokens_output,
        response_time_ms,
        _truncate_utf8(error, error_limit),
        _bounded_json(rag_chunks, metadata_limit),
        question_length,
        answer_length,
        user_id,
        timing_details,
    )

    def write(conn):
        cursor = conn.execute(
            """INSERT INTO interactions
               (session_id, agent_mode, timestamp, question, answer, chapter, provider, model,
                tokens_input, tokens_output, response_time_ms, error,
                rag_chunks_used, question_length, answer_length, user_id, timing_details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        return cursor.lastrowid

    return _run_analytics_write("log_interaction", write, fallback=None)


def get_recent_response_timings(limit=30):
    """Return per-stage response timings for the administrator dashboard."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT i.timestamp, i.question, i.model, i.response_time_ms,
                  i.timing_details, u.username, u.display_name
           FROM interactions i
           LEFT JOIN users u ON u.id = i.user_id
           WHERE i.timing_details IS NOT NULL AND TRIM(i.timing_details) <> ''
           ORDER BY i.timestamp DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["timings"] = json.loads(item.pop("timing_details") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["timings"] = {}
            item.pop("timing_details", None)
        result.append(item)
    return result


def log_error(
    session_id,
    question,
    error_type,
    error_message,
    traceback_str="",
    user_id=None,
    interaction_id=None,
    agent_mode="assistant",
):
    normalized_mode = _truncate_utf8(
        str(agent_mode or "").strip() or "assistant",
        ANALYTICS_IDENTIFIER_MAX_BYTES,
    )
    question_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_QUESTION_MAX_BYTES,
        AUTHENTICATED_QUESTION_MAX_BYTES,
    )
    error_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_ERROR_MESSAGE_MAX_BYTES,
        AUTHENTICATED_ERROR_MESSAGE_MAX_BYTES,
    )
    traceback_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_TRACEBACK_MAX_BYTES,
        AUTHENTICATED_TRACEBACK_MAX_BYTES,
    )
    values = (
        _truncate_utf8(session_id, ANALYTICS_IDENTIFIER_MAX_BYTES),
        datetime.now().isoformat(),
        _truncate_utf8(question, question_limit),
        _truncate_utf8(error_type, ANALYTICS_IDENTIFIER_MAX_BYTES),
        _truncate_utf8(error_message, error_limit),
        _truncate_utf8(traceback_str, traceback_limit),
        user_id,
        interaction_id,
        normalized_mode,
    )

    def write(conn):
        conn.execute(
            """INSERT INTO error_log
               (session_id, timestamp, question, error_type, error_message, traceback,
                user_id, interaction_id, agent_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        return True

    return _run_analytics_write("log_error", write, fallback=False)


def log_feedback(interaction_id, session_id, rating, comment="", user_id=None):
    comment_limit = _analytics_payload_limit(
        user_id,
        ANONYMOUS_FEEDBACK_MAX_BYTES,
        AUTHENTICATED_FEEDBACK_MAX_BYTES,
    )
    values = (
        interaction_id,
        _truncate_utf8(session_id, ANALYTICS_IDENTIFIER_MAX_BYTES),
        datetime.now().isoformat(),
        _truncate_utf8(rating, ANALYTICS_IDENTIFIER_MAX_BYTES),
        _truncate_utf8(comment, comment_limit),
        user_id,
    )

    def write(conn):
        conn.execute(
            "INSERT INTO feedback (interaction_id, session_id, timestamp, rating, comment, user_id) VALUES (?, ?, ?, ?, ?, ?)",
            values,
        )
        return True

    return _run_analytics_write("log_feedback", write, fallback=False)


def delete_interaction(interaction_id, user_id):
    """Delete one conversation record only when it belongs to the user."""
    if not interaction_id or not user_id:
        return False
    def write(conn):
        conn.execute(
            "DELETE FROM feedback WHERE interaction_id=? AND user_id=?",
            (interaction_id, user_id),
        )
        cursor = conn.execute(
            "DELETE FROM interactions WHERE id=? AND user_id=?",
            (interaction_id, user_id),
        )
        return cursor.rowcount > 0

    return _run_analytics_write("delete_interaction", write, fallback=False)


def get_user_recent_interactions(user_id, limit=20):
    """Return recent successful interactions for restoring a user's chat history."""
    if not user_id:
        return []
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, timestamp, question, answer, chapter
           FROM interactions
           WHERE user_id=? AND question IS NOT NULL AND answer IS NOT NULL
           ORDER BY timestamp DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_user_interaction_count(user_id):
    if not user_id:
        return 0
    conn = _get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM interactions WHERE user_id=?",
        (user_id,),
    ).fetchone()[0]
    conn.close()
    return count


def get_user_interactions(user_id):
    """Return all successful conversation records belonging to one user."""
    if not user_id:
        return []
    conn = _get_conn()
    rows = conn.execute(
        """SELECT timestamp, question, answer, chapter
           FROM interactions
           WHERE user_id=? AND question IS NOT NULL AND answer IS NOT NULL
           ORDER BY timestamp ASC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ==================== Analytics Queries ====================

def get_chapter_stats():
    """各章节提问统计"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT chapter, COUNT(*) as cnt, SUM(tokens_input) as ti, SUM(tokens_output) as to_tokens FROM interactions WHERE chapter IS NOT NULL GROUP BY chapter ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_error_stats():
    """错误统计"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT error_type, COUNT(*) as cnt FROM error_log GROUP BY error_type ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_stats():
    """每日用量统计"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT date(timestamp) as day, COUNT(*) as questions, SUM(tokens_input) as ti, SUM(tokens_output) as to_tokens FROM interactions GROUP BY day ORDER BY day DESC LIMIT 30"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_errors(limit=20):
    """最近错误"""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT e.timestamp, e.question, e.error_type, e.error_message, e.traceback,
                  u.username, u.display_name
           FROM error_log e
           LEFT JOIN users u ON u.id = e.user_id
           ORDER BY e.timestamp DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unanswered_questions():
    """未回答成功的问题（有错误的）"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT question, error, timestamp, chapter FROM interactions WHERE error IS NOT NULL ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_total_stats():
    """总体统计"""
    conn = _get_conn()
    total_q = conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
    total_err = conn.execute("SELECT COUNT(*) FROM interactions WHERE error IS NOT NULL").fetchone()[0]
    total_ti = conn.execute("SELECT COALESCE(SUM(tokens_input),0) FROM interactions").fetchone()[0]
    total_to = conn.execute("SELECT COALESCE(SUM(tokens_output),0) FROM interactions").fetchone()[0]
    sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()
    return {
        "total_questions": total_q,
        "total_errors": total_err,
        "error_rate": f"{total_err/max(total_q,1)*100:.1f}%",
        "total_input_tokens": total_ti,
        "total_output_tokens": total_to,
        "total_sessions": sessions,
    }


def get_feedback_stats():
    """反馈统计"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT rating, COUNT(*) as cnt FROM feedback GROUP BY rating"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_feedback(limit=30):
    """Return recent detailed feedback for the administrator dashboard."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT f.timestamp, f.rating, f.comment, u.username, u.display_name
           FROM feedback f
           LEFT JOIN users u ON u.id = f.user_id
           WHERE f.comment IS NOT NULL AND TRIM(f.comment) <> ''
           ORDER BY f.timestamp DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_stats():
    """用户统计"""
    conn = _get_conn()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM sessions WHERE user_id IS NOT NULL").fetchone()[0]
    total_logins = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id IS NOT NULL").fetchone()[0]
    recent_users = conn.execute(
        """SELECT id, username, display_name, role, identity_type, institutional_id,
                  real_name, identity_verified, teacher_approval_status,
                  teacher_approval_reviewed_at, created_at, last_login
           FROM users
           ORDER BY COALESCE(last_login, created_at) DESC
           LIMIT 20"""
    ).fetchall()
    user_list = conn.execute(
        """SELECT u.id, u.username, u.display_name, u.role, u.identity_type,
                  u.institutional_id, u.real_name, u.identity_verified, u.created_at,
                  u.last_login, u.is_active, u.teacher_approval_status,
                  u.teacher_approval_reviewed_at,
                  COUNT(s.session_id) AS login_count,
                  MAX(s.start_time) AS last_session
           FROM users u
           LEFT JOIN sessions s ON s.user_id = u.id
           GROUP BY u.id
           ORDER BY COALESCE(u.last_login, u.created_at) DESC
           LIMIT 500"""
    ).fetchall()
    login_daily = conn.execute(
        """SELECT date(start_time) AS day,
                  COUNT(*) AS logins,
                  COUNT(DISTINCT user_id) AS users
           FROM sessions
           WHERE user_id IS NOT NULL
           GROUP BY date(start_time)
           ORDER BY day DESC
           LIMIT 30"""
    ).fetchall()
    conn.close()
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_logins": total_logins,
        "recent": [dict(r) for r in recent_users],
        "list": [dict(r) for r in user_list],
        "login_daily": [dict(r) for r in login_daily],
    }


def get_learning_analytics():
    """Aggregate registered-user activity for the administrator dashboard."""
    conn = _get_conn()
    learner_rows = conn.execute(
        """
        WITH interaction_stats AS (
            SELECT user_id,
                   COUNT(*) AS question_count,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS error_count,
                   COUNT(DISTINCT date(timestamp)) AS learning_days,
                   COUNT(DISTINCT CASE
                       WHEN chapter IS NOT NULL AND TRIM(chapter) <> '' THEN chapter
                   END) AS chapters_covered,
                   MIN(timestamp) AS first_question,
                   MAX(timestamp) AS last_question,
                   ROUND(AVG(CASE WHEN response_time_ms > 0 THEN response_time_ms END)) AS avg_response_ms
            FROM interactions
            WHERE user_id IS NOT NULL
            GROUP BY user_id
        ),
        session_stats AS (
            SELECT user_id,
                   COUNT(*) AS session_count,
                   MAX(COALESCE(last_seen, start_time)) AS last_session
            FROM sessions
            WHERE user_id IS NOT NULL
            GROUP BY user_id
        ),
        feedback_stats AS (
            SELECT user_id,
                   SUM(CASE WHEN rating = 'good' THEN 1 ELSE 0 END) AS good_feedback,
                   SUM(CASE WHEN rating = 'bad' THEN 1 ELSE 0 END) AS bad_feedback
            FROM feedback
            WHERE user_id IS NOT NULL
            GROUP BY user_id
        )
        SELECT u.id, u.username, u.display_name, u.identity_type, u.institutional_id,
               u.real_name, u.identity_verified, u.created_at, u.last_login,
               COALESCE(i.question_count, 0) AS question_count,
               COALESCE(i.error_count, 0) AS error_count,
               COALESCE(i.learning_days, 0) AS learning_days,
               COALESCE(i.chapters_covered, 0) AS chapters_covered,
               COALESCE(s.session_count, 0) AS session_count,
               COALESCE(i.avg_response_ms, 0) AS avg_response_ms,
               COALESCE(f.good_feedback, 0) AS good_feedback,
               COALESCE(f.bad_feedback, 0) AS bad_feedback,
               i.first_question,
               COALESCE(
                   NULLIF(MAX(
                       COALESCE(i.last_question, ''),
                       COALESCE(s.last_session, ''),
                       COALESCE(u.last_login, '')
                   ), ''),
                   u.created_at
               ) AS last_activity
        FROM users u
        LEFT JOIN interaction_stats i ON i.user_id = u.id
        LEFT JOIN session_stats s ON s.user_id = u.id
        LEFT JOIN feedback_stats f ON f.user_id = u.id
        WHERE u.is_active = 1 AND u.role = 'student'
        ORDER BY last_activity DESC, u.id DESC
        """
    ).fetchall()

    chapter_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(chapter), ''), '未分类') AS chapter,
               COUNT(*) AS question_count,
               COUNT(DISTINCT user_id) AS learner_count,
               SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS error_count,
               COUNT(DISTINCT date(timestamp)) AS active_days,
               ROUND(AVG(CASE WHEN response_time_ms > 0 THEN response_time_ms END)) AS avg_response_ms
        FROM interactions i
        JOIN users u ON u.id = i.user_id AND u.role = 'student'
        WHERE i.user_id IS NOT NULL
        GROUP BY COALESCE(NULLIF(TRIM(chapter), ''), '未分类')
        ORDER BY question_count DESC, chapter ASC
        """
    ).fetchall()

    daily_rows = conn.execute(
        """
        SELECT date(i.timestamp) AS day,
               COUNT(*) AS question_count,
               COUNT(DISTINCT i.user_id) AS learner_count,
               SUM(CASE WHEN i.error IS NOT NULL THEN 1 ELSE 0 END) AS error_count
        FROM interactions i
        JOIN users u ON u.id = i.user_id AND u.role = 'student'
        WHERE i.user_id IS NOT NULL
          AND date(i.timestamp) >= date('now', '-29 days')
        GROUP BY date(i.timestamp)
        ORDER BY day ASC
        """
    ).fetchall()

    overview = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM users WHERE is_active = 1 AND role = 'student') AS registered_learners,
            (SELECT COUNT(DISTINCT i.user_id) FROM interactions i JOIN users u ON u.id=i.user_id
             WHERE u.role='student' AND i.timestamp >= datetime('now', '-7 days')) AS active_7d,
            (SELECT COUNT(DISTINCT i.user_id) FROM interactions i JOIN users u ON u.id=i.user_id
             WHERE u.role='student' AND i.timestamp >= datetime('now', '-30 days')) AS active_30d,
            (SELECT COUNT(*) FROM interactions i JOIN users u ON u.id=i.user_id
             WHERE u.role='student') AS registered_questions,
            (SELECT COUNT(DISTINCT i.user_id) FROM interactions i JOIN users u ON u.id=i.user_id
             WHERE u.role='student') AS engaged_learners
        """
    ).fetchone()
    conn.close()

    learners = []
    attention = []
    now = datetime.now()
    for raw_row in learner_rows:
        row = dict(raw_row)
        questions = int(row["question_count"] or 0)
        errors = int(row["error_count"] or 0)
        row["error_rate"] = round(errors * 100 / questions, 1) if questions else 0.0
        try:
            last_activity = datetime.fromisoformat(row["last_activity"])
            row["days_since_activity"] = max((now - last_activity).days, 0)
        except (TypeError, ValueError):
            row["days_since_activity"] = None

        reason = ""
        if questions == 0:
            reason = "尚未开始提问"
        elif row["days_since_activity"] is not None and row["days_since_activity"] >= 14:
            reason = "连续 14 天未学习"
        elif questions >= 3 and row["error_rate"] >= 30:
            reason = "问答请求失败率较高"
        elif row["bad_feedback"] >= 2 and row["bad_feedback"] > row["good_feedback"]:
            reason = "负向反馈较多"
        row["attention_reason"] = reason
        row["status"] = "attention" if reason else "active"
        learners.append(row)
        if reason:
            attention.append(row)

    overview_data = dict(overview)
    engaged = int(overview_data["engaged_learners"] or 0)
    overview_data["avg_questions_per_learner"] = round(
        int(overview_data["registered_questions"] or 0) / engaged, 1
    ) if engaged else 0.0
    overview_data["attention_count"] = len(attention)

    chapters = []
    for raw_row in chapter_rows:
        row = dict(raw_row)
        questions = int(row["question_count"] or 0)
        errors = int(row["error_count"] or 0)
        row["error_rate"] = round(errors * 100 / questions, 1) if questions else 0.0
        chapters.append(row)

    return {
        "overview": overview_data,
        "learners": learners,
        "attention": attention,
        "chapters": chapters,
        "daily": [dict(row) for row in daily_rows],
        "attention_rules": [
            "尚未开始提问",
            "连续 14 天未学习",
            "至少提问 3 次且问答请求失败率不低于 30%",
            "负向反馈不少于 2 次且多于正向反馈",
        ],
    }


if __name__ == "__main__":
    init_db()
