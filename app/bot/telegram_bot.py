from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import Final
from zoneinfo import ZoneInfo

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from bot.handlers import (
    assignments_command,
    calendar_command,
    courses_command,
    error_handler,
    grades_command,
    help_command,
    main_menu_callback,
    planner_command,
    reminders_command,
    set_canvas_token_command,
    start_command,
)
from utils.config import get_telegram_bot_token

logger = logging.getLogger(__name__)


class CourseMateBot:
    """Telegram bot wrapper for CourseMate."""

    def __init__(self, token: str | None = None) -> None:
        self._token: Final[str] = token or get_telegram_bot_token()
        self._application: Application = ApplicationBuilder().token(self._token).build()
        self._register_handlers()

        logger.info("CourseMateBot initialized and handlers registered")

    def _register_handlers(self) -> None:
        self._application.add_handler(CommandHandler("start", start_command))
        self._application.add_handler(CommandHandler("help", help_command))
        self._application.add_handler(
            CommandHandler("settoken", set_canvas_token_command)
        )
        self._application.add_handler(CommandHandler("courses", courses_command))
        self._application.add_handler(
            CommandHandler("assignments", assignments_command)
        )
        self._application.add_handler(CommandHandler("calendar", calendar_command))

        self._application.add_handler(CommandHandler("grades", grades_command))
        self._application.add_handler(CommandHandler("reminders", reminders_command))
        self._application.add_handler(CallbackQueryHandler(main_menu_callback))
        self._application.add_error_handler(error_handler)
        self._application.add_handler(CommandHandler("planner", planner_command))

        # Schedule periodic planner announcement checks for subscribed users
        self._schedule_announcements()

    def _schedule_announcements(self) -> None:
        """Schedule planner announcements to run daily for subscribed users."""
        job_queue = self._application.job_queue
        if job_queue is None:
            raise RuntimeError(
                "JobQueue is not initialized. Install PTB with job-queue support."
            )

        tz = ZoneInfo("Asia/Phnom_Penh")
        hours = [7, 8, 10, 12, 15, 17, 21]

        # Uncomment the following line to run the job immediately on startup for testing purposes.
        # # Run once immediately via job_queue
        # job_queue.run_once(_planner_announcements_job, when=0)

        now = datetime.now(tz)

        # Schedule one-time job at 07:00 today (or tomorrow if 07:00 passed)
        run_time = datetime.combine(now.date(), dt_time(7, 0, tzinfo=tz))
        if run_time < now:
            run_time += timedelta(days=1)

        job_queue.run_once(
            _planner_announcements_job, when=run_time, name="planner_announcements_once"
        )

        # Schedule daily announcements
        for hour in hours:
            job_queue.run_daily(
                _planner_announcements_job,
                time=dt_time(hour, 0, tzinfo=tz),
                name=f"planner_announcements_{hour}",
            )

    def run(self) -> None:
        """Run the bot using long polling."""
        # Disable built-in signal handling so KeyboardInterrupt propagates
        # to app.main(), where we handle it gracefully.
        logger.info("Starting CourseMateBot polling loop")
        self._application.run_polling(stop_signals=None)


def run_bot() -> None:
    """Backwards-compatible helper to run the bot."""
    bot = CourseMateBot()
    bot.run()


async def _planner_announcements_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job that sends planner-based announcement notifications.

    Runs at fixed times in the Asia/Phnom_Penh timezone and iterates
    over all users who have opted in.
    """

    from bot.commands import send_planner_announcement_notifications_for_chat
    from services.user_store import (
        get_chat_ids_with_planner_announcement_notifications_enabled,
    )

    application = context.application

    chat_ids = get_chat_ids_with_planner_announcement_notifications_enabled()

    for chat_id in chat_ids:
        await send_planner_announcement_notifications_for_chat(
            chat_id,
            application=application,
        )
