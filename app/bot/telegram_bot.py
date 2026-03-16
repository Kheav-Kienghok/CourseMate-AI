from __future__ import annotations
from typing import Final

from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

from bot.handlers import (
    assignments_command,
    courses_command,
    error_handler,
    grades_command,
    help_command,
    main_menu_callback,
    reminders_command,
    start_command,
)
from utils.config import get_telegram_bot_token


class CourseMateBot:
    """Telegram bot wrapper for CourseMate."""

    def __init__(self, token: str | None = None) -> None:
        self._token: Final[str] = token or get_telegram_bot_token()
        self._application: Application = ApplicationBuilder().token(self._token).build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self._application.add_handler(CommandHandler("start", start_command))
        self._application.add_handler(CommandHandler("help", help_command))
        # self._application.add_handler(
        #     CommandHandler("settoken", set_canvas_token_command)
        # )
        self._application.add_handler(CommandHandler("courses", courses_command))
        self._application.add_handler(
            CommandHandler("assignments", assignments_command)
        )
        self._application.add_handler(CommandHandler("grades", grades_command))
        self._application.add_handler(CommandHandler("reminders", reminders_command))
        self._application.add_handler(CallbackQueryHandler(main_menu_callback))
        self._application.add_error_handler(error_handler)

    def run(self) -> None:
        """Run the bot using long polling."""
        # Disable built-in signal handling so KeyboardInterrupt propagates
        # to app.main(), where we handle it gracefully.
        self._application.run_polling(stop_signals=None)


def run_bot() -> None:
    """Backwards-compatible helper to run the bot."""
    bot = CourseMateBot()
    bot.run()
