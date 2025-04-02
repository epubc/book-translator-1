import json
import logging
import os
import time
import portalocker  # Cross-platform file locking
from pathlib import Path
from typing import Dict, Optional

from logger import logging_utils


def _safe_read_json(file_path: Path) -> Optional[Dict]:
    """Safely read a JSON file with file locking."""
    try:
        with portalocker.Lock(file_path, 'r', encoding='utf-8', timeout=10) as f:
            return json.load(f)
    except portalocker.LockException:
        logging.error(f"Could not acquire lock for reading {file_path}")
        return None
    except Exception as e:
        logging.error(f"Error reading JSON file {file_path}: {e}")
        return None


def _safe_write_json(file_path: Path, data: Dict) -> Optional[bool]:
    """Safely write a JSON file with file locking and atomic write."""
    temp_path = file_path.with_suffix('.json.tmp')
    try:
        # Write to temporary file first
        with portalocker.Lock(temp_path, 'w', encoding='utf-8', timeout=10) as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename - use os.replace for cross-platform atomic replace
        os.replace(str(temp_path), str(file_path))
        return True
    except portalocker.LockException:
        logging.error(f"Could not acquire lock for writing {file_path}")
        return False
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
        if progress_file_path.exists():
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
