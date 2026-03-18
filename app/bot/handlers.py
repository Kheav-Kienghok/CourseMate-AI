from __future__ import annotations

import logging
from datetime import datetime, timezone

from canvas.canvas_client import (
    get_assignment_submission,
    get_course_assignments,
    get_dashboard_cards,
    get_student_assignment,
)
from services.user_store import get_user_canvas_token, set_user_canvas_token
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.keyboards import (
    course_assignments_keyboard,
    course_menu_keyboard,
    courses_keyboard,
    main_menu_keyboard,
)

logger = logging.getLogger(__name__)


def _format_canvas_datetime(value: str | None) -> str | None:
    """Format a Canvas ISO8601 datetime into a readable string.

    Example input: "2026-02-23T16:59:59Z"
    Output: "February 23, 2026 04:59 PM" (UTC)
    """

    if not value:
        return None

    try:
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc,
            )
        else:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

        # Format in 12-hour clock with AM/PM, e.g. "March 20, 2026 01:30 PM"
        return dt.strftime("%B %-d, %Y %I:%M %p")
    except Exception:  # noqa: BLE001
        # Fallback to raw value if parsing fails
        return value


# Number of assignments to show per page when listing course assignments.
ASSIGNMENTS_PAGE_SIZE = 5


# -----------------------------------------------------------
# Shared renderer for courses (used by command + callback)
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
        today_str = datetime.now(timezone.utc).date().isoformat()

        filtered: list[dict] = []
        for a in assignments:
            due_at = a.get("due_at")
            if not due_at:
                # Treat assignments without a due date as upcoming
                if status == "upcoming":
                    filtered.append(a)
                continue

            due_date_str = str(due_at).split("T", maxsplit=1)[0]

            if status == "past" and due_date_str < today_str:
                filtered.append(a)
            elif status == "upcoming" and due_date_str >= today_str:
                filtered.append(a)

        assignments = filtered

    if not assignments:
        label = (
            "past"
            if status == "past"
            else "upcoming" if status == "upcoming" else "any"
        )
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


# -----------------------------------------------------------
# Callback handler
# -----------------------------------------------------------


async def main_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
        chat = query.message.chat if query.message else None
        chat_id = getattr(chat, "id", None) if chat else None

        if chat_id is None:
            await query.edit_message_text(
                "I couldn't identify your Telegram user. Please try again.",
                reply_markup=main_menu_keyboard(),
            )
            return

        canvas_token = get_user_canvas_token(chat_id)
        if not canvas_token:
            await query.edit_message_text(
                "To load your Canvas courses, please set your personal Canvas API token first.\n\n"
                "Send it using:\n"
                "*/settoken YOUR_CANVAS_TOKEN*\n\n"
                "You can create a token in Canvas under *Account → Settings → New Access Token*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return

        await render_courses(query.message, canvas_token=canvas_token, edit=True)

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

        parts = data.split(":")

        # course:{course_id}:assignments[:status][:page]
        #   - status can be "past" or "upcoming"
        if len(parts) >= 3 and parts[2] == "assignments":
            try:
                course_id_int = int(parts[1])
            except ValueError:
                logger.warning("Malformed course assignments callback data: %s", data)
                await query.edit_message_text(
                    "Could not understand which course's assignments to load.",
                    reply_markup=main_menu_keyboard(),
                )
                return

            page = 1
            status: str | None = None

            if len(parts) >= 4:
                # pattern: course:{course_id}:assignments:{page}
                # or:      course:{course_id}:assignments:{status}:{page}
                if parts[3] in {"past", "upcoming"}:
                    status = parts[3]
                    if len(parts) >= 5:
                        try:
                            page = int(parts[4])
                        except ValueError:
                            page = 1
                else:
                    try:
                        page = int(parts[3])
                    except ValueError:
                        page = 1

            chat = query.message.chat if query.message else None
            chat_id = getattr(chat, "id", None) if chat else None
            if chat_id is None:
                await query.edit_message_text(
                    "I couldn't identify your Telegram user. Please try again.",
                    reply_markup=main_menu_keyboard(),
                )
                return

            canvas_token = get_user_canvas_token(chat_id)
            if not canvas_token:
                await query.edit_message_text(
                    "To load assignments, please set your personal Canvas API token first.\n\n"
                    "Send it using:\n"
                    "*/settoken YOUR_CANVAS_TOKEN*\n\n"
                    "You can create a token in Canvas under *Account → Settings → New Access Token*.",
                    parse_mode="Markdown",
                    reply_markup=main_menu_keyboard(),
                )
                return

            await render_course_assignments(
                query.message,
                course_id_int,
                canvas_token,
                page=page,
                edit=True,
                status=status,
            )
            return

        # course:{course_id}:rollcall
        if len(parts) == 3 and parts[2] == "rollcall":
            await query.edit_message_text(
                "📋 Roll Call attendance is not implemented yet.",
                reply_markup=course_menu_keyboard(int(parts[1])),
            )
            return

        # course:{course_id}:grades
        if len(parts) == 3 and parts[2] == "grades":
            await grades_command(update, context)
            return

        # course:{course_id}
        course_id = parts[1]

        chat = query.message.chat if query.message else None
        chat_id = getattr(chat, "id", None) if chat else None
        if chat_id is None:
            await query.edit_message_text(
                "I couldn't identify your Telegram user. Please try again.",
                reply_markup=main_menu_keyboard(),
            )
            return

        canvas_token = get_user_canvas_token(chat_id)
        if not canvas_token:
            await query.edit_message_text(
                "To view course details, please set your personal Canvas API token first.\n\n"
                "Send it using:\n"
                "*/settoken YOUR_CANVAS_TOKEN*\n\n"
                "You can create a token in Canvas under *Account → Settings → New Access Token*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return

        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)

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
            f"You selected *{name} ({code}) - Section {section}*.",
            reply_markup=course_menu_keyboard(int(course_id)),
            parse_mode="Markdown",
        )

    elif data and data.startswith("course-assignment:"):
        try:
            _, course_id_str, assignment_id_str = data.split(":", maxsplit=2)
            course_id = int(course_id_str)
            assignment_id = int(assignment_id_str)
        except ValueError:
            logger.warning("Malformed course-assignment callback data: %s", data)
            await query.edit_message_text(
                "Could not understand which assignment you selected.",
                reply_markup=main_menu_keyboard(),
            )
            return

        chat = query.message.chat if query.message else None
        chat_id = getattr(chat, "id", None) if chat else None
        if chat_id is None:
            await query.edit_message_text(
                "I couldn't identify your Telegram user. Please try again.",
                reply_markup=main_menu_keyboard(),
            )
            return

        canvas_token = get_user_canvas_token(chat_id)
        if not canvas_token:
            await query.edit_message_text(
                "To load assignments, please set your personal Canvas API token first.\n\n"
                "Send it using:\n"
                "*/settoken YOUR_CANVAS_TOKEN*\n\n"
                "You can create a token in Canvas under *Account → Settings → New Access Token*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return

        try:
            assignments = get_course_assignments(course_id, canvas_token=canvas_token)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to load assignments for course %s when opening one: %s",
                course_id,
                exc,
            )
            await query.edit_message_text(
                f"Failed to load assignments for course {course_id}: {exc}",
                reply_markup=main_menu_keyboard(),
            )
            return

        selected = None
        for a in assignments:
            if a.get("id") == assignment_id:
                selected = a
                break

        if not selected:
            await query.edit_message_text(
                "Assignment not found.",
                reply_markup=main_menu_keyboard(),
            )
            return

        name = selected.get("name") or f"Assignment {assignment_id}"
        points_possible = selected.get("points_possible")
        due_at = selected.get("due_at")
        created_at = selected.get("created_at")
        allowed_attempts = selected.get("allowed_attempts")
        has_submitted = selected.get("has_submitted_submissions")

        # Try to fetch the current user's submission to get the score/grade
        submission_score = None
        try:
            submission = get_assignment_submission(
                course_id,
                assignment_id,
                canvas_token=canvas_token,
            )
            submission_score = submission.get("score")
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not load submission for course_id=%s assignment_id=%s: %s",
                course_id,
                assignment_id,
                exc,
            )

        lines: list[str] = [
            f"📝 *{name}*",
            "------------------------------------------------",
            "",
        ]

        if points_possible is not None:
            lines.append(f"🏷 Points possible: *{points_possible}*")

        if submission_score is not None:
            if points_possible is not None:
                lines.append(
                    f"📊 Score: *{submission_score}* / *{points_possible}*",
                )
            else:
                lines.append(f"📊 Score: *{submission_score}*")

        if allowed_attempts is not None:
            if allowed_attempts == -1:
                attempts_text = "Unlimited attempts"
            else:
                attempts_text = str(allowed_attempts)
            lines.append(f"🔁 Allowed attempts: *{attempts_text}*")

        if has_submitted is not None:
            if has_submitted:
                lines.append("📌 You have submitted this assignment.")
            else:
                lines.append("📌 You have not submitted this assignment yet.")

        # Blank line before timestamps
        lines.append("")

        if created_at:
            pretty_created = _format_canvas_datetime(created_at)
            if pretty_created:
                lines.append(f"🕒 Created at: {pretty_created}")

        if due_at:
            pretty_due = _format_canvas_datetime(due_at)
            if pretty_due:
                lines.append(f"📅 Due: {pretty_due}")

        text = "\n".join(lines)

        back_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Back to assignments",
                        callback_data=f"course:{course_id}:assignments",
                    )
                ]
            ]
        )

        await query.edit_message_text(
            text,
            reply_markup=back_keyboard,
            parse_mode="Markdown",
        )

    elif data and data.startswith("assignment:"):
        try:
            _, assignment_lid, submission_id = data.split(":", maxsplit=2)
        except ValueError:
            logger.warning("Malformed assignment callback data: %s", data)
            await query.edit_message_text(
                "Could not understand which assignment you selected.",
                reply_markup=main_menu_keyboard(),
            )
            return

        chat = query.message.chat if query.message else None
        chat_id = getattr(chat, "id", None) if chat else None
        if chat_id is None:
            await query.edit_message_text(
                "I couldn't identify your Telegram user. Please try again.",
                reply_markup=main_menu_keyboard(),
            )
            return

        canvas_token = get_user_canvas_token(chat_id)
        if not canvas_token:
            await query.edit_message_text(
                "To load assignment details, please set your personal Canvas API token first.\n\n"
                "Send it using:\n"
                "*/settoken YOUR_CANVAS_TOKEN*\n\n"
                "You can create a token in Canvas under *Account → Settings → New Access Token*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
            return

        try:
            result = get_student_assignment(
                assignment_lid, submission_id, canvas_token=canvas_token
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load assignment via GraphQL: %s", exc)
            await query.edit_message_text(
                f"Failed to load assignment details: {exc}",
                reply_markup=main_menu_keyboard(),
            )
            return

        data_block = result.get("data", {}) if isinstance(result, dict) else {}
        assignment = data_block.get("assignment") or {}
        submission = data_block.get("submission") or {}

        name = assignment.get("name", "Assignment")
        points_possible = assignment.get("pointsPossible")
        due_at = assignment.get("dueAt")

        score = submission.get("score")

        lines: list[str] = [
            f"📝 *{name}*",
            "------------------------------------------------",
            "",
        ]

        if points_possible is not None:
            lines.append(f"🏷 Points possible: *{points_possible}*")

        if score is not None:
            if points_possible:
                lines.append(f"📊 Score: *{score}* / *{points_possible}*")
            else:
                lines.append(f"📊 Score: *{score}*")

        # Blank line before timestamps
        lines.append("")

        if due_at:
            pretty_due = _format_canvas_datetime(due_at)
            if pretty_due:
                lines.append(f"📅 Due: {pretty_due}")

        if len(lines) <= 3:
            lines.append("No additional details available.")

        text = "\n".join(lines)

        back_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Back to assignments", callback_data="assignments"
                    )
                ]
            ]
        )

        await query.edit_message_text(
            text,
            reply_markup=back_keyboard,
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
