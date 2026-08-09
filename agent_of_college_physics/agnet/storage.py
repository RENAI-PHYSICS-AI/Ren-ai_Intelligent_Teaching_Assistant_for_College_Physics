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
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                images_json TEXT NOT NULL DEFAULT '[]',
                visualizations_json TEXT NOT NULL DEFAULT '[]',
                interaction_id INTEGER,
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
    with _connect() as connection:
        row = connection.execute(
            """SELECT id, username, password_hash, salt FROM users
               WHERE username = ? AND COALESCE(is_active, 1) = 1""",
            (username.strip(),),
        ).fetchone()
    if row is None:
        return None, None
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


def save_message(user_id: int, message: dict) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages(user_id, role, content, images_json, visualizations_json, interaction_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                message["role"],
                message.get("content", ""),
                _serialize_images(message.get("images", [])),
                json.dumps(message.get("visualizations", []), ensure_ascii=False),
                message.get("interaction_id"),
            ),
        )
        message_id = int(cursor.lastrowid)
        return message_id


def load_messages(user_id: int, include_image_data: bool = True) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, images_json, visualizations_json, interaction_id, created_at
            FROM messages WHERE user_id = ? ORDER BY id
            """,
            (user_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "images": _deserialize_images(row["images_json"], include_image_data),
            "visualizations": json.loads(row["visualizations_json"] or "[]"),
            "interaction_id": row["interaction_id"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def load_messages_page(
    user_id: int,
    *,
    before_id: int | None = None,
    limit: int = 8,
) -> tuple[list[dict], bool]:
    """Load one newest-first database page and return it in chat order."""
    page_size = max(1, min(int(limit), 100))
    parameters: list[int] = [int(user_id)]
    before_clause = ""
    if before_id is not None:
        before_clause = "AND id < ?"
        parameters.append(int(before_id))
    parameters.append(page_size + 1)
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, role, content, visualizations_json, interaction_id, created_at,
                   CASE WHEN COALESCE(TRIM(images_json), '[]') <> '[]'
                        THEN 1 ELSE 0 END AS has_images
            FROM messages
            WHERE user_id = ? {before_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    has_more = len(rows) > page_size
    selected = rows[:page_size]
    messages = [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "images": [],
            "_has_images": bool(row["has_images"]),
            "visualizations": json.loads(row["visualizations_json"] or "[]"),
            "interaction_id": row["interaction_id"],
            "created_at": row["created_at"],
        }
        for row in reversed(selected)
    ]
    return messages, has_more


def load_message_images(user_id: int, message_id: int) -> list[dict]:
    """Decode attachments for one visible message only."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT images_json FROM messages WHERE id = ? AND user_id = ?",
            (int(message_id), int(user_id)),
        ).fetchone()
    if row is None:
        return []
    return _deserialize_images(row["images_json"])


def load_context_messages(
    user_id: int,
    *,
    before_id: int | None = None,
    limit: int = 80,
) -> list[dict]:
    """Load recent text-only messages for the model without UI media payloads."""
    context_limit = max(2, min(int(limit), 200))
    parameters: list[int] = [int(user_id)]
    before_clause = ""
    if before_id is not None:
        before_clause = "AND id < ?"
        parameters.append(int(before_id))
    parameters.append(context_limit)
    with _connect() as connection:
        rows = connection.execute(
            f"""
            SELECT role, content
            FROM messages
            WHERE user_id = ? {before_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    messages = [
        {"role": row["role"], "content": row["content"]}
        for row in reversed(rows)
    ]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages


def delete_message(user_id: int, message_id: int) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM messages WHERE id = ? AND user_id = ?",
            (message_id, user_id),
        )
        return cursor.rowcount > 0


def clear_messages(user_id: int) -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))


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
        for image in message.get("images", []):
            lines.append(f"> 附图：{image.get('name', 'image.png')}")
        if message.get("images"):
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
