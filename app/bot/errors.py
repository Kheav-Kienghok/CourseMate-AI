from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.keyboards import main_menu_keyboard

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler."""

    error = context.error

    # Ignore harmless Telegram errors that typically occur when the user
    # taps the same inline button multiple times and the message content
    # doesn't actually change.
    if isinstance(error, BadRequest) and "Message is not modified" in str(error):
        logger.info("Ignoring BadRequest 'Message is not modified'")
        return

    logger.exception("Bot error: %s", error)

    if isinstance(update, Update):
        message = update.effective_message

        if message:
            await message.reply_text(
                "⚠️ Something went wrong. Please try again later.",
                reply_markup=main_menu_keyboard(),
            )
