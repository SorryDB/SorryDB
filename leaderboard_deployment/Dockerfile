# Use angcloud run deploy official lightweight Python image
FROM python:3.13-slim

# Install dependencies
# TODO: we may be able to remove build-essential when minimizing the leaderboard deps
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Poetry
RUN pip install poetry

# Set environment variables for Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy project files
COPY pyproject.toml poetry.lock ./

# Poetry complains if there is no README.md file
RUN touch README.md

# Run poetry with `--no-root` to only install deps
RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

# Copy source files
COPY sorrydb ./sorrydb

# Install sorrydb
RUN poetry install --without dev

EXPOSE 8080

CMD ["sh", "-c", "poetry run python -m uvicorn sorrydb.leaderboard.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
