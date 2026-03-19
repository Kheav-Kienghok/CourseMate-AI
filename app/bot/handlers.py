"""Compatibility exports for bot handlers.

Historically, command, callback, and error logic lived in this module.
The implementation now lives in dedicated modules to avoid duplication,
while keeping imports like ``from bot.handlers import ...`` working.
"""

from __future__ import annotations

from bot.callbacks import main_menu_callback
from bot.commands import (
    courses_command,
    grades_command,
    help_command,
    reminders_command,
    render_course_assignments,
    render_courses,
    set_canvas_token_command,
    start_command,
)
from bot.errors import error_handler

__all__ = [
    "start_command",
    "help_command",
    "courses_command",
    "grades_command",
    "reminders_command",
    "set_canvas_token_command",
    "main_menu_callback",
    "error_handler",
    "render_courses",
    "render_course_assignments",
]
