from __future__ import annotations

import calendar as _calendar
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast

from telegram import Update
from telegram.ext import ContextTypes

from bot.datetime_utils import _format_due_with_relative
from bot.intent_parser import ParsedIntent, parse_user_intent
from bot.keyboards import (
    calendar_keyboard,
    course_assignments_keyboard,
    courses_keyboard,
    main_menu_keyboard,
    month_assignments_keyboard,
    reminders_keyboard,
)
from canvas.canvas_client import (
    get_calendar_events,
    get_course_assignments,
    get_course_grade,
    get_dashboard_cards,
    get_planner_items,
)
from canvas.grade_rule import GradeCalculator
from services.user_store import get_user_canvas_token, set_user_canvas_token

logger = logging.getLogger(__name__)


# Number of assignments to show per page when listing course assignments.
ASSIGNMENTS_PAGE_SIZE = 5


_grade_calculator = GradeCalculator()


def _month_window(now_utc: datetime) -> tuple[int, int, datetime, datetime]:
    """Return (year, month, start_dt, end_dt) for the current month ± 7 days."""

    year = now_utc.year
    month = now_utc.month

    first_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = _calendar.monthrange(year, month)[1]
    last_of_month = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    start_dt = first_of_month - timedelta(days=7)
    end_dt = last_of_month + timedelta(days=7)

    return year, month, start_dt, end_dt


def _build_assignments_by_date(
    events: list[dict],
    *,
    today: date | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Transform Canvas calendar events into an assignments-by-date mapping.

    Shared by /calendar and calendar navigation callbacks to keep the
    calendar keyboard markers and click behaviour consistent.
    """

    assignments_by_date: dict[str, list[dict[str, Any]]] = {}

    today_date = today or date.today()

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

        # Basic safety: skip events we cannot parse into a valid date.
        try:
            event_date = datetime.fromisoformat(date_str).date()
        except Exception:  # noqa: BLE001
            try:
                event_date = date.fromisoformat(date_str)
            except Exception:  # noqa: BLE001
                continue

        # Determine status based on due date vs today and submission state.
        has_submitted = bool(event.get("has_submitted"))

        if event_date <= today_date:
            status = "past_submitted" if has_submitted else "past_unsubmitted"
        else:
            status = "upcoming"

        title = event.get("title") or "Assignment"
        description = event.get("description") or "Description not available"
        course_name = event.get("context_name") or "Unknown course"

        assignments_by_date.setdefault(date_str, []).append(
            {
                "title": title,
                "description": description,
                "status": status,
                "has_submitted": has_submitted,
                "course_name": str(course_name),
            }
        )

    return assignments_by_date


def _to_canvas_iso(dt: datetime) -> str:
    """Return an ISO8601 timestamp string suitable for Canvas API."""

    return dt.isoformat().replace("+00:00", "Z")


def _is_duplicate_command(
    context: ContextTypes.DEFAULT_TYPE,
    user,
    name: str,
    window_seconds: float = 5.0,
) -> bool:
    """Return True if this command was just used by the same user.

    This prevents users from triggering expensive commands (like /courses)
    multiple times in quick succession and receiving duplicate responses.
    """

    user_data = context.user_data or {}
    last_cmds = user_data.setdefault("_cm_last_commands", {})

    key_parts: list[str] = []
    if getattr(user, "id", None) is not None:
        key_parts.append(str(user.id))
    key_parts.append(name)
    key = ":".join(key_parts)

    now = time.monotonic()
    last_ts = last_cmds.get(key)
    if isinstance(last_ts, (int, float)) and now - float(last_ts) < window_seconds:
        return True

    last_cmds[key] = now
    return False


async def _get_chat_id_or_error(update: Update) -> int | None:
    """Return chat_id for the update, or reply with an error and return None."""

    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return None

    chat_id = getattr(chat, "id", None)
    if chat_id is None:
        await message.reply_text(
            "I couldn't identify your Telegram user. Please try again.",
            reply_markup=main_menu_keyboard(),
        )
        return None

    return chat_id


def _active_courses(dashboard_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return active courses, or the original list if no active state exists."""

    active = [c for c in dashboard_cards if c.get("enrollmentState") == "active"]
    return active or dashboard_cards


def _course_label(course: dict[str, Any]) -> str:
    name = course.get("shortName") or course.get("originalName") or "Unknown course"
    code = course.get("courseCode") or ""
    if code:
        return f"{name} ({code})"
    return str(name)


def _normalize_course_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _resolve_course_by_name(
    query: str | None,
    courses: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve a parsed course name to the best matching dashboard course."""

    if not query:
        return None

    normalized_query = _normalize_course_key(query)
    if not normalized_query:
        return None

    exact: list[dict[str, Any]] = []
    contains: list[dict[str, Any]] = []

    for course in courses:
        candidates: list[str] = []

        short_name = course.get("shortName")
        if isinstance(short_name, str):
            candidates.append(short_name)

        original_name = course.get("originalName")
        if isinstance(original_name, str):
            candidates.append(original_name)

        course_code = course.get("courseCode")
        if isinstance(course_code, str):
            candidates.append(course_code)

        for candidate in candidates:
            normalized_candidate = _normalize_course_key(candidate)
            if not normalized_candidate:
                continue

            if normalized_candidate == normalized_query:
                exact.append(course)
                break

            if (
                normalized_query in normalized_candidate
                or normalized_candidate in normalized_query
            ):
                contains.append(course)
                break

    if exact:
        return exact[0]
    if contains:
        return contains[0]
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False

    return None


def _target_percent_from_letter(desired_letter: str) -> float | None:
    for rule in _grade_calculator.rules:
        if rule.grade.upper() == desired_letter.upper():
            return float(rule.min_percent)
    return None


def _normalize_grade_components(raw_components: Any) -> list[dict[str, Any]]:
    """Normalize component entries used by grade calculations."""

    if not isinstance(raw_components, list):
        return []

    components: list[dict[str, Any]] = []

    for idx, item in enumerate(raw_components):
        if not isinstance(item, dict):
            continue

        name_raw = item.get("name")
        if isinstance(name_raw, str):
            name = name_raw.strip()
        elif name_raw is None:
            name = ""
        else:
            name = str(name_raw).strip()

        if not name:
            name = f"component_{idx + 1}"

        score = _to_float(item.get("score"))
        if score is not None and (score < 0.0 or score > 100.0):
            score = None

        weight_percent = _to_float(item.get("weight_percent"))
        if weight_percent is not None and (weight_percent < 0.0 or weight_percent > 100.0):
            weight_percent = None

        is_target_component = _to_bool(item.get("is_target_component"))

        components.append(
            {
                "name": name,
                "score": score,
                "weight_percent": weight_percent,
                "is_target_component": is_target_component,
            }
        )

    return components


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

    # Keep the header compact since the actual course list is presented
    # as buttons below.
    text = f"📚 *Your courses for* _{term}_\nChoose a course and keep making progress today 🔥"

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

    text = f"📝 *{label} for* _{course_label}_ (Page {page}/{total_pages}):"

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


async def _reply_single_course_grade(
    message,
    *,
    course: dict[str, Any],
    canvas_token: str,
) -> None:
    """Reply with a concise grade summary for one specific course."""

    course_id = course.get("id")
    if course_id is None:
        await message.reply_text(
            "I could not determine the selected course id.",
            reply_markup=main_menu_keyboard(),
        )
        return

    try:
        grade_info = get_course_grade(int(course_id), canvas_token=canvas_token)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load grade for course %s: %s", course_id, exc)
        await message.reply_text(
            f"Failed to load grade for {_course_label(course)}: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return

    current_score = grade_info.get("current_score")
    final_score = grade_info.get("final_score")
    current_grade = grade_info.get("current_grade")
    final_grade = grade_info.get("final_grade")

    score_value = _to_float(current_score)
    if score_value is None:
        score_value = _to_float(final_score)

    letter = current_grade or final_grade
    gpa: float | None = None

    if score_value is not None:
        mapped = _grade_calculator.get_rule(float(score_value))
        if mapped is not None:
            gpa = float(mapped.gpa)
            if not letter:
                letter = mapped.grade

    lines: list[str] = ["Course grade summary", ""]
    lines.append(f"Course: {_course_label(course)}")

    if score_value is not None:
        lines.append(f"Score: {score_value:.2f}%")
    else:
        lines.append("Score: N/A")

    lines.append(f"Letter: {letter or 'N/A'}")
    lines.append(f"GPA: {gpa:.2f}" if gpa is not None else "GPA: N/A")

    await message.reply_text("\n".join(lines), reply_markup=main_menu_keyboard())


async def _handle_today_assignments_intent(
    message,
    *,
    parsed: ParsedIntent,
    canvas_token: str,
    dashboard_cards: list[dict[str, Any]],
    selected_course: dict[str, Any] | None,
) -> None:
    """Handle AI intent for day-based assignment lookup."""

    target_date = parsed.date or date.today().isoformat()
    try:
        parsed_day = date.fromisoformat(target_date)
        target_date = parsed_day.isoformat()
    except ValueError:
        target_date = date.today().isoformat()

    courses_scope = [selected_course] if selected_course else _active_courses(
        dashboard_cards
    )

    context_codes: list[str] = []
    for course in courses_scope:
        if not course:
            continue
        course_id = course.get("id")
        if course_id is not None:
            context_codes.append(f"course_{course_id}")

    if not context_codes:
        await message.reply_text(
            "No active courses were found to search assignments.",
            reply_markup=main_menu_keyboard(),
        )
        return

    start_date = f"{target_date}T00:00:00.000Z"
    end_date = f"{target_date}T23:59:59.000Z"

    try:
        events = get_calendar_events(
            canvas_token=canvas_token,
            start_date=start_date,
            end_date=end_date,
            context_codes=context_codes,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load day assignments for AI intent: %s", exc)
        await message.reply_text(
            f"Failed to load assignments for {target_date}: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not events:
        scope_text = (
            f" in {_course_label(selected_course)}" if selected_course else ""
        )
        await message.reply_text(
            f"No assignments found for {target_date}{scope_text}.",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines: list[str] = [f"Assignments on {target_date}"]
    if selected_course:
        lines.append(f"Course: {_course_label(selected_course)}")
    lines.append("")

    events_sorted = sorted(events, key=lambda event: str(event.get("start_at") or ""))

    for event in events_sorted[:20]:
        title = event.get("title") or "Assignment"
        course_name = event.get("context_name") or "Unknown course"
        due_text = _format_due_with_relative(event.get("start_at")) or (
            event.get("start_at") or "Due date unavailable"
        )
        status = "submitted" if event.get("has_submitted") else "pending"

        if selected_course:
            lines.append(f"- {title} ({due_text}, {status})")
        else:
            lines.append(f"- {title} [{course_name}] ({due_text}, {status})")

    await message.reply_text("\n".join(lines), reply_markup=main_menu_keyboard())


async def _handle_grade_calculation_intent(
    message,
    *,
    parsed: ParsedIntent,
    canvas_token: str,
    selected_course: dict[str, Any] | None,
) -> None:
    """Handle AI intent for target-grade calculations."""

    inputs = parsed.grade_inputs or {}

    calculation_type_raw = inputs.get("calculation_type")
    calculation_type = (
        calculation_type_raw.strip().lower()
        if isinstance(calculation_type_raw, str)
        else None
    )
    if calculation_type not in {"current_total", "required_score"}:
        calculation_type = None

    target_percent = _to_float(inputs.get("target_percent"))
    desired_letter_raw = inputs.get("desired_letter")
    desired_letter = (
        desired_letter_raw.strip().upper()
        if isinstance(desired_letter_raw, str)
        else None
    )

    if target_percent is None and desired_letter:
        target_percent = _target_percent_from_letter(desired_letter)

    components = _normalize_grade_components(inputs.get("components"))

    if components:
        missing_weight = [
            str(component["name"])
            for component in components
            if component.get("weight_percent") is None
        ]
        if missing_weight:
            await message.reply_text(
                "Each component must include a weight percentage. Missing weight for: "
                + ", ".join(missing_weight),
                reply_markup=main_menu_keyboard(),
            )
            return

        total_weight = sum(float(component["weight_percent"]) for component in components)

        if total_weight <= 0.0:
            await message.reply_text(
                "The sum of component weights must be greater than 0.",
                reply_markup=main_menu_keyboard(),
            )
            return

        if total_weight > 100.0:
            await message.reply_text(
                "The sum of component weights cannot be more than 100%.",
                reply_markup=main_menu_keyboard(),
            )
            return

        known_components = [c for c in components if c.get("score") is not None]
        unknown_components = [c for c in components if c.get("score") is None]

        known_weight = sum(float(component["weight_percent"]) for component in known_components)
        known_contribution = sum(
            float(component["score"]) * float(component["weight_percent"]) / 100.0
            for component in known_components
        )

        current_total_so_far: float | None = None
        if known_weight > 0.0:
            current_total_so_far = known_contribution / (known_weight / 100.0)

        wants_required_score = (
            calculation_type == "required_score" or target_percent is not None
        )

        if wants_required_score:
            if target_percent is None:
                await message.reply_text(
                    "I need your target grade first. Example: target A- or target 90%.",
                    reply_markup=main_menu_keyboard(),
                )
                return

            if not unknown_components:
                lines: list[str] = ["Grade target check", ""]
                if selected_course is not None:
                    lines.append(f"Course: {_course_label(selected_course)}")

                lines.append(f"Target percent: {target_percent:.2f}%")
                lines.append(
                    f"Overall weighted grade from provided components: {known_contribution:.2f}%"
                )

                gap = target_percent - known_contribution
                if gap <= 0:
                    lines.append("Result: target is already reached.")
                else:
                    lines.append(
                        f"Result: target is short by {gap:.2f} percentage points."
                    )

                await message.reply_text(
                    "\n".join(lines),
                    reply_markup=main_menu_keyboard(),
                )
                return

            target_candidates = [
                c for c in unknown_components if c.get("is_target_component") is True
            ]

            if len(target_candidates) > 1:
                await message.reply_text(
                    "Only one target component can be unknown for required-score calculation.",
                    reply_markup=main_menu_keyboard(),
                )
                return

            if len(unknown_components) > 1 and not target_candidates:
                unknown_names = ", ".join(
                    str(component["name"]) for component in unknown_components
                )
                await message.reply_text(
                    "I can solve required score only when exactly one component score is unknown. "
                    f"Please provide more scores. Unknown components: {unknown_names}",
                    reply_markup=main_menu_keyboard(),
                )
                return

            target_component = (
                target_candidates[0] if target_candidates else unknown_components[0]
            )

            if len(unknown_components) > 1:
                unresolved = [
                    str(component["name"])
                    for component in unknown_components
                    if component is not target_component
                ]
                if unresolved:
                    await message.reply_text(
                        "I still need the score for: " + ", ".join(unresolved),
                        reply_markup=main_menu_keyboard(),
                    )
                    return

            unknown_weight = float(target_component["weight_percent"])
            if unknown_weight <= 0.0:
                await message.reply_text(
                    "Target component weight must be greater than 0.",
                    reply_markup=main_menu_keyboard(),
                )
                return

            required_score = (
                target_percent - known_contribution
            ) / (unknown_weight / 100.0)

            lines = ["Grade target calculation", ""]
            if selected_course is not None:
                lines.append(f"Course: {_course_label(selected_course)}")

            lines.append(f"Target percent: {target_percent:.2f}%")
            if desired_letter:
                lines.append(f"Target letter: {desired_letter}")

            lines.append(f"Known weighted contribution: {known_contribution:.2f}%")
            lines.append(
                f"Target component: {target_component['name']} ({unknown_weight:.2f}%)"
            )
            lines.append(f"Required score: {required_score:.2f}%")

            if current_total_so_far is not None:
                lines.append(
                    f"Current total over scored components: {current_total_so_far:.2f}%"
                )

            if required_score > 100.0:
                lines.append("Result: mathematically impossible with current numbers.")
            elif required_score < 0.0:
                lines.append("Result: target is already secured.")
            elif required_score >= 90.0:
                lines.append("Result: very challenging but still possible.")
            else:
                lines.append("Result: achievable with a focused prep plan.")

            await message.reply_text(
                "\n".join(lines),
                reply_markup=main_menu_keyboard(),
            )
            return

        if current_total_so_far is None:
            await message.reply_text(
                "I need at least one component score to calculate current total.",
                reply_markup=main_menu_keyboard(),
            )
            return

        lines = ["Current total grade calculation", ""]
        if selected_course is not None:
            lines.append(f"Course: {_course_label(selected_course)}")

        lines.append(
            f"Current total over scored components: {current_total_so_far:.2f}%"
        )
        lines.append(f"Scored weight: {known_weight:.2f}%")
        lines.append(f"Provided total component weight: {total_weight:.2f}%")
        lines.append(f"Weighted contribution so far: {known_contribution:.2f}%")

        if unknown_components:
            unknown_names = ", ".join(
                str(component["name"]) for component in unknown_components
            )
            lines.append(f"Missing scores for: {unknown_names}")
        elif abs(total_weight - 100.0) <= 1e-6:
            lines.append(
                f"Overall course total from provided components: {known_contribution:.2f}%"
            )
        else:
            lines.append(
                "All provided components are scored, but they account for less than 100% of the course."
            )

        await message.reply_text(
            "\n".join(lines),
            reply_markup=main_menu_keyboard(),
        )
        return

    current_percent = _to_float(inputs.get("current_percent"))
    final_weight_percent = _to_float(inputs.get("final_weight_percent"))
    current_weight_percent = _to_float(inputs.get("current_weight_percent"))

    if current_percent is None and selected_course is not None:
        selected_course_id = selected_course.get("id")
        if selected_course_id is not None:
            try:
                grade_info = get_course_grade(
                    int(selected_course_id),
                    canvas_token=canvas_token,
                )
                current_percent = _to_float(grade_info.get("current_score"))
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Could not auto-fill current score from course %s: %s",
                    selected_course_id,
                    exc,
                )

    if target_percent is None:
        await message.reply_text(
            "I need your target grade first. Example: target A- or target 90%.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if current_percent is None:
        await message.reply_text(
            "I need your current percentage. Example: current 78.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if final_weight_percent is None:
        await message.reply_text(
            "I need the final exam weight percentage. Example: final weight 40.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if final_weight_percent <= 0 or final_weight_percent > 100:
        await message.reply_text(
            "Final exam weight must be between 0 and 100.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if current_weight_percent is None:
        current_weight_percent = 100.0 - final_weight_percent

    if current_weight_percent < 0 or current_weight_percent > 100:
        await message.reply_text(
            "Current weight must be between 0 and 100.",
            reply_markup=main_menu_keyboard(),
        )
        return

    required_final = (
        target_percent - current_percent * (current_weight_percent / 100.0)
    ) / (final_weight_percent / 100.0)

    lines: list[str] = ["Grade target calculation", ""]
    if selected_course is not None:
        lines.append(f"Course: {_course_label(selected_course)}")

    lines.append(f"Current score: {current_percent:.2f}%")
    lines.append(f"Current weight: {current_weight_percent:.2f}%")
    lines.append(f"Final weight: {final_weight_percent:.2f}%")

    if desired_letter:
        lines.append(f"Target letter: {desired_letter}")
    lines.append(f"Target percent: {target_percent:.2f}%")
    lines.append("")
    lines.append(f"Required final score: {required_final:.2f}%")

    if required_final > 100:
        lines.append("Result: mathematically impossible with current numbers.")
    elif required_final < 0:
        lines.append("Result: target is already secured.")
    elif required_final >= 90:
        lines.append("Result: very challenging but still possible.")
    else:
        lines.append("Result: achievable with a focused final prep plan.")

    await message.reply_text("\n".join(lines), reply_markup=main_menu_keyboard())


async def natural_language_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle free-text messages via AI intent parsing and backend routing."""

    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    text = (message.text or "").strip()
    if not text:
        return

    if _is_duplicate_command(context, user, "ai_text", window_seconds=2.5):
        await message.reply_text(
            "Still processing your previous message, please wait…",
            reply_markup=main_menu_keyboard(),
        )
        return

    chat_id = await _get_chat_id_or_error(update)
    if chat_id is None:
        return

    canvas_token = get_user_canvas_token(chat_id)
    if not canvas_token:
        await message.reply_text(
            "To use AI message parsing, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    try:
        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load courses before AI parsing: %s", exc)
        await message.reply_text(
            f"Failed to load your courses: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return

    active_courses = _active_courses(dashboard_cards)
    available_course_names = [_course_label(course) for course in active_courses]

    parsed = parse_user_intent(
        text,
        today=date.today(),
        available_courses=available_course_names,
    )

    logger.info(
        "AI parse result | intent=%s course=%s date=%s confidence=%.2f error=%s",
        parsed.intent,
        parsed.course,
        parsed.date,
        parsed.confidence,
        parsed.error,
    )

    if parsed.intent == "unknown" and parsed.error:
        if "GEMINI_API_KEY" in parsed.error:
            await message.reply_text(
                "AI parsing is not configured yet. Please set GEMINI_API_KEY in your environment.",
                reply_markup=main_menu_keyboard(),
            )
            return

    selected_course = _resolve_course_by_name(parsed.course, active_courses)

    if parsed.course and selected_course is None and parsed.intent in {
        "course_assignments",
        "grades",
        "grade_calculation",
    }:
        await message.reply_text(
            f"I could not find a matching course for '{parsed.course}'. "
            "Try using the course code or the exact course name.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if parsed.intent == "today_assignments":
        await _handle_today_assignments_intent(
            message,
            parsed=parsed,
            canvas_token=canvas_token,
            dashboard_cards=dashboard_cards,
            selected_course=selected_course,
        )
        return

    if parsed.intent == "course_assignments":
        if selected_course is None:
            await message.reply_text(
                "Please include a course name. Example: assignments for Database Systems.",
                reply_markup=main_menu_keyboard(),
            )
            return

        selected_course_id = selected_course.get("id")
        if selected_course_id is None:
            await message.reply_text(
                "I could not determine the selected course id.",
                reply_markup=main_menu_keyboard(),
            )
            return

        await render_course_assignments(
            message,
            int(selected_course_id),
            canvas_token,
            page=1,
            edit=False,
            status=None,
        )
        return

    if parsed.intent == "grades":
        if selected_course is not None:
            await _reply_single_course_grade(
                message,
                course=selected_course,
                canvas_token=canvas_token,
            )
        else:
            await grades_command(update, context)
        return

    if parsed.intent == "overall_performance":
        await grades_command(update, context)
        return

    if parsed.intent == "grade_calculation":
        await _handle_grade_calculation_intent(
            message,
            parsed=parsed,
            canvas_token=canvas_token,
            selected_course=selected_course,
        )
        return

    await message.reply_text(
        "I could not confidently understand that request.\n\n"
        "Try examples:\n"
        "- assignments due today\n"
        "- assignments for Data Structures\n"
        "- show my grades\n"
        "- what do I need on the final to get A- (current 78, final 40%)",
        reply_markup=main_menu_keyboard(),
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
        "🗓 */planner* — Upcoming incomplete planner assignments\n"
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
    if not message:
        return

    user = update.effective_user

    logger.info(
        "Received /calendar from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    chat_id = await _get_chat_id_or_error(update)
    if chat_id is None:
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
    year, month, start_dt, end_dt = _month_window(now_utc)

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

    assignments_by_date = _build_assignments_by_date(events)

    legend_lines = [
        "📅 Choose a date from the calendar below:",
        "",
        "Legend:",
        "🔵 Today",
        "🟡 Upcoming assignments",
        "🟢 Past assignments (submitted)",
        "🔴 Past assignments (not submitted)",
    ]

    await message.reply_text(
        "\n".join(legend_lines),
        reply_markup=calendar_keyboard(
            year=year,
            month=month,
            assignments_by_date=assignments_by_date,
        ),
    )


async def courses_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /courses command."""

    message = update.effective_message
    if not message:
        return

    user = update.effective_user

    if _is_duplicate_command(context, user, "courses"):
        await message.reply_text(
            "Still processing your previous /courses request, please wait…",
            reply_markup=main_menu_keyboard(),
        )
        return

    logger.info(
        "Received /courses from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    chat_id = await _get_chat_id_or_error(update)
    if chat_id is None:
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
    if not message:
        return

    user = update.effective_user

    if _is_duplicate_command(context, user, "assignments"):
        await message.reply_text(
            "Still processing your previous /assignments request, please wait…",
            reply_markup=main_menu_keyboard(),
        )
        return

    logger.info(
        "Received /assignments from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    chat_id = await _get_chat_id_or_error(update)
    if chat_id is None:
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


async def planner_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /planner command.

    Shows upcoming, incomplete assignment items from the Canvas planner.
    """

    message = update.effective_message
    if not message:
        return

    user = update.effective_user

    logger.info(
        "Received /planner from user_id=%s username=%s",
        getattr(user, "id", None),
        getattr(user, "username", None),
    )

    chat_id = await _get_chat_id_or_error(update)
    if chat_id is None:
        return

    canvas_token = get_user_canvas_token(chat_id)
    if not canvas_token:
        await message.reply_text(
            "To load your upcoming planner assignments, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    try:
        items = get_planner_items(
            canvas_token=canvas_token,
            # Use a fixed term start date so we include all
            # relevant planner items from the semester onwards.
            start_date=_to_canvas_iso(
                datetime(2025, 9, 25, tzinfo=timezone.utc),
            ),
            filter="incomplete_items",
            order="asc",
            per_page=14,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load planner items: %s", exc)
        await message.reply_text(
            f"Failed to load planner items: {exc}",
            reply_markup=main_menu_keyboard(),
        )
        return

    upcoming: list[dict] = []
    for item in items:
        if item.get("plannable_type") != "assignment":
            continue

        submissions = item.get("submissions") or {}
        if submissions.get("submitted"):
            continue

        plannable = item.get("plannable") or {}

        upcoming.append(
            {
                "course_name": item.get("context_name") or "Unknown course",
                "title": plannable.get("title") or f"Assignment {plannable.get('id')}",
                "due_at": plannable.get("due_at"),
            }
        )

    if not upcoming:
        await message.reply_text(
            "You have no incomplete planner assignments starting from today.",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines: list[str] = ["📝 *Upcoming planner assignments*", ""]

    for entry in upcoming:
        course_name = entry["course_name"]
        title = entry["title"]
        due_at = entry["due_at"]

        pretty_due = _format_due_with_relative(due_at) or (
            due_at or "Due date not available"
        )

        lines.append(f"• *{title}* — _{course_name}_")
        lines.append(f"  {pretty_due}")

    await message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def send_planner_announcement_notifications_for_chat(
    chat_id: int,
    *,
    application,
) -> None:
    """Send unread announcement notifications for a single chat, if any.

    Used by scheduled jobs; respects the user's Canvas token and
    Canvas planner state (new_activity + unread announcements).
    """

    canvas_token = get_user_canvas_token(chat_id)
    if not canvas_token:
        return

    try:
        items = get_planner_items(
            canvas_token=canvas_token,
            # Use a fixed term start date to catch new activity
            # on announcements throughout the semester.
            start_date=_to_canvas_iso(
                datetime(2025, 9, 25, tzinfo=timezone.utc),
            ),
            filter="new_activity",
            order="asc",
            per_page=50,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to load planner items for announcements (chat_id=%s): %s",
            chat_id,
            exc,
        )
        return

    announcements: list[dict] = []

    for item in items:
        if item.get("plannable_type") != "announcement":
            continue

        if not item.get("new_activity"):
            continue

        plannable = item.get("plannable") or {}

        read_state = plannable.get("read_state") or "unknown"

        if read_state == "read":
            continue

        announcements.append(
            {
                "course_name": item.get("context_name") or "Unknown course",
                "title": plannable.get("title")
                or f"Announcement {plannable.get('id')}",
            }
        )

    if not announcements:
        return

    # Send each announcement as an individual message so that
    # every new activity shows up clearly in the chat.
    for entry in announcements:
        course_name = entry["course_name"]
        title = entry["title"]

        lines: list[str] = ["📢 *Course announcement*", ""]
        lines.append(f"*{title}* — _{course_name}_")

        await application.bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="Markdown",
        )


async def grades_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /grades command."""

    message = update.effective_message
    if not message:
        return

    user = update.effective_user
    query = update.callback_query
    data = query.data if query else None

    if _is_duplicate_command(context, user, "grades"):
        await message.reply_text(
            "Still processing your previous /grades request, please wait…",
            reply_markup=main_menu_keyboard(),
        )
        return

    logger.info(
        "Received /grades from user_id=%s username=%s (callback=%s)",
        getattr(user, "id", None),
        getattr(user, "username", None),
        bool(query),
    )

    chat_id = await _get_chat_id_or_error(update)
    if chat_id is None:
        return

    canvas_token = get_user_canvas_token(chat_id)
    if not canvas_token:
        text = (
            "To view your grades, please set your personal Canvas API token first.\n\n"
            "Send it using:\n"
            "*/settoken YOUR_CANVAS_TOKEN*\n\n"
            "You can create a token in Canvas under *Account → Settings → New Access Token*."
        )

        if query:
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        return

    # Detect whether this was triggered for a specific course via
    # callback data like "course:{course_id}:grades".
    selected_course_id: int | None = None
    if (
        isinstance(data, str)
        and data.startswith("course:")
        and data.endswith(":grades")
    ):
        parts = data.split(":", maxsplit=2)
        if len(parts) == 3:
            try:
                selected_course_id = int(parts[1])
            except ValueError:
                selected_course_id = None

    try:
        dashboard_cards = get_dashboard_cards(canvas_token=canvas_token)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load courses for grades: %s", exc)
        if query:
            await query.edit_message_text(
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
        text = "No courses found on your Canvas dashboard."
        if query:
            await query.edit_message_text(text, reply_markup=main_menu_keyboard())
        else:
            await message.reply_text(text, reply_markup=main_menu_keyboard())
        return

    # Filter to a single course when invoked from a course-specific
    # callback; otherwise include all active courses.
    courses_to_show: list[dict[str, Any]] = []

    for course in dashboard_cards:
        course_id = course.get("id")
        if course_id is None:
            continue

        if selected_course_id is not None and int(course_id) != selected_course_id:
            continue

        # Only show active enrollments in the overall grades view to
        # avoid clutter from concluded/archived courses.
        if selected_course_id is None and course.get("enrollmentState") != "active":
            continue

        courses_to_show.append(course)

    if not courses_to_show:
        text = "No matching courses found to show grades for."
        if query:
            await query.edit_message_text(text, reply_markup=main_menu_keyboard())
        else:
            await message.reply_text(text, reply_markup=main_menu_keyboard())
        return

    lines: list[str] = []

    # Derive a simple semester/term label from the first dashboard card.
    raw_term = dashboard_cards[0].get("term") if dashboard_cards else None
    if isinstance(raw_term, dict):
        term_label = (
            raw_term.get("name") or raw_term.get("sis_term_id") or "Current Term"
        )
    else:
        term_label = str(raw_term) if raw_term else "Current Term"

    if selected_course_id is not None:
        lines.append("📊 *Course Grade* ")
    else:
        lines.append("📊 *Your Current Course Grades*")

    lines.append(f"_Semester: {term_label}_")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("")

    overall_gpas: list[float] = []

    for course in courses_to_show:
        course_id_any = course.get("id")
        if course_id_any is None:
            continue

        name = (
            course.get("shortName") or course.get("originalName") or str(course_id_any)
        )
        code = course.get("courseCode") or ""
        section = course.get("section") or ""
        label = f"{name} ({code})".strip() if code else str(name)

        icon = "📚"

        try:
            grade_info = get_course_grade(int(course_id_any), canvas_token=canvas_token)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not load grade for course_id=%s: %s", course_id_any, exc
            )
            lines.append(f"• *{label}* — grade not available")
            continue

        current_score = grade_info.get("current_score")
        final_score = grade_info.get("final_score")
        current_grade = grade_info.get("current_grade")
        final_grade = grade_info.get("final_grade")

        def _fmt_score(score) -> str:
            if score is None:
                return "N/A"
            try:
                return f"{float(score):.2f}%"
            except Exception:  # noqa: BLE001
                return str(score)

        def _compute_letter_and_gpa(
            score, letter_from_canvas: str | None
        ) -> tuple[str | None, float | None]:
            """Return (letter, gpa) for a numeric score.

            Always uses the local grading_scale for GPA and prefers the
            Canvas-provided letter when present.
            """

            mapped = None
            if isinstance(score, (int, float)):
                mapped = _grade_calculator.get_rule(float(score))

            if mapped is not None:
                letter = mapped.grade
                gpa = mapped.gpa
                if letter_from_canvas:
                    letter = letter_from_canvas
                if isinstance(letter, str) and isinstance(gpa, (int, float)):
                    return letter, float(gpa)

            if letter_from_canvas:
                return letter_from_canvas, None

            return None, None

        if current_score is not None or current_grade:
            score_str = _fmt_score(current_score)
            letter, gpa = _compute_letter_and_gpa(current_score, current_grade)
            if gpa is not None:
                overall_gpas.append(gpa)
            letter_display = letter or "N/A"
            gpa_display = f"{gpa:.2f}" if gpa is not None else "N/A"
            lines.append(f"{icon} *{label}*")
            if section:
                lines.append(f"📌 Section: `{section}`")
            lines.append(
                f"📈 Score: *{score_str}* → *{letter_display}*  (`GPA {gpa_display}`)"
            )
            lines.append("")
        elif final_score is not None or final_grade:
            score_str = _fmt_score(final_score)
            letter, gpa = _compute_letter_and_gpa(final_score, final_grade)
            if gpa is not None:
                overall_gpas.append(gpa)
            letter_display = letter or "N/A"
            gpa_display = f"{gpa:.2f}" if gpa is not None else "N/A"
            lines.append(f"{icon} *{label}*")
            if section:
                lines.append(f"📌 Section: `{section}`")
            lines.append(
                f"📈 Score: *{score_str}* → *{letter_display}*  (`GPA {gpa_display}`)"
            )
            lines.append("")
        else:
            lines.append(f"{icon} *{label}*")
            if section:
                lines.append(f"📌 Section: `{section}`")
            lines.append("📈 Score: *N/A* → *N/A*  (`GPA N/A`)")
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━")

    # Compute a simple overall GPA across the shown courses using the
    # per-course GPA values from the grading scale.
    overall_gpa = sum(overall_gpas) / len(overall_gpas) if overall_gpas else None
    if overall_gpa is not None:
        overall_rule = _grade_calculator.get_rule_by_gpa(overall_gpa)
        overall_letter = overall_rule.grade if overall_rule else "N/A"
        lines.append(f"📊 *Overall GPA:* {overall_gpa:.2f} → *{overall_letter}*")
        if overall_gpa < 3.0:
            lines.append(
                "⚠️ *Overall Status:* There's room to improve — keep studying hard, you can do this!"
            )
        elif overall_gpa < 4.0:
            lines.append(
                "✅ *Overall Status:* Looking strong — keep up the great work! 🔥"
            )
        else:
            lines.append(
                "🏆 *Overall Status:* You are absolutely overkilling this semester — amazing job! 💥"
            )
    else:
        lines.append("ℹ️ *Overall Status:* Not enough grade data yet to compute GPA.")

    text = "\n".join(lines)

    if query:
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reminders command.

    Currently used to opt in/out of planner announcement notifications.
    """

    message = update.effective_message
    if not message:
        return

    chat_id = await _get_chat_id_or_error(update)
    if chat_id is None:
        return

    from services.user_store import get_planner_announcement_notifications

    enabled = get_planner_announcement_notifications(chat_id)

    text = (
        "⏰ *Planner Notifications*\n\n"
        "Would you like to receive Telegram notifications when there are "
        "unread Canvas announcements with new activity?"
    )

    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=reminders_keyboard(enabled),
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
    if not message or not user:
        return

    chat_id = await _get_chat_id_or_error(update)
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)

    if chat_id is None:
        return

    chat = update.effective_chat
    assert chat is not None
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
