from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from services.db import Base


def generate_uuid_str() -> str:
    """Generate a UUIDv4 string for use as primary key.

    Stored as 36-character canonical string for broad DB compatibility
    (including SQLite).
    """

    return str(uuid.uuid4())


def generate_secure_token() -> str:
    """Generate a cryptographically secure random token.

    Uses a URL-safe representation so it can be sent to external
    services or used in URLs if needed.
    """

    return secrets.token_urlsafe(32)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid_str,
    )

    # Telegram chat id this user record belongs to.
    # Stored in the "telegram_user_id" column for backwards
    # compatibility with existing databases.
    chat_id: Mapped[int] = mapped_column(
        "telegram_user_id",
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
    )

    lastname: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    firstname: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    # Plaintext Canvas API token for this user.
    # It is not hashed, so ensure the database remains protected
    # and avoid logging it.
    canvas_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"User(id={self.id!r}, username={self.username!r}, "
            f"firstname={self.firstname!r}, lastname={self.lastname!r})"
        )


class UserSettings(Base):
    """Per-user feature flags and notification preferences."""

    __tablename__ = "user_settings"

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    planner_announcement_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="0",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"UserSettings(chat_id={self.chat_id!r}, "
            f"planner_announcement_notifications_enabled="
            f"{self.planner_announcement_notifications_enabled!r})"
        )
