# One image for every service; each service runs one script (see compose.yaml).
FROM python:3.12-slim

# git and curl for the agent's own work; tzdata so TZ (your timezone) works.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Everything runs as an ordinary user, never root.
RUN useradd --create-home --uid 1000 agent
USER agent
WORKDIR /app
# Mount points for the volumes, created as `agent` so the volumes are writable by it.
RUN mkdir -p data/agent-home data/workspace.git agent/sites

# Claude Code, installed for that user (the runner is the only service that uses it).
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH=/app/.venv/bin:/home/agent/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

COPY --chown=agent pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --python-preference only-system
COPY --chown=agent . .
