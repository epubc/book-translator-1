import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import re

from epub.generator import EPUBGenerator
from logger import logging_utils
from translator import text_processing
from config import settings
from translator.helper import is_in_chapter_range, generate_chapter_suffix
from translator.text_processing import get_unique_names_from_text, add_underscore


class FileHandler:
    """Handles file operations: creation, loading, saving, path management."""

    def __init__(self, book_dir: Path, start_chapter: Optional[int], end_chapter: Optional[int]):
        self.book_dir = book_dir
        self.chapter_suffix =  generate_chapter_suffix(start=start_chapter, end=end_chapter)
        self._ensure_directory_structure()


    def _ensure_directory_structure(self) -> None:
        """Create necessary directories if they don't exist."""
        for key in ["prompt_files", "translation_responses", "translated_chapters", "epub"]:
            dir_path = self.get_path(key)
            dir_path.mkdir(parents=True, exist_ok=True)


    def get_progress_path(self) -> Path:
        return self.book_dir / f"progress{self.chapter_suffix}.json"

    def get_log_path(self) -> Path:
        return self.book_dir / f"translation_log{self.chapter_suffix}.log"


    def get_path(self, key: str) -> Path:
        """Retrieve a path object for a given key."""
        return self.book_dir.joinpath(key)


    def list_files_in_dir(self, dir_path: Path, pattern: str = '*') -> List[Path]:
        """List files in a subdirectory based on a glob pattern."""
        if not dir_path.is_dir():
            logging.warning(f"Directory not found: {dir_path}")
            return []
        return list(dir_path.glob(pattern))


    def delete_file(self, filename: str, sub_dir_key: str) -> bool:
        """Delete a specific file, return True if successful, False otherwise."""
        file_path = self.get_path(sub_dir_key) / filename
        if file_path.exists() and file_path.is_file():
            try:
                file_path.unlink() # More modern and Pathlib-centric way to delete
                logging.info(f"Deleted file: {filename}")
                return True
            except Exception as e:
                logging_utils.log_exception(e, f"Error deleting file: {file_path}")
                return False
        else:
            logging.warning(f"File not found, cannot delete: {file_path}")
            return False


    def _initiate_progress(self) -> Dict:
        """Initialize a new progress dictionary."""
        return {
            "last_batch_time": 0,
            "last_batch_size": 0,
        }


    def load_progress(self) -> Dict:
        """Load and return progress data from progress.json, initialize if not exists."""
        progress_file_path = self.get_progress_path()
        try:
            return json.loads(progress_file_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            logging.info("Progress file not found, initializing new progress.")
            return self._initiate_progress() # Initialize progress if file doesn't exist
        except json.JSONDecodeError:
            logging.error("Progress file is corrupt, re-initializing.")
            return self._initiate_progress() # Re-initialize if JSON is corrupt
        except Exception as e:
            logging_utils.log_exception(e, "Error loading progress file.")
            return self._initiate_progress() # Fallback to new progress on any error


    def save_progress(self, progress_data: Dict) -> None:
        """Save progress data to progress.json."""
        progress_file_path = self.get_progress_path()
        try:
            progress_file_path.write_text(json.dumps(progress_data, indent=4), encoding='utf-8')
            logging.debug("Progress saved successfully.") # Debug level - frequent operation
        except Exception as e:
            logging_utils.log_exception(e, "Error saving progress to file.")

    def save_content_to_file(self, content: str, filename: str, sub_dir_key: str) -> Path:
        """Save content to a file within a specified subdirectory, return Path."""
        file_path = self.get_path(sub_dir_key) / filename
        try:
            file_path.write_text(content, encoding='utf-8')
            logging.debug(f"File saved: {file_path}") # Debug level logging
            return file_path
        except Exception as e:
            logging_utils.log_exception(e, f"Error saving file: {file_path}")
            raise # Re-raise exception after logging


    def load_content_from_file(self, filename: str, sub_dir_key: str) -> Optional[str]:
        """Load content from a file, return None if file not found or error."""
        file_path = self.get_path(sub_dir_key) / filename
        try:
            return file_path.read_text(encoding='utf-8')
        except FileNotFoundError:
            logging.warning(f"File not found: {file_path}") # Warning, not error
            return None
        except Exception as e:
            logging_utils.log_exception(e, f"Error reading file: {file_path}")
            return None


    def is_translation_complete(self, start_chapter: Optional[int] = None, end_chapter: Optional[int] = None) -> bool:
        """Check if all expected translations in specified chapter range are completed."""
        prompts_dir = self.get_path("prompt_files")
        responses_dir = self.get_path("translation_responses")

        # Generate display strings for logging
        start_str = str(start_chapter) if start_chapter is not None else 'begin'
        end_str = str(end_chapter) if end_chapter is not None else 'end'

        # Get filtered prompts and responses
        prompt_files = {
            p.stem for p in prompts_dir.glob("*.txt")
            if is_in_chapter_range(p.name, start_chapter, end_chapter)
        }

        response_files = {
            r.stem
            for r in responses_dir.glob("*.txt")
            if is_in_chapter_range(r.name, start_chapter, end_chapter)
        }

        untranslated_prompts = prompt_files - response_files
        if untranslated_prompts:
            logging.info(f"Remaining translations in chapters {start_str}-{end_str}: {len(untranslated_prompts)}")
            return False

        logging.info(f"All translations completed for chapters {start_str}-{end_str}")
        return True


    def combine_chapter_translations(self) -> None:
        """Combines translated prompt files for each chapter (in book_dir)."""
        translated_responses_dir = self.get_path("translation_responses")
        translated_chapters_dir = self.get_path("translated_chapters")

        response_files = translated_responses_dir.glob("*.txt")

        chapter_files = {}
        for filename in response_files:
            match = re.match(r"(.*)_\d+\.txt", filename.name)
            if match:
                chapter_name = match.group(1)
                if chapter_name not in chapter_files:
                    chapter_files[chapter_name] = []
                chapter_files[chapter_name].append(filename)

        # Combine files for each chapter
        for chapter_name in sorted(chapter_files.keys()):
            # Optionally, sort the files for each chapter
            files = sorted(chapter_files[chapter_name])

            # Use the translated_chapters_dir that we got earlier
            output_path = translated_chapters_dir / f"{chapter_name}.txt"
            try:
                with open(output_path, "w", encoding="utf-8") as outfile:
                    for file_path in files:
                        try:
                            # file_path is already a Path object
                            with open(file_path, "r", encoding="utf-8") as infile:
                                content = infile.read()
                                outfile.write(content + "\n")  # Add newline between prompts
                        except Exception as e:
                            logging.error(f"Error reading file {file_path}: {e}")
                    logging.info(f"Combined chapter translation: {chapter_name}")
            except OSError as e:
                logging.error(f"Error writing to {output_path}: {e}")

        logging.info("Combine chapter translations complete")


    def create_prompt_files_from_chapters(self) -> None:
        """Create prompt files from downloaded chapters, return count of prompts created."""
        download_dir = self.get_path("downloaded_chapters")
        prompt_count = 0

        chapter_files = self.list_files_in_dir(download_dir, "*.txt")
        if not chapter_files:
            logging.warning(f"No chapter files found in: {download_dir}")
            return

        for chapter_file in chapter_files:
            chapter_text = self.load_content_from_file(chapter_file.name, "downloaded_chapters")
            if chapter_text:
                prompts = text_processing.split_text_into_chunks(chapter_text, settings.MAX_TOKENS_PER_PROMPT)
                for idx, prompt_text in enumerate(prompts):
                    prompt_filename = f"{chapter_file.stem}_{idx + 1}.txt" # chapter_0001_1.txt, chapter_0001_2.txt, etc.
                    self.save_content_to_file(add_underscore(prompt_text), prompt_filename, "prompt_files")
                    prompt_count += 1
        logging.info(f"Created {prompt_count} prompt files from downloaded chapters.")
        return


    def load_prompt_file_content(self, prompt_filename: str) -> Optional[str]:
        """Load content of a prompt file, return None if not found."""
        return self.load_content_from_file(prompt_filename, "prompt_files")


    def delete_invalid_translations(self) -> int:
        """Deletes very short translation files, likely errors, returns count deleted."""
        responses_dir = self.get_path("translation_responses")
        deleted_count = 0
        files_to_check = self.list_files_in_dir(responses_dir, "*.txt")

        for file_path in files_to_check:
            content = self.load_content_from_file(file_path.name, "translation_responses")
            reasons = []

            # Check 1: Short content (<=1 line)
            if len(content.splitlines()) <= 1:
                reasons.append("Short content")

            # Check 2: Repeated words (20+ consecutive repeats)
            if re.search(r'(\b\w+\b)(\W+\1){20,}', content, flags=re.IGNORECASE):
                reasons.append("Repeated words")

            # Check 3: Repeated special characters (100+ consecutive)
            if re.search(r'[_\-=]{100,}', content):
                reasons.append("Repeated special characters")

            if reasons:
                if self.delete_file(file_path.name, "translation_responses"):
                    deleted_count += 1
                    logging.warning(f"Deleted likely invalid translation: {file_path.name} (Short content).")
        if deleted_count > 0:
            logging.info(f"Deleted {deleted_count} potentially invalid translation files.")
        else:
            logging.info("No invalid translation files found.")
        return deleted_count

    def _process_text_file_for_names(self, filepath: Path) -> Optional[dict[str, int]]:
        """Process text file, extract names, handle encoding, return counts."""
        try:
            text = filepath.read_text(encoding='utf-8')
            return get_unique_names_from_text(text)
        except FileNotFoundError:
            logging.error(f"File not found: {filepath}")
            return None
        except Exception as e:
            logging_utils.log_exception(e, f"Error processing file for names: {filepath}")
            return None


    def _count_names_in_directory(self, directory_path: Path) -> dict[str, int]:
        """Process all translated text files in directory, aggregate name counts."""
        all_name_counts: dict[str, int] = {}
        if not directory_path.is_dir():
            logging.warning(f"Directory not found: {directory_path}")
            return all_name_counts

        for filepath in directory_path.glob('*.txt'):
            name_counts = self._process_text_file_for_names(filepath)
            if name_counts:
                for name, count in name_counts.items():
                    all_name_counts[name] = all_name_counts.get(name, 0) + count
        return {key: value for key, value in all_name_counts.items() if value>=10}


    def extract_and_count_names(self) -> None:
        """Orchestrates name extraction, counting, and saving."""
        logging.info("Starting name extraction and counting...")
        responses_dir = self.book_dir / "translation_responses"
        aggregated_names = self._count_names_in_directory(responses_dir)

        if aggregated_names:
            sorted_names = sorted(aggregated_names.items(), key=lambda item: item[1], reverse=True)
            sorted_names_dict = dict(sorted_names)
            output_path = self.book_dir / "names.json"
            try:
                output_path.write_text(json.dumps(sorted_names_dict, indent=4, ensure_ascii=False), encoding='utf-8')
                logging.info(f"Saved sorted names to: {output_path}")
            except Exception as e:
                logging_utils.log_exception(e, f"Error saving sorted names to JSON: {output_path}")
        else:
            logging.warning("No names found to extract.")


    def load_and_convert_names_to_string(self) -> Optional[str]:
        """Load names from JSON, format to string for instructions."""
        json_path = self.book_dir / "names.json"
        try:
            data = json.loads(json_path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                logging.error(f"JSON file does not contain a dictionary: {json_path}")
                return
            output_string = ""
            for name, count in data.items():
                output_string += f"{name} - {count}\n"
            return output_string
        except FileNotFoundError:
            logging.debug(f"File not found: {json_path}")
            return
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON format in file: {json_path}")
            return
        except Exception as e:
            logging_utils.log_exception(e, f"Error loading or converting names from JSON: {json_path}")
            return


    def generate_epub(self, book_title: str, book_author: str) -> Optional[Path]:
        """Generate EPUB from combined translations, return path to EPUB or None on failure."""
        translated_chapters_dir = self.get_path("translated_chapters")
        chapter_files = sorted(translated_chapters_dir.glob("*.txt"))

        if not chapter_files:
            logging.warning("No translated files found to create EPUB.")
            return

        output_filepath = self.get_path("epub") / f"{book_title}.epub"

        epub_generator = EPUBGenerator() # Instantiate generator
        try:
            epub_generator.create_epub_from_txt_files(
                chapter_files,
                book_title,
                book_author,
                output_filepath,
                language="vi",
                toc_title="Mục Lục"
            )
            logging.info(f"EPUB file created: {output_filepath}")
            return output_filepath
        except Exception as e:
            logging_utils.log_exception(e, "EPUB generation failed.")
            return None
