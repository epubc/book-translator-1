import json
from pathlib import Path
import uuid
from PyQt5.QtCore import QStandardPaths

class HistoryManager:
    @classmethod
    def get_history_file(cls):
        app_data_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        app_data_dir.mkdir(parents=True, exist_ok=True)
        return app_data_dir / "novel_translator_history.json"

    @classmethod
    def load_history(cls):
        history_file = cls.get_history_file()
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except json.JSONDecodeError:
                return []
        return []

    @classmethod
    def save_history(cls, history):
        history_file = cls.get_history_file()
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)

    @classmethod
    def add_task(cls, task):
        history = cls.load_history()
        task_type = task.get("task_type")
        if task_type == "web":
            for existing in history:
                if existing.get("task_type") == "web" and existing.get("book_url") == task.get("book_url"):
                    existing.update(task)
                    cls.save_history(history)
                    return existing.get("id")
        elif task_type == "file":
            for existing in history:
                if existing.get("task_type") == "file" and existing.get("file_path") == task.get("file_path"):
                    existing.update(task)
                    cls.save_history(history)
                    return existing.get("id")
        task["id"] = str(uuid.uuid4())
        history.append(task)
        cls.save_history(history)
        return task["id"]

    @classmethod
    def update_task(cls, task_id, updates):
        history = cls.load_history()
        for task in history:
            if task.get("id") == task_id:
                task.update(updates)
                break
        cls.save_history(history)

    @classmethod
    def remove_task_by_id(cls, task_id):
        history = cls.load_history()
        history = [task for task in history if task.get("id") != task_id]
        cls.save_history(history)
