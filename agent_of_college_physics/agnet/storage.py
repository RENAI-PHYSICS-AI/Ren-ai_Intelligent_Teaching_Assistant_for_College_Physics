from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from config import APP_DIR


DB_FILE = APP_DIR / "data" / "assistant.db"
USERNAME_RE = re.compile(r"^[\w\-\u4e00-\u9fff]{3,32}$")
ARTIFACT_MAX_COUNT = 8
ARTIFACT_MAX_ITEM_BYTES = 8 * 1024**2
ARTIFACT_MAX_TOTAL_BYTES = 16 * 1024**2
UPLOAD_MAX_ITEM_BYTES = 20 * 1024**2
ARTIFACT_ALLOWED_MIMES = {
    ".tex": frozenset({"text/x-tex", "application/x-tex"}),
    ".pdf": frozenset({"application/pdf"}),
    ".zip": frozenset({"application/zip"}),
}


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
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
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        additions = {
            "display_name": "TEXT", "identity_type": "TEXT", "institutional_id": "TEXT",
            "real_name": "TEXT", "identity_verified": "INTEGER DEFAULT 0",
            "password_salt": "TEXT", "role": "TEXT DEFAULT 'student'",
            "last_login": "TEXT", "is_active": "INTEGER DEFAULT 1",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        connection.execute("UPDATE users SET display_name=username WHERE display_name IS NULL OR display_name='' ")
        connection.execute("UPDATE users SET password_salt=salt WHERE password_salt IS NULL OR password_salt='' ")
        connection.execute("UPDATE users SET role='student' WHERE role IS NULL OR role='' ")
        connection.execute("UPDATE users SET is_active=1 WHERE is_active IS NULL")
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


def _password_hash(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return digest.hex()


def create_user(username: str, password: str) -> tuple[int | None, str]:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        return None, "用户名需为3–32位中文、字母、数字、下划线或连字符。"
    if len(password) < 8:
        return None, "密码至少需要8个字符。"
    salt = secrets.token_bytes(16)
    try:
        with _connect() as connection:
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
            cursor = connection.execute(
                """INSERT INTO users
                   (username, display_name, password_hash, salt, password_salt, role, is_active)
                   VALUES (?, ?, ?, ?, ?, 'student', 1)""",
                (username, username, _password_hash(password, salt), salt.hex(), salt.hex()),
            )
            return int(cursor.lastrowid), "注册成功。"
    except sqlite3.IntegrityError:
        return None, "该用户名已存在。"


def authenticate(username: str, password: str) -> tuple[int | None, str | None]:
    login_name = username.strip()
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
    if len(rows) != 1:
        return None, None
    row = rows[0]
    candidate = _password_hash(password, bytes.fromhex(row["salt"]))
    if not hmac.compare_digest(candidate, row["password_hash"]):
        return None, None
    with _connect() as connection:
        connection.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), row["id"]),
        )
    return int(row["id"]), str(row["username"])


def _serialize_images(images: list[dict]) -> str:
    serializable = []
    for image in images:
        data = image.get("data", b"")
        if isinstance(data, str):
            encoded = data
        else:
            encoded = base64.b64encode(data).decode("ascii")
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
    artifacts_json = _serialize_artifacts(message.get("artifacts", []))
    with _connect() as connection:
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
                message.get("content", ""),
                _serialize_images(message.get("images", [])),
                json.dumps(message.get("visualizations", []), ensure_ascii=False),
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
            """SELECT id, role, parent_message_id FROM messages
               WHERE id = ? AND user_id = ? AND agent_mode = ?""",
            (assistant_message_id, user_id, mode),
        ).fetchone()
        if answer is None or answer["role"] != "assistant":
            return ()

        previous = None
        if answer["parent_message_id"] is not None:
            previous = connection.execute(
                """
                SELECT id, role
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
                SELECT id, role
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
        return tuple(deleted_ids)


def clear_messages(user_id: int, agent_mode: str = "assistant") -> None:
    mode = _normalize_agent_mode(agent_mode)
    with _connect() as connection:
        connection.execute(
            "DELETE FROM messages WHERE user_id = ? AND agent_mode = ?",
            (user_id, mode),
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
