from __future__ import annotations

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the main inline keyboard for general navigation."""

    keyboard = [
        [
            InlineKeyboardButton("📚 Courses", callback_data="courses"),
            InlineKeyboardButton("📝 Assignments", callback_data="assignments"),
        ],
        [
            InlineKeyboardButton("📊 Grades", callback_data="grades"),
            InlineKeyboardButton("⏰ Reminders", callback_data="reminders"),
        ],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ]

    return InlineKeyboardMarkup(keyboard)


def courses_keyboard(courses: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Return an inline keyboard with one button per course name."""

    buttons: list[list[InlineKeyboardButton]] = []

    for course in courses:
        course_id = course.get("id")
        name = (
            course.get("shortName")
            or course.get("originalName")
            or str(course_id)
        )

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
