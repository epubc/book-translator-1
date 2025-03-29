import json
import logging
import re
import time
from threading import Lock
from pathlib import Path
from typing import Dict, Optional

from config import settings
from epub.generator import EPUBGenerator
from logger import logging_utils
from text_processing import text_processing
from translator.helper import sanitize_path_name
from file_operations import (
    file_io,
    json_operations,
)
from translator import chapter_operations


class FileHandler:
    """Handles file operations: creation, loading, saving, path management."""

    def __init__(self, book_dir: Path):
        self.book_dir = book_dir
        self._ensure_directory_structure()
        self._progress_lock = Lock()  # Lock for progress file operations

    def _ensure_directory_structure(self) -> None:
        """Create necessary directories if they don't exist."""
        for key in ["prompt_files", "translation_responses", "translated_chapters", "epub"]:
            dir_path = self.get_path(key)
            dir_path.mkdir(parents=True, exist_ok=True)

    def _get_progress_path(self) -> Path:
        """Return path to progress.json file"""
        return self.book_dir / "progress.json"

    def get_path(self, key: str) -> Path:
        """Retrieve a path object for a given key."""
        return self.book_dir.joinpath(key)

    def delete_file(self, filename: str, sub_dir_key: str) -> bool:
        """Delete a specific file, return True if successful, False otherwise."""
        return file_io.delete_file(self.get_path(sub_dir_key) / filename)

    def load_progress(self) -> Dict:
        """Load and return progress data from progress.json, initialize if not exists."""
        progress_file_path = self._get_progress_path()

        with self._progress_lock:
            return json_operations.load_progress_file(progress_file_path)

    def save_progress(self, progress_data: Dict) -> None:
        """Save progress data to progress.json with proper locking."""
        progress_file_path = self._get_progress_path()

        with self._progress_lock:
            json_operations.save_progress_file(progress_file_path, progress_data)

    def save_content_to_file(self, content: str, filename: str, sub_dir_key: str) -> Path:
        """Save content to a file within a specified subdirectory, return Path."""
        file_path = self.get_path(sub_dir_key) / filename
        return file_io.save_content_to_file(content, file_path)

    def load_content_from_file(self, filename: str, sub_dir_key: str) -> Optional[str]:
        """Load content from a file, return None if file not found or error."""
        file_path = self.get_path(sub_dir_key) / filename
        return file_io.load_content_from_file(file_path)

    def is_translation_complete(self, start_chapter: Optional[int] = None, end_chapter: Optional[int] = None) -> bool:
        """Check if all expected translations in specified chapter range are completed."""
        return chapter_operations.is_translation_complete(
            self.get_path("prompt_files"),
            self.get_path("translation_responses"),
            self.load_progress(),
            start_chapter,
            end_chapter
        )

    def combine_chapter_translations(self, start_chapter: Optional[int] = None,
                                     end_chapter: Optional[int] = None) -> None:
        """Combines translated prompt files for each chapter."""
        chapter_operations.combine_translations(
            self.get_path("translation_responses"),
            self.get_path("translated_chapters"),
            start_chapter,
            end_chapter
        )

    def create_prompt_files_from_chapters(self, start_chapter: Optional[int] = None,
                                          end_chapter: Optional[int] = None) -> None:
        """Create prompt files from downloaded chapters, but only for chapters without existing prompt files."""
        chapter_operations.create_prompt_files(
            self.get_path("input_chapters"),
            self.get_path("prompt_files"),
            self.load_content_from_file,
            self.save_content_to_file,
            start_chapter,
            end_chapter
        )

    def load_prompt_file_content(self, prompt_filename: str) -> Optional[str]:
        """Load content of a prompt file, return None if not found."""
        return self.load_content_from_file(prompt_filename, "prompt_files")

    def delete_invalid_translations(self) -> int:
        """Deletes very short translation files, likely errors, returns count deleted."""
        deleted_count = 0
        responses_dir = self.get_path("translation_responses")
        files_to_check = responses_dir.glob("*.txt")

        for file_path in files_to_check:
            try:
                content = self.load_content_from_file(file_path.name, "translation_responses")
                if content is None:  # File couldn't be read
                    if self.delete_file(file_path.name, "translation_responses"):
                        deleted_count += 1
                        logging.warning(f"Deleted unreadable translation: {file_path.name}")
                    continue
                if '[TRANSLATION FAILED]' in content:
                    continue

                original_content = self.load_content_from_file(file_path.name, "prompt_files")
                if original_content is None:  # No corresponding prompt file
                    if self.delete_file(file_path.name, "translation_responses"):
                        deleted_count += 1
                        logging.warning(f"Deleted translation with no prompt: {file_path.name}")
                    continue

                reasons = []

                # Check 1: Short content (<=1 line)
                if len(content.splitlines()) <= 1 < len(original_content.splitlines()):
                    reasons.append("Short content")

                # Check 2: Repeated words (20+ consecutive repeats)
                if re.search(r'(\b\w+\b)(\W+\1){20,}', content, flags=re.IGNORECASE):
                    reasons.append("Repeated words")

                # Check 3: Repeated special characters (100+ consecutive)
                if re.search(r'[_\-=]{100,}', content):
                    reasons.append("Repeated special characters")

                # Check 4: Very low content to prompt ratio
                if len(content) < len(original_content) * 0.3 and len(content.splitlines()) < len(
                        original_content.splitlines()) * 0.5:
                    reasons.append("Suspicious length ratio")

                if reasons:
                    if self.delete_file(file_path.name, "translation_responses"):
                        deleted_count += 1
                        logging.warning(
                            f"Deleted likely invalid translation: {file_path.name} (Reasons: {', '.join(reasons)}).")
            except Exception as e:
                logging.error(f"Error checking translation file {file_path.name}: {str(e)}")
                # If we can't process the file, it's safer to delete it
                if self.delete_file(file_path.name, "translation_responses"):
                    deleted_count += 1
                    logging.warning(f"Deleted problematic translation file: {file_path.name}")

        if deleted_count > 0:
            logging.info(f"Deleted {deleted_count} potentially invalid translation files.")
        else:
            logging.info("No invalid translation files found.")
        return deleted_count

    def extract_chinese_sentences_to_file(self) -> [bool, Optional[Path]]:
        """
        Extract all Chinese sentences from all translation response files and save them to a JSON file.

        Returns:
            Path to the created Chinese sentences file, or None on failure
        """
        logging.info("Extracting Chinese sentences from translation responses...")

        translation_dir = self.get_path("translation_responses")
        translation_files = list(translation_dir.glob("*.txt"))

        if not translation_files:
            logging.warning("No translation files found for Chinese sentence extraction.")
            return None

        chinese_sentences = set()
        for file_path in translation_files:
            try:
                content = self.load_content_from_file(
                    file_path.name,
                    "translation_responses" if file_path in translation_files else "translated_chapters",
                )
                if content:
                    sentences = text_processing.extract_chinese_sentences(content)
                    for sentence in sentences:
                        chinese_sentences.add(sentence)
            except Exception as e:
                logging.error(f"Error extracting Chinese sentences from {file_path.name}: {str(e)}")

        if not chinese_sentences:
            logging.info("No Chinese sentences found in translation files.")
            return False, None

        output_filepath = self.book_dir / "chinese_sentences.json"

        try:
            from translator.manager import TranslationManager
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from text_processing.text_processing import split_text_into_chunks
            import json
            from config.models import GEMINI_FLASH_LITE_MODEL_CONFIG
            from config.prompts import PromptStyle

            translator = TranslationManager(
                model_config=GEMINI_FLASH_LITE_MODEL_CONFIG,
                file_handler=self
            )

            # Split the text into chunks
            raw_text = '\n'.join(chinese_sentences)
            chunks = split_text_into_chunks(raw_text, chunk_size=settings.MAX_TOKENS_PER_PROMPT)

            if not chunks:
                logging.error("Failed to split text into chunks")
                return False, None

            logging.info(f"Split text into {len(chunks)} chunks for parallel processing")

            translated_chunks = translator.translate_chunk(chunks, prompt_style=PromptStyle.Sentences)

            if not translated_chunks:
                logging.error("No chunks were successfully translated")
                return False, None

            result = {}
            for translated_chunk in translated_chunks:
                translated_chunk = translated_chunk.replace("```", "").replace("json", "").strip()
                try:
                    json_result = json.loads(translated_chunk)
                except json.JSONDecodeError:
                    logging.error(f"Failed to parse JSON from translation response: {translated_chunk}")
                    return False, None
                result.update(json_result)

            for key, value in result.items():
                if key and key[0].isupper():
                    continue
                words = value.split()
                if len(words) < 2:
                    continue
                first_word, second_word = words[0], words[1]
                if first_word[0].isupper() and second_word[0].isupper():
                    continue
                value = value[0].lower() + value[1:]
                if value[-1] == ".":
                    value = value[:-1]
                result[key] = value

            # Save to file
            with open(output_filepath, "w", encoding="utf-8") as outfile:
                json.dump(result, outfile, ensure_ascii=False, indent=2)

            logging.info(f"Chinese sentences extracted and translated to: {output_filepath}")
            return True, output_filepath

        except Exception as e:
            logging.error(f"Error translating batch of Chinese sentences: {str(e)}")
            return False, None

    def replace_chinese_sentences_in_translation_responses(self, has_chinese: bool) -> int:
        """
        Replace Chinese sentences in all translated chapter files with their Vietnamese translations.
        Uses the previously created chinese_sentences.json mapping.

        Returns:
            Number of files processed
        """

        if not has_chinese:
            logging.warning("No Chinese sentences in translation. Skipping replacement.")
            return 0

        chinese_sentences_file = self.book_dir / "chinese_sentences.json"
        if not chinese_sentences_file.exists():
            logging.warning("Chinese sentences mapping file not found. Skipping replacement.")
            return 0

        try:
            # Load the Chinese-Vietnamese mapping
            with open(chinese_sentences_file, "r", encoding="utf-8") as f:
                chinese_vietnamese_map = json.load(f)

            if not chinese_vietnamese_map:
                logging.warning("Chinese sentences mapping is empty. Skipping replacement.")
                return 0

            logging.info(f"Loaded {len(chinese_vietnamese_map)} Chinese-Vietnamese word mappings")

            # Process all chapter files
            translated_responses_dir = self.get_path("translation_responses")
            translated_files = list(translated_responses_dir.glob("*.txt"))

            if not translated_files:
                logging.warning("No translated response files found to process.")
                return 0

            files_processed = 0
            for file_path in translated_files:
                try:
                    # Read the file content
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Replace Chinese sentences with Vietnamese translations
                    updated_content = text_processing.replace_text_segments(content, chinese_vietnamese_map)

                    # Write back the updated content
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)

                    files_processed += 1

                except Exception as e:
                    logging.error(f"Error processing file {file_path.name}: {str(e)}")

            logging.info(f"Replaced Chinese sentences in {files_processed} translated response files")
            return files_processed

        except Exception as e:
            logging.error(f"Error during Chinese sentence replacement: {str(e)}")
            return 0


    def generate_epub(self, book_title: str, book_author: str, cover_image: str) -> Optional[Path]:
        """Generate EPUB from combined translations, return path to EPUB or None on failure."""
        translated_chapters_dir = self.get_path("translated_chapters")
        chapter_files = sorted(translated_chapters_dir.glob("*.txt"))

        if not chapter_files:
            logging.warning("No translated files found to create EPUB.")
            return None

        book_title = sanitize_path_name(book_title)
        output_filepath = self.get_path("epub") / f"{book_title}.epub"

        try:
            epub_generator = EPUBGenerator()
            epub_generator.create_epub_from_txt_files(
                chapter_files,
                title=book_title,
                author=book_author,
                cover_image=cover_image,
                output_filepath=output_filepath,
                language="vi",
                toc_title="Mục Lục"
            )
            logging.info(f"EPUB file created: {output_filepath}")
            return output_filepath
        except Exception as e:
            logging_utils.log_exception(e, "EPUB generation failed.")
            return None

    def get_chapter_status(self, start_chapter: Optional[int] = None, end_chapter: Optional[int] = None) -> Dict[
        str, Dict[str, any]]:
        """Get status information for all chapters in the specified range."""
        return chapter_operations.get_chapters_status(
            self.get_path("prompt_files"),
            self.get_path("translation_responses"),
            self.load_progress,
            self.load_content_from_file,
            start_chapter,
            end_chapter
        )
