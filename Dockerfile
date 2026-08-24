FROM python:3.12-slim

WORKDIR /app

# System dependencies for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Application
COPY src/ src/
COPY prompts/ prompts/

# Runtime directories
RUN mkdir -p /app/tmp

EXPOSE 7777

CMD ["python", "-m", "src.main"]