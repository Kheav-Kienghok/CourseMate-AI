import os

import dotenv

dotenv.load_dotenv()


def get_environment() -> str:
    """Return the current application environment.

    Defaults to "Development" if ENVIRONMENT is not set.
    """

    return os.getenv("ENVIRONMENT", "Development")


def get_canvas_base_url() -> str | None:
    """Return Canvas base HTTP URL from env (HTTP_URL)."""
    return os.getenv("HTTP_URL")


def get_telegram_bot_token() -> str:
    """Return Telegram bot token from env (TELEGRAM_BOT_TOKEN).

    Raises ValueError if missing.
    """

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    return token


def get_telegram_allowed_chat_id() -> int | None:
    """Return the single allowed Telegram chat ID (TELEGRAM_ALLOWED_CHAT_ID).

    If the env var is missing or invalid, returns None.
    """

    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def get_telegram_allowed_username() -> str | None:
    """Return the single allowed Telegram username (TELEGRAM_ALLOWED_USERNAME).

    Username should be provided without the leading '@'. Comparison is
    case-insensitive. If the env var is missing, returns None.
    """

    raw = os.getenv("TELEGRAM_ALLOWED_USERNAME")
    if not raw:
        return None
    return raw.lstrip("@").lower()


def is_telegram_user_allowed(*, chat_id: int | None, username: str | None) -> bool:
    """Return True if the Telegram user is allowed to use the bot.

    Security model:
    - You configure your own chat ID and/or username via env vars.
    - If at least one of them is set, only a user matching one of them
      is allowed.
    - If neither is set, everyone is allowed (no restriction).
    """

    allowed_chat_id = get_telegram_allowed_chat_id()
    allowed_username = get_telegram_allowed_username()

    # If no restriction is configured, allow everyone.
    if allowed_chat_id is None and allowed_username is None:
        return True

    if allowed_chat_id is not None and chat_id is not None:
        if chat_id == allowed_chat_id:
            return True

    if allowed_username is not None and username:
        if username.lower() == allowed_username:
            return True

    return False
