FROM python:3.12-slim

WORKDIR /app
ENV AGNO_TELEMETRY=false \
    PYTHONDONTWRITEBYTECODE=1 \
    ANCORA_EVAL_REQUIRE_VOLUME=1 \
    ANCORA_EVAL_STATE_DIR=/eval-state

# Dedicated allowlisted context: no .git, .env, databases or operator credentials.
COPY pyproject.toml README.md ./
COPY src/ src/
COPY scripts/ scripts/
COPY prompts/ prompts/
COPY evals/ evals/
RUN pip install --no-cache-dir .

# Match the external, clean checkout's preflight. No self-assigned runtime SHA.
ARG RAILWAY_GIT_COMMIT_SHA
ARG ANCORA_EVAL_BUILD_SHA
ARG ANCORA_EVAL_BUILD_SOURCE
RUN python /app/scripts/eval_source.py \
    --code-sha "${ANCORA_EVAL_BUILD_SHA:-$RAILWAY_GIT_COMMIT_SHA}" \
    --source-fingerprint "$ANCORA_EVAL_BUILD_SOURCE"

RUN mkdir -p /eval-state && chmod 700 /eval-state

# No server, ports, provider calls, cron or automatic campaign on start/restart.
CMD ["python", "/app/scripts/eval_service.py"]