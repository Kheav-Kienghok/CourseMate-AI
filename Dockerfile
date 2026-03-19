ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY app ./app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm

WORKDIR /app

# Create non-root user
RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup appuser

# Copy app
COPY --from=builder /app /app

# Fix ownership (important)
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "app/main.py"]

