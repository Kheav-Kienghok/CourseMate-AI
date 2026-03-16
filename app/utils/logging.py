from __future__ import annotations

import logging
from pathlib import Path

from utils.config import get_environment


def setup_logging() -> None:
    """Configure application-wide logging.

    - Uses 5 standard levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    - DEBUG logs are only enabled for *your* project modules in the
      "Development" environment. Third-party libraries stay at INFO+.
    - In the Development environment, logs are also written to a file.
    """

    env = get_environment().lower()

    # Common log format:
    # 2026-03-16 14:22:51 | INFO | bot.handlers.assignment | handlers.py:45 | Message
    log_format = (
        "%(asctime)s | %(levelname)s | %(name)s | "
        "%(filename)s:%(lineno)d | %(message)s"
    )

    # Root logger: INFO by default so third-party libs don't spam DEBUG.
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
    )

    root_logger = logging.getLogger()

    if env == "development":
        # Enable DEBUG only for your own packages.
        for name in ("bot", "canvas", "utils", "ui", "services"):
            logging.getLogger(name).setLevel(logging.DEBUG)

        # Also log to a file in development only.
        log_path = Path("app.log")

        # Avoid adding duplicate file handlers if setup_logging is
        # called more than once.
        if not any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", None)
            and str(h.baseFilename) == str(log_path.resolve())
            for h in root_logger.handlers
        ):
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(file_handler)

    # Quiet some noisy libraries explicitly if present.
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
