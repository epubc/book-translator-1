import json
import threading
from pathlib import Path
import uuid
import logging
from PyQt5.QtCore import QStandardPaths


class HistoryManager:
    _history_cache = None
    _lock = threading.RLock()
    _active_tasks = {}  # Dictionary to track active task threads: {task_id: thread}

    @classmethod
    def get_history_file(cls):
        app_data_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        app_data_dir.mkdir(parents=True, exist_ok=True)
        return app_data_dir / "novel_translator_history.json"

    @classmethod
    def _load_history(cls):
        if cls._history_cache is not None:
            return

        history_file = cls.get_history_file()
        if not history_file.exists():
            cls._history_cache = []
            return

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                cls._history_cache = data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error loading history: {e}")
            cls._history_cache = []

    @classmethod
    def _save_history(cls):
        history_file = cls.get_history_file()
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(cls._history_cache, f, indent=4, ensure_ascii=False)
        except IOError as e:
            logging.error(f"Error saving history: {e}")

    @classmethod
    def load_history(cls):
        with cls._lock:
            cls._load_history()
            return [task.copy() for task in cls._history_cache]

    @classmethod
    def add_task(cls, task):
        with cls._lock:
            cls._load_history()
            task_type = task.get("task_type")
            task_id = None

            for existing in cls._history_cache:
                if (
                    task_type == "web"
                    and existing.get("task_type") == "web"
                    and existing.get("book_url") == task.get("book_url")
                ):
                    existing.update(task)
                    task_id = existing.get("id")
                    break
                elif (
                    task_type == "file"
                    and existing.get("task_type") == "file"
                    and existing.get("file_path") == task.get("file_path")
                ):
                    existing.update(task)
                    task_id = existing.get("id")
                    break

            if task_id is None:
                task["id"] = str(uuid.uuid4())
                cls._history_cache.append(task)
                task_id = task["id"]

            cls._save_history()
            return task_id

    @classmethod
    def update_task(cls, task_id, updates):
        with cls._lock:
            cls._load_history()
            for task in cls._history_cache:
                if task.get("id") == task_id:
                    task.update(updates)
                    break
            cls._save_history()

    @classmethod
    def remove_task_by_id(cls, task_id):
        with cls._lock:
            cls._load_history()
            cls._history_cache = [task for task in cls._history_cache if task.get("id") != task_id]
            cls._save_history()

            # Check if the task is active and stop it
            cls.stop_task_if_active(task_id)

    @classmethod
    def register_active_task(cls, task_id, thread):
        """Register a task as active with its associated thread"""
        with cls._lock:
            # If there's already an active thread for this task, stop it first
            cls.stop_task_if_active(task_id)
            cls._active_tasks[task_id] = thread

            # Update task status in history
            cls.update_task(task_id, {"status": "In Progress"})

    @classmethod
    def unregister_active_task(cls, task_id):
        """Remove a task from the active tasks list"""
        with cls._lock:
            if task_id in cls._active_tasks:
                del cls._active_tasks[task_id]

    @classmethod
    def stop_task_if_active(cls, task_id):
        """Stop a running task if it exists"""
        with cls._lock:
            if task_id in cls._active_tasks:
                thread = cls._active_tasks[task_id]
                if thread and thread.isRunning():
                    logging.info(f"Stopping active task: {task_id}")
                    thread.stop()
                    # We don't wait here to avoid potential deadlocks
                cls.unregister_active_task(task_id)

    @classmethod
    def stop_all_active_tasks(cls):
        """Stop all running tasks"""
        with cls._lock:
            task_ids = list(cls._active_tasks.keys())
            for task_id in task_ids:
                cls.stop_task_if_active(task_id)

    @classmethod
    def is_task_active(cls, task_id):
        """Check if a task is currently active"""
        with cls._lock:
            if task_id in cls._active_tasks:
                thread = cls._active_tasks[task_id]
                if thread and thread.isRunning():
                    return True
                # Clean up references to finished threads
                cls.unregister_active_task(task_id)
            return False

    @classmethod
    def get_task_by_id(cls, task_id):
        """Get a task by its ID"""
        with cls._lock:
            cls._load_history()
            for task in cls._history_cache:
                if task.get("id") == task_id:
                    return task.copy()
            return None

    @classmethod
    def get_active_task_count(cls):
        """Get the number of currently active tasks"""
        with cls._lock:
            # First clean up any finished threads
            for task_id in list(cls._active_tasks.keys()):
                thread = cls._active_tasks[task_id]
                if not thread or not thread.isRunning():
                    cls.unregister_active_task(task_id)
            return len(cls._active_tasks)
