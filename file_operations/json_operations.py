import json
import logging
import fcntl
import os
import time
from pathlib import Path
from typing import Dict, Optional

from logger import logging_utils


def _safe_read_json(file_path: Path) -> Optional[Dict]:
    """Safely read a JSON file with file locking."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Acquire a shared (read) lock
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logging.error(f"Error reading JSON file {file_path}: {e}")
        return None


def _safe_write_json(file_path: Path, data: Dict) -> Optional[bool]:
    """Safely write a JSON file with file locking and atomic write."""
    temp_path = file_path.with_suffix('.json.tmp')
    try:
        # Write to temporary file first
        with open(temp_path, 'w', encoding='utf-8') as f:
            # Acquire an exclusive (write) lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Atomic rename
        temp_path.replace(file_path)
        return True
    except Exception as e:
        logging.error(f"Error writing JSON file {file_path}: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False


def _initiate_progress() -> Dict:
    """Initialize a new progress dictionary."""
    return {
        "model_rate_limits": {},
        "failed_translations": {}
    }


def load_progress_file(progress_file_path: Path) -> Dict:
    """Load and return progress data from progress.json, initialize if not exists."""
    try:
        # Try to read existing progress file
        data = _safe_read_json(progress_file_path)
        if data is not None:
            return data

        # If file doesn't exist or is corrupt, initialize new progress
        logging.info("Progress file not found or corrupt, initializing new progress.")
        new_progress = _initiate_progress()
        _safe_write_json(progress_file_path, new_progress)
        return new_progress

    except Exception as e:
        logging_utils.log_exception(e, "Error loading progress file.")
        new_progress = _initiate_progress()
        _safe_write_json(progress_file_path, new_progress)
        return new_progress


def save_progress_file(progress_file_path: Path, progress_data: Dict) -> None:
    """Save progress data to progress.json with proper locking and retries."""
    try:
        # Ensure the data is valid before saving
        if not isinstance(progress_data, dict):
            raise ValueError("Progress data must be a dictionary")

        if "failed_translations" not in progress_data:
            progress_data["failed_translations"] = {}

        # Save with retries
        max_retries = 3
        for attempt in range(max_retries):
            if _safe_write_json(progress_file_path, progress_data):
                return
            if attempt < max_retries - 1:
                time.sleep(0.1)  # Small delay before retry

        raise Exception("Failed to save progress after multiple attempts")

    except Exception as e:
        logging_utils.log_exception(e, "Error saving progress to file.")
        try:
            _safe_write_json(progress_file_path, _initiate_progress())
        except Exception as recover_error:
            logging.error(f"Failed to recover progress file: {recover_error}")
