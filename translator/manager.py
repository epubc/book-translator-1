import concurrent
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Dict, List, Optional, Any

from google.generativeai import GenerativeModel

from config import settings
from config.models import ModelConfig
from config.prompts import PromptStyle
from translator.file_handler import FileHandler
from text_processing.text_processing import normalize_translation, detect_untranslated_chinese
from translator.model import ModelManager
from translator.progress import ProgressTracker, TaskManager, RateLimiter
from translator.prompt import PromptBuilder
from translator.task import TranslationTask


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
                self.progress_tracker.mark_task_as_retried(task.filename, progress_data)
                
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
                        f"ERROR:partial_chinese, translation contains partial chinese with ratio: ({ratio:.2f}%)",
                        progress_data,
                        store_failure_marker=False
                    )
                else:
                    # Excessive Chinese characters - create failure marker
                    error_msg = f"ERROR:exceeds_chinese, translation contains chinese with ratio: ({ratio:.2f}%)"
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

    def translate_chunk(self, chunks: List[str], prompt_style: PromptStyle) -> List[str]:
        """Translate a list of text chunks using the primary model.

        Args:
            chunks: List of text chunks to translate
            prompt_style: Style of prompt to use for translation

        Returns:
            List of translated chunks or empty list if translation fails
        """
        if not chunks:
            logging.error("Failed to split text into chunks")
            return []

        translated_chunks = []
        batch_size = self.model_manager.primary_batch_size
        progress_data = self.progress_tracker.load_progress()
        model = self.model_manager.primary_model
        model_name = model.model_name

        # Convert chunks to tasks for consistent processing
        chunk_tasks = []
        for i, chunk in enumerate(chunks):
            chunk_tasks.append(TranslationTask(f"chunk_{i}", chunk))

        batch_index = 0
        while chunk_tasks and not self._stop_requested:
            # Prepare batch similar to _prepare_batch
            self.rate_limiter.enforce_rate_limit(
                progress_data,
                len(chunk_tasks),
                batch_size,
                model_name
            )

            batch = chunk_tasks[:batch_size]
            chunk_tasks = chunk_tasks[batch_size:]

            logging.info("Processing chunk batch %d with %d chunks", batch_index + 1, len(batch))

            # Process batch with ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                future_to_task = {
                    executor.submit(
                        self._translate,
                        model=model,
                        raw_text=task.content,
                        additional_info=None,
                        prompt_style=prompt_style
                    ): task for task in batch
                }

                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        translated_chunk = future.result()
                        if translated_chunk:
                            translated_chunks.append(translated_chunk)
                        else:
                            logging.warning(f"Empty translation result for chunk {task.filename}")
                    except Exception as e:
                        logging.error(f"Error translating chunk {task.filename}: {str(e)}")

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

            batch_index += 1

        if self._stop_requested:
            logging.info("Chunk translation cancelled.")

        return translated_chunks

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
                error_msg = f"exceeds_chinese ({ratio:.2f}%)"
                self.progress_tracker.mark_translation_failed(task.filename, error_msg, progress_data)
                
        except Exception as e:
            logging.error("Error processing Chinese retry for %s: %s", task.filename, str(e))
            self.progress_tracker.mark_task_as_retried(task.filename, progress_data)
            if not ("429" in str(e) or "504" in str(e)):
                self.progress_tracker.mark_translation_failed(task.filename, str(e).lower(), progress_data)

