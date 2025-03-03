import logging
import time
from pathlib import Path
from typing import Optional

from config import settings


def configure_logging(book_dir: Path) -> None:
    """Configures logging with chapter-range specific filenames."""
    base_log_path = Path("operation.log")

    log_file_path = book_dir / base_log_path.stem
    log_level = settings.LOG_LEVEL.upper()

    # Remove any existing file handlers to prevent duplicate logging
    for handler in logging.root.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logging.root.removeHandler(handler)

    # Configure file logging
    file_handler = logging.FileHandler(
        log_file_path,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logging.root.addHandler(file_handler)

    # Ensure console handler exists
    if not any(isinstance(h, logging.StreamHandler) for h in logging.root.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter('%(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logging.root.addHandler(console_handler)

    logging.root.setLevel(log_level)
    logging.info(f"Logging configured to file: {log_file_path}")


def log_exception(e: Exception, message: str = "An exception occurred"):
    """Utility function to log exceptions with detailed info."""
    logging.error(f"{message}: {e}")
    logging.debug("Exception details:", exc_info=True) # Adds traceback to logs

def log_performance(start_time, operation_name="operation"):
    """Logs the duration of an operation."""
    duration_sec = time.time() - start_time
    logging.info(f"{operation_name} completed in {duration_sec:.2f} seconds.")
