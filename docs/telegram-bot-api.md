# Telegram Bot API (Function-Level Overview)

This document describes the Telegram-facing API surface of CourseMate AI:

- command handlers (`/start`, `/courses`, etc.)
- callback router (`main_menu_callback`)
- shared “render” helpers called by both commands and callbacks
- keyboard/callback_data contracts the UI relies on

All handlers are **async** and designed for `python-telegram-bot` v20+.

---

## 0) Handler registration (`app/bot/telegram_bot.py`)

### `CourseMateBot`

**Purpose**
Creates and runs the Telegram `Application`, registers handlers, and starts polling.

**Key methods**

- `__init__(token: str | None = None)`
  - Resolves the bot token via `utils.config.get_telegram_bot_token()` if not provided.
  - Builds the `Application` using `ApplicationBuilder`.
  - Calls `_register_handlers()`.

- `_register_handlers() -> None`
  Registers:
  - `CommandHandler("start", start_command)`
  - `CommandHandler("help", help_command)`
  - `CommandHandler("settoken", set_canvas_token_command)`
  - `CommandHandler("courses", courses_command)`
  - `CommandHandler("assignments", assignments_command)`
  - `CommandHandler("calendar", calendar_command)`
  - `CommandHandler("download", download_command)`
  - `CommandHandler("grades", grades_command)` (placeholder)
  - `CommandHandler("reminders", reminders_command)` (placeholder)
  - `CallbackQueryHandler(main_menu_callback)` (all inline keyboard interactions)
  - global error handler: `error_handler`

- `run() -> None`
  Starts long polling via `run_polling(stop_signals=None)` so signal handling is done by `app/main.py`.

### `run_bot() -> None`

Backwards-compatible wrapper:

1. constructs `CourseMateBot()`
2. calls `.run()`

---

## 1) Shared render helpers (`app/bot/commands.py`)

These functions are not Telegram commands, but are reused by commands and callbacks.

### `render_courses(message, canvas_token: str, edit: bool = False) -> None`

**Purpose**
Renders the user’s *active* Canvas dashboard courses as a formatted message plus an inline keyboard.

**Inputs**

- `message`: a `telegram.Message` used to `reply_text` or `edit_text`
- `canvas_token: str`: Canvas API token
- `edit: bool`: if `True`, edits the existing message; otherwise replies with a new message

**Canvas calls**

- `canvas.canvas_client.get_dashboard_cards(canvas_token)`

**Output / side effects**

- Sends or edits a Markdown message containing:
  - header + term
  - a list of active courses formatted as `name (code) - Section <section>`
- Attaches `courses_keyboard(dashboard_cards)`.

**Failure behavior**

- On exception from Canvas: sends/edits `"Failed to load courses: <exc>"` with `main_menu_keyboard()`.
- If there are no dashboard cards: sends/edits `"No courses found..."` with `main_menu_keyboard()`.

---

### `render_course_assignments(message, course_id: int, canvas_token: str, *, page: int = 1, edit: bool = False, status: str | None = None) -> None`

**Purpose**
Renders assignments for a specific course, with pagination and optional filtering.

**Inputs**

- `course_id: int`: Canvas course id
- `status: str | None`:
  - `None`: show all assignments
  - `"past"`: due date strictly before “today (UTC)”
  - `"upcoming"`: due date today or later (UTC); also hides “Roll Call Attendance”
- `page: int`: 1-based page index
- `edit: bool`: reply vs edit

**Canvas calls**

- `get_course_assignments(course_id, canvas_token)` (REST)
- `get_dashboard_cards(canvas_token)` (for friendly course label)

**Pagination**

- `ASSIGNMENTS_PAGE_SIZE = 5`
- `total_pages = ceil(total_assignments / 5)`
- clamps `page` into `[1, total_pages]`

**Sorting**

- The Canvas client sorts by due date ascending (undated last).
- This renderer then reverses the list initially (`assignments = list(reversed(assignments))`)
  and applies additional status-specific sorting when `status in {"past","upcoming"}`.

**Output / side effects**

- Sends/edits a Markdown message like:
  - `📝 Upcoming assignments for <course_label> (Page X/Y):`
- Attaches `course_assignments_keyboard(course_id, page_assignments, page, total_pages, status)`.

**Notable UX behavior**

- If `status == "upcoming"` and there are no assignments, sends a friendly “Well done” message.

---

### `render_month_assignments_overview(message, canvas_token: str, *, filter_mode: str = "todo", edit: bool = False, compact: bool = True) -> None`

**Purpose**
Builds a “this month” cross-course summary using assignment due dates and submission state, then renders:

- totals (total/completed/pending/overdue)
- “Next up” urgent item (if present)
- grouped sections (Upcoming, Submitted, Past Due)
- a keyboard to toggle compact/full and do urgent actions

**Inputs**

- `filter_mode` (bucket assignment):
  - `"todo"`: not submitted + not past due
  - `"submitted"`: submitted
  - `"past"`: past due + not submitted
  > Note: the current implementation *computes all buckets* and renders sections; the UI uses `compact` to limit items shown.
- `compact: bool`:
  - `True`: shows at most 5 items per section and adds “Showing a quick summary…”
  - `False`: shows more items

**Canvas calls**

- `get_dashboard_cards(canvas_token)`
- `get_course_assignments(course_id, canvas_token)` per active course

**Urgency**

- Picks the nearest upcoming `todo` assignment in the current month and creates action buttons:
  - “✅ Mark Done” (local-only acknowledgement)
  - “⏰ Remind Me” (local-only acknowledgement)

**Output / side effects**

- Sends/edits a Markdown summary.
- Attaches `month_assignments_keyboard(urgent_course_id, urgent_assignment_id, compact=compact)`.

---

## 2) Telegram commands (`app/bot/commands.py`)

### `start_command(update, context) -> None`

**Purpose**
Welcomes the user and shows the main menu.

**Side effects**

- `reply_text(..., reply_markup=main_menu_keyboard(), parse_mode="Markdown")`

**Canvas usage**
None.

---

### `help_command(update, context) -> None`

**Purpose**
Shows a list of supported commands.

**Side effects**

- replies with a Markdown command list

**Canvas usage**
None.

---

### `courses_command(update, context) -> None`

**Purpose**
Shows the user’s Canvas courses.

**Processing**

1. Resolve `chat_id`
2. `canvas_token = get_user_canvas_token(chat_id)`
3. If missing token: send `/settoken` instructions
4. Else: call `render_courses(message, canvas_token)`

---

### `assignments_command(update, context) -> None`

**Purpose**
Shows the “this month” assignment overview.

**Processing**
Same token flow as `/courses`, then calls:

- `render_month_assignments_overview(..., filter_mode="todo", compact=True)`

---

### `calendar_command(update, context) -> None`

**Purpose**
Displays a navigable inline calendar for the current month, with markers for days that have assignments.

**Processing**

1. Resolve `chat_id`, load Canvas token
2. Compute a window:
   - start: first of month minus 7 days
   - end: last of month plus 7 days
3. Build `context_codes = ["course_<id>", ...]` from active courses
4. Fetch events via `get_calendar_events(...)`
5. Build `assignments_by_date: dict[YYYY-MM-DD, list[assignment_meta]]`
6. Reply with `calendar_keyboard(year, month, assignments_by_date)`

**Canvas usage**

- `get_dashboard_cards`
- `get_calendar_events`

---

### `download_command(update, context) -> None`

**Purpose**
Finds downloadable Canvas file links embedded in assignment descriptions (HTML `data-api-endpoint="..."`) within the current-month calendar window and sends the files to the user.

**Processing**

1. Same token + time window + context code logic as `/calendar`
2. Fetch events via `get_calendar_events`
3. Regex for file endpoints:
   - `data-api-endpoint="([^"]+)"`
4. For each endpoint:
   - `download_canvas_file(canvas_token, api_endpoint)`
   - send with `message.reply_document(InputFile(...), caption=...)`
   - delete temp file

**Canvas usage**

- `get_dashboard_cards`
- `get_calendar_events`
- `download_canvas_file`

---

### `grades_command(update, context) -> None` / `reminders_command(update, context) -> None`

Placeholders that reply “not implemented yet” and show `main_menu_keyboard()`.

---

### `set_canvas_token_command(update, context) -> None`

**Purpose**
Stores the user’s Canvas token in the DB (encrypted) and deletes the original message if possible.

**Expected usage**
`/settoken <TOKEN>`

**Processing**

- reads token from `context.args`
- calls `set_user_canvas_token(chat_id, username, token, first_name, last_name)`
- attempts `message.delete()`
- sends confirmation via `message.chat.send_message(...)`

---

## 3) Inline callbacks (`app/bot/callbacks.py`)

### `_require_canvas_token(query, action_text: str) -> str | None`

**Purpose**
Shared helper to ensure a callback has access to a valid Canvas token.

**Behavior**

- If no chat id: edits message with generic error + main menu keyboard
- If no token: edits message with `/settoken` instructions + main menu keyboard
- Else returns token

---

### `main_menu_callback(update, context) -> None`

**Purpose**
Central router for all `callback_data`.

**General behavior**

- deduplicates repeated taps for same `(user, callback_data)` within 10 seconds
- always calls `query.answer()` (spinner stop) unless returning early

#### Callback data: calendar (`cal:*`)

Generated by `calendar_keyboard()`.

- `cal:ignore`  
  Non-interactive cells (header, weekday labels, blanks). No action.

- `cal:prev:YYYY-MM` / `cal:next:YYYY-MM`  
  Updates only the markup:
  - `query.edit_message_reply_markup(reply_markup=calendar_keyboard(year, month))`

- `cal:day:YYYY-MM-DD`  
  Day without assignments. No action.

- `cal:day:YYYY-MM-DD:assignments` or `cal:day:YYYY-MM-DD:urgent`
  1. requires token
  2. rebuilds context codes from active courses
  3. calls `get_calendar_events()` with that single-day window
  4. edits the message to show assignment blocks, and downloads any Canvas files linked in descriptions

#### Callback data: main menu

- `calendar` -> calls `calendar_command(update, context)`
- `help` -> calls `help_command(update, context)`
- `assignments` -> requires token then `render_month_assignments_overview(..., edit=True, compact=True)`
- `courses` -> requires token then `render_courses(..., edit=True)`
- `grades` / `reminders` -> placeholders
- `menu` -> edits message to “Main menu:” + `main_menu_keyboard()`

#### Callback data: monthly assignment overview toggles/actions

- `assignments:this_month:compact` / `assignments:this_month:full`
  - reloads overview with `compact=(view_mode != "full")`

- `assignments:urgent:done:<course_id>:<assignment_id>`
- `assignments:urgent:remind:<course_id>:<assignment_id>`
  - currently acknowledges via `query.answer(...)` only (no persistence yet)

#### Callback data: course navigation

- `course:<course_id>`
  - shows course label + `course_menu_keyboard(course_id)`

- `course:<course_id>:rollcall`
  - placeholder: edits message “not implemented yet”

- `course:<course_id>:assignments[:<status>][:<page>]`
  - status may be `past` or `upcoming`
  - calls `render_course_assignments(..., edit=True, page=..., status=...)`

#### Callback data: assignment details (REST)

- `course-assignment:<course_id>:<assignment_id>`
  - fetches assignments list via `get_course_assignments()`
  - finds selected assignment
  - tries `get_assignment_submission()` to get score
  - edits message with details + “Back to assignments” button

#### Callback data: assignment details (GraphQL)

- `assignment:<assignment_lid>:<submission_id>`
  - fetches via `get_student_assignment()` (GraphQL)
  - edits message with points + score + due date + back button

---

## 4) Keyboard contracts (`app/bot/keyboards.py`)

These are important because callback routing depends on `callback_data` formats.

- `main_menu_keyboard()` -> callback_data:
  - `courses`, `calendar`, `grades`, `reminders`, `help`

- `courses_keyboard(courses)` -> per-course:
  - `course:<course_id>`
  - plus navigation `menu`

- `course_menu_keyboard(course_id)`:
  - `course:<id>:rollcall`
  - `course:<id>:assignments:past`
  - `course:<id>:assignments:upcoming`
  - back: `courses`

- `course_assignments_keyboard(course_id, ..., status)`:
  - assignment select: `course-assignment:<course_id>:<assignment_id>`
  - paging:
    - `course:<id>:assignments:<page>`
    - or `course:<id>:assignments:<status>:<page>`
  - back: `course:<id>`

- `month_assignments_keyboard(...)`:
  - urgent actions:
    - `assignments:urgent:done:<course_id>:<assignment_id>`
    - `assignments:urgent:remind:<course_id>:<assignment_id>`
  - toggle:
    - `assignments:this_month:full` or `assignments:this_month:compact`
  - menu: `menu`

- `calendar_keyboard(...)`:
  - day selection:
    - `cal:day:YYYY-MM-DD`
    - `cal:day:YYYY-MM-DD:assignments`
    - `cal:day:YYYY-MM-DD:urgent`
  - month nav:
    - `cal:prev:YYYY-MM`
    - `cal:next:YYYY-MM`
  - ignore:
    - `cal:ignore`
