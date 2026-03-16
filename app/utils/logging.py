from __future__ import annotations

import logging

from utils.config import get_environment


def setup_logging() -> None:
    """Configure application-wide logging.

    - Uses 5 standard levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.
    - DEBUG logs are only enabled for *your* project modules in the
      "Development" environment. Third-party libraries stay at INFO+.
    """

    env = get_environment().lower()

    # Root logger: INFO by default so third-party libs don't spam DEBUG.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    if env == "development":
        # Enable DEBUG only for your own packages.
        for name in ("bot", "canvas", "utils", "ui", "services"):
            logging.getLogger(name).setLevel(logging.DEBUG)

    # Quiet some noisy libraries explicitly if present.
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
