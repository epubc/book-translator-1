import logging
from PyQt5.QtCore import QThread, pyqtSignal
from translator.core import Translator
from translator.file_handler import FileHandler, FileSplitter
from downloader.factory import DownloaderFactory
from config.models import get_model_config
from core.history_manager import HistoryManager
from pathlib import Path

class TranslationThread(QThread):
    update_log = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    stage_update = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self._is_running = True
        self.downloader = None
        self.file_handler = None
        self.translator = None

    def run(self):
        try:
            self.stage_update.emit("Initializing...")
            self.update_progress.emit(5)

            output_dir = Path(self.params['output_directory'])
            start_chapter = self.params.get('start_chapter')
            end_chapter = self.params.get('end_chapter')
            model_config = get_model_config(self.params['model_name'])

            if self.params.get('task_type') == 'web':
                book_url = self.params['book_url']
                self.stage_update.emit("Creating downloader...")
                self.downloader = DownloaderFactory.create_downloader(
                    url=book_url,
                    output_dir=output_dir,
                    start_chapter=start_chapter,
                    end_chapter=end_chapter,
                )
                if not self._is_running:
                    return
                book_info = self.downloader.book_info
                book_dir = self.downloader.book_dir
                self.stage_update.emit("Downloading chapters...")
                self.downloader.download_book()
            elif self.params.get('task_type') == 'file':
                file_path = self.params['file_path']
                book_title = self.params['book_title']
                book_author = self.params['book_author']
                book_dir = output_dir / book_title.replace('/', '_').replace('\\', '_')
                book_dir.mkdir(parents=True, exist_ok=True)
                self.stage_update.emit("Splitting file into chapters...")
                splitter = FileSplitter(file_path, book_dir)
                splitter.split_chapters()
                book_info = type('BookInfo', (), {'title': book_title, 'author': book_author, 'cover_img': None})()
            else:
                raise ValueError("Invalid task_type")

            if 'task_id' in self.params:
                HistoryManager.update_task(self.params['task_id'], {"book_title": book_info.title})

            from logger.logging_utils import configure_logging
            configure_logging(book_dir, start_chapter=start_chapter, end_chapter=end_chapter)

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

            self.stage_update.emit("Creating prompts...")
            self.update_progress.emit(50)
            if not self._is_running:
                return
            self.file_handler.create_prompt_files_from_chapters(start_chapter=start_chapter, end_chapter=end_chapter)

            self.stage_update.emit("Translating content...")
            self.update_progress.emit(75)
            if not self._is_running:
                return
            self.translator.process_book_translation(
                prompt_style=self.params['prompt_style'],
                start_chapter=start_chapter,
                end_chapter=end_chapter
            )

            self.stage_update.emit("Generating EPUB...")
            self.update_progress.emit(95)
            if not self._is_running:
                return
            epub_path = self.file_handler.generate_epub(book_info.title, book_info.author, book_info.cover_img)
            self.update_log.emit(f"EPUB generated at: {epub_path}")

            self.update_progress.emit(100)
            self.finished.emit(True, str(epub_path))

        except Exception as e:
            logging.exception("An error occurred during translation:")
            self.update_log.emit(f"Error: {e}")
            self.finished.emit(False, "")
        finally:
            self._is_running = False
            self.downloader = None
            self.file_handler = None
            self.translator = None

    def stop(self):
        self._is_running = False
        if self.translator:
            self.translator.stop()
        self.update_log.emit("Stopping process...")
        self.wait(1000)
        if self.isRunning():
            self.terminate()
            self.update_log.emit("Process terminated.")
        else:
            self.update_log.emit("Process stopped cleanly.")
