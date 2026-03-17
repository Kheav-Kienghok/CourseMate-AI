FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies into the project virtualenv (no dev dependencies)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Copy the full project and ensure venv is up to date
ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy the application (including the .venv created by uv) from the builder
COPY --from=builder /app /app

# Use the project virtualenv Python first
ENV PATH="/app/.venv/bin:$PATH"

# Default command: run the Telegram bot entrypoint script
CMD ["python", "app/main.py"]
