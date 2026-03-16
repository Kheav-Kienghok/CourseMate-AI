from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from canvas.canvas_client import get_dashboard_cards
from bot.keyboards import main_menu_keyboard, courses_keyboard


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "👋 Welcome to CourseMate AI!\n\n" "Choose an option below:",
        reply_markup=main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "Here are the commands you can use:\n\n"
        "• /start – Introduce the bot and link Canvas account\n"
        "• /courses – Show current semester courses\n"
        "• /assignments – List upcoming assignments\n"
        "• /grades – Display current grade summary\n"
        "• /reminders – Set or view upcoming reminders\n"
        "• /help – Show this help message"
    )


async def courses_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /courses command."""

    message = update.effective_message
    if not message:
        return

    try:
        dashboard_cards = get_dashboard_cards()
    except Exception as exc:  # noqa: BLE001
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

    term = dashboard_cards[0].get("term", "Unknown Term")

    lines: list[str] = [
        "📚 *YOUR COURSES*",
        f"🎓 _{term}_",
        "━━━━━━━━━━━━━━━",
        "",
    ]

    for course in dashboard_cards:
        if course.get("enrollmentState") == "active":

            name = (
                course.get("shortName")
                or course.get("originalName")
                or str(course.get("id"))
            )

            course_code = course.get("courseCode", "")
            section = course.get("section", "")
            state = course.get("enrollmentState", "unknown")

            full_name = f"{name} ({course_code}) - Section {section}".strip()

            lines.append(f"- *{full_name}* ")

    await message.reply_text(
        "\n".join(lines),
        reply_markup=courses_keyboard(dashboard_cards),
        parse_mode="Markdown",
    )


async def assignments_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /assignments command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "📝 Upcoming assignments are not implemented yet. "
        "This feature will list upcoming assignments from Canvas."
    )


async def grades_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /grades command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "📊 Grade summary is not implemented yet. "
        "This feature will show your current grades per course."
    )


async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reminders command."""

    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "⏰ Reminders are not implemented yet. "
        "In the future, this will let you set reminders for assignments and exams."
    )


async def main_menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle button clicks from the main inline menu.

    Routes button presses to the same logic as the text commands.
    """

    query = update.callback_query
    if not query:
        return

    # Acknowledge the button press so Telegram stops "loading" spinner
    await query.answer()

    data = query.data

    if data == "help":
        await help_command(update, context)
    elif data == "courses":
        # For the "Courses" button, replace the current menu message
        # with the list of courses and per-course buttons instead of
        # sending a new message. This way, the visible menu no longer
        # shows the generic "Courses / Assignments / Grades / Reminders / Help"
        # options but the actual courses.

        try:
            dashboard_cards = get_dashboard_cards()
        except Exception as exc:  # noqa: BLE001
            await query.edit_message_text(
                f"Failed to load courses: {exc}",
                reply_markup=main_menu_keyboard(),
            )
            return

        if not dashboard_cards:
            await query.edit_message_text(
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
            if course.get("enrollmentState") == "active":

                name = (
                    course.get("shortName")
                    or course.get("originalName")
                    or str(course.get("id"))
                )

                course_code = course.get("courseCode", "")
                section = course.get("section", "")

                full_name = f"{name} ({course_code}) - Section {section}".strip()

                lines.append(f"- *{full_name}* ")

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=courses_keyboard(dashboard_cards),
            parse_mode="Markdown",
        )
    elif data == "assignments":
        await assignments_command(update, context)
    elif data == "grades":
        await grades_command(update, context)
    elif data == "reminders":
        await reminders_command(update, context)
    elif data and data.startswith("course:"):
        # User clicked on a specific course button from courses_keyboard.
        # Replace the course list message with the selected course info
        # (so the previous list is "hidden") and show the main menu again.

        course_id_str = data.split(":", maxsplit=1)[1]

        try:
            dashboard_cards = get_dashboard_cards()
        except Exception as exc:  # noqa: BLE001
            await query.edit_message_text(
                f"Failed to load course details: {exc}",
                reply_markup=main_menu_keyboard(),
            )
            return

        selected_course = None
        for course in dashboard_cards:
            if str(course.get("id")) == course_id_str:
                selected_course = course
                break

        if not selected_course:
            await query.edit_message_text(
                "Could not find that course.",
                reply_markup=main_menu_keyboard(),
            )
            return

        name = (
            selected_course.get("shortName")
            or selected_course.get("originalName")
            or str(selected_course.get("id"))
        )

        course_code = selected_course.get("courseCode", "")
        section = selected_course.get("section", "")

        full_name = f"{name} ({course_code} Section {section})".strip()

        await query.edit_message_text(
            f"You selected *{full_name}*.",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown",
        )
    else:
        # Fallback for unknown buttons
        message = update.effective_message
        if message:
            await message.reply_text(
                "Unknown action.", reply_markup=main_menu_keyboard()
            )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler.

    Sends a friendly message to the user when something unexpected fails.
    """

    # Log the error to the console for debugging
    print("Bot error:", context.error)  # noqa: T201

    # Try to notify the user if we have a message context
    if isinstance(update, Update):
        message = update.effective_message
        if message:
            await message.reply_text(
                "⚠️ Something went wrong. Please try again later.",
                reply_markup=main_menu_keyboard(),
            )
