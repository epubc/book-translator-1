import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union

from PyQt5.QtCore import QThread, pyqtSignal

from logger.logging_utils import configure_logging
from translator.core import Translator
from translator.file_handler import FileHandler, FileSplitter
from downloader.factory import DownloaderFactory
from config.models import get_model_config
from core.history_manager import HistoryManager


@dataclass
class BookInfo:
    title: str
    author: str
    cover_img: Optional[str] = None


class TranslationThread(QThread):
    update_log = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    stage_update = pyqtSignal(str)

    def __init__(self, params: Dict[str, Any]):
        super().__init__()
        self.params = params
        self._is_running = True
        self.downloader = None
        self.file_handler = None
        self.translator = None

    def _initialize_process(self) -> None:
        """Initialize the translation process with progress updates."""
        self.stage_update.emit("Initializing...")
        self.update_progress.emit(5)

    def _handle_web_task(self) -> tuple[BookInfo, Path]:
        """Handle web-based translation tasks."""
        output_dir = Path(self.params['output_directory'])
        start_chapter = self.params.get('start_chapter')
        end_chapter = self.params.get('end_chapter')
        book_url = self.params['book_url']

        self.stage_update.emit("Creating downloader...")
        self.downloader = DownloaderFactory.create_downloader(
            url=book_url,
            output_dir=output_dir,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
        )

        if not self._is_running:
            raise InterruptedError("Translation stopped by user")

        book_info = self.downloader.book_info
        book_dir = self.downloader.book_dir

        configure_logging(book_dir)

        # Update history with book info before downloading chapters
        self._update_task_history(book_info, book_dir)

        self.stage_update.emit("Downloading chapters...")
        self.downloader.download_book()

        return book_info, book_dir

    def _handle_file_task(self) -> tuple[BookInfo, Path]:
        """Handle file-based translation tasks."""
        output_dir = Path(self.params['output_directory'])
        start_chapter = self.params.get('start_chapter')
        end_chapter = self.params.get('end_chapter')
        file_path = self.params['file_path']
        book_title = self.params['book_title']
        book_author = self.params['author']

        book_dir = output_dir / self._sanitize_filename(book_title)
        book_dir.mkdir(parents=True, exist_ok=True)

        configure_logging(book_dir)

        self.stage_update.emit("Splitting file into chapters...")
        splitter = FileSplitter(file_path, book_dir)
        splitter.split_chapters()

        book_info = BookInfo(title=book_title, author=book_author)

        # Update history with book info immediately
        self._update_task_history(book_info, book_dir)

        return book_info, book_dir

    # Remove the _update_task_history call from the run() method
    def run(self) -> None:
        try:
            self._initialize_process()

            if not self._is_running:
                return

            # Process based on task type
            if self.params.get('task_type') == 'web':
                book_info, book_dir = self._handle_web_task()
            elif self.params.get('task_type') == 'file':
                book_info, book_dir = self._handle_file_task()
            else:
                raise ValueError("Invalid task_type")

            if not self._is_running:
                return

            # Execute translation process
            epub_path = self._execute_translation_process(book_dir, book_info)

            self.update_progress.emit(100)
            self.finished.emit(True, str(epub_path))

        except Exception as e:
            logging.exception("An error occurred during translation:")
            self.update_log.emit(f"Error: {e}")
            self.finished.emit(False, "")
        finally:
            self._cleanup()

    def _update_task_history(self, book_info: BookInfo, book_dir: Path = None) -> None:
        """Update the task history if a task ID is provided."""
        if 'task_id' in self.params:
            update_data = {
                "book_title": book_info.title,
                "author": book_info.author
            }
            
            # Add book_dir to history if provided
            if book_dir:
                update_data["book_dir"] = str(book_dir)
                
            HistoryManager.update_task(self.params['task_id'], update_data)

    def _execute_translation_process(self, book_dir: Path, book_info: BookInfo) -> Path:
        """Execute the main translation process workflow."""
        start_chapter = self.params.get('start_chapter')
        end_chapter = self.params.get('end_chapter')
        model_config = get_model_config(self.params['model_name'])

        # Update task history with book_dir (in case it wasn't already added)
        if 'task_id' in self.params:
            HistoryManager.update_task(self.params['task_id'], {
                "book_dir": str(book_dir)
            })

        # Initialize handlers
        self.stage_update.emit("Preparing file handler...")
        self.file_handler = FileHandler(
            book_dir=book_dir,
            start_chapter=start_chapter,
            end_chapter=end_chapter
        )

        self.translator = Translator(
            model_config=model_config,
            file_handler=self.file_handler
        )

        # Create prompts
        self.stage_update.emit("Creating prompts...")
        self.update_progress.emit(50)
        if not self._is_running:
            raise InterruptedError("Translation stopped by user")

        self.file_handler.create_prompt_files_from_chapters(
            start_chapter=start_chapter,
            end_chapter=end_chapter
        )

        # Translate content
        self.stage_update.emit("Translating content...")
        self.update_progress.emit(75)
        if not self._is_running:
            raise InterruptedError("Translation stopped by user")

        self.translator.process_book_translation(
            prompt_style=self.params['prompt_style'],
            start_chapter=start_chapter,
            end_chapter=end_chapter
        )

        # Generate EPUB
        self.stage_update.emit("Generating EPUB...")
        self.update_progress.emit(95)
        if not self._is_running:
            raise InterruptedError("Translation stopped by user")

        epub_path = self.file_handler.generate_epub(
            book_info.title,
            book_info.author,
            book_info.cover_img
        )

        self.update_log.emit(f"EPUB generated at: {epub_path}")
        return epub_path

    def stop(self) -> None:
        """Stop the translation process safely."""
        self._is_running = False

        if self.downloader:
            self.downloader.stop()
        if self.translator:
            self.translator.stop()

        if not self.wait(2000):  # Wait 2 seconds for thread to finish
            self.terminate()  # Force termination if not finished
            self.update_log.emit("Process terminated.")
        else:
            self.update_log.emit("Process stopped gracefully.")


    def _cleanup(self) -> None:
        """Clean up resources after the process is complete."""
        self._is_running = False
        self.downloader = None
        self.file_handler = None
        self.translator = None

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize filename by removing or replacing invalid characters."""
        return filename.replace('/', '_').replace('\\', '_')
