# CourseMate AI

CourseMate AI is a lightweight Telegram assistant that integrates with Canvas LMS to help students quickly access courses, assignments, and calendar-based workloads—without repeated login hassles.

It securely stores each user’s Canvas API token (encrypted at rest) and uses it to fetch data via Canvas REST and GraphQL APIs.

---

## 🚀 Features

### Telegram Commands

* `/start` – Display welcome message and main menu
* `/help` – List all available commands
* `/settoken <CANVAS_TOKEN>` – Store Canvas API token (encrypted)
* `/courses` – List dashboard courses
* `/assignments` – View assignment overview (monthly / to-do style)
* `/calendar` – Interactive monthly calendar with assignment drill-down
* `/grades` – *(Coming soon)*
* `/reminders` – *(Coming soon)*

### Inline Navigation

* Menu-driven navigation via inline keyboards
* Pagination for assignments
* Course browsing
* Interactive calendar date selection

---

## 🏗️ Architecture

```bash
app/
├── main.py              # Entry point
├── bot/                 # Telegram bot handlers and UI
├── canvas/              # Canvas REST + GraphQL client
├── services/            # Database + ORM models
├── utils/               # Config, encryption, logging
docs/
├── telegram-bot-api.md
├── canvas-client-api.md
├── telegram-canvas-architecture.md
```

---

## ⚙️ Setup

### 1. Create `.env`

Copy the example and configure:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
HTTP_URL=https://<school>.instructure.com/api
COURSEMATE_ENCRYPTION_SECRET=your_secret_key
DATABASE_URL=sqlite:///coursemate.sqlite3   # optional
ENVIRONMENT=Development                     # optional
```

⚠️ **Important:**
Keep `COURSEMATE_ENCRYPTION_SECRET` consistent. Changing it will break decryption of stored tokens.

---

### 2. Install Dependencies

This project uses `uv` via Makefile:

```bash
make setup
```

---

### 3. Run the Application

```bash
make run
```

Development mode (auto-reload):

```bash
make dev
```

Or manually:

```bash
python -m app.main
```

---

## 🧰 Development Commands

| Command          | Description          |
| ---------------- | -------------------- |
| `make lint`      | Run Ruff lint checks |
| `make lint-fix`  | Auto-fix lint issues |
| `make format`    | Format with Black    |
| `make typecheck` | Run mypy             |
| `make test`      | Run pytest           |
| `make check`     | Lint + typecheck     |
| `make clean`     | Remove caches        |
| `make help`      | List all commands    |

---

## 🔐 Security & Privacy

* Canvas tokens are encrypted using **Fernet encryption**
* Secrets are derived from `COURSEMATE_ENCRYPTION_SECRET`
* Do **not** commit `.env` or expose tokens

### Optional Access Control

* `TELEGRAM_ALLOWED_CHAT_ID`
* `TELEGRAM_ALLOWED_USERNAME`

If unset, the bot is publicly accessible.

---

## 🧑‍💻 Developer Notes

* Main bot class: `app/bot/telegram_bot.py`
* Callback handler: `app/bot/callbacks.py::main_menu_callback`
* Canvas client: `app/canvas/canvas_client.py`

Detailed documentation:

* `docs/telegram-bot-api.md`
* `docs/canvas-client-api.md`
* `docs/telegram-canvas-architecture.md`

---

## 📄 License

This project is licensed under the terms described in the [LICENSE](LICENSE.txt) file.
