from __future__ import annotations

import calendar as _calendar
import logging
import os
import re
import html
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from bot.keyboards import (
    calendar_keyboard,
    course_assignments_keyboard,
    courses_keyboard,
    main_menu_keyboard,
    month_assignments_keyboard,
)
from canvas.canvas_client import (
    download_canvas_file,
    get_calendar_events,
    get_course_assignments,
    get_dashboard_cards,
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

        with_due.sort(
            key=lambda pair: cast(Any, pair[0]),
            reverse=reverse,
        )

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

    # Build a human-friendly course label (name instead of raw ID)
    course_label = str(course_id)
    try:
        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
        for course in dashboard_cards:
            if str(course.get("id")) == str(course_id):
                name = (
                    course.get("shortName")
                    or course.get("originalName")
                    or str(course_id)
                )
                code = course.get("courseCode", "")
                section = course.get("section", "")
                course_label = f"{name} ({code}) - Section {section}".strip()
                break
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not load course name for course_id=%s: %s", course_id, exc)

    if status == "past":
        label = "Past assignments"
    elif status == "upcoming":
        label = "Upcoming assignments"
    else:
        label = "Assignments"

    text = f"📝 *{label} for* _{course_label}_ " f"(Page {page}/{total_pages}):"

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


async def render_month_assignments_overview(
    message,
    canvas_token: str,
    *,
    filter_mode: str = "todo",
    edit: bool = False,
    compact: bool = True,
) -> None:
    """Render a this-month assignments overview across all active courses.

    filter_mode:
      - "todo": not submitted and not past due
      - "submitted": submitted assignments
      - "past": past-due and not submitted
    """

    try:
        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load courses for assignments overview: %s", exc)

        await message.reply_text(
            f"Failed to load courses: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not dashboard_cards:
        await message.reply_text(
            "No courses found on your Canvas dashboard.",
            reply_markup=main_menu_keyboard(),
        )
        return

    today = datetime.now(timezone.utc).date()
    current_month = today.month
    current_year = today.year

    all_month_assignments: list[dict] = []

    for course in dashboard_cards:
        if course.get("enrollmentState") != "active":
            continue

        course_id = course.get("id")
        if course_id is None:
            continue

        course_name = (
            course.get("shortName") or course.get("originalName") or str(course_id)
        )

        try:
            assignments = get_course_assignments(course_id, canvas_token=canvas_token)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load assignments for course %s: %s", course_id, exc
            )
            continue

        for a in assignments:
            due_at = a.get("due_at")
            if not due_at:
                continue

            try:
                if due_at.endswith("Z"):
                    dt = datetime.strptime(due_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc,
                    )
                else:
                    dt = datetime.fromisoformat(due_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                continue

            if dt.month != current_month or dt.year != current_year:
                continue

            due_date = dt.date()
            has_submitted = bool(a.get("has_submitted_submissions"))

            if has_submitted:
                bucket = "submitted"
            elif due_date < today:
                bucket = "past"
            else:
                bucket = "todo"

            all_month_assignments.append(
                {
                    "course_id": course_id,
                    "course_name": course_name,
                    "assignment": a,
                    "due_dt": dt,
                    "bucket": bucket,
                }
            )

    if not all_month_assignments:
        await message.reply_text(
            "No assignments with due dates in this month were found.",
            reply_markup=main_menu_keyboard(),
        )
        return

    todo_count = sum(1 for item in all_month_assignments if item["bucket"] == "todo")
    submitted_count = sum(
        1 for item in all_month_assignments if item["bucket"] == "submitted"
    )
    past_count = sum(1 for item in all_month_assignments if item["bucket"] == "past")

    total_count = len(all_month_assignments)

    # Determine the most urgent upcoming (to-do) assignment
    upcoming_items = [
        item
        for item in all_month_assignments
        if item["bucket"] == "todo" and item["due_dt"].date() >= today
    ]
    upcoming_items.sort(key=lambda item: item["due_dt"])

    urgent_item = upcoming_items[0] if upcoming_items else None
    urgent_course_id: int | None = urgent_item["course_id"] if urgent_item else None
    urgent_assignment_id: int | None = (
        urgent_item["assignment"].get("id") if urgent_item else None
    )

    def _relative_due_phrase(due_dt) -> str:
        days = (due_dt.date() - today).days
        if days == 0:
            return "Due today"
        if days == 1:
            return "Due tomorrow"
        if days > 1:
            return f"Due in {days} days"
        # Past
        days_ago = abs(days)
        if days_ago == 1:
            return "1 day ago"
        return f"{days_ago} days ago"

    def _priority_badge(due_dt) -> str:
        days = (due_dt.date() - today).days
        if days <= 1:
            return "🔥"
        if days <= 7:
            return "⏳"
        return "📌"

    # Header with month + progress summary
    lines: list[str] = []
    month_label = today.strftime("%B %Y")
    lines.append(f"*{month_label} — Assignments*")
    lines.append(
        f"Total {total_count} · Completed {submitted_count} · Pending {todo_count} · Overdue {past_count}"
    )

    # Urgent focus block
    if urgent_item:
        a = urgent_item["assignment"]
        course_name = urgent_item["course_name"]
        name = a.get("name") or f"Assignment {a.get('id')}"
        due_dt = urgent_item["due_dt"]
        badge = _priority_badge(due_dt)
        due_phrase = _relative_due_phrase(due_dt)

        lines.append("")
        lines.append(f"Next up: {badge} *{name}* — _{course_name}_")
        lines.append(f"{due_phrase}")
        lines.append("Tip: Reserve 20–30 minutes to start this.")

    # Grouped sections: Upcoming (todo), Submitted, Past Due
    def _render_section(title: str, items: list[dict], *, past: bool = False) -> None:
        if not items:
            return

        lines.append("")
        lines.append(f"*{title}*")

        # Sort nearest deadlines first; for past, nearest in the past first
        items_sorted = sorted(
            items,
            key=lambda item: item["due_dt"],
            reverse=past,
        )

        if compact:
            items_sorted = items_sorted[:5]

        for item in items_sorted:
            a = item["assignment"]
            course_name = item["course_name"]
            name = a.get("name") or f"Assignment {a.get('id')}"
            due_dt = item["due_dt"]
            badge = _priority_badge(due_dt)
            due_phrase = _relative_due_phrase(due_dt)

            lines.append(f"• {badge} *{name}* — _{course_name}_\n  {due_phrase}")

    upcoming_section = [
        item
        for item in all_month_assignments
        if item["bucket"] == "todo" and item["due_dt"].date() >= today
    ]
    submitted_section = [
        item for item in all_month_assignments if item["bucket"] == "submitted"
    ]
    past_section = [item for item in all_month_assignments if item["bucket"] == "past"]

    _render_section("Upcoming", upcoming_section, past=False)
    _render_section("Submitted", submitted_section, past=False)
    _render_section("Past Due", past_section, past=True)

    if compact and (total_count > 5):
        lines.append("")
        lines.append("Showing a quick summary. Tap *View All* for full details.")

    text = "\n".join(lines)

    reply_markup = month_assignments_keyboard(
        urgent_course_id,
        urgent_assignment_id,
        compact=compact,
    )

    if edit:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await message.reply_text(
            text,
            reply_markup=reply_markup,
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
        "📝 */assignments* — This month's assignment To-Do list\n"
        "📅 */calendar* — Open date picker calendar\n"
        "📊 */grades* — Current grades\n"
        "⏰ */reminders* — Manage reminders\n"
        "❓ */help* — Show this message",
        parse_mode="Markdown",
    )


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /calendar command.

    Shows an inline monthly calendar keyboard where the user can pick a date.
    """

    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    user = update.effective_user

    logger.info(
        "Received /calendar from user_id=%s username=%s",
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
            "To load your calendar assignments, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Determine the visible month (current month) and a slightly wider
    # window to fetch calendar events around it.
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    month = now_utc.month

    first_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = _calendar.monthrange(year, month)[1]
    last_of_month = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    start_dt = first_of_month - timedelta(days=7)
    end_dt = last_of_month + timedelta(days=7)

    def _to_canvas_iso(dt: datetime) -> str:
        # Canvas expects an ISO8601 timestamp, typically with a 'Z' suffix.
        return dt.isoformat().replace("+00:00", "Z")

    # Build context codes from the user's active dashboard courses.
    try:
        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load courses for calendar: %s", exc)
        await message.reply_text(
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

    assignments_by_date: dict[str, list[dict[str, Any]]] = {}

    try:
        events = get_calendar_events(
            canvas_token=canvas_token,
            start_date=_to_canvas_iso(start_dt),
            end_date=_to_canvas_iso(end_dt),
            context_codes=context_codes,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load calendar events: %s", exc)
        await message.reply_text(
            f"Failed to load calendar events: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return

    today_date = date.today()

    for event in events:
        # get_calendar_events returns a simplified event dict with
        # a normalized "start_at" timestamp. We only need the
        # calendar date portion (YYYY-MM-DD).
        raw_date = event.get("start_at")
        if not raw_date:
            continue

        if "T" in raw_date:
            date_str = raw_date.split("T", maxsplit=1)[0]
        else:
            date_str = raw_date

        # Basic safety: skip events outside our month window.
        try:
            event_date = datetime.fromisoformat(date_str).date()
        except Exception:  # noqa: BLE001
            # Fallback: best-effort parse using simple slicing.
            try:
                event_date = date.fromisoformat(date_str)
            except Exception:  # noqa: BLE001
                continue

        # Consider an assignment "urgent" if it's today or in the past.
        urgent = event_date <= today_date

        title = event.get("title") or "Assignment"
        description = event.get("description") or "Description not available"

        course_name = event.get("context_name") or "Unknown course"

        assignments_by_date.setdefault(date_str, []).append(
            {
                "title": title,
                "description": description,
                "urgent": urgent,
                "course_name": str(course_name),
            }
        )

    await message.reply_text(
        "📅 Choose a date from the calendar below:",
        reply_markup=calendar_keyboard(
            year=year,
            month=month,
            assignments_by_date=assignments_by_date,
        ),
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


async def assignments_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /assignments command.

    Shows a this-month overview of assignments across all active courses.
    """

    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    user = update.effective_user

    logger.info(
        "Received /assignments from user_id=%s username=%s",
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
            "To load your assignments, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    await render_month_assignments_overview(
        message,
        canvas_token=canvas_token,
        filter_mode="todo",
        edit=False,
        compact=True,
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


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /download command.

    Extracts Canvas file API links (data-api-endpoint) from assignment
    descriptions in the same calendar window used by /calendar and
    sends them to the user.
    """

    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    user = update.effective_user

    logger.info(
        "Received /download from user_id=%s username=%s",
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
            "To fetch assignment downloads, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Use the same time window as /calendar (current month ± 7 days).
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    month = now_utc.month

    first_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = _calendar.monthrange(year, month)[1]
    last_of_month = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    start_dt = first_of_month - timedelta(days=7)
    end_dt = last_of_month + timedelta(days=7)

    def _to_canvas_iso(dt: datetime) -> str:
        return dt.isoformat().replace("+00:00", "Z")

    # Build context codes from the user's active dashboard courses.
    try:
        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load courses for download list: %s", exc)
        await message.reply_text(
            f"Failed to load courses for downloads: {exc}",
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

    try:
        events = get_calendar_events(
            canvas_token=canvas_token,
            start_date=_to_canvas_iso(start_dt),
            end_date=_to_canvas_iso(end_dt),
            context_codes=context_codes,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load calendar events for downloads: %s", exc)
        await message.reply_text(
            f"Failed to load calendar events: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines: list[str] = [
        "📥 *Download links from your assignments*",
        "",
    ]

    link_count = 0
    pattern = re.compile(r'data-api-endpoint="([^"]+)"')

    for event in events:
        raw_desc_html = event.get("description") or ""
        if not raw_desc_html:
            continue

        # Extract Canvas file API URLs from the HTML description
        links = pattern.findall(raw_desc_html)
        if not links:
            continue

        # Clean description text (strip tags, decode HTML entities, normalize spaces)
        clean_desc = re.sub(r"<[^>]+>", "", raw_desc_html)
        clean_desc = html.unescape(clean_desc)
        clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

        course_name = event.get("context_name") or "Unknown course"
        title = event.get("title") or "Assignment"

        # Block-style summary per assignment
        lines.append(f"• {course_name}")
        lines.append(f"  Title: {title}")
        if clean_desc:
            lines.append(f"  Description: {clean_desc}")

        # Download and send each linked file to the user
        for api_endpoint in links:
            try:
                tmp_path, filename, _mime = download_canvas_file(
                    canvas_token, api_endpoint
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to download Canvas file %s: %s", api_endpoint, exc)
                lines.append(f"  File (failed): {api_endpoint} — {exc}")
                continue

            link_count += 1
            caption = f"{course_name}\nTitle: {title}"

            try:
                with open(tmp_path, "rb") as fh:
                    await message.reply_document(
                        document=InputFile(fh, filename=filename),
                        caption=caption,
                    )
                lines.append(f"  File: {filename}")
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    logger.warning("Failed to remove temp file %s", tmp_path)

        lines.append("")

    if link_count == 0:
        await message.reply_text(
            "No downloadable Canvas files were found in your current calendar assignments.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
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
