from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.commands import (
    calendar_command,
    grades_command,
    help_command,
    reminders_command,
    render_course_assignments,
    render_courses,
    render_month_assignments_overview,
)
from bot.datetime_utils import _format_due_with_relative
from bot.keyboards import calendar_keyboard, course_menu_keyboard, main_menu_keyboard
from canvas.canvas_client import (
    get_assignment_submission,
    get_calendar_events,
    get_course_assignments,
    get_dashboard_cards,
    get_student_assignment,
)
from services.user_store import get_user_canvas_token

logger = logging.getLogger(__name__)


async def _require_canvas_token(query, action_text: str) -> str | None:
    """Return Canvas token for callback user, or show a friendly error and return None."""

    chat = query.message.chat if query.message else None
    chat_id = getattr(chat, "id", None) if chat else None
    if chat_id is None:
        await query.edit_message_text(
            "I couldn't identify your Telegram user. Please try again.",
            reply_markup=main_menu_keyboard(),
        )
        return None

    canvas_token = get_user_canvas_token(chat_id)

    if not canvas_token:
        await query.edit_message_text(
            f"To {action_text}, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return None

    return canvas_token


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

    # Calendar callbacks (date picker similar to telegram-calendar)
    if data and data.startswith("cal:"):
        parts = data.split(":")

        action = parts[1] if len(parts) >= 2 else ""

        # Ignore non-interactive cells (header/day-names/empty cells).
        if action == "ignore":
            return

        # User selected a concrete date without assignments:
        # cal:day:YYYY-MM-DD
        if action == "day" and len(parts) == 3:
            # No assignments for this date; keep current view unchanged.
            return

        # User selected a date that has assignments:
        # cal:day:YYYY-MM-DD:assignments or cal:day:YYYY-MM-DD:urgent
        if action == "day" and len(parts) >= 4:
            selected_date = parts[2]
            _flag = parts[3]

            canvas_token = await _require_canvas_token(
                query,
                "view assignments for this date",
            )
            if not canvas_token:
                return

            # Build context codes from the user's active dashboard courses.
            try:
                dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to load courses for calendar callback: %s", exc)
                await query.edit_message_text(
                    f"Failed to load courses for calendar: {exc}",
                    reply_markup=main_menu_keyboard(),
                )
                return

            context_codes: list[str] = []
            for course in dashboard_cards:
                if course.get("enrollmentState") != "active":
                    continue
                course_id = course.get("id")
                if course_id is not None:
                    context_codes.append(f"course_{course_id}")

            # Restrict the window to the specific calendar date.
            start_date = f"{selected_date}T00:00:00.000Z"
            end_date = f"{selected_date}T23:59:59.000Z"

            try:
                events = get_calendar_events(
                    canvas_token=canvas_token,
                    start_date=start_date,
                    end_date=end_date,
                    context_codes=context_codes,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to load calendar events for %s: %s", selected_date, exc
                )
                await query.edit_message_text(
                    f"Failed to load calendar events: {exc}",
                    reply_markup=main_menu_keyboard(),
                )
                return

            lines: list[str] = [
                f"📅 *Assignments on {selected_date}*",
                "",
            ]

            if not events:
                lines.append("No assignments for this date.")
            else:
                for event in events:
                    assignment_info = event.get("assignment") or {}
                    title = (
                        assignment_info.get("name")
                        or event.get("title")
                        or "Assignment"
                    )
                    course_name = (
                        event.get("context_name")
                        or assignment_info.get("course_id")
                        or "Unknown course"
                    )
                    lines.append(f"• *{course_name}* — {title}")

            await query.edit_message_text(
                "\n".join(lines),
                parse_mode="Markdown",
                reply_markup=None,
            )
            return

        # Navigation between months: cal:prev:YYYY-MM or cal:next:YYYY-MM
        if action in {"prev", "next"} and len(parts) == 3:
            year_month = parts[2]
            try:
                year_str, month_str = year_month.split("-", maxsplit=1)
                year = int(year_str)
                month = int(month_str)
            except Exception:  # noqa: BLE001
                logger.warning("Malformed calendar nav callback data: %s", data)
                return

            # For prev we already encoded target year-month; same for next.
            await query.edit_message_reply_markup(
                reply_markup=calendar_keyboard(year=year, month=month)
            )
            return

        # Unknown calendar action: fall through to generic handler below.

    if data == "calendar":
        await calendar_command(update, context)

    elif data == "help":
        await help_command(update, context)

    elif data == "assignments":
        canvas_token = await _require_canvas_token(
            query,
            "view your assignments",
        )
        if not canvas_token:
            return

        await render_month_assignments_overview(
            query.message,
            canvas_token=canvas_token,
            filter_mode="todo",
            edit=True,
            compact=True,
        )

    elif data == "courses":
        canvas_token = await _require_canvas_token(
            query,
            "load your Canvas courses",
        )
        if not canvas_token:
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

    elif data and data.startswith("assignments:this_month:"):
        parts = data.split(":")
        view_mode = parts[2] if len(parts) >= 3 else "compact"

        compact = view_mode != "full"

        canvas_token = await _require_canvas_token(
            query,
            "view your assignments",
        )
        if not canvas_token:
            return

        await render_month_assignments_overview(
            query.message,
            canvas_token=canvas_token,
            filter_mode="todo",
            edit=True,
            compact=compact,
        )

    elif data and data.startswith("assignments:urgent:"):
        # Lightweight actions for the most urgent upcoming assignment.
        # These do not send new messages; they acknowledge via callback
        # and keep the current view in place.
        parts = data.split(":")
        if len(parts) == 5:
            _scope, _urgent, action, course_id_str, assignment_id_str = parts
        else:
            action = ""

        if action == "done":
            await query.answer("Marked as done (in CourseMate view).", show_alert=False)
        elif action == "remind":
            await query.answer(
                "Reminder noted. I will surface this again as it gets closer.",
                show_alert=False,
            )
        else:
            await query.answer("Action not recognized.")

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

            canvas_token = await _require_canvas_token(query, "load assignments")
            if not canvas_token:
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

        canvas_token = await _require_canvas_token(query, "view course details")
        if not canvas_token:
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

        canvas_token = await _require_canvas_token(query, "load assignments")
        if not canvas_token:
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

        if due_at:
            pretty_due = _format_due_with_relative(due_at)
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

        canvas_token = await _require_canvas_token(
            query,
            "load assignment details",
        )
        if not canvas_token:
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
            pretty_due = _format_due_with_relative(due_at)
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
