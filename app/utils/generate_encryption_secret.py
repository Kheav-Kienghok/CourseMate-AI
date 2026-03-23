from __future__ import annotations

import os
from pathlib import Path
from secrets import token_urlsafe

import dotenv


def _get_env_path() -> Path:
    """Return the path to the project-level .env file.

    This assumes the project structure:
    /project_root/app/utils/generate_encryption_secret.py
    and places .env in /project_root/.env.
    """

    return Path(__file__).resolve().parents[2] / ".env"


def generate_and_store_secret() -> str:
    """Generate a new encryption secret and store it in .env.

    - If COURSEMATE_ENCRYPTION_SECRET is already set in the environment
      or in .env, the function will not overwrite it and simply returns
      the existing value.
    - Otherwise, it generates a random secret, appends it to .env, and
      returns the newly created value.
    """

    env_path = _get_env_path()

    # Load existing .env if present so we can see current values.
    if env_path.exists():
        dotenv.load_dotenv(dotenv_path=env_path)

    existing = os.getenv("COURSEMATE_ENCRYPTION_SECRET")
    if existing:
        # Do not overwrite an existing secret; just return it.
        return existing

    # Generate a new high-entropy secret string.
    secret = token_urlsafe(32)

    # Ensure the .env file exists.
    if not env_path.exists():
        env_path.touch()

    # Append the new secret to the .env file.
    with env_path.open("a", encoding="utf-8") as f:
        f.write(f"COURSEMATE_ENCRYPTION_SECRET={secret}\n")

    return secret
