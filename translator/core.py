import concurrent
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional

from google.generativeai import GenerativeModel
import google.generativeai as genai

from config import settings, prompts
from config.models import ModelConfig, DEFAULT_MODEL_CONFIG
from config.prompts import PromptStyle
from config.settings import TRANSLATION_INTERVAL_SECONDS
from translator.file_handler import FileHandler
from translator.helper import is_in_chapter_range
from translator.text_processing import normalize_translation, validate_translation_quality


@dataclass
class TranslationTask:
    """Dataclass to represent a translation task"""
    filename: str
    content: str


class Translator:

    def __init__(self, model_config: ModelConfig = DEFAULT_MODEL_CONFIG, file_handler: Optional[FileHandler] = None, fallback_model_config: Optional[ModelConfig] = DEFAULT_MODEL_CONFIG):
        self._log_handlers = []
        self.model = self._create_model(model_config)
        self.fallback_model = self._create_model(fallback_model_config) if fallback_model_config else None
        self.model_batch_size = model_config.BATCH_SIZE
        self.fallback_model_batch_size = fallback_model_config.BATCH_SIZE if fallback_model_config else None
        self.file_handler = file_handler
        self._stop_requested = False  # Cancellation flag

    def _create_model(self, model_config: ModelConfig) -> GenerativeModel:
        if not model_config.MODEL_NAME:
            raise ValueError("Model name must be provided")
        genai.configure(api_key=settings.get_api_key())
        model = genai.GenerativeModel(
            model_name=model_config.MODEL_NAME,
            generation_config=model_config.GENERATION_CONFIG,
            safety_settings=model_config.SAFETY_SETTINGS
        )
        logging.info("Successfully initialized model: %s", model_config.MODEL_NAME)
        return model

    def process_book_translation(
            self,
            prompt_style: PromptStyle = PromptStyle.Modern,
            start_chapter: Optional[int] = None,
            end_chapter: Optional[int] = None
    ) -> None:
        logging.info("Starting translation process for: %s (chapters %s-%s)",
                     self.file_handler.book_dir, start_chapter or 'begin', end_chapter or 'end')
        self._stop_requested = False  # Reset cancellation flag before starting
        
        # Check if there was a previous clean cancellation and reset progress markers if needed
        try:
            progress_data = self.file_handler.load_progress()
            if progress_data.get("clean_cancellation", False):
                logging.info("Detected previous clean cancellation")
                progress_data.pop("clean_cancellation", None)
                self.file_handler.save_progress(progress_data)
        except Exception as e:
            logging.warning(f"Failed to check cancellation status: {e}")
        
        while not self._stop_requested and not self.file_handler.is_translation_complete(start_chapter, end_chapter):
            futures = self._process_translation_batch(prompt_style, start_chapter, end_chapter, self.model_batch_size)
            concurrent.futures.wait(futures)

            futures = self._process_translation_batch(prompt_style, start_chapter, end_chapter, self.fallback_model_batch_size, is_retry=True)
            concurrent.futures.wait(futures)

            if self._stop_requested:
                logging.info("Translation process was cancelled by the user.")
                break

            self.file_handler.delete_invalid_translations()
            self.file_handler.extract_and_count_names()

        if not self._stop_requested:
            self.file_handler.combine_chapter_translations(start_chapter=start_chapter, end_chapter=end_chapter)
            logging.info("Translation process completed for: %s", self.file_handler.book_dir)
        else:
            logging.info("Translation process stopped before completion.")

    def _process_translation_batch(
        self,
        prompt_style: PromptStyle = PromptStyle.Modern,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        batch_size: Optional[int] = None,
        is_retry: bool = False,
    ) -> List[concurrent.futures.Future]:
        executor = ThreadPoolExecutor(max_workers=batch_size)
        futures = []
        
        # Get tasks based on is_retry flag
        if is_retry:
            tasks = self._prepare_retry_tasks(start_chapter, end_chapter)
        else:
            tasks = self._prepare_tasks(start_chapter, end_chapter)
        
        if not tasks:
            logging.info("No tasks to process")
            return futures

        progress_data = self.file_handler.load_progress()
        retry_lock = Lock()

        batch_index = 0
        while tasks and not self._stop_requested:
            self._enforce_rate_limit(progress_data, len(tasks), batch_size)
            batch_index += 1
            batch = tasks[:batch_size]
            if not is_retry and self.has_processed_tasks(batch):
                tasks = self._prepare_tasks(start_chapter, end_chapter)
                batch = tasks[:batch_size]
            tasks = tasks[batch_size:]

            logging.info("Processing batch %d with %d tasks", batch_index, len(batch))
            logging.info(f"Tasks in this batch: {[task.filename for task in batch]}")

            batch_futures = [
                executor.submit(
                    self._process_task,
                    task,
                    progress_data,
                    retry_lock,
                    prompt_style,
                    is_retry,
                )
                for task in batch
            ]
            futures.extend(batch_futures)

            # Update batch tracking
            progress_data.update({
                "last_batch_time": time.time(),
                "last_batch_size": len(batch)
            })
            self.file_handler.save_progress(progress_data)

        executor.shutdown(wait=False)
        return futures

    def _enforce_rate_limit(self, progress_data: Dict, pending_tasks: int, batch_size: int) -> None:
        """Enforce rate limiting between batches."""
        last_batch_time = progress_data.get("last_batch_time", 0)
        elapsed = time.time() - last_batch_time
        remaining = TRANSLATION_INTERVAL_SECONDS - elapsed

        if remaining > 0 and (progress_data.get("last_batch_size", 0) + pending_tasks) > batch_size:
            logging.info("Rate limiting - sleeping %.2f seconds", remaining)
            time.sleep(remaining)


    def _prepare_tasks(
            self,
            start_chapter: Optional[int] = None,
            end_chapter: Optional[int] = None
    ) -> List[TranslationTask]:
        """Prepare tasks with chapter range filtering."""
        prompts_dir = self.file_handler.get_path("prompt_files")
        responses_dir = self.file_handler.get_path("translation_responses")

        existing_responses = [f.stem for f in responses_dir.glob("*.txt")]

        tasks = [
            TranslationTask(f.name, self.file_handler.load_prompt_file_content(f.name))
            for f in prompts_dir.glob("*.txt")
            if (f.stem not in existing_responses and
                is_in_chapter_range(f.name, start_chapter, end_chapter))
        ]

        return sorted(tasks, key=lambda t: t.filename)

    def has_processed_tasks(
            self,
            batch: List[TranslationTask],
    ) ->bool:
        responses_dir = self.file_handler.get_path("translation_responses")
        existing_responses = [f.name for f in responses_dir.glob("*.txt")]

        processed_tasks = [
            task for task in batch if task.filename in existing_responses
        ]
        return len(processed_tasks) > 0


    def _process_task(
            self,
            task: TranslationTask,
            progress_data: Dict,
            retry_lock: Lock,
            prompt_style: PromptStyle,
            is_retry: bool = False,
    ) -> None:
        # Check cancellation before processing each task.
        if self._stop_requested:
            logging.info("Translation task %s cancelled.", task.filename)
            return
        model = self.model
        if is_retry:
            model = self.fallback_model
            # Mark that this is being retried in the progress data
            with retry_lock:
                if "failed_translations" in progress_data and task.filename in progress_data["failed_translations"]:
                    progress_data["failed_translations"][task.filename]["retried"] = True
                    self.file_handler.save_progress(progress_data)
                    
        try:
            translated_text = self._translate(
                model=model,
                raw_text=task.content,
                prompt_style=prompt_style,
            )
            if not translated_text:
                logging.error("Error processing %s", task.filename)
                return
            validate_translation_quality(translated_text)
            self._handle_translation_success(task, translated_text, progress_data, retry_lock)
        except Exception as e:
            logging.error("Error processing %s: %s", task.filename, str(e))
            if "429" in str(e):
                return
            self._mark_translation_failed(task.filename, str(e).lower(), progress_data, retry_lock)


    def _handle_translation_success(self, task: TranslationTask, translated_text: str,
                                    progress_data: Dict,
                                    lock: Lock) -> None:
        """Handle successful translation with cleanup."""
        logging.info("Successfully translated: %s", task.filename)
        self.file_handler.save_content_to_file(translated_text, task.filename, "translation_responses")
        
        with lock:
            if "failed_translations" in progress_data and task.filename in progress_data["failed_translations"]:
                logging.info(f"Removing {task.filename} from failed translations after successful retry")
                del progress_data["failed_translations"][task.filename]
                self.file_handler.save_progress(progress_data)


    def _translate(
            self,
            model: GenerativeModel,
            raw_text: str,
            additional_info: Optional[str] = None,
            prompt_style: PromptStyle = PromptStyle.Modern
    ) -> Optional[str]:
        """Execute translation with quality checks."""
        prompt = self._build_translation_prompt(raw_text, additional_info, prompt_style)
        response = self._get_model_response(model, prompt)
        translated_text = response.text.strip()
        if not translated_text:
            raise ValueError("Empty model response")

        return normalize_translation(translated_text)




    def _build_translation_prompt(
            self,
            text: str,
            additional_info: Optional[str],
            prompt_style: PromptStyle
    ) -> str:
        """Build prompt based on selected style."""
        base_prompt = {
            PromptStyle.Modern: prompts.MODERN_PROMPT,
            PromptStyle.ChinaFantasy: prompts.CHINA_FANTASY_PROMPT,
            PromptStyle.BookInfo: prompts.BOOK_INFO_PROMPT,
            PromptStyle.Words: prompts.WORDS_PROMPT,
        }[PromptStyle(prompt_style)]
        text = f"[**NỘI DUNG ĐOẠN VĂN**]\n{text.strip()}\n[**NỘI DUNG ĐOẠN VĂN**]"
        if additional_info:
            return f"{base_prompt}\n{text}\n{base_prompt}\n\n{additional_info}".strip()
        return f"{base_prompt}\n{text}\n{base_prompt}".strip()


    def _get_model_response(self, model: GenerativeModel, prompt: str) -> any:
        """Get model response with timeout handling."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(model.generate_content, prompt)
            return future.result(timeout=180)

    def translate_text(self, text: Optional[str], prompt_style: PromptStyle) -> str:
        if not text:
            return ""
        return self._translate(self.model, text, prompt_style=prompt_style)

    def stop(self):
        """Stop all translation operations and clean up resources."""
        logging.info("Translator stop() called - cancelling all translation operations")
        self._stop_requested = True
        
        # Ensure any pending progress data is saved
        if self.file_handler:
            try:
                progress_data = self.file_handler.load_progress()
                # Mark in progress data that we had a clean cancellation
                progress_data["clean_cancellation"] = True
                self.file_handler.save_progress(progress_data)
            except Exception as e:
                logging.error(f"Error saving cancellation state: {e}")

    def _mark_translation_failed(self, filename: str, error_message: str, progress_data: Dict, lock: Lock) -> None:
        """Mark a translation as failed and categorize the failure."""
        with lock:
            # Initialize failed_translations dict if it doesn't exist
            if "failed_translations" not in progress_data:
                progress_data["failed_translations"] = {}
            
            # Categorize the failure type
            failure_type = "generic"
            if 'chinese' in error_message:
                failure_type = "contains_chinese"
            elif 'prohibited' in error_message:
                failure_type = "prohibited_content"
            elif 'copyrighted' in error_message:
                failure_type = "copyrighted_content"
            
            # Store the failure information
            progress_data["failed_translations"][filename] = {
                "error": error_message,
                "failure_type": failure_type,
                "timestamp": time.time(),
                "retried": False  # Initialize with retried=False
            }
            
            # Save a marker file in translation_responses directory
            # This prevents the system from continuously retrying this translation
            failure_message = f"[TRANSLATION FAILED]\n\nFailure Type: {failure_type}\n\nError: {error_message}\n\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\nThis file indicates a failed translation. Please check the error details above or manually translate this content."
            try:
                self.file_handler.save_content_to_file(failure_message, filename, "translation_responses")
                logging.info(f"Created failure marker file for {filename}")
            except Exception as e:
                logging.error(f"Failed to create failure marker file for {filename}: {e}")
            
            logging.warning(f"Translation for {filename} marked as failed: {failure_type}")
            self.file_handler.save_progress(progress_data)

    def _prepare_retry_tasks(
        self,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
    ) -> List[TranslationTask]:
        """Prepare retry tasks from failed translations that have not been retried."""
        # Load failed translations from progress data
        progress_data = self.file_handler.load_progress()
        failed_translations = progress_data.get("failed_translations", {})
        
        if not failed_translations:
            logging.info("No failed translations to retry")
            return []
        
        # Create tasks from failed translations that have not been retried
        tasks = []
        for filename, failure_info in failed_translations.items():
            # Skip if already retried
            if failure_info.get("retried", False):
                continue
                
            # Check if the file is in the specified chapter range
            if is_in_chapter_range(filename, start_chapter, end_chapter):
                # Get content from the prompt file
                content = self.file_handler.load_prompt_file_content(filename)
                if content:
                    tasks.append(TranslationTask(filename, content))
        
        logging.info(f"Found {len(tasks)} failed translations to retry")
        return tasks
