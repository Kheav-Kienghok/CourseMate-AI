from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the main inline keyboard for general navigation."""

    keyboard = [
        [
            InlineKeyboardButton("📚 Courses", callback_data="courses"),
            InlineKeyboardButton("📋 Assignments", callback_data="assignments"),
        ],
        [
            InlineKeyboardButton("📊 Grades", callback_data="grades"),
            InlineKeyboardButton("⏰ Reminders", callback_data="reminders"),
        ],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
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
