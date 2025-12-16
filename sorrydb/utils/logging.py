import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def setup_logger(name: str, log_path: Path) -> Generator[logging.Logger, None, None]:
    """
    Context manager that creates a logger with automatic cleanup.

    This logger is async-safe and thread-safe, with each logger instance
    maintaining its own handlers and file streams. Automatically closes
    and removes all handlers when exiting the context to prevent file
    descriptor leaks.

    Args:
        name: Unique name for this logger (e.g., "sorry_id0", "repo_build_abc123")
        log_path: Path to the log file

    Yields:
        Configured logger instance

    Example:
        with setup_logger("my_task", Path("task.log")) as logger:
            logger.info("Processing task...")
    """
    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create logger with unique name
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Don't propagate to root logger

    # Clear any existing handlers (in case logger was previously used)
    logger.handlers.clear()

    # Format with timestamps matching the old LogContext format
    formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # File handler
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    try:
        yield logger
    finally:
        # Clean up logger handlers to prevent file descriptor leaks
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
