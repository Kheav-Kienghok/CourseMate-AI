from __future__ import annotations

import sys

from bot.telegram_bot import run_bot
from services.db import init_db
from ui.terminal import prompt_start_or_exit, startup_screen
from utils.logging import setup_logging


def main() -> None:
    """Entry point for the application."""

    try:
        # Configure logging before starting the bot so all modules
        # share the same logging setup.
        setup_logging()

        # Ensure database tables for ORM models exist (e.g. users table).
        init_db()

        startup_screen()
        if not prompt_start_or_exit():
            sys.exit(0)

        run_bot()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:  # noqa: BLE001
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
