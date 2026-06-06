FROM python:3.10

ENV PYTHONUNBUFFERED=1

WORKDIR /app/

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="/app/.venv/bin:$PATH"

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy

# Copy dependency files first
COPY backend/pyproject.toml backend/uv.lock /app/

# Install dependencies
RUN uv sync --frozen --no-install-project

ENV PYTHONPATH=/app

# Copy application files
COPY backend/scripts /app/scripts
COPY backend/alembic.ini /app/
COPY backend/app /app/app

# Sync the project to install the app itself
RUN uv sync --no-dev

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--workers", "4", "--log-level", "debug"]
