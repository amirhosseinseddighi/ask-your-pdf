FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/

WORKDIR /app

# UV docker optimizations:
# Compile .pyc files before run-time
ENV UV_COMPILE_BYTECODE=1

# use copy instead of hardlink(works better with docker)
ENV UV_LINK_MODE=copy


# Use the python image don't download your own image
ENV UV_PYTHON_DOWNLOADS=0


COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-install-project  --no-dev
# --no-install-project means do not install the project itself. only install dependencies for now
# --no-dev means do not install development dependencies


COPY . ./
RUN uv sync --locked --no-dev


FROM python:3.13-slim-bookworm

WORKDIR /app

RUN useradd -m appuser && chown -R appuser:appuser /app
RUN mkdir -p /app/media && chown -R 1000:1000 /app/media
USER appuser

COPY --from=builder --chown=appuser:appuser /app /app


ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

CMD ["/bin/sh", "-c", "exec fastapi dev --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips '*'"]