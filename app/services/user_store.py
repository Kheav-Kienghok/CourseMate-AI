from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


# Database file stored at the project root
_DB_PATH = Path(__file__).resolve().parents[2] / "coursemate.sqlite3"


def _get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection.

    The connection is not cached so that each call is short-lived and safe
    across threads used by python-telegram-bot.
    """

    # Ensure parent directory exists (it should, as it's the project root)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(_DB_PATH)


def _init_db() -> None:
    """Create the user token table if it does not exist."""

    conn = _get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_canvas_tokens (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                token TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


# Initialize database schema at import time
_init_db()


def set_user_canvas_token(
    telegram_user_id: int, username: Optional[str], token: str
) -> None:
    """Create or update the Canvas API token for a Telegram user.

    The token is stored locally in a SQLite database file. It is not
    encrypted, so make sure the host machine is trusted.
    """

    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO user_canvas_tokens (telegram_user_id, username, token)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username=excluded.username,
                token=excluded.token,
                updated_at=CURRENT_TIMESTAMP
            """,
            (telegram_user_id, username, token),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_canvas_token(telegram_user_id: int) -> Optional[str]:
    """Return the stored Canvas API token for the given Telegram user.

    Returns None if no token has been stored yet.
    """

    conn = _get_connection()
    try:
        cur = conn.execute(
            "SELECT token FROM user_canvas_tokens WHERE telegram_user_id = ?",
            (telegram_user_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()
