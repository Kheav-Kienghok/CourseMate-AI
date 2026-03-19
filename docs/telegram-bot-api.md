# Telegram Bot API (Function-Level Overview)

This document explains the main Telegram-facing functions in the bot, with clear inputs and outputs. All handlers are `async` functions built for `python-telegram-bot`.

---

## Commands (`app/bot/commands.py`)

### `start_command(update, context)`

- **Purpose**: Handle `/start`. Introduces the bot and shows the main menu.
- **Inputs**:
  - `update: telegram.Update` – used for `effective_chat`, `effective_message`, `effective_user`.
  - `context: ContextTypes.DEFAULT_TYPE` – not used for state here.
- **Outputs / Side effects**:
  - Sends a welcome message to the user.
  - Attaches the main menu inline keyboard via `main_menu_keyboard()`.
  - Returns `None` (like other handlers).

### `help_command(update, context)`

- **Purpose**: Handle `/help`. Lists available commands.
- **Inputs**:
  - `update`, `context` as above.
- **Outputs / Side effects**:
  - Sends a Markdown-formatted help text describing each command.
  - Returns `None`.

### `courses_command(update, context)`

- **Purpose**: Handle `/courses`. Shows the user’s Canvas courses.
- **Inputs**:
  - `update`, `context` as above.
- **Processing**:
  - Reads `chat_id` from `update.effective_chat.id`.
  - Uses `get_user_canvas_token(chat_id)` to load the stored Canvas token.
  - If no token, replies with instructions for `/settoken` and stops.
  - If token exists, calls `render_courses(message, canvas_token)`.
- **Outputs / Side effects**:
  - On success: displays a formatted list of courses and a courses keyboard.
  - On missing token: sends guidance to set a token.
  - On errors from Canvas: handled inside `render_courses` with user-friendly messages.
  - Returns `None`.

### `assignments_command(update, context)`

- **Purpose**: Handle `/assignments`. Shows this month’s To‑Do assignments across courses.
- **Inputs**:
  - `update`, `context` as above.
- **Processing**:
  - Reads `chat_id`.
  - Uses `get_user_canvas_token(chat_id)`.
  - If no token, replies with `/settoken` instructions.
  - If token exists, calls
    `render_month_assignments_overview(message, canvas_token, filter_mode="todo")`.
- **Outputs / Side effects**:
  - On success: sends a monthly overview message with an inline keyboard to switch buckets (todo/submitted/past).
  - On missing token: sends configuration instructions.
  - Returns `None`.

### `grades_command(update, context)`

- **Purpose**: Handle `/grades`. Placeholder for future grade summary.
- **Inputs**:
  - `update`, `context` as above.
- **Outputs / Side effects**:
  - Currently replies with "not implemented yet" and shows the main menu keyboard.
  - Returns `None`.

### `reminders_command(update, context)`

- **Purpose**: Handle `/reminders`. Placeholder for future reminder management.
- **Inputs**:
  - `update`, `context` as above.
- **Outputs / Side effects**:
  - Currently replies with "not implemented yet" and shows the main menu keyboard.
  - Returns `None`.

### `set_canvas_token_command(update, context)`

- **Purpose**: Handle `/settoken`. Stores the user’s Canvas API token securely.
- **Expected usage**: `/settoken YOUR_CANVAS_TOKEN`.
- **Inputs**:
  - `update`, `context` as above.
  - Uses `context.args` to read the token text.
- **Processing**:
  - Extracts `chat_id`, `username`, `first_name`, `last_name` from the update.
  - Validates that a non-empty token argument was provided.
  - Calls `set_user_canvas_token(chat_id, username, token, first_name, last_name)`.
  - Attempts to delete the original message (so the token is not left in chat history).
- **Outputs / Side effects**:
  - Persists the encrypted Canvas token in the local DB.
  - Sends a confirmation message with the main menu keyboard.
  - Returns `None`.

---

## Shared Render Helpers (`app/bot/commands.py`)

These functions are not Telegram handlers themselves but are called by commands and callbacks.

### `render_courses(message, canvas_token, edit=False)`

- **Purpose**: Render the user’s Canvas courses into a Telegram message.
- **Inputs**:
  - `message: telegram.Message` – the message to reply to or edit.
  - `canvas_token: str` – user’s Canvas API token.
  - `edit: bool` – if `True`, edits the existing message; otherwise, sends a new message.
- **Processing**:
  - Calls `get_dashboard_cards(canvas_token)`.
  - Formats course info (short name, code, section, term).
  - Builds and attaches a courses keyboard.
- **Outputs / Side effects**:
  - Sends or edits a message listing courses with an inline keyboard.
  - On Canvas/HTTP errors, sends a friendly error message instead.
  - Returns `None`.

### `render_course_assignments(message, course_id, canvas_token, page=1, edit=False, status=None)`

- **Purpose**: Render assignments for a specific course.
- **Inputs**:
  - `message: telegram.Message` – base message for reply/edit.
  - `course_id: int` – Canvas course id.
  - `canvas_token: str` – user’s Canvas API token.
  - `page: int` – which page of assignments to show (pagination).
  - `edit: bool` – whether to edit the existing message.
  - `status: str | None` – optional filter, e.g. `"past"` or `"upcoming"`.
- **Processing**:
  - Calls `get_course_assignments(course_id, canvas_token)`.
  - Filters and paginates assignments.
  - Uses course info (via `get_dashboard_cards`) to label the header.
  - Builds an inline keyboard for paging and navigation.
- **Outputs / Side effects**:
  - Sends or edits a message listing course assignments with navigation buttons.
  - Handles Canvas/HTTP errors with fallback messages.
  - Returns `None`.

### `render_month_assignments_overview(message, canvas_token, filter_mode="todo")`

- **Purpose**: Render a monthly assignment overview across courses.
- **Inputs**:
  - `message: telegram.Message` – base message for reply/edit.
  - `canvas_token: str` – user’s Canvas API token.
  - `filter_mode: str` – which bucket to display: `"todo"`, `"submitted"`, or `"past"`.
- **Processing**:
  - Calls `get_dashboard_cards(canvas_token)` to get active courses.
  - For each course, calls `get_course_assignments(course_id, canvas_token)`.
  - Filters to assignments in the current calendar month.
  - Groups assignments into buckets (todo / submitted / past) based on due and submission info.
  - Builds a summary text and a `month_assignments_keyboard` to switch buckets.
- **Outputs / Side effects**:
  - Sends or edits a summary message with an inline keyboard.
  - On errors, sends a user-friendly fallback message.
  - Returns `None`.

---

## Callbacks (`app/bot/callbacks.py`)

### `_require_canvas_token(query, action_text)`

- **Purpose**: Shared helper to ensure the user has a Canvas token before a callback uses Canvas.
- **Inputs**:
  - `query: telegram.CallbackQuery` – used for `message` and `message.chat.id`.
  - `action_text: str` – short description inserted into error text (e.g. "view your assignments").
- **Processing**:
  - Reads `chat_id` from `query.message.chat.id`.
  - Calls `get_user_canvas_token(chat_id)`.
  - If no `chat_id`, edits the message with a generic error.
  - If no token, edits the message with `/settoken` instructions.
- **Outputs / Side effects**:
  - On success: returns the Canvas token string.
  - On failure: edits the message with an error/instruction and returns `None`.

### `main_menu_callback(update, context)`

- **Purpose**: Central handler for inline keyboard callbacks.
- **Inputs**:
  - `update: telegram.Update` – used for `callback_query`.
  - `context: ContextTypes.DEFAULT_TYPE` – passed through to command handlers.
- **Callback data patterns and behavior**:
  - `"help"` → calls `help_command` to show help text.
  - `"assignments"` →
    - Calls `_require_canvas_token`.
    - On success, calls `render_month_assignments_overview(..., filter_mode="todo")`.
  - `"courses"` →
    - Calls `_require_canvas_token`.
    - On success, calls `render_courses(..., edit=True)`.
  - `"grades"` → calls `grades_command` (placeholder).
  - `"reminders"` → calls `reminders_command` (placeholder).
  - `"menu"` → edits the message to show a simple "Main menu" text plus `main_menu_keyboard()`.
  - `"assignments:this_month:{filter_mode}"` →
    - Parses `filter_mode` (e.g. `"todo"`, `"submitted"`, `"past"`).
    - Calls `_require_canvas_token` and then `render_month_assignments_overview` with that filter.
  - `"course:{course_id}:assignments[:status][:page]"` →
    - Parses `course_id`, optional `status`, and optional `page`.
    - Calls `_require_canvas_token`.
    - On success, calls `render_course_assignments(..., status=status, page=page, edit=True)`.
  - `"course:{course_id}:rollcall"` → placeholder; replies that roll call is not implemented.
  - `"course:{course_id}:grades"` → calls `grades_command` (placeholder).
  - `"course:{course_id}"` →
    - Calls `_require_canvas_token`.
    - On success, fetches `dashboard_cards` and finds the selected course.
    - Edits the message to show a course-specific menu with `course_menu_keyboard(course_id)`.
  - `"course-assignment:{course_id}:{assignment_id}"` →
    - Calls `_require_canvas_token`.
    - Fetches submission info via `get_assignment_submission`.
    - Edits the message to show assignment details and a back button.
  - `"assignment:{assignment_lid}:{submission_id}"` →
    - Calls `_require_canvas_token`.
    - Fetches GraphQL details via `get_student_assignment`.
    - Edits the message to show detailed assignment and submission info.
- **Outputs / Side effects**:
  - Answers the callback (`query.answer()`) to stop the loading spinner.
  - Edits existing messages or routes to command-style handlers that send new messages.
  - Returns `None`.

---

This document is intended as a quick reference for junior developers to see what each Telegram-facing function takes as input, what it does, and what it outputs or changes in the system.
