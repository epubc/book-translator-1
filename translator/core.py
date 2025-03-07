import concurrent
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional, Tuple

from google.generativeai import GenerativeModel
import google.generativeai as genai

from config import settings, prompts
from config.models import ModelConfig, DEFAULT_MODEL_CONFIG
from config.prompts import NAME_PROMPT
from config.settings import TRANSLATION_INTERVAL_SECONDS
from translator.file_handler import FileHandler
from translator.helper import is_in_chapter_range
from translator.text_processing import normalize_translation, validate_translation_quality, \
    preprocess_raw_text


class PromptStyle(Enum):
    Modern = 1
    ChinaFantasy = 2
    BookInfo = 3


@dataclass
class TranslationTask:
    """Dataclass to represent a translation task"""
    filename: str
    content: str


class Translator:

    def __init__(self, model_config: ModelConfig = DEFAULT_MODEL_CONFIG, file_handler: Optional[FileHandler] = None, fallback_model_config: Optional[ModelConfig] = None):
        self._log_handlers = []
        self.model = self._create_model(model_config)
        self.fallback_model = self._create_model(fallback_model_config) if fallback_model_config else None
        self.batch_size = model_config.BATCH_SIZE
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
                logging.info("Detected previous clean cancellation, resetting batch timing data")
                if "last_batch_time" in progress_data:
                    progress_data.pop("last_batch_time")
                if "last_batch_size" in progress_data:
                    progress_data.pop("last_batch_size")
                progress_data.pop("clean_cancellation", None)
                self.file_handler.save_progress(progress_data)
        except Exception as e:
            logging.warning(f"Failed to check cancellation status: {e}")
        
        while not self._stop_requested and not self.file_handler.is_translation_complete(start_chapter, end_chapter):
            futures = self._process_translation_batch(prompt_style, start_chapter, end_chapter)
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
        end_chapter: Optional[int] = None
    ) -> List[concurrent.futures.Future]:
        executor = ThreadPoolExecutor(max_workers=self.batch_size)
        futures = []
        tasks = self._prepare_tasks(start_chapter, end_chapter)
        if not tasks:
            logging.info("No tasks to process")
            return futures

        progress_data = self.file_handler.load_progress()
        progress_data.setdefault("retries", {})
        retry_lock = Lock()

        batch_index = 0
        while tasks and not self._stop_requested:
            self._enforce_rate_limit(progress_data, len(tasks))
            batch_index += 1
            batch = tasks[:self.batch_size]
            if self.has_processed_tasks(batch):
                tasks = self._prepare_tasks(start_chapter, end_chapter)
                batch = tasks[:self.batch_size]
            tasks = tasks[self.batch_size:]

            logging.info("Processing batch %d with %d tasks", batch_index, len(batch))
            logging.info(f"Tasks in this batch: {[task.filename for task in batch]}")

            batch_futures = [
                executor.submit(
                    self._process_task,
                    task,
                    progress_data,
                    retry_lock,
                    prompt_style
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

    def _enforce_rate_limit(self, progress_data: Dict, pending_tasks: int) -> None:
        """Enforce rate limiting between batches."""
        last_batch_time = progress_data.get("last_batch_time", 0)
        elapsed = time.time() - last_batch_time
        remaining = TRANSLATION_INTERVAL_SECONDS - elapsed

        if remaining > 0 and (progress_data.get("last_batch_size", 0) + pending_tasks) > self.batch_size:
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
            prompt_style: PromptStyle
    ) -> None:
        # Check cancellation before processing each task.
        if self._stop_requested:
            logging.info("Translation task %s cancelled.", task.filename)
            return
        try:
            retry_count = self._get_retry_count(task.filename, progress_data, retry_lock)
            raw_text = preprocess_raw_text(task.content, retry_count)
            model = self._select_model(retry_count)
            additional_info = self._get_additional_info()
            translated_text = self._translate(
                model=model,
                raw_text=raw_text,
                additional_info=additional_info,
                prompt_style=prompt_style
            )
            if not translated_text:
                logging.error("Error processing %s", task.filename)
                return
            validate_translation_quality(translated_text, retry_count)
            self._handle_translation_success(task, translated_text, progress_data, retry_lock)
        except Exception as e:
            logging.error("Error processing %s: %s", task.filename, str(e))
            self._increase_retry_count(task.filename, progress_data, retry_lock)


    def _get_retry_count(self, filename: str, progress_data: Dict, lock: Lock) -> int:
        """Get current retry count with thread safety."""
        with lock:
            # Initialize retry count if not present
            if filename not in progress_data["retries"]:
                progress_data["retries"][filename] = 0
            return progress_data["retries"].get(filename, 0)

    def _increase_retry_count(self, filename: str, progress_data: Dict, lock: Lock):
        """Increase retry count with thread safety."""
        with lock:
            if filename not in progress_data["retries"]:
                progress_data["retries"][filename] = 0
            progress_data["retries"][filename] += 1
            self.file_handler.save_progress(progress_data)


    def _select_model(self, retry_count: int) -> GenerativeModel:
        """Select appropriate model based on retry count and availability."""
        return self.fallback_model if retry_count > 0 and self.fallback_model else self.model


    def _get_additional_info(self) -> str:
        """Get system instruction for translation context."""
        character_names = self.file_handler.load_and_convert_names_to_string()
        if not character_names:
            return ""
        return f"{NAME_PROMPT} {character_names}"


    def _handle_translation_success(self, task: TranslationTask, translated_text: str,
                                    progress_data: Dict,
                                    lock: Lock) -> None:
        """Handle successful translation with cleanup."""
        logging.info("Successfully translated: %s", task.filename)
        self.file_handler.save_content_to_file(translated_text, task.filename, "translation_responses")

        with lock:
            progress_data["retries"].pop(task.filename, None)
            self.file_handler.save_progress(progress_data)


    def _translate(
            self,
            model: GenerativeModel,
            raw_text: str,
            additional_info: Optional[str] = None,
            prompt_style: PromptStyle = PromptStyle.Modern
    ) -> Optional[str]:
        """Execute translation with quality checks."""
        try:
            prompt = self._build_translation_prompt(raw_text, additional_info, prompt_style)
            response = self._get_model_response(model, prompt)
            translated_text = response.text.strip()
            if not translated_text:
                raise ValueError("Empty model response")

            return normalize_translation(translated_text)

        except Exception as e:
            logging.warning("Translation error: %s", str(e))
            return None


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
        }[PromptStyle(prompt_style)]

        if additional_info:
            base_prompt = f"{additional_info}\n{base_prompt}"
        return f"{base_prompt}\n{text}".strip()


    def _get_model_response(self, model: GenerativeModel, prompt: str) -> any:
        """Get model response with timeout handling."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(model.generate_content, prompt)
            return future.result(timeout=120)

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
