
# CourseMate AI (Canvas + Telegram Assistant)

CourseMate AI is a lightweight Telegram assistant that integrates with Canvas LMS to help students view courses, assignments, and calendar-based workload quickly—without repeated login hassles. It stores each user’s Canvas API token securely (encrypted at rest) and uses it to fetch data from the Canvas REST and GraphQL APIs.

## What this repo contains

- A **Telegram bot** (built with `python-telegram-bot`) with commands + inline keyboard navigation.
- A **Canvas API client** (`requests`) that wraps Canvas REST + GraphQL calls.
- A small **SQLAlchemy** persistence layer (SQLite by default; supports `DATABASE_URL`).
- A **terminal UI** startup screen (Rich) for local/dev runs.

## High-level architecture

- `app/main.py`: App entrypoint (logging + DB init + startup screen + run bot)
- `app/bot/*`: Telegram bot handlers, callbacks, keyboards
- `app/canvas/*`: Canvas API wrappers + GraphQL queries
- `app/services/*`: Database setup + ORM models + token storage/retrieval
- `app/utils/*`: Configuration, encryption, logging utilities
- `docs/*`: Function-level docs for bot + canvas client + integration architecture

## Features (current)

### Telegram commands

- `/start` – show welcome + main menu
- `/help` – list commands
- `/settoken <CANVAS_TOKEN>` – store user’s Canvas API token (encrypted)
- `/courses` – list Canvas dashboard courses
- `/assignments` – show assignment overview (this month / to-do style)
- `/calendar` – show a navigable monthly calendar; select days to view assignments
- `/download` – download assignment-related files (when Canvas descriptions include file links)
- `/grades`, `/reminders` – placeholders for future features

### Inline keyboard navigation

The bot uses inline callback buttons (handled by `main_menu_callback`) for:

- switching between menu screens
- browsing courses
- browsing assignments (including pagination)
- using a calendar date picker to drill down into assignment events

## Setup

### 1) Create a `.env`

Copy the example file and fill in your values:

- `TELEGRAM_BOT_TOKEN` (required)
- `HTTP_URL` (required) – Canvas base API URL (example: `https://<school>.instructure.com/api`)
- `COURSEMATE_ENCRYPTION_SECRET` (required) – used to encrypt stored Canvas tokens
- `DATABASE_URL` (optional) – if not set, a local `coursemate.sqlite3` is created
- `ENVIRONMENT` (optional) – defaults to `Development`

> Important: `COURSEMATE_ENCRYPTION_SECRET` must remain stable.  
> If it changes, previously stored tokens may become undecryptable.

### 2) Install dependencies

This repo appears configured for modern Python packaging. Use your preferred tool (uv/pip).

Example (pip):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # if present, or install via pyproject
```

If you’re using `make`:

```bash
make setup
```

### 3) Run

```bash
make run
```

Or run the entrypoint directly:

```bash
python -m app.main
```

On startup, CourseMate AI:

1. configures logging
2. initializes DB tables
3. shows a Rich startup screen (dev)
4. launches Telegram polling

## Security / privacy notes

- Canvas tokens are stored in the DB **encrypted** using Fernet derived from `COURSEMATE_ENCRYPTION_SECRET`.
- Avoid committing `.env` and never share your Telegram token or Canvas token.
- Optional access restriction is supported:
  - `TELEGRAM_ALLOWED_CHAT_ID`
  - `TELEGRAM_ALLOWED_USERNAME`

If neither is set, the bot does not restrict users.

## Developer notes

- The Telegram bot is configured in `app/bot/telegram_bot.py` (`CourseMateBot`).
- The global callback handler is `app/bot/callbacks.py::main_menu_callback`.
- Canvas HTTP helpers live in `app/canvas/canvas_client.py`.

For deep function-by-function docs, see:

- `docs/telegram-bot-api.md`
- `docs/canvas-client-api.md`
- `docs/telegram-canvas-architecture.md`
