import logging
from pathlib import Path


def setup_logger(name: str, log_path: Path) -> logging.Logger:
    """
    Create a logger that writes to both console and file with timestamps.

    This logger is async-safe and thread-safe, with each logger instance
    maintaining its own handlers and file streams.

    Args:
        name: Unique name for this logger (e.g., "sorry_id0", "repo_build_abc123")
        log_path: Path to the log file

    Returns:
        Configured logger instance
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

    # Console handler (to stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
