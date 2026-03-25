from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the main inline keyboard for general navigation."""

    keyboard = [
        [
            InlineKeyboardButton("📚 Courses", callback_data="courses"),
            InlineKeyboardButton("📅 Calendar", callback_data="calendar"),
        ],
        [
            InlineKeyboardButton("📊 Grades", callback_data="grades"),
            InlineKeyboardButton("⏰ Reminders", callback_data="reminders"),
        ],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ]

    return InlineKeyboardMarkup(keyboard)


def reminders_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    """Inline keyboard for toggling planner announcement notifications."""

    status_label = "✅ Notifications ON" if enabled else "❌ Notifications OFF"

    keyboard = [
        [
            InlineKeyboardButton(
                "Yes, send announcements",
                callback_data="reminders:announcements:yes",
            ),
            InlineKeyboardButton(
                "No, don't send",
                callback_data="reminders:announcements:no",
            ),
        ],
        [InlineKeyboardButton(status_label, callback_data="reminders:ignore")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu")],
    ]

    return InlineKeyboardMarkup(keyboard)


def course_menu_keyboard(course_id: int) -> InlineKeyboardMarkup:
    """Return an inline keyboard for a specific course."""

    keyboard = [
        [
            InlineKeyboardButton(
                "📋 Roll Call Attendance",
                callback_data=f"course:{course_id}:rollcall",
            ),
            InlineKeyboardButton(
                "📜 Past Assignments",
                callback_data=f"course:{course_id}:assignments:past",
            ),
        ],
        [
            InlineKeyboardButton(
                "📝 Upcoming Assignments",
                callback_data=f"course:{course_id}:assignments:upcoming",
            ),
        ],
        [InlineKeyboardButton("⬅️ Back to Courses", callback_data="courses")],
    ]

    return InlineKeyboardMarkup(keyboard)


def courses_keyboard(courses: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Return an inline keyboard with one button per course name."""

    buttons: list[list[InlineKeyboardButton]] = []

    for course in courses:
        course_id = course.get("id")
        name = course.get("shortName") or course.get("originalName") or str(course_id)

        fullname = f"{name} ({course.get('courseCode', '')}) - {course.get('section', '')}".strip()

        if course_id is None:
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    fullname,
                    callback_data=f"course:{course_id}",
                )
            ]
        )

    # Fallback to main menu if we somehow had no valid courses
    if not buttons:
        return main_menu_keyboard()

    # Add navigation
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu")])

    return InlineKeyboardMarkup(buttons)


def month_assignments_keyboard(
    urgent_course_id: int | None,
    urgent_assignment_id: int | None,
    *,
    compact: bool = True,
) -> InlineKeyboardMarkup:
    """Inline keyboard for this month's assignments overview.

    The layout is action‑oriented with at most 2–3 buttons per row.
    """

    buttons: list[list[InlineKeyboardButton]] = []

    # Primary actions for the most urgent upcoming assignment
    if urgent_course_id is not None and urgent_assignment_id is not None:
        buttons.append(
            [
                InlineKeyboardButton(
                    "✅ Mark Done",
                    callback_data=(
                        f"assignments:urgent:done:{urgent_course_id}:{urgent_assignment_id}"
                    ),
                ),
                InlineKeyboardButton(
                    "⏰ Remind Me",
                    callback_data=(
                        f"assignments:urgent:remind:{urgent_course_id}:{urgent_assignment_id}"
                    ),
                ),
            ]
        )

    # Secondary navigation / scope actions
    # Button always points to the *other* mode so tapping it
    # actually changes what we render and avoids "message is not modified".
    target_mode = "full" if compact else "compact"
    toggle_label = "View All" if compact else "Show Less"

    buttons.append(
        [
            InlineKeyboardButton(
                toggle_label,
                callback_data=f"assignments:this_month:{target_mode}",
            ),
            InlineKeyboardButton("⬅️ Menu", callback_data="menu"),
        ]
    )

    return InlineKeyboardMarkup(buttons)


def assignments_keyboard(assignments: list[dict[str, str]]) -> InlineKeyboardMarkup:
    """Return an inline keyboard with one button per assignment.

    Each assignment dict should contain:
    - title
    - assignment_lid
    - submission_id
    """

    buttons: list[list[InlineKeyboardButton]] = []

    for a in assignments:
        assignment_lid = a.get("assignment_lid")
        submission_id = a.get("submission_id")
        title = a.get("title", "Assignment")

        if not assignment_lid or not submission_id:
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    title,
                    callback_data=f"assignment:{assignment_lid}:{submission_id}",
                )
            ]
        )

    if not buttons:
        return main_menu_keyboard()

    # Navigation
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu")])

    return InlineKeyboardMarkup(buttons)


def course_assignments_keyboard(
    course_id: int,
    assignments: list[dict[str, Any]],
    page: int,
    total_pages: int,
    status: str | None = None,
) -> InlineKeyboardMarkup:
    """Return an inline keyboard for a page of course assignments.

    Each assignment dict is expected to have at least:
    - id
    - name
    """

    buttons: list[list[InlineKeyboardButton]] = []

    for a in assignments:
        assignment_id = a.get("id")
        name = a.get("name") or f"Assignment {assignment_id}"

        if assignment_id is None:
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    name,
                    callback_data=f"course-assignment:{course_id}:{assignment_id}",
                )
            ]
        )

    if not buttons:
        return main_menu_keyboard()

    # Pagination + back, all on a single row when applicable
    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []

        # Always include back-to-course on paginated views
        nav_row.append(
            InlineKeyboardButton(
                "⬅️ Back to course", callback_data=f"course:{course_id}"
            )
        )

        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    "⬅️ Prev",
                    callback_data=(
                        f"course:{course_id}:assignments:{status}:{page - 1}"
                        if status in {"past", "upcoming"}
                        else f"course:{course_id}:assignments:{page - 1}"
                    ),
                )
            )

        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    "Next ➡️",
                    callback_data=(
                        f"course:{course_id}:assignments:{status}:{page + 1}"
                        if status in {"past", "upcoming"}
                        else f"course:{course_id}:assignments:{page + 1}"
                    ),
                )
            )

        buttons.append(nav_row)
    else:
        # Single-page: only show back-to-course
        buttons.append(
            [
                InlineKeyboardButton(
                    "⬅️ Back to course", callback_data=f"course:{course_id}"
                )
            ]
        )

    return InlineKeyboardMarkup(buttons)


def calendar_keyboard(
    year: int | None = None,
    month: int | None = None,
    assignments_by_date: dict[str, list[dict[str, Any]]] | None = None,
) -> InlineKeyboardMarkup:
    """Return an inline keyboard showing a monthly calendar grid.

    Layout:
    - Row 1: prev month, "Month YYYY" label, next month
    - Row 2: weekday names (Mo..Su)
    - Rows 3+: weeks with day numbers; empty cells are non-clickable

    Visual markers:
    - Today: 🔵
    - Upcoming assignment day: 🟡
    - Past assignment day (submitted): 🟢
    - Past assignment day (not submitted): 🔴
    - Combined (e.g. today + past): 🔵🔴 or 🔵🟢
    """

    today = date.today()
    year = year or today.year
    month = month or today.month
    assignments_by_date = assignments_by_date or {}

    cal = calendar.Calendar(firstweekday=0)  # Monday start

    # Header row with navigation
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    header_row = [
        InlineKeyboardButton(
            "<",
            callback_data=f"cal:prev:{prev_year}-{prev_month:02d}",
        ),
        InlineKeyboardButton(
            f"{calendar.month_name[month]} {year}",
            callback_data="cal:ignore",
        ),
        InlineKeyboardButton(
            ">",
            callback_data=f"cal:next:{next_year}-{next_month:02d}",
        ),
    ]

    # Weekday names row (Mo-Su)
    weekday_names = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    weekdays_row = [
        InlineKeyboardButton(name, callback_data="cal:ignore") for name in weekday_names
    ]

    keyboard: list[list[InlineKeyboardButton]] = [header_row, weekdays_row]

    def _build_day_button(day_number: int) -> InlineKeyboardButton:
        day_date = date(year, month, day_number)
        day_str = day_date.strftime("%Y-%m-%d")

        is_today = day_date == today
        day_assignments = assignments_by_date.get(day_str, [])
        has_assignments = bool(day_assignments)

        statuses = {a.get("status") for a in day_assignments}
        has_past_unsubmitted = "past_unsubmitted" in statuses
        has_past_submitted = "past_submitted" in statuses
        has_upcoming = "upcoming" in statuses

        markers: list[str] = []
        if is_today:
            markers.append("🔵")
        if has_past_unsubmitted:
            markers.append("🔴")
        elif has_past_submitted:
            markers.append("🟢")
        elif has_upcoming:
            markers.append("🟡")

        marker_text = "".join(markers)
        label = str(day_number)

        if has_assignments and len(day_assignments) > 1:
            # Show the number of assignments in parentheses, e.g. "21 (2)".
            label = f"{label} ({len(day_assignments)})"

        if marker_text:
            label = f"{label}{marker_text}"

        if has_assignments:
            # The callback flag is currently informational only.
            flag = "assignments"
            callback_suffix = f"{day_str}:{flag}"
        else:
            callback_suffix = day_str

        callback_data = f"cal:day:{callback_suffix}"
        return InlineKeyboardButton(label, callback_data=callback_data)

    # Weeks of the month
    for week in cal.monthdayscalendar(year, month):
        row: list[InlineKeyboardButton] = []
        for day_number in week:
            if day_number == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal:ignore"))
            else:
                row.append(_build_day_button(day_number))
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)
