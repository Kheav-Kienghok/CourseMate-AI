from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from canvas.canvas_client import get_dashboard_cards
from bot.keyboards import main_menu_keyboard, courses_keyboard


logger = logging.getLogger(__name__)


# -----------------------------------------------------------
# Shared renderer for courses (used by command + callback)
# -----------------------------------------------------------

async def render_courses(message, edit: bool = False) -> None:
    """Render the course list either by replying or editing."""

    try:
        dashboard_cards = get_dashboard_cards()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load courses: %s", exc)

        if edit:
            await message.edit_text(
                f"Failed to load courses: {exc}",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.reply_text(
                f"Failed to load courses: {exc}",
                reply_markup=main_menu_keyboard(),
            )
        return

    if not dashboard_cards:
        if edit:
            await message.edit_text(
                "No courses found on your Canvas dashboard.",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.reply_text(
                "No courses found on your Canvas dashboard.",
                reply_markup=main_menu_keyboard(),
            )
        return

    term = dashboard_cards[0].get("term", "Unknown Term")

    lines: list[str] = [
        "📚 *YOUR COURSES*",
        f"🎓 _{term}_",
        "━━━━━━━━━━━━━━━",
        "",
    ]

    for course in dashboard_cards:

        if course.get("enrollmentState") != "active":
            continue

        name = (
            course.get("shortName")
            or course.get("originalName")
            or str(course.get("id"))
        )

        course_code = course.get("courseCode", "")
        section = course.get("section", "")

        full_name = f"{name} ({course_code}) - Section {section}".strip()

        lines.append(f"- *{full_name}*")

    text = "\n".join(lines)

    if edit:
        await message.edit_text(
            text,
            reply_markup=courses_keyboard(dashboard_cards),
            parse_mode="Markdown",
        )
    else:
        await message.reply_text(
            text,
            reply_markup=courses_keyboard(dashboard_cards),
            parse_mode="Markdown",
        )


# -----------------------------------------------------------
# Commands
# -----------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""

    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    chat = update.effective_chat

    logger.info(
        "Received /start from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    logger.debug(
        "Start command | user_id=%s username=%s chat_id=%s text=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
        getattr(chat, "id", None),
        getattr(message, "text", None),
    )

    await message.reply_text(
        "👋 *Hey there! Welcome to CourseMate AI.*\n\n"
        "I'm here to help you keep up with your Canvas courses without the stress.\n\n"
        "You can check assignments, track grades, view courses, and set reminders anytime.\n\n"
        "Just choose an option from the menu below to begin ⬇️",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""

    message = update.effective_message
    if not message:
        return

    user = update.effective_user

    logger.info(
        "Received /help from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    await message.reply_text(
        "*📚 Canvas Bot Commands*\n\n"
        "🚀 */start* — Introduce the bot\n"
        "📖 */courses* — Show your courses\n"
        "📝 */assignments* — Upcoming assignments\n"
        "📊 */grades* — Current grades\n"
        "⏰ */reminders* — Manage reminders\n"
        "❓ */help* — Show this message",
        parse_mode="Markdown",
    )


async def courses_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /courses command."""

    message = update.effective_message
    if not message:
        return

    user = update.effective_user

    logger.info(
        "Received /courses from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    await render_courses(message)


async def assignments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /assignments command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "📝 Upcoming assignments are not implemented yet.",
        reply_markup=main_menu_keyboard(),
    )


async def grades_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /grades command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "📊 Grade summary is not implemented yet.",
        reply_markup=main_menu_keyboard(),
    )


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reminders command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "⏰ Reminders are not implemented yet.",
        reply_markup=main_menu_keyboard(),
    )


# -----------------------------------------------------------
# Callback handler
# -----------------------------------------------------------

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callbacks."""

    query = update.callback_query
    if not query:
        return

    await query.answer()

    user = query.from_user
    data = query.data

    logger.info(
        "Received callback '%s' from user_id=%s username=%s",
        data,
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    if data == "help":
        await help_command(update, context)

    elif data == "courses":
        await render_courses(query.message, edit=True)

    elif data == "assignments":
        await assignments_command(update, context)

    elif data == "grades":
        await grades_command(update, context)

    elif data == "reminders":
        await reminders_command(update, context)

    elif data == "menu":
        await query.edit_message_text(
            "Main menu:",
            reply_markup=main_menu_keyboard(),
        )

    elif data and data.startswith("course:"):

        course_id = data.split(":", maxsplit=1)[1]

        dashboard_cards = get_dashboard_cards()

        selected = None
        for course in dashboard_cards:
            if str(course.get("id")) == course_id:
                selected = course
                break

        if not selected:
            await query.edit_message_text(
                "Course not found.",
                reply_markup=main_menu_keyboard(),
            )
            return

        name = (
            selected.get("shortName")
            or selected.get("originalName")
            or str(selected.get("id"))
        )

        code = selected.get("courseCode", "")
        section = selected.get("section", "")

        await query.edit_message_text(
            f"You selected *{name} ({code}) Section {section}*.",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown",
        )

    else:
        logger.warning("Unknown callback data: %s", data)

        message = update.effective_message
        if message:
            await message.reply_text(
                "Unknown action.",
                reply_markup=main_menu_keyboard(),
            )


# -----------------------------------------------------------
# Global error handler
# -----------------------------------------------------------

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