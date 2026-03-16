from __future__ import annotations

import sys

from bot.telegram_bot import run_bot
from ui.terminal import startup_screen, prompt_start_or_exit


def main() -> None:
    """Entry point for the application."""

    try:
        startup_screen()
        if not prompt_start_or_exit():
            sys.exit(0)

        run_bot()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()