import concurrent
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Dict, List, Optional, Any

from google.generativeai import GenerativeModel
import google.generativeai as genai

from config import settings, prompts
from config.models import ModelConfig, GEMINI_FLASH_LITE_MODEL_CONFIG, GEMINI_PRO_MODEL_CONFIG
from config.prompts import PromptStyle
from config.settings import TRANSLATION_INTERVAL_SECONDS
from translator.file_handler import FileHandler
from translator.helper import is_in_chapter_range
from translator.text_processing import normalize_translation, detect_untranslated_chinese


@dataclass
class TranslationTask:
    """Dataclass to represent a translation task"""
    filename: str
    content: str


class ModelManager:
    """Handles model initialization and selection"""
    
    def __init__(self, model_config: ModelConfig):
        self.primary_model = self._initialize_model(model_config)
        self.lite_model = self._initialize_model(GEMINI_FLASH_LITE_MODEL_CONFIG)
        self.pro_model = self._initialize_model(GEMINI_PRO_MODEL_CONFIG)
        self.primary_batch_size = model_config.BATCH_SIZE
        self.lite_batch_size = GEMINI_FLASH_LITE_MODEL_CONFIG.BATCH_SIZE
        self.pro_batch_size = GEMINI_PRO_MODEL_CONFIG.BATCH_SIZE
        
    def _initialize_model(self, model_config: ModelConfig) -> GenerativeModel:
        """Initialize a Gemini model with the given configuration."""
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
    
    def select_model_for_task(self, is_retry: bool) -> GenerativeModel:
        """Select the appropriate model based on whether this is a retry or not."""
        return self.pro_model if is_retry else self.primary_model


class PromptBuilder:
    """Handles building translation prompts"""
    
    @staticmethod
    def build_translation_prompt(
            text: str,
            additional_info: Optional[str],
            prompt_style: PromptStyle
    ) -> str:
        """Build prompt based on selected style."""
        base_prompt = {
            PromptStyle.Modern: prompts.MODERN_PROMPT,
            PromptStyle.ChinaFantasy: prompts.CHINA_FANTASY_PROMPT,
            PromptStyle.BookInfo: prompts.BOOK_INFO_PROMPT,
            PromptStyle.Sentences: prompts.SENTENCES_PROMPT,
            PromptStyle.IncompleteHandle: prompts.INCOMPLETE_HANDLE_PROMPT,
        }[PromptStyle(prompt_style)]
        text = f"[**NỘI DUNG ĐOẠN VĂN**]\n{text.strip()}\n[**NỘI DUNG ĐOẠN VĂN**]"
        if additional_info:
            return f"{base_prompt}\n{text}\n{base_prompt}\n\n{additional_info}".strip()
        return f"{base_prompt}\n{text}\n{base_prompt}".strip()


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
        
    def handle_previous_cancellation(self) -> None:
        """Handle any previous cancellation state in the progress data."""
        try:
            progress_data = self.load_progress()
            if progress_data.get("clean_cancellation", False):
                logging.info("Detected previous clean cancellation")
                progress_data.pop("clean_cancellation", None)
                self.save_progress(progress_data)
        except Exception as e:
            logging.warning(f"Failed to check cancellation status: {e}")
            
    def mark_task_as_retried(
            self,
            filename: str,
            progress_data: Dict,
            is_retry: bool
    ) -> None:
        """Mark a task as having been retried in the progress data."""
        with self.retry_lock:
            # Use original failed_translations key for compatibility
            if "failed_translations" in progress_data and filename in progress_data["failed_translations"]:
                progress_data["failed_translations"][filename]["retried"] = True
                if not is_retry:  # Only increment retry count on first retry attempt
                    count = progress_data["failed_translations"][filename].get("retry_count", 0) + 1
                    progress_data["failed_translations"][filename]["retry_count"] = count
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
            should_retry = is_existing and failure_type != "contains_chinese_but_stored"
            
            # Update failure information
            progress_data["failed_translations"][filename] = {
                "error": error_message,
                "failure_type": failure_type,
                "timestamp": time.time(),
                "retried": should_retry
            }
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
        
        if 'contains_chinese_but_stored' in error_lower:
            return "contains_chinese_but_stored"
        elif 'chinese' in error_lower:
            return "contains_chinese"
        elif 'prohibited' in error_lower:
            return "prohibited_content"
        elif 'copyrighted' in error_lower:
            return "copyrighted_content"
        else:
            return "generic"
            
    def _create_failure_marker(self, filename: str, failure_type: str, error_message: str) -> None:
        """Create a failure marker file to track failed translations."""
        marker_content = f"[TRANSLATION FAILED]\n\nFailure Type: {failure_type}\n\nError: {error_message}\n\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\nThis file indicates a failed translation. Please check the error details above or manually translate this content."
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
        for filename, failure_info in failed_translations.items():
            if self._should_skip_retry(failure_info):
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
        for filename, failure_info in failed_translations.items():
            if self._should_skip_chinese_retry(failure_info):
                continue
                
            if is_in_chapter_range(filename, start_chapter, end_chapter):
                # Use the translated content (with Chinese) instead of the prompt content
                content = self.file_handler.load_content_from_file(filename, "translation_responses")
                if content:
                    retry_tasks.append(TranslationTask(filename, content))
        
        logging.info(f"Found {len(retry_tasks)} translations with Chinese characters to retry")
        return sorted(retry_tasks, key=lambda t: t.filename)
        
    def _should_skip_retry(self, failure_info: Dict) -> bool:
        """Determine if a retry should be skipped based on retry count and failure type."""
        if failure_info.get("retried", False):
            return True
        if failure_info.get("failure_type") == "contains_chinese_but_stored":
            return True
        return False
        
    def _should_skip_chinese_retry(self, failure_info: Dict) -> bool:
        """Determine if a Chinese character retry should be skipped."""
        if failure_info.get("retried", False):
            return True
        if failure_info.get("final", False):
            return True
        if failure_info.get("failure_type") != "contains_chinese_but_stored":
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


class TranslationManager:
    """Manages the translation process for a book, handling different types of translations and retries."""

    def __init__(self, model_config: ModelConfig, file_handler: FileHandler):
        """Initialize the translation manager.
        
        Args:
            model_config: Configuration for the translation model
            file_handler: Initialized FileHandler instance for this translation
        """
        if file_handler is None:
            raise ValueError("FileHandler must be provided when creating a TranslationManager")
            
        self._log_handlers = []  # Keep original attribute
        self.file_handler = file_handler
        self.model_manager = ModelManager(model_config)
        self.progress_tracker = ProgressTracker(self.file_handler)
        self.task_manager = TaskManager(self.file_handler)
        self.prompt_builder = PromptBuilder()
        self.rate_limiter = RateLimiter()
        self._stop_requested = False  # Cancellation flag

    def translate_book(
            self,
            prompt_style: PromptStyle = PromptStyle.Modern,
            start_chapter: Optional[int] = None,
            end_chapter: Optional[int] = None
    ) -> None:
        """Main method to handle the book translation process."""
        logging.info("Starting translation process for: %s (chapters %s-%s)",
                     self.file_handler.book_dir, start_chapter or 'begin', end_chapter or 'end')
        self._stop_requested = False
        
        self.progress_tracker.handle_previous_cancellation()
        
        while not self._stop_requested and not self.file_handler.is_translation_complete(start_chapter, end_chapter):
            self._process_translation_phases(prompt_style, start_chapter, end_chapter)
            
            if self._stop_requested:
                logging.info("Translation process was cancelled by the user.")
                break

            self._perform_post_processing()

        self._finalize_translation(start_chapter, end_chapter)

    def _process_translation_phases(
            self,
            prompt_style: PromptStyle,
            start_chapter: Optional[int],
            end_chapter: Optional[int]
    ) -> None:
        """Process all phases of translation including regular, Chinese-specific, and failed retries."""
        # Process regular translation tasks
        logging.info("--- Processing regular translation tasks ---")
        futures = self._process_regular_translation_batch(
            prompt_style, start_chapter, end_chapter, 
            self.model_manager.primary_batch_size
        )
        concurrent.futures.wait(futures)

        # Process Chinese-specific retries
        logging.info("--- Processing Chinese character specific retries ---")
        futures = self._process_chinese_retry_batch(
           start_chapter, end_chapter,
            self.model_manager.lite_batch_size
        )
        concurrent.futures.wait(futures)

        # Process regular failed translation retries
        logging.info("--- Processing failed translation retries (regular failures) ---")
        futures = self._process_regular_translation_batch(
            prompt_style, start_chapter, end_chapter, 
            self.model_manager.pro_batch_size, is_retry=True
        )
        concurrent.futures.wait(futures)

    def _perform_post_processing(self) -> None:
        """Perform post-processing tasks after each translation phase."""
        self.file_handler.delete_invalid_translations()
        self.file_handler.extract_and_count_names()

    def _finalize_translation(self, start_chapter: Optional[int], end_chapter: Optional[int]) -> None:
        """Finalize the translation process by combining chapters."""
        if not self._stop_requested:
            self.file_handler.combine_chapter_translations(start_chapter=start_chapter, end_chapter=end_chapter)
            logging.info("Translation process completed for: %s", self.file_handler.book_dir)
        else:
            logging.info("Translation process stopped before completion.")

    def _process_regular_translation_batch(
        self,
        prompt_style: PromptStyle = PromptStyle.Modern,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        batch_size: Optional[int] = None,
        is_retry: bool = False,
    ) -> List[concurrent.futures.Future]:
        """Process a batch of regular translation tasks."""
        executor = ThreadPoolExecutor(max_workers=batch_size)
        futures = []
        
        tasks = self._prepare_regular_tasks(start_chapter, end_chapter, is_retry)
        if not tasks:
            logging.info("No tasks to process")
            return futures

        progress_data = self.progress_tracker.load_progress()
        retry_lock = Lock()  # Use retry_lock directly in this method like original code

        batch_index = 0
        while tasks and not self._stop_requested:
            batch = self._prepare_batch(tasks, batch_size, is_retry, start_chapter, end_chapter)
            if not batch:
                break

            model = self.model_manager.select_model_for_task(is_retry)
            futures.extend(self._submit_batch_tasks(
                executor, batch, progress_data, 
                retry_lock, prompt_style, is_retry, batch_index, 
                model.model_name
            ))
            batch_index += 1

        executor.shutdown(wait=False)
        return futures

    def _prepare_regular_tasks(
            self,
            start_chapter: Optional[int] = None,
            end_chapter: Optional[int] = None,
            is_retry: bool = False
    ) -> List[TranslationTask]:
        """Prepare regular translation tasks based on whether it's a retry or not."""
        if is_retry:
            return self.task_manager.prepare_retry_tasks(start_chapter, end_chapter)
        return self.task_manager.prepare_new_tasks(start_chapter, end_chapter)

    def _prepare_batch(
            self,
            tasks: List[TranslationTask],
            batch_size: int,
            is_retry: bool,
            start_chapter: Optional[int],
            end_chapter: Optional[int]
    ) -> List[TranslationTask]:
        """Prepare a batch of tasks for processing."""
        progress_data = self.progress_tracker.load_progress()
        model = self.model_manager.select_model_for_task(is_retry)
        self.rate_limiter.enforce_rate_limit(progress_data, len(tasks), batch_size, model.model_name)
        
        batch = tasks[:batch_size]
        
        if not is_retry and self.task_manager.has_processed_tasks(batch):
            tasks = self.task_manager.prepare_new_tasks(start_chapter, end_chapter)
            batch = tasks[:batch_size]
            
        tasks[:] = tasks[batch_size:]  # Remove processed tasks
        return batch

    def _submit_batch_tasks(
            self,
            executor: ThreadPoolExecutor,
            batch: List[TranslationTask],
            progress_data: Dict,
            retry_lock: Lock,
            prompt_style: PromptStyle,
            is_retry: bool,
            batch_index: int,
            model_name: str
    ) -> List[concurrent.futures.Future]:
        """Submit a batch of tasks for processing."""
        logging.info("Processing batch %d with %d tasks", batch_index+1, len(batch))
        logging.info(f"Tasks in this batch: {[task.filename for task in batch]}")

        batch_futures = [
            executor.submit(
                self._process_regular_task,
                task,
                progress_data,
                retry_lock,
                prompt_style,
                is_retry,
            )
            for task in batch
        ]

        # Update model-specific rate limiting information
        model_rate_limits = progress_data.get("model_rate_limits", {})
        if model_name not in model_rate_limits:
            model_rate_limits[model_name] = {"last_batch_time": 0, "last_batch_size": 0}
        
        model_rate_limits[model_name].update({
            "last_batch_time": time.time(),
            "last_batch_size": len(batch)
        })
        progress_data["model_rate_limits"] = model_rate_limits
        self.progress_tracker.save_progress(progress_data)

        return batch_futures

    def _process_regular_task(
            self,
            task: TranslationTask,
            progress_data: Dict,
            retry_lock: Lock,
            prompt_style: PromptStyle,
            is_retry: bool = False,
    ) -> None:
        """Process a single regular translation task."""
        if self._stop_requested:
            logging.info("Translation task %s cancelled.", task.filename)
            return
            
        try:
            # Mark as retried if necessary
            if is_retry:
                self.progress_tracker.mark_task_as_retried(task.filename, progress_data, is_retry)
                
            # Select appropriate model
            model = self.model_manager.select_model_for_task(is_retry)
            
            # Translate the content
            translated_text = self._translate(model, task.content, None, prompt_style)
            
            if translated_text:
                # Handle Chinese characters if present
                has_chinese, ratio = detect_untranslated_chinese(translated_text)
                
                if not has_chinese or ratio <= 0.5:
                    # No Chinese characters or negligible amount - handle as success
                    self.progress_tracker.handle_translation_success(task, translated_text, progress_data)
                elif has_chinese and ratio <= 20:
                    # Some Chinese characters (≤20%) - store content but mark as failed
                    logging.warning(f"Text contains Chinese characters ({ratio:.2f}%) but ratio ≤ 20% for {task.filename}")
                    self.file_handler.save_content_to_file(translated_text, task.filename, "translation_responses")
                    self.progress_tracker.mark_translation_failed(
                        task.filename, 
                        f"contains_chinese_but_stored ({ratio:.2f}%)", 
                        progress_data,
                        store_failure_marker=False
                    )
                else:
                    # Excessive Chinese characters - create failure marker
                    error_msg = f"excessive chinese characters ({ratio:.2f}%)"
                    logging.error(f"Text contains excessive Chinese characters ({ratio:.2f}%) for {task.filename}")
                    self.progress_tracker.mark_translation_failed(task.filename, error_msg, progress_data)
            else:
                # Handle translation error
                error_msg = "Empty translation result"
                logging.error(f"Error processing {task.filename}: {error_msg}")
                if not ("429" in error_msg or "504" in error_msg):
                    self.progress_tracker.mark_translation_failed(task.filename, error_msg.lower(), progress_data)
                
        except Exception as e:
            # Handle exceptions
            error_message = f"Error translating {task.filename}: {str(e)}"
            logging.error(error_message)
            if not ("429" in str(e) or "504" in str(e)):
                self.progress_tracker.mark_translation_failed(task.filename, str(e).lower(), progress_data)

    def _translate(
            self,
            model: GenerativeModel,
            raw_text: str,
            additional_info: Optional[str] = None,
            prompt_style: PromptStyle = PromptStyle.Modern
    ) -> Optional[str]:
        """Translate text using the specified model and prompt style."""
        if not raw_text:
            logging.warning("Empty text provided for translation")
            return None
            
        prompt = self.prompt_builder.build_translation_prompt(raw_text, additional_info, prompt_style)
        
        try:
            response = self._get_model_response(model, prompt)
            if response:
                translated_text = response.text.strip()
                if not translated_text:
                    raise ValueError("Empty model response")
                return normalize_translation(translated_text)
        except Exception as e:
            logging.error(f"Error during translation: {str(e)}")
            raise
            
        return None

    def _get_model_response(self, model: GenerativeModel, prompt: str) -> Any:
        """Get a response from the model with timeout handling."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(model.generate_content, prompt)
            return future.result(timeout=180)

    def translate_text(self, text: Optional[str], prompt_style: PromptStyle) -> str:
        """Translate a single text snippet using the primary model."""
        if not text:
            return ""
        return self._translate(self.model_manager.primary_model, text, None, prompt_style) or ""

    def stop(self):
        """Stop the translation process."""
        logging.info("Translator stop() called - cancelling all translation operations")
        self._stop_requested = True
        
        if self.file_handler:
            try:
                progress_data = self.progress_tracker.load_progress()
                progress_data["clean_cancellation"] = True
                self.progress_tracker.save_progress(progress_data)
            except Exception as e:
                logging.error(f"Error saving cancellation state: {e}")

    def _process_chinese_retry_batch(
        self,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> List[concurrent.futures.Future]:
        """Process a batch of Chinese-specific retry tasks."""
        executor = ThreadPoolExecutor(max_workers=batch_size)
        futures = []
        
        tasks = self.task_manager.prepare_chinese_retry_tasks(start_chapter, end_chapter)
        if not tasks:
            logging.info("No Chinese-containing translations to process")
            return futures

        progress_data = self.progress_tracker.load_progress()
        retry_lock = Lock()

        batch_index = 0
        while tasks and not self._stop_requested:
            self.rate_limiter.enforce_rate_limit(
                progress_data, len(tasks), batch_size, 
                self.model_manager.lite_model.model_name
            )
            
            batch = tasks[:batch_size]
            if not batch:
                break
                
            logging.info("Processing Chinese retry batch %d with %d tasks", batch_index+1, len(batch))
            logging.info(f"Chinese retry tasks in this batch: {[task.filename for task in batch]}")

            batch_futures = [
                executor.submit(
                    self._process_chinese_retry_task,
                    task,
                    progress_data,
                    retry_lock,
                    PromptStyle.IncompleteHandle,
                )
                for task in batch
            ]
            
            futures.extend(batch_futures)
            tasks = tasks[batch_size:]  # Remove processed tasks
            batch_index += 1
            
            # Update model-specific rate limiting information
            model_rate_limits = progress_data.get("model_rate_limits", {})
            model_name = self.model_manager.lite_model.model_name
            if model_name not in model_rate_limits:
                model_rate_limits[model_name] = {"last_batch_time": 0, "last_batch_size": 0}
            
            model_rate_limits[model_name].update({
                "last_batch_time": time.time(),
                "last_batch_size": len(batch)
            })
            progress_data["model_rate_limits"] = model_rate_limits
            self.progress_tracker.save_progress(progress_data)

        executor.shutdown(wait=False)
        return futures

    def _process_chinese_retry_task(
            self,
            task: TranslationTask,
            progress_data: Dict,
            retry_lock: Lock,
            prompt_style: PromptStyle,
    ) -> None:
        """Process a translation task that contains Chinese characters specifically."""
        if self._stop_requested:
            logging.info("Chinese retry task %s cancelled.", task.filename)
            return
            
        model = self.model_manager.lite_model
                    
        try:
            translated_text = self._translate(
                model=model,
                raw_text=task.content,
                prompt_style=prompt_style,
            )
            
            if not translated_text:
                logging.error("Error processing Chinese retry for %s", task.filename)
                return
            
            has_chinese, ratio = detect_untranslated_chinese(translated_text)
            
            if not has_chinese or ratio <= 10:
                self.progress_tracker.handle_translation_success(task, translated_text, progress_data)
                logging.info(f"Successfully reduced Chinese characters in {task.filename} to {ratio:.2f}%")
            else:
                logging.warning(f"Chinese retry failed for {task.filename}, still has {ratio:.2f}% Chinese characters")
                error_msg = f"excessive chinese characters ({ratio:.2f}%)"
                self.progress_tracker.mark_translation_failed(task.filename, error_msg, progress_data)
                
        except Exception as e:
            logging.error("Error processing Chinese retry for %s: %s", task.filename, str(e))
            if "429" in str(e):
                return
