FROM python:3.12-slim

WORKDIR /app

# Disable Agno's product telemetry before any runtime imports. AncoraMind's
# metadata-only OTLP pipeline is configured explicitly at application startup.
ENV AGNO_TELEMETRY=false

# System dependencies for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install the application after all package metadata and source files exist.
COPY pyproject.toml README.md ./
COPY src/ src/
COPY prompts/ prompts/
COPY alembic.ini ./
COPY migrations/ migrations/
RUN pip install --no-cache-dir .

# Runtime directories
RUN mkdir -p /app/tmp

EXPOSE 7777

CMD ["python", "-m", "src.main"]