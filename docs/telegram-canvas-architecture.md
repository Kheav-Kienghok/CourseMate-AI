# Telegram–Canvas Integration Overview

## 1. Overview

This document describes how the Telegram bot interacts with the Canvas API, including:

- User-facing commands and callbacks.
- The HTTP requests sent to Canvas and how responses are used.

For detailed, function-by-function input/output documentation, see:

- Telegram bot API: `docs/telegram-bot-api.md`
- Canvas client API: `docs/canvas-client-api.md`

---

## 2. High-Level Architecture

### 2.1 Components

- **Telegram Bot** (in `app/bot/`)
  - Handles commands (e.g. `/start`, `/help`, `/courses`, `/assignments`).
  - Handles inline keyboard callbacks for navigation and details.
  - Formats all messages and keyboards shown to the user.

- **Canvas Client** (in `app/canvas/canvas_client.py`)
  - Wraps calls to the Canvas REST and GraphQL APIs.
  - Exposes helper functions such as `get_dashboard_cards`, `get_course_assignments`, and `get_assignment_submission`.

- **User Store** (in `app/services/`)
  - `models.User`: stores Telegram user identity and encrypted Canvas token.
  - `user_store.get_user_canvas_token`: returns the decrypted Canvas token for a chat.
  - `user_store.set_user_canvas_token`: creates/updates user entry and stores encrypted token.

- **Configuration & DB**
  - `utils.config.get_canvas_base_url()` provides the Canvas base HTTP URL (`HTTP_URL` env variable).
  - `services.db` configures the SQLAlchemy engine and session and creates tables.

### 2.2 Data Flow

At a high level, handling a Canvas-related operation looks like this:

1. **Telegram → Bot**: The user sends a command or taps an inline button.
2. **Bot → User Store**: The bot resolves the Telegram chat id, loads the associated user, and fetches the stored Canvas token (if any).
3. **Bot → Canvas**: The bot calls the Canvas API via `canvas_client` using the user’s token (if present).
4. **Canvas → Bot**: Canvas responds with JSON; the bot parses it into simplified Python structures.
5. **Bot → Telegram**: The bot renders a human-friendly message and sends it back to the user, sometimes with inline keyboards for further navigation.

---

## 3. Telegram Commands and Callbacks

### 3.1 Commands

Implemented in `app/bot/commands.py`.

#### `/start`

- **Purpose**: Welcome the user and show the main menu.
- **Processing**:
  - Logs basic user info.
  - Sends a welcome message describing what the bot can do.
  - Attaches the main menu keyboard (`main_menu_keyboard`).
- **Canvas usage**: None.

#### `/help`

- **Purpose**: Show available commands.
- **Processing**:
  - Logs basic user info.
  - Sends a Markdown-formatted list of supported commands and their descriptions.
- **Canvas usage**: None.

#### `/settoken <YOUR_CANVAS_TOKEN>`

- **Purpose**: Store the user’s personal Canvas API token.
- **Processing**:
  1. Resolve Telegram `chat_id`, `username`, `first_name`, and `last_name` from the update.
  2. If `chat_id` is missing, respond with an error.
  3. Validate that an argument was provided and is non-empty.
  4. Call `set_user_canvas_token(chat_id, username, token, first_name, last_name)`:
     - Creates or updates a `User` row.
     - Encrypts the token with `utils.crypto.encrypt_text` before storing.
  5. Attempt to delete the original `/settoken` message (to avoid leaving the raw token in chat history).
  6. Send a confirmation message.
- **Canvas usage**: None at this step (only stores the token locally).

#### `/courses`

- **Purpose**: Show a list of the user’s active Canvas courses.
- **Processing**:
  1. Resolve `chat_id` from the Telegram chat.
  2. Use `get_user_canvas_token(chat_id)` to fetch and decrypt the stored Canvas token.
  3. If no Canvas token is found, send instructions for how to create and set a token (`/settoken`).
  4. If a token is present, call `render_courses(message, canvas_token)`.

- **Response**:
  - On success: a formatted course list showing course names, codes, sections, and term, plus a keyboard (`courses_keyboard`) for selecting a course.
  - On error: a user-friendly message (no token, failed Canvas call, etc.) with a main menu keyboard.

#### `/assignments`

- **Purpose**: Show a “this month” overview of assignments across all active courses.
- **Processing**:
  1. Resolve `chat_id` from the Telegram chat.
  2. Fetch Canvas token with `get_user_canvas_token(chat_id)`.
  3. If no token, instruct the user to configure one via `/settoken`.
  4. If a token exists, call `render_month_assignments_overview(message, canvas_token, filter_mode="todo")`.

- **Response**:
  - On success: a monthly overview that:
    - Shows the period (e.g. "March 2026").
    - Summarizes counts by bucket (to‑do / submitted / past due).
    - Lists assignments in the selected bucket with course name, due date, and status.
    - Includes an inline keyboard (`month_assignments_keyboard`) to switch between buckets.
  - On error: appropriate error or guidance, plus the main menu keyboard.

#### `/grades` and `/reminders`

- **Purpose**: Placeholders for future features (grade summary and reminders).
- **Processing**:
  - Reply that the feature is not implemented yet, with the main menu keyboard.
- **Canvas usage**: None currently.

### 3.2 Inline Callback Handling

Implemented in `app/bot/callbacks.py` via `main_menu_callback`.

Key callback types include:

- `assignments` – Show the monthly assignment overview.
- `courses` – Show the course list.
- `course:{course_id}` – Show a single course’s menu.
- `course:{course_id}:assignments[:status][:page]` – Paginated course assignments view.
- `course-assignment:{course_id}:{assignment_id}` – Detailed info for a specific assignment.
- `assignment:{assignment_lid}:{submission_id}` – GraphQL-based assignment details.

All callbacks that access Canvas use the shared helper `_require_canvas_token(query, action_text)`:

1. Resolve `chat_id` from the callback’s message.
2. Fetch the user’s Canvas token using `get_user_canvas_token(chat_id)`.
3. If no token is found, edit the message with instructions for `/settoken` and exit.
4. If a token exists, return it so the callback can call Canvas via `canvas_client`.

---

## 4. Canvas HTTP Requests and Responses

All Canvas calls use the base URL from `utils.config.get_canvas_base_url()` which reads `HTTP_URL` from the environment. Each call includes the user’s token:

- `Authorization: Bearer <user_canvas_token>`

These calls are implemented in `app/canvas/canvas_client.py`.

### 4.1 Dashboard Cards (Courses)

- **Function**: `get_dashboard_cards(canvas_token: str | None) -> list[dict[str, Any]]`
- **HTTP request**:
  - `GET {HTTP_URL}/v1/dashboard/dashboard_cards`
  - Headers: `Authorization: Bearer <token>`
- **Purpose**: Fetch the user’s dashboard courses and present them as simplified course dicts.
- **Used by**:
  - `render_courses`
  - `render_course_assignments` (for course labels)
  - `render_month_assignments_overview` (to iterate courses)

### 4.2 Course Assignments

- **Function**: `get_course_assignments(course_id: int, canvas_token: str | None) -> list[dict[str, Any]]`
- **HTTP request**:
  - `GET {HTTP_URL}/v1/courses/{course_id}/assignment_groups`
  - Query params: `include[]=assignments`, `per_page=50`
  - Headers: `Authorization: Bearer <token>`
- **Purpose**:
  - Fetch all assignment groups for a course and flatten to a single list of assignments.
  - Sorts assignments by `due_at` (earliest first, undated last).
- **Used by**:
  - `render_course_assignments` (per-course assignment lists and pagination).
  - `render_month_assignments_overview` (aggregated monthly view across courses).
  - `main_menu_callback` when opening a specific course assignment.

### 4.3 Assignment Submission

- **Function**: `get_assignment_submission(course_id: int, assignment_id: int, canvas_token: str | None) -> dict[str, Any]`
- **HTTP request**:
  - `GET {HTTP_URL}/v1/courses/{course_id}/assignments/{assignment_id}/submissions/self`
  - Headers: `Authorization: Bearer <token>`
- **Purpose**:
  - Fetch the current user’s submission data including `score`.
- **Used by**:
  - `main_menu_callback` for `course-assignment:{course_id}:{assignment_id}` to display score and points possible.

### 4.4 GraphQL Assignment Details

- **Function**: `get_student_assignment(assignment_lid: str, submission_id: str, canvas_token: str | None) -> dict[str, Any]`
- **HTTP request**:
  - `POST {HTTP_URL}/graphql`
  - Headers:
    - `Authorization: Bearer <token>`
    - `Content-Type: application/json`
  - JSON body:
    - `operationName`: `GetStudentAssignment`
    - `variables`: `{ "assignmentLid": ..., "submissionID": ... }`
    - `query`: `GET_STUDENT_ASSIGNMENT_QUERY` from `canvas.queries`.
- **Purpose**:
  - Retrieve richer assignment and submission info through Canvas GraphQL.
- **Used by**:
  - `main_menu_callback` for `assignment:{assignment_lid}:{submission_id}` when the user opens a specific assignment via GraphQL.

---

## 5. Guidelines for Future Changes

To keep the system consistent and maintainable:

- **Adding a new Canvas-backed command** (e.g. `/grades`):
  1. Resolve `chat_id`.
  2. Fetch Canvas token with `get_user_canvas_token(chat_id)`.
  3. If no token, send clear instructions to configure one via `/settoken`.
  4. If a token exists, call the appropriate `canvas_client` helper.
  5. Render a user-friendly message and attach keyboards as needed.

- **Adding a new Canvas-backed inline callback**:
  1. Route the callback data in `main_menu_callback`.
  2. Inside the handler, call `_require_canvas_token(query, action_text)`.
  3. If it returns `None`, stop; otherwise, use the token to call Canvas.

- **Changing the Canvas base URL**:
  - Update the `HTTP_URL` environment variable or `utils.config.get_canvas_base_url` implementation as needed.

For function-level inputs and outputs, refer to the dedicated Telegram and Canvas API docs mentioned in the overview.
