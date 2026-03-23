# Telegram–Canvas Integration Overview

This document explains how the Telegram bot (UI + handlers) integrates with Canvas (REST + GraphQL), and how the user token and data flow through the system.

For function-level documentation:

- `docs/telegram-bot-api.md`
- `docs/canvas-client-api.md`

---

## 1) Components

### Telegram bot (`app/bot/*`)

Responsibilities:

- define user-visible commands (e.g. `/courses`, `/calendar`)
- provide inline navigation via inline keyboards (callback queries)
- format Canvas data into readable Telegram messages
- orchestrate multi-step flows (e.g. open course -> open assignment -> show score)

Key modules:

- `app/bot/telegram_bot.py`: registers handlers
- `app/bot/commands.py`: commands + shared render helpers
- `app/bot/callbacks.py`: central callback router (`main_menu_callback`)
- `app/bot/keyboards.py`: callback_data generation contracts
- `app/bot/datetime_utils.py`: formatting due dates and relative phrases
- `app/bot/errors.py`: global error handler

### Canvas client (`app/canvas/*`)

Responsibilities:

- perform REST + GraphQL requests to Canvas
- validate basic response type expectations (list/dict)
- normalize Canvas JSON into simplified Python dicts that the bot can display

Key modules:

- `app/canvas/canvas_client.py`
- `app/canvas/queries.py`

### Token storage / user store (`app/services/*`)

The bot stores a Canvas token per Telegram user (by `chat_id`), encrypted at rest.

Key calls in bot flows:

- `services.user_store.get_user_canvas_token(chat_id)` -> `str | None`
- `services.user_store.set_user_canvas_token(chat_id, username, token, first_name, last_name)`

---

## 2) End-to-end data flow

### 2.1 Token-dependent actions

Any action requiring Canvas data follows a consistent pattern:

1. **User triggers action**
   - sends a command (`/courses`)
   - or taps an inline button (`callback_data="courses"`)

2. **Bot resolves Telegram identity**
   - command path: `update.effective_chat.id`
   - callback path: `query.message.chat.id`

3. **Bot fetches stored Canvas token**
   - `get_user_canvas_token(chat_id)`
   - if missing, the bot sends instructions:
     - “Send it using: `/settoken YOUR_CANVAS_TOKEN`”
     - explains where to generate the token in Canvas UI

4. **Bot calls Canvas**
   - REST: `/v1/...`
   - GraphQL: `/graphql`

5. **Bot renders output**
   - responds with `reply_text` or edits an existing message via `edit_text`
   - attaches inline keyboards for next navigation step

---

## 3) Command flows (examples)

### `/courses`

- `courses_command`:
  - gets token
  - calls `render_courses`
- `render_courses`:
  - calls `get_dashboard_cards`
  - filters to `enrollmentState == "active"`
  - attaches `courses_keyboard`, which uses `callback_data="course:<id>"`

### `/assignments`

- `assignments_command`:
  - gets token
  - calls `render_month_assignments_overview(compact=True)`
- `render_month_assignments_overview`:
  - reads dashboard cards (active courses)
  - loads per-course assignments from `get_course_assignments`
  - filters to “current month” by `due_at`
  - buckets items:
    - `todo` / `submitted` / `past`
  - chooses a “Next up” urgent assignment
  - attaches `month_assignments_keyboard` (toggle compact/full + urgent actions)

### `/calendar`

- `calendar_command`:
  - gets token
  - builds context codes (`course_<id>`) from active dashboard cards
  - calls `get_calendar_events` for current-month ± 7 days window
  - builds `assignments_by_date`
  - replies with `calendar_keyboard` which encodes:
    - `cal:prev:YYYY-MM`
    - `cal:next:YYYY-MM`
    - `cal:day:YYYY-MM-DD[:assignments|:urgent]`

### `/download`

- `download_command`:
  - uses same time window + course context codes as calendar
  - calls `get_calendar_events`
  - scrapes `data-api-endpoint="..."` links from `description` HTML
  - for each endpoint:
    - `download_canvas_file` -> temp path + filename
    - replies with `reply_document`
    - deletes the temp file

---

## 4) Inline navigation flows

### 4.1 Main menu routing

All inline keyboard presses route into:

- `main_menu_callback(update, context)`

Main menu callback_data:

- `courses`, `calendar`, `assignments`, `help`, `grades`, `reminders`, `menu`

### 4.2 Course selection -> course menu

1. user taps a course in `courses_keyboard`
2. callback_data: `course:<course_id>`
3. `main_menu_callback`:
   - loads dashboard cards again
   - finds the selected course
   - edits message with course label + `course_menu_keyboard(course_id)`

### 4.3 Course menu -> course assignments

1. user taps “Upcoming Assignments” or “Past Assignments”
2. callback_data:
   - `course:<id>:assignments:upcoming`
   - `course:<id>:assignments:past`
3. `main_menu_callback` calls:
   - `render_course_assignments(..., status=<past|upcoming>, page=1, edit=True)`

### 4.4 Assignment details (REST path)

1. user taps an assignment in `course_assignments_keyboard`
2. callback_data: `course-assignment:<course_id>:<assignment_id>`
3. callback handler:
   - calls `get_course_assignments` and selects the assignment
   - calls `get_assignment_submission` to load the score (best-effort)
   - edits the message with a summary and back button

### 4.5 Assignment details (GraphQL path)

1. user taps an assignment entry that uses global identifiers (from other list flows)
2. callback_data: `assignment:<assignment_lid>:<submission_id>`
3. callback handler:
   - calls `get_student_assignment` (GraphQL)
   - renders points possible + score + due date and shows back button

---

## 5) Reliability and UX design notes

### 5.1 Callback deduplication

`main_menu_callback` deduplicates repeated taps:

- key: `<user_id>:<callback_data>`
- ignores duplicates within 10 seconds and responds:
  - `"Still processing your previous request, please wait…"`

This prevents:

- duplicate Canvas calls
- Telegram “message is not modified” / rapid edits
- repeated downloads

### 5.2 Temp file lifecycle for downloads

`download_canvas_file` writes to a temp file and returns the path.
The caller (command or callback) is responsible for deleting it after sending.

### 5.3 Time handling

- Calendar windowing uses UTC timestamps (`datetime.now(timezone.utc)`)
- Relative “due” messaging uses utilities in `app/bot/datetime_utils.py` for consistent formatting

---

## 6) How to add a new Canvas-backed feature

### New command

1. create handler in `app/bot/commands.py`
2. resolve token via `get_user_canvas_token(chat_id)` with helpful `/settoken` error path
3. call the necessary `canvas_client` function(s)
4. render and attach a keyboard if needed
5. register the command in `app/bot/telegram_bot.py`

### New callback route

1. define a stable callback_data format in `app/bot/keyboards.py`
2. add a routing branch in `main_menu_callback`
3. use `_require_canvas_token(query, action_text)` before Canvas calls
4. prefer `edit_message_text` to keep the interaction single-message where possible
