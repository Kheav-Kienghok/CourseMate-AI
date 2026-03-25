from __future__ import annotations

import os
import sys

import dotenv

from bot.telegram_bot import run_bot
from services.db import init_db
from ui.terminal import prompt_start_or_exit, startup_screen
from utils.config import validate_required_env_vars
from utils.generate_encryption_secret import generate_and_store_secret
from utils.logging import setup_logging
from utils.security_patches import disable_vulnerable_pygments_lexers


def main() -> None:
    """Entry point for the application."""

    try:
        # Apply runtime security hardening (e.g. Pygments ReDoS mitigation).
        disable_vulnerable_pygments_lexers()

        # Configure logging before starting the bot so all modules
        # share the same logging setup.
        setup_logging()

        # Ensure encryption secret exists; offer to generate or let user add it.
        if not os.getenv("COURSEMATE_ENCRYPTION_SECRET"):
            print("COURSEMATE_ENCRYPTION_SECRET is not set.\n")
            print("1) Generate a new random secret and store it in .env")
            print("2) I will add my own secret to .env now")
            print("3) Exit")

            try:
                choice = input("Choose an option [1/2/3] (default 1): ").strip() or "1"
            except EOFError:
                print(
                    "No input available to configure COURSEMATE_ENCRYPTION_SECRET.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if choice == "1":
                secret = generate_and_store_secret()
                os.environ["COURSEMATE_ENCRYPTION_SECRET"] = secret
                print(
                    "A new COURSEMATE_ENCRYPTION_SECRET has been generated and "
                    "stored in your .env file.\n",
                )
            elif choice == "2":
                try:
                    input(
                        "Please add COURSEMATE_ENCRYPTION_SECRET to your .env file "
                        "and press Enter when done (or Ctrl+C to abort)... ",
                    )
                except EOFError:
                    print(
                        "No input available to continue after manual .env edit.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                dotenv.load_dotenv()
                if not os.getenv("COURSEMATE_ENCRYPTION_SECRET"):
                    print(
                        "COURSEMATE_ENCRYPTION_SECRET is still missing after manual "
                        ".env update; exiting.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            else:
                print(
                    "COURSEMATE_ENCRYPTION_SECRET not configured; exiting.",
                    file=sys.stderr,
                )
                sys.exit(1)

        missing_keys = validate_required_env_vars()
        if missing_keys:
            keys = ", ".join(missing_keys)
            print(f"Missing required environment variables: {keys}", file=sys.stderr)
            sys.exit(1)

        # Ensure database tables for ORM models exist (e.g. users table).
        init_db()

        startup_screen()
        if not prompt_start_or_exit():
            sys.exit(0)

        run_bot()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:  # noqa: BLE001
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
