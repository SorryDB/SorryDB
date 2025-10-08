# Use an official lightweight Python image
FROM python:3.13-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    gcc \
    g++ \
    make \
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

EXPOSE 8000

