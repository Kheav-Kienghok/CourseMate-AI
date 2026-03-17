from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from canvas.canvas_client import get_course_assignments, get_dashboard_cards
from bot.keyboards import (
    course_assignments_keyboard,
    courses_keyboard,
    main_menu_keyboard,
)
from services.user_store import get_user_canvas_token, set_user_canvas_token

logger = logging.getLogger(__name__)


# Number of assignments to show per page when listing course assignments.
ASSIGNMENTS_PAGE_SIZE = 5


# -----------------------------------------------------------
# Shared renderers
# -----------------------------------------------------------


async def render_courses(message, canvas_token: str, edit: bool = False) -> None:
    """Render the course list either by replying or editing."""

    try:
        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
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


async def render_course_assignments(
    message,
    course_id: int,
    canvas_token: str,
    *,
    page: int = 1,
    edit: bool = False,
    status: str | None = None,
) -> None:
    """Render assignments for a specific course.

    Assignments are already sorted by due date in the Canvas client.
    This function paginates them, showing ASSIGNMENTS_PAGE_SIZE at a time.
    """

    try:
        assignments = get_course_assignments(course_id, canvas_token=canvas_token)
        assignments = list(reversed(assignments))  # reverse order
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load assignments for course %s: %s", course_id, exc)

        if edit:
            await message.edit_text(
                f"Failed to load assignments for course {course_id}: {exc}",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.reply_text(
                f"Failed to load assignments for course {course_id}: {exc}",
                reply_markup=main_menu_keyboard(),
            )
        return

    # Optionally filter assignments into past or upcoming based on due date
    if status in {"past", "upcoming"}:
        today = datetime.now(timezone.utc).date()

        with_due: list[tuple[object, dict]] = []
        no_due: list[dict] = []

        for a in assignments:
            # For upcoming assignments, optionally hide the Canvas Roll Call Attendance item
            if status == "upcoming":
                name = (a.get("name") or "").strip().lower()
                if name == "roll call attendance":
                    continue

            due_at = a.get("due_at")
            if not due_at:
                if status == "upcoming":
                    no_due.append(a)
                continue

            date_str = str(due_at).split("T", maxsplit=1)[0]
            try:
                due_date = datetime.fromisoformat(date_str).date()
            except ValueError:
                # If we cannot parse the date, treat as undated upcoming
                if status == "upcoming":
                    no_due.append(a)
                continue

            if status == "past" and due_date < today:
                with_due.append((due_date, a))
            elif status == "upcoming" and due_date >= today:
                with_due.append((due_date, a))

        # Sort so that:
        # - past: nearest to today first (latest due date first)
        # - upcoming: nearest deadline first (earliest due date first)
        reverse = status == "past"
        with_due.sort(key=lambda pair: pair[0], reverse=reverse)

        sorted_with_due = [a for _, a in with_due]

        if status == "upcoming":
            # Place assignments without a due date after the dated ones
            assignments = sorted_with_due + no_due
        else:
            assignments = sorted_with_due

    if not assignments:
        # Special friendly message when there are no upcoming assignments
        if status == "upcoming":
            text = (
                "Well done!\n"
                "Your to do list assignment for the course is empty. Time to recharge."
            )
        else:
            label = "past" if status == "past" else "any"
            text = f"📝 No {label} assignments found for course `{course_id}`."

        if edit:
            await message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await message.reply_text(text, reply_markup=main_menu_keyboard())
        return

    total_assignments = len(assignments)
    page_size = ASSIGNMENTS_PAGE_SIZE

    total_pages = (total_assignments + page_size - 1) // page_size or 1

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    page_assignments = assignments[start_index:end_index]

    if status == "past":
        label = "Past assignments"
    elif status == "upcoming":
        label = "Upcoming assignments"
    else:
        label = "Assignments"

    text = f"📝 *{label} for course* `{course_id}` " f"(Page {page}/{total_pages}):"

    if edit:
        await message.edit_text(
            text,
            reply_markup=course_assignments_keyboard(
                course_id, page_assignments, page, total_pages, status
            ),
            parse_mode="Markdown",
        )
    else:
        await message.reply_text(
            text,
            reply_markup=course_assignments_keyboard(
                course_id, page_assignments, page, total_pages, status
            ),
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
    chat = update.effective_chat
    if not message or not chat:
        return

    user = update.effective_user

    logger.info(
        "Received /courses from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    chat_id = getattr(chat, "id", None)
    if chat_id is None:
        await message.reply_text(
            "I couldn't identify your Telegram user. Please try again.",
            reply_markup=main_menu_keyboard(),
        )
        return

    canvas_token = get_user_canvas_token(chat_id)
    if not canvas_token:
        await message.reply_text(
            "To load your Canvas courses, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    await render_courses(message, canvas_token=canvas_token)


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


async def set_canvas_token_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /settoken command to store a user's Canvas API token.

    Expected usage: /settoken YOUR_CANVAS_TOKEN
    The token is stored locally in a SQLite database, per Telegram user.
    """

    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    chat_id = getattr(chat, "id", None)
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)

    if chat_id is None:
        await message.reply_text(
            "I couldn't identify your Telegram user. Please try again.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not context.args:
        await message.reply_text(
            "Please send your Canvas API token like this:\n\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    token = " ".join(context.args).strip()

    if not token:
        await message.reply_text(
            "The token you provided looks empty. Please try again.",
            reply_markup=main_menu_keyboard(),
        )
        return

    set_user_canvas_token(chat_id, username, token, first_name, last_name)

    logger.info("Stored Canvas token for chat_id=%s username=%s", chat_id, username)
    # Try to delete the original message that contained the token
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        # If we cannot delete (e.g. insufficient rights), continue silently.
        pass

    await message.chat.send_message(
        "✅ Your Canvas API token has been saved for this bot.",
        reply_markup=main_menu_keyboard(),
    )
