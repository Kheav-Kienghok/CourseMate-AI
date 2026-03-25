from __future__ import annotations

from typing import Optional

from services.db import SessionLocal
from services.models import User, UserSettings
from utils.crypto import decrypt_text, encrypt_text


def set_user_canvas_token(
    chat_id: int,
    username: Optional[str],
    token: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> None:
    """Create or update the Canvas API token for a Telegram user using ORM.

    The token is stored in the user_canvas_tokens table via SQLAlchemy.
    It is not encrypted, so make sure the host machine is trusted.
    """

    with SessionLocal() as session:
        user = session.query(User).filter_by(chat_id=chat_id).one_or_none()

        if user is None:
            # Fallbacks for required name fields if Telegram does not
            # provide them.
            resolved_first = first_name or username or "Unknown"
            resolved_last = last_name or username or "User"

            user = User(
                chat_id=chat_id,
                username=username or str(chat_id),
                firstname=resolved_first,
                lastname=resolved_last,
                canvas_token=encrypt_text(token),
            )
            session.add(user)
        else:
            user.canvas_token = encrypt_text(token)
            if username is not None:
                user.username = username
            if first_name is not None:
                user.firstname = first_name
            if last_name is not None:
                user.lastname = last_name

        session.commit()


def get_user_canvas_token(chat_id: int) -> Optional[str]:
    """Return the stored Canvas API token for the given chat.

    Returns None if no token has been stored yet.
    """

    with SessionLocal() as session:
        user = session.query(User).filter_by(chat_id=chat_id).one_or_none()
        if user is None:
            return None

        return decrypt_text(user.canvas_token)


def create_user(lastname: str, firstname: str, username: str) -> User:
    """Create a new user in the users table.

    A secure token is generated automatically by the ORM model.
    Returns the persisted User instance.
    """

    with SessionLocal() as session:
        user = User(
            lastname=lastname,
            firstname=firstname,
            username=username,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def get_user_by_id(user_id: str) -> Optional[User]:
    """Return a user by primary key, or None if not found."""

    with SessionLocal() as session:
        return session.get(User, user_id)


def get_user_by_username(username: str) -> Optional[User]:
    """Return the user with the given username, or None if missing."""

    with SessionLocal() as session:
        return session.query(User).filter_by(username=username).first()


def set_planner_announcement_notifications(chat_id: int, enabled: bool) -> None:
    """Enable or disable planner announcement notifications for a user."""

    with SessionLocal() as session:
        settings = session.query(UserSettings).filter_by(chat_id=chat_id).one_or_none()

        if settings is None:
            settings = UserSettings(
                chat_id=chat_id,
                planner_announcement_notifications_enabled=enabled,
            )
            session.add(settings)
        else:
            settings.planner_announcement_notifications_enabled = enabled

        session.commit()


def get_planner_announcement_notifications(chat_id: int) -> bool:
    """Return True if planner announcement notifications are enabled."""

    with SessionLocal() as session:
        settings = session.query(UserSettings).filter_by(chat_id=chat_id).one_or_none()

        return bool(settings and settings.planner_announcement_notifications_enabled)


def get_chat_ids_with_planner_announcement_notifications_enabled() -> list[int]:
    """Return chat IDs for all users with announcement notifications enabled."""

    with SessionLocal() as session:
        rows = (
            session.query(UserSettings.chat_id)
            .filter_by(planner_announcement_notifications_enabled=True)
            .all()
        )

        return [chat_id for (chat_id,) in rows]
