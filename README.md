# CourseMate AI Project

```bash
ai-telegram-course-bot/
│
├── app/
│   ├── __init__.py
│   │
│   ├── main.py                # Entry point of the application
│   ├── config.py              # Environment variables and configuration
│   ├── logger.py              # Logging setup
│   │
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── telegram_bot.py    # Telegram bot initialization
│   │   ├── handlers.py        # Command and message handlers
│   │   ├── keyboards.py       # Telegram inline keyboards / buttons
│   │
│   ├── canvas/
│   │   ├── __init__.py
│   │   ├── canvas_client.py   # Canvas API wrapper
│   │   ├── courses.py         # Fetch course list
│   │   ├── assignments.py     # Fetch assignments
│   │   ├── announcements.py   # Fetch announcements
│   │   ├── grades.py          # Fetch grade data
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── notification_service.py   # Send reminders
│   │   ├── scheduler.py              # Background job scheduling
│   │   ├── course_service.py         # Business logic for courses
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── nlp_query.py        # Natural language query processing
│   │   ├── summarizer.py       # Announcement summarization
│   │   ├── grade_predictor.py  # Grade prediction logic
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py           # Data models
│   │   ├── db.py               # Database connection
│   │   ├── repository.py       # CRUD operations
│   │
│   └── utils/
│       ├── __init__.py
│       ├── time_utils.py
│       ├── formatters.py
│
├── scripts/
│   ├── run_bot.py              # Start bot script
│   ├── fetch_canvas_data.py    # Manual data fetch
│
├── tests/
│   ├── test_canvas.py
│   ├── test_ai.py
│   ├── test_bot.py
│
├── .env                        # API tokens
├── .gitignore
├── requirements.txt
├── README.md
└── docker-compose.yml          # Optional deployment
```
