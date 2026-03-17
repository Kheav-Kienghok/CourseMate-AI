from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler."""

    logger.exception("Bot error: %s", context.error)

    if isinstance(update, Update):
        message = update.effective_message

        if message:
            await message.reply_text(
                "⚠️ Something went wrong. Please try again later.",
                reply_markup=main_menu_keyboard(),
            )
