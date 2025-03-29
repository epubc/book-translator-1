import logging
from pathlib import Path
from typing import Optional

from logger import logging_utils

def delete_file(file_path: Path) -> bool:
    """Delete a file, return True if successful, False otherwise."""
    if file_path.exists() and file_path.is_file():
        try:
            file_path.unlink()  # More modern and Pathlib-centric way to delete
            logging.info(f"Deleted file: {file_path.name}")
            return True
        except Exception as e:
            logging_utils.log_exception(e, f"Error deleting file: {file_path}")
            return False
    else:
        logging.warning(f"File not found, cannot delete: {file_path}")
        return False

def save_content_to_file(content: str, file_path: Path) -> Path:
    """Save content to a file, return Path."""
    try:
        file_path.write_text(content, encoding='utf-8')
        logging.debug(f"File saved: {file_path}")  # Debug level logging
        return file_path
    except Exception as e:
        logging_utils.log_exception(e, f"Error saving file: {file_path}")
        raise  # Re-raise exception after logging

def load_content_from_file(file_path: Path) -> Optional[str]:
    """Load content from a file, return None if file not found or error."""
    try:
        return file_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        logging.warning(f"File not found: {file_path}")
        return None
    except Exception as e:
        logging_utils.log_exception(e, f"Error reading file: {file_path}")
        return None
