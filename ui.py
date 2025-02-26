import logging
import sys
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox, QFileDialog,
                             QDialog, QFormLayout, QTextEdit, QMessageBox, QProgressBar)
from PyQt5.QtCore import Qt, QSettings, QThread, pyqtSignal, pyqtSlot, QObject
from PyQt5.QtGui import QFont, QTextCursor

from logger import logging_utils
from translator.core import Translator
from translator.file_handler import FileHandler
from downloader.factory import DownloaderFactory
from config.models import get_model_config


# ======================
# Custom Log Handler
# ======================
class QTextEditLogHandler(QObject, logging.Handler):
    log_signal = pyqtSignal(str)

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        self.setFormatter(formatter)

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)


# ======================
# Thread Workers
# ======================
class TranslationThread(QThread):
    update_log = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    finished = pyqtSignal(bool)
    stage_update = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self._is_running = True

    def run(self):
        try:
            self.stage_update.emit("Initializing...")
            self.update_progress.emit(5)

            book_url = self.params['book_url']
            output_dir = Path(self.params['output_directory'])

            self.stage_update.emit("Creating downloader...")
            downloader = DownloaderFactory.create_downloader(url=book_url, output_dir=output_dir)
            book_info = downloader.book_info
            book_dir = downloader.book_dir

            start_chapter = self.params['start_chapter']
            end_chapter = self.params['end_chapter']
            model_config = get_model_config(self.params['model_name'])

            logging_utils.configure_logging(
                book_dir,
                start_chapter=start_chapter,
                end_chapter=end_chapter
            )

            self.stage_update.emit("Preparing file handler...")
            file_handler = FileHandler(
                book_dir=book_dir,
                start_chapter=start_chapter,
                end_chapter=end_chapter
            )
            translator = Translator(
                model_config=model_config,
                file_handler=file_handler
            )

            # Stage 1: Download
            self.stage_update.emit("Downloading chapters")
            self.update_progress.emit(25)
            if not self._is_running:
                return
            downloader.download_book()

            # Stage 2: Create prompts
            self.stage_update.emit("Creating prompts")
            self.update_progress.emit(50)
            if not self._is_running:
                return
            file_handler.create_prompt_files_from_chapters()

            # Stage 3: Translate
            self.stage_update.emit("Translating content")
            self.update_progress.emit(75)
            if not self._is_running:
                return
            translator.process_translation(
                start_chapter=start_chapter,
                end_chapter=end_chapter,
                prompt_style=self.params['prompt_style']
            )

            # Stage 4: Generate EPUB
            self.stage_update.emit("Generating EPUB")
            self.update_progress.emit(95)
            if not self._is_running:
                return
            epub_path = file_handler.generate_epub(book_info.title, book_info.author)
            self.update_log.emit(f"EPUB generated at: {epub_path}")

            self.update_progress.emit(100)
            self.finished.emit(True)
        except Exception as e:
            logging.error(str(e))
            self.finished.emit(False)
        finally:
            self._is_running = False

    def stop(self):
        self._is_running = False
        self.terminate()


# ======================
# Configuration Dialogs
# ======================
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.setFixedSize(400, 200)
        self.init_ui()
        self.setWindowModality(Qt.ApplicationModal)  # Prevent interaction with main window


    def init_ui(self):
        layout = QVBoxLayout()

        # API Key Section
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter Gemini API Key")
        self.api_key_edit.setEchoMode(QLineEdit.Password)

        form_layout = QFormLayout()
        form_layout.addRow("Gemini API Key:", self.api_key_edit)

        # Load existing settings
        self.load_settings()

        # Buttons
        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)

        layout.addLayout(form_layout)
        layout.addLayout(btn_box)
        self.setLayout(layout)

    def load_settings(self):
        settings = QSettings("NovelTranslator", "Config")
        self.api_key_edit.setText(settings.value("APIKey", ""))

    def save_settings(self):
        settings = QSettings("NovelTranslator", "Config")
        settings.setValue("APIKey", self.api_key_edit.text())
        QMessageBox.information(self, "Success", "Settings saved successfully!")
        self.accept()


# ======================
# Translation Dialog
# ======================
class TranslationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translate from URL")
        self.setMinimumSize(600, 400)
        self.thread = None
        self.log_handler = None
        self.init_ui()
        self.setup_logging()

    def setup_logging(self):
        self.log_handler = QTextEditLogHandler()
        self.log_handler.log_signal.connect(self.handle_log_message)
        logging.root.addHandler(self.log_handler)

    def handle_log_message(self, message):
        self.log_area.moveCursor(QTextCursor.End)
        self.log_area.insertPlainText(message + '\n')
        self.log_area.ensureCursorVisible()

    def init_ui(self):
        layout = QVBoxLayout()

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.stage_label = QLabel("Current Stage: Idle")

        # URL Input and other controls remain the same...

        # Progress Section
        progress_layout = QVBoxLayout()
        progress_layout.addWidget(self.stage_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        # URL Input
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Enter book URL")

        # Model Selection
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.0-flash", "gemini-2.0-flash-lite"])

        # Prompt Style
        self.style_combo = QComboBox()
        self.style_combo.addItem("Modern Style", 1)
        self.style_combo.addItem("China Fantasy Style", 2)

        # Chapter Range
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 9999)
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, 9999)

        # Output Directory
        self.output_edit = QLineEdit()
        self.output_edit.setText(str(Path.home() / "Downloads"))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.choose_directory)

        # Progress Section
        progress_layout = QVBoxLayout()
        progress_layout.addWidget(self.stage_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        # Log Display
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)

        # Form Layout
        form_layout = QFormLayout()
        form_layout.addRow("Book URL:", self.url_edit)
        form_layout.addRow("Model:", self.model_combo)
        form_layout.addRow("Style:", self.style_combo)
        form_layout.addRow("Start Chapter:", self.start_spin)
        form_layout.addRow("End Chapter:", self.end_spin)

        # Output Layout
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(browse_btn)
        form_layout.addRow("Output Directory:", output_layout)

        # Buttons
        self.start_btn = QPushButton("Start Translation")
        self.start_btn.clicked.connect(self.start_translation)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(form_layout)
        layout.addWidget(QLabel("Progress Log:"))
        layout.addWidget(self.log_area)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        # Modify cancel button connection
        self.cancel_btn.clicked.connect(self.on_cancel)

    def on_cancel(self):
        if self.thread and self.thread.isRunning():
            reply = QMessageBox.question(
                self, 'Cancel Translation',
                'Are you sure you want to cancel the current translation?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.thread.stop()
                self.log_area.append("Translation cancelled by user")
                self.start_btn.setEnabled(True)
        else:
            self.reject()

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            event.ignore()
            QMessageBox.warning(self, "Operation in Progress",
                                "Please cancel the current translation before closing")
        else:
            logging.root.removeHandler(self.log_handler)
            super().closeEvent(event)



    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_edit.setText(directory)

    def start_translation(self):
        params = {
            'book_url': self.url_edit.text(),
            'model_name': self.model_combo.currentText(),
            'prompt_style': self.style_combo.currentData(),
            'start_chapter': self.start_spin.value(),
            'end_chapter': self.end_spin.value(),
            'output_directory': self.output_edit.text()
        }

        if not params['book_url']:
            QMessageBox.warning(self, "Warning", "Please enter a valid URL!")
            return

        self.thread = TranslationThread(params)
        self.thread.update_log.connect(self.update_log)
        self.thread.finished.connect(self.on_finished)
        self.start_btn.setEnabled(False)
        self.thread.start()
        self.thread.stage_update.connect(self.update_stage)
        self.thread.update_progress.connect(self.progress_bar.setValue)

    @pyqtSlot(str)
    def update_stage(self, stage_name):
        self.stage_label.setText(f"Current Stage: {stage_name}")

    def update_log(self, message):
        self.log_area.append(message)

    def on_finished(self, success):
        self.start_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", "Translation completed successfully!")
        else:
            QMessageBox.warning(self, "Warning", "Translation completed with errors!")


# ======================
# Main Window
# ======================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Novel Translator")
        self.setFixedSize(400, 200)
        self.init_ui()
        self.load_settings()
        self.setWindowModality(Qt.NonModal)  # Allow interaction with dialogs


    def init_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()

        title = QLabel("Novel Translator")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        btn_style = """
            QPushButton {
                padding: 15px;
                font-size: 16px;
                min-width: 200px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """

        translate_btn = QPushButton("Translate from URL")
        translate_btn.setStyleSheet(btn_style)
        translate_btn.clicked.connect(self.show_translate_dialog)

        config_btn = QPushButton("Configuration")
        config_btn.setStyleSheet(btn_style)
        config_btn.clicked.connect(self.show_settings)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(translate_btn)
        layout.addWidget(config_btn)
        layout.addStretch()

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def show_translate_dialog(self):
        dialog = TranslationDialog(self)
        dialog.setModal(False)  # Allow keeping dialog open
        dialog.show()

    def show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_settings()

    def load_settings(self):
        settings = QSettings("NovelTranslator", "Config")
        api_key = settings.value("APIKey", "")
        if api_key:
            import os
            os.environ["GEMINI_API_KEY"] = api_key


# ======================
# Application Entry
# ======================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
