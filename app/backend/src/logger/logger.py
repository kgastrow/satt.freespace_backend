from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import traceback


def setup_logger(name, log_file, level=logging.INFO):
    """Function to set up a logger with a specified name and log file."""

    # File logging
    file_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    )
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1024 * 1024 * 100, backupCount=10
    )
    file_handler.setFormatter(file_formatter)

    # Console logging
    console_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s  [in %(pathname)s:%(lineno)d]"
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)

    # Create the logger and set its level
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def print_exception_with_trace(exc: Exception, context: str = ""):
    """
    Print exception with full stack trace to stdout.

    Args:
        exc: Exception object to print
        context: Optional context string describing where the exception occurred
    """
    separator = "=" * 80
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f"\n{separator}")
    print(f"[EXCEPTION] {timestamp}")
    if context:
        print(f"Context: {context}")
    print(f"Exception Type: {type(exc).__name__}")
    print(f"Exception Message: {str(exc)}")
    print("\nStack Trace:")
    print(traceback.format_exc())
    print(f"{separator}\n")


# Example usage: Set up a logger for your application
Logger = setup_logger("app_logger", "app.log")
