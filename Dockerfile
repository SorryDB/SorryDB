# Use an official lightweight Python image
FROM python:3.13-slim

# Install dependencies for Lean
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m sorrydbuser

# Set working directory
WORKDIR /app

# Install elan (Lean package manager)
# RUN curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- --default-toolchain stable -y

# Set up environment variables for Lean
# ENV PATH="/root/.elan/bin:${PATH}"
#
# Verify Lean installation
# RUN lean --version

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

# Copy source files and repo_lists
COPY src ./src
COPY repo_lists ./repo_lists


# Install sorrydb
RUN poetry install --without dev

# Set proper ownership for all files
RUN chown -R sorrydbuser:sorrydbuser /app

# Switch to non-root user
USER sorrydbuser

# Install Lean
RUN curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- --default-toolchain stable -y

# Set up environment variables for Lean
ENV PATH="/home/sorrydbuser/.elan/bin:${PATH}"

# Verify Lean installation
RUN lean --version

CMD ["poetry", "run", "init_db", "--repos-file", "repo_lists/mock_with_carleson.json", "--database-file", "sorry_database.json", "--starting-date", "2025-03-07"]
