import logging
import time
from threading import Lock
from typing import Dict, Optional, List

from config.settings import TRANSLATION_INTERVAL_SECONDS
from text_processing.text_processing import normalize_translation
from translator.file_handler import FileHandler
from translator.helper import is_in_chapter_range
from translator.task import FailedTranslationTask, TranslationTask


class RateLimiter:
    """Handles rate limiting for API calls"""

    @staticmethod
    def enforce_rate_limit(progress_data: Dict, pending_tasks: int, batch_size: int, model_name: str) -> None:
        """Enforce rate limiting between batches of API calls."""
        if pending_tasks == 0 or batch_size <= 0:
            return

        model_rate_limits = progress_data.get("model_rate_limits", {})

        # Initialize model data if it doesn't exist
        if model_name not in model_rate_limits:
            model_rate_limits[model_name] = {"last_batch_time": 0, "last_batch_size": 0}
            progress_data["model_rate_limits"] = model_rate_limits

        model_data = model_rate_limits[model_name]
        last_batch_time = model_data.get("last_batch_time", 0)
        elapsed = time.time() - last_batch_time
        remaining = TRANSLATION_INTERVAL_SECONDS - elapsed

        # Only apply rate limiting if the combined size exceeds batch size
        if remaining > 0 and (model_data.get("last_batch_size", 0) + pending_tasks) > batch_size:
            logging.info("Rate limiting for model %s - sleeping %.2f seconds", model_name, remaining)
            time.sleep(remaining)


class ProgressTracker:
    """Manages translation progress tracking"""

    def __init__(self, file_handler: FileHandler):
        self.file_handler = file_handler
        self.retry_lock = Lock()

    def load_progress(self) -> Dict:
        """Load the current progress data."""
        return self.file_handler.load_progress()

    def save_progress(self, progress_data: Dict) -> None:
        """Save the current progress data."""
        self.file_handler.save_progress(progress_data)

    def mark_task_as_retried(
            self,
            filename: str,
            progress_data: Dict,
    ) -> None:
        """Mark a task as having been retried in the progress data."""
        with self.retry_lock:
            if "failed_translations" in progress_data and filename in progress_data["failed_translations"]:
                progress_data["failed_translations"][filename]["retried"] = True
                self.save_progress(progress_data)

    def mark_translation_failed(
            self,
            filename: str,
            error_message: str,
            progress_data: Dict,
            store_failure_marker: bool = True,
            failure_type: Optional[str] = None
    ) -> None:
        """Mark a translation as failed in the progress data."""
        with self.retry_lock:
            # Set up the failed_translations key if it doesn't exist
            if "failed_translations" not in progress_data:
                progress_data["failed_translations"] = {}

            # Determine failure type if not provided
            if failure_type is None:
                failure_type = self._categorize_failure(error_message)

            # Check if this is an existing failure
            is_existing = filename in progress_data["failed_translations"]
            should_retry = is_existing and failure_type != "partial_chinese"

            # Create failed task object
            failed_task = FailedTranslationTask(
                filename=filename,
                failure_description=error_message,
                failure_type=failure_type,
                timestamp=time.time(),
                retried=should_retry
            )

            # Update failure information
            progress_data["failed_translations"][filename] = failed_task.to_dict()
            self.save_progress(progress_data)

            # Create failure marker file
            if store_failure_marker:
                self._create_failure_marker(filename, failure_type, error_message)

            logging.warning(f"Translation for {filename} marked as failed: {failure_type}")

    def handle_translation_success(
            self,
            task: TranslationTask,
            translated_text: str,
            progress_data: Dict,
    ) -> None:
        """Handle a successful translation by saving the result and updating progress."""
        with self.retry_lock:
            # Save translated content
            normalized_text = normalize_translation(translated_text)
            self.file_handler.save_content_to_file(normalized_text, task.filename, "translation_responses")

            # Remove from failures if it was previously marked as failed
            if "failed_translations" in progress_data and task.filename in progress_data["failed_translations"]:
                logging.info(f"Removing {task.filename} from failed translations after successful retry")
                del progress_data["failed_translations"][task.filename]
                self.save_progress(progress_data)

            # Delete any failure marker file
            self.delete_failure_marker(task.filename)
            logging.info("Successfully translated: %s", task.filename)

    def delete_failure_marker(self, filename: str) -> None:
        """Delete a failure marker file for a translation."""
        try:
            responses_dir = self.file_handler.get_path("translation_responses")
            marker_file = responses_dir / filename
            if marker_file.exists():
                content = self.file_handler.load_content_from_file(filename, "translation_responses")
                if content and '[TRANSLATION FAILED]' in content:
                    self.file_handler.delete_file(filename, "translation_responses")
                    logging.info(f"Deleted failure marker file for {filename}")
        except Exception as e:
            logging.error(f"Failed to delete failure marker file for {filename}: {e}")

    def _categorize_failure(self, error_message: str) -> str:
        """Categorize a failure based on the error message."""
        error_lower = error_message.lower()

        if 'partial_chinese' in error_lower:
            return "partial_chinese"
        elif 'exceeds_chinese' in error_lower:
            return "exceeds_chinese"
        elif 'prohibited' in error_lower:
            return "prohibited_content"
        elif 'copyrighted' in error_lower:
            return "copyrighted_content"
        else:
            return "generic"

    def _create_failure_marker(self, filename: str, failure_type: str, error_message: str) -> None:
        """Create a failure marker file to track failed translations."""
        marker_content = f"[TRANSLATION FAILED]\n\nFailure Type: {failure_type}\n\nDescription: {error_message}\n\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\nThis file indicates a failed translation. Please check the error details above or manually translate this content."
        try:
            self.file_handler.save_content_to_file(marker_content, filename, "translation_responses")
            logging.info(f"Created failure marker file for {filename}")
        except Exception as e:
            logging.error(f"Failed to create failure marker file for {filename}: {e}")


class TaskManager:
    """Manages translation tasks, including preparation and processing"""

    def __init__(self, file_handler: FileHandler):
        self.file_handler = file_handler

    def prepare_new_tasks(
            self,
            start_chapter: Optional[int] = None,
            end_chapter: Optional[int] = None
    ) -> List[TranslationTask]:
        """Prepare new translation tasks that haven't been processed yet."""
        prompts_dir = self.file_handler.get_path("prompt_files")
        responses_dir = self.file_handler.get_path("translation_responses")

        existing_responses = {f.stem for f in responses_dir.glob("*.txt")}

        tasks = []
        for f in prompts_dir.glob("*.txt"):
            # Only include files that haven't been translated yet
            if (f.stem not in existing_responses and
                    is_in_chapter_range(f.name, start_chapter, end_chapter)):
                content = self.file_handler.load_content_from_file(f.name, "prompt_files")
                if content:
                    tasks.append(TranslationTask(f.name, content))

        return sorted(tasks, key=lambda t: t.filename)

    def prepare_retry_tasks(
            self,
            start_chapter: Optional[int] = None,
            end_chapter: Optional[int] = None
    ) -> List[TranslationTask]:
        """Prepare tasks for retry that previously failed."""
        progress_data = self.file_handler.load_progress()
        failed_translations = progress_data.get("failed_translations", {})

        if not failed_translations:
            logging.info("No failed translations to retry")
            return []

        retry_tasks = []
        for filename, failure_data in failed_translations.items():
            failed_task = FailedTranslationTask.from_dict(filename, failure_data)
            if self._should_skip_retry(failed_task):
                continue

            if is_in_chapter_range(filename, start_chapter, end_chapter):
                content = self.file_handler.load_content_from_file(filename, "prompt_files")
                if content:
                    retry_tasks.append(TranslationTask(filename, content))

        logging.info(f"Found {len(retry_tasks)} failed translations to retry")
        return sorted(retry_tasks, key=lambda t: t.filename)

    def prepare_chinese_retry_tasks(
            self,
            start_chapter: Optional[int] = None,
            end_chapter: Optional[int] = None
    ) -> List[TranslationTask]:
        """Prepare tasks specifically for Chinese character retry."""
        progress_data = self.file_handler.load_progress()
        failed_translations = progress_data.get("failed_translations", {})

        if not failed_translations:
            logging.info("No translations with Chinese to retry")
            return []

        retry_tasks = []
        for filename, failure_data in failed_translations.items():
            failed_task = FailedTranslationTask.from_dict(filename, failure_data)
            if self._should_skip_chinese_retry(failed_task):
                continue

            if is_in_chapter_range(filename, start_chapter, end_chapter):
                # Use the translated content (with Chinese) instead of the prompt content
                content = self.file_handler.load_content_from_file(filename, "translation_responses")
                if content:
                    retry_tasks.append(TranslationTask(filename, content))

        logging.info(f"Found {len(retry_tasks)} translations with Chinese characters to retry")
        return sorted(retry_tasks, key=lambda t: t.filename)

    def _should_skip_retry(self, failed_task: FailedTranslationTask) -> bool:
        """Determine if a retry should be skipped based on retry count and failure type."""
        if failed_task.retried:
            return True
        if failed_task.failure_type == "partial_chinese":
            return True
        return False

    def _should_skip_chinese_retry(self, failed_task: FailedTranslationTask) -> bool:
        """Determine if a Chinese character retry should be skipped."""
        if failed_task.retried:
            return True
        if failed_task.failure_type != "partial_chinese":
            return True
        return False

    def has_processed_tasks(self, batch: List[TranslationTask]) -> bool:
        """Check if any tasks in the batch have already been processed."""
        responses_dir = self.file_handler.get_path("translation_responses")
        existing_responses = [f.name for f in responses_dir.glob("*.txt")]

        processed_tasks = [
            task for task in batch if task.filename in existing_responses
        ]
        return len(processed_tasks) > 0