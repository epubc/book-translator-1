import logging
import sys
import json
import uuid
import datetime
from pathlib import Path
from typing import Dict

from PyQt5 import sip
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox, QFileDialog,
                             QDialog, QFormLayout, QTextEdit, QMessageBox, QProgressBar, QTableWidget, QTableWidgetItem,
                             QScrollArea)
from PyQt5.QtCore import Qt, QSettings, QThread, pyqtSignal, pyqtSlot, QObject, QStandardPaths
from PyQt5.QtGui import QFont, QTextCursor

from logger import logging_utils  # Assuming this is your custom logger setup
from translator.core import Translator  # And other necessary imports
from translator.file_handler import FileHandler
from downloader.factory import DownloaderFactory
from config.models import get_model_config


##############################
# History Manager
##############################
class HistoryManager:
    @classmethod
    def get_history_file(cls):
        app_data_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        app_data_dir.mkdir(parents=True, exist_ok=True)
        return app_data_dir / "novel_translator_history.json"

    @classmethod
    def load_history(cls):
        history_file = cls.get_history_file()
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except json.JSONDecodeError:
                return []
        return []

    @classmethod
    def save_history(cls, history):
        history_file = cls.get_history_file()
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)

    @classmethod
    def add_task(cls, task):
        """
        If a task with the same book_url already exists, update it.
        Otherwise, add it as a new task.
        """
        history = cls.load_history()
        for existing in history:
            if existing.get("book_url") == task.get("book_url"):
                # Update the existing task with new parameters.
                existing.update(task)
                cls.save_history(history)
                return existing.get("id")
        # No duplicate found: generate a unique id and add the task.
        task["id"] = str(uuid.uuid4())
        history.append(task)
        cls.save_history(history)
        return task["id"]

    @classmethod
    def update_task(cls, task_id, updates):
        history = cls.load_history()
        for task in history:
            if task.get("id") == task_id:
                task.update(updates)
                break
        cls.save_history(history)

    @classmethod
    def remove_task(cls, index):
        history = cls.load_history()
        if 0 <= index < len(history):
            del history[index]
            cls.save_history(history)


##############################
# Custom Log Handler
##############################
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


##############################
# Thread Workers
##############################
class TranslationThread(QThread):
    update_log = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    finished = pyqtSignal(bool)
    stage_update = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self._is_running = True  # Flag to control execution
        self.downloader = None  # Store downloader instance
        self.file_handler = None  # Store file_handler instance
        self.translator = None  # Store translator instance

    def run(self):
        try:
            self.stage_update.emit("Initializing...")
            self.update_progress.emit(5)

            book_url = self.params['book_url']
            output_dir = Path(self.params['output_directory'])
            start_chapter = self.params['start_chapter']
            end_chapter = self.params['end_chapter']
            model_config = get_model_config(self.params['model_name'])

            self.stage_update.emit("Creating downloader...")
            self.downloader = DownloaderFactory.create_downloader(url=book_url, output_dir=output_dir)
            if not self._is_running:
                return
            book_info = self.downloader.book_info
            book_dir = self.downloader.book_dir

            logging_utils.configure_logging(
                book_dir,
                start_chapter=start_chapter,
                end_chapter=end_chapter
            )

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

            # Stage 1: Download
            self.stage_update.emit("Downloading chapters")
            self.update_progress.emit(25)
            if not self._is_running:
                return
            self.downloader.download_book()

            # Stage 2: Create prompts
            self.stage_update.emit("Creating prompts")
            self.update_progress.emit(50)
            if not self._is_running:
                return
            self.file_handler.create_prompt_files_from_chapters()

            # Stage 3: Translate
            self.stage_update.emit("Translating content")
            self.update_progress.emit(75)
            if not self._is_running:
                return
            self.translator.process_book_translation(prompt_style=self.params['prompt_style'],
                                                     start_chapter=start_chapter, end_chapter=end_chapter)

            # Stage 4: Generate EPUB
            self.stage_update.emit("Generating EPUB")
            self.update_progress.emit(95)
            if not self._is_running:
                return
            epub_path = self.file_handler.generate_epub(book_info.title, book_info.author)
            self.update_log.emit(f"EPUB generated at: {epub_path}")

            self.update_progress.emit(100)
            self.finished.emit(True)

        except Exception as e:
            logging.exception("An error occurred during translation:")
            self.update_log.emit(f"Error: {e}")
            self.finished.emit(False)
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


##############################
# Chapter Progress Dialog
##############################
class ChapterProgressDialog(QDialog):
    def __init__(self, chapter_status: Dict[str, Dict[str, any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chapter Translation Progress")
        self.resize(500, 400)
        self.chapter_status = chapter_status
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        # Create a scroll area with fixed height
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(300)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(5, 5, 5, 5)
        scroll_layout.setSpacing(10)

        # For each chapter, add a horizontal layout with a label and progress bar
        for chapter, info in self.chapter_status.items():
            hlayout = QHBoxLayout()
            hlayout.setSpacing(10)
            chapter_label = QLabel(chapter)
            chapter_label.setFixedWidth(150)
            progress_bar = QProgressBar()
            progress_value = int(info.get("progress", 0))
            progress_bar.setValue(progress_value)
            progress_bar.setFormat(f"{progress_value}%")
            progress_bar.setToolTip(f"Status: {info.get('status', '')}\n"
                                    f"Shards: {info.get('translated_shards', 0)} / {info.get('total_shards', 0)}")
            hlayout.addWidget(chapter_label)
            hlayout.addWidget(progress_bar)
            scroll_layout.addLayout(hlayout)

        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # Close button at the bottom
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)
        self.setLayout(layout)


##############################
# Configuration Dialog
##############################
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.setFixedSize(400, 200)
        self.init_ui()
        self.setWindowModality(Qt.ApplicationModal)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter Gemini API Key")
        self.api_key_edit.setEchoMode(QLineEdit.Password)

        form_layout = QFormLayout()
        form_layout.addRow("Gemini API Key:", self.api_key_edit)

        self.load_settings()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(20)
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


##############################
# Translation Dialog (Singleton)
##############################
class TranslationDialog(QDialog):
    active_instance = None

    @classmethod
    def get_instance(cls, parent=None):
        if cls.active_instance is None or sip.isdeleted(cls.active_instance):
            cls.active_instance = TranslationDialog(parent)
        return cls.active_instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translate from URL")
        self.setMinimumSize(600, 500)
        self.thread = None
        self.log_handler = None
        self.current_history_id = None  # Stores the current task's unique id
        self.init_ui()
        self.setup_logging()
        TranslationDialog.active_instance = self  # Set the singleton instance

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
        layout.setContentsMargins(15, 15, 15, 15)

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

        # Chapter Range (initially hidden)
        self.start_spin_label = QLabel("Start Chapter:")
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 9999)
        self.start_spin.setValue(0)
        self.start_spin.hide()
        self.start_spin_label.hide()

        self.end_spin_label = QLabel("End Chapter:")
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, 9999)
        self.end_spin.setValue(0)
        self.end_spin.hide()
        self.end_spin_label.hide()

        # Chapter Range Toggle Button
        self.chapter_range_btn = QPushButton("Set Chapter Range")
        self.chapter_range_btn.setCheckable(True)
        self.chapter_range_btn.clicked.connect(self.toggle_chapter_range)

        # Output Directory
        self.output_edit = QLineEdit()
        self.output_edit.setText(str(Path.home() / "Downloads"))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.choose_directory)

        # Progress Bar and Stage Label
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.stage_label = QLabel("Current Stage: Idle")

        progress_layout = QVBoxLayout()
        progress_layout.addWidget(self.stage_label)
        progress_layout.addWidget(self.progress_bar)

        # Form Layout
        form_layout = QFormLayout()
        form_layout.addRow("Book URL:", self.url_edit)
        form_layout.addRow("Model:", self.model_combo)
        form_layout.addRow("Style:", self.style_combo)
        form_layout.addRow(self.chapter_range_btn)
        form_layout.addRow(self.start_spin_label, self.start_spin)
        form_layout.addRow(self.end_spin_label, self.end_spin)

        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_edit)
        output_layout.addWidget(browse_btn)
        form_layout.addRow("Output Directory:", output_layout)

        # New buttons above process log: Chapter Progress and Log Toggle
        progress_buttons_layout = QHBoxLayout()
        progress_buttons_layout.setSpacing(20)
        self.chapter_progress_btn = QPushButton("Show Chapter Progress")
        self.chapter_progress_btn.clicked.connect(self.show_chapter_progress)
        self.toggle_log_btn = QPushButton("Collapse Log")
        self.toggle_log_btn.clicked.connect(self.toggle_log)
        progress_buttons_layout.addWidget(self.chapter_progress_btn)
        progress_buttons_layout.addWidget(self.toggle_log_btn)

        # Log Display (initially visible)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(100)
        self.log_area.setFont(QFont("Consolas", 12))

        # Buttons for starting/cancelling translation
        self.start_btn = QPushButton("Start Translation")
        self.start_btn.clicked.connect(self.start_translation)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.on_cancel)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.cancel_btn)

        # Assemble all layouts into main layout
        layout.addLayout(form_layout)
        layout.addLayout(progress_layout)
        layout.addLayout(progress_buttons_layout)
        layout.addWidget(QLabel("Progress Log:"))
        layout.addWidget(self.log_area)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def toggle_chapter_range(self):
        if self.chapter_range_btn.isChecked():
            self.start_spin.show()
            self.end_spin.show()
            self.start_spin_label.show()
            self.end_spin_label.show()
        else:
            self.start_spin.hide()
            self.end_spin.hide()
            self.start_spin_label.hide()
            self.end_spin_label.hide()

    def on_cancel(self):
        if self.thread and self.thread.isRunning():
            reply = QMessageBox.question(
                self, 'Cancel Translation',
                'Are you sure you want to cancel the current translation?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.thread.stop()
                self.log_area.append("Translation cancelled by user.")
                self.start_btn.setEnabled(True)
                self.accept()  # Close the dialog after canceling
        else:
            self.reject()

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            event.ignore()
            QMessageBox.warning(self, "Operation in Progress",
                                "Please cancel the current translation before closing.")
        else:
            logging.root.removeHandler(self.log_handler)
            TranslationDialog.active_instance = None  # Clear singleton reference
            super().closeEvent(event)
            self.deleteLater()  # Ensure the widget is properly deleted

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_edit.setText(directory)

    def start_translation(self):
        # Determine chapter values (or use None if not set)
        start_chapter = self.start_spin.value() if self.start_spin.isVisible() else None
        end_chapter = self.end_spin.value() if self.end_spin.isVisible() else None

        params = {
            'book_url': self.url_edit.text(),
            'model_name': self.model_combo.currentText(),
            'prompt_style': self.style_combo.currentData(),
            'start_chapter': start_chapter,
            'end_chapter': end_chapter,
            'output_directory': self.output_edit.text()
        }

        if not params['book_url']:
            QMessageBox.warning(self, "Warning", "Please enter a valid URL!")
            return

        # Create (or update) a history record based on URL uniqueness.
        self.current_history_id = HistoryManager.add_task({
            "timestamp": datetime.datetime.now().isoformat(),
            "book_url": self.url_edit.text(),
            "model_name": self.model_combo.currentText(),
            "prompt_style": self.style_combo.currentText(),
            "start_chapter": start_chapter,
            "end_chapter": end_chapter,
            "output_directory": self.output_edit.text(),
            "status": "In Progress",
            "current_stage": "Starting",
            "progress": 0
        })

        self.thread = TranslationThread(params)
        self.thread.update_log.connect(self.update_log)
        self.thread.finished.connect(self.on_finished)
        self.thread.stage_update.connect(self.on_stage_update)
        self.thread.update_progress.connect(self.on_progress_update)

        self.start_btn.setEnabled(False)
        self.thread.start()

    @pyqtSlot(str)
    def on_stage_update(self, stage):
        self.stage_label.setText(f"Current Stage: {stage}")
        if self.current_history_id:
            HistoryManager.update_task(self.current_history_id, {"current_stage": stage})

    @pyqtSlot(int)
    def on_progress_update(self, progress):
        self.progress_bar.setValue(progress)
        if self.current_history_id:
            HistoryManager.update_task(self.current_history_id, {"progress": progress})

    def update_log(self, message):
        self.log_area.append(message)

    def on_finished(self, success):
        self.start_btn.setEnabled(True)
        final_status = "Success" if success else "Error"
        if success:
            QMessageBox.information(self, "Success", "Translation completed successfully!")
        else:
            QMessageBox.warning(self, "Warning", "Translation completed with errors!")
        if self.current_history_id:
            HistoryManager.update_task(self.current_history_id, {"status": final_status})

    def show_chapter_progress(self):
        # Check if the file handler is available from the running thread
        if not self.thread or not self.thread.file_handler:
            QMessageBox.warning(self, "Unavailable", "Chapter progress is not available at this time.")
            return
        # Use the same chapter range settings if visible; otherwise, pass None
        start_chapter = self.start_spin.value() if self.start_spin.isVisible() else None
        end_chapter = self.end_spin.value() if self.end_spin.isVisible() else None
        chapter_status = self.thread.file_handler.get_chapter_status(start_chapter, end_chapter)
        dialog = ChapterProgressDialog(chapter_status, self)
        dialog.exec_()
        # Activate and bring the parent dialog to the front after closing the chapter progress
        self.activateWindow()
        self.raise_()

    def toggle_log(self):
        if self.log_area.isVisible():
            self.log_area.hide()
            self.toggle_log_btn.setText("Expand Log")
        else:
            self.log_area.show()
            self.toggle_log_btn.setText("Collapse Log")

    def load_task(self, task):
        """Load task parameters into the dialog."""
        self.url_edit.setText(task.get("book_url", ""))
        model_name = task.get("model_name", "gemini-2.0-flash")
        index = self.model_combo.findText(model_name)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        prompt_style = task.get("prompt_style", "Modern Style")
        index = self.style_combo.findText(prompt_style)
        if index >= 0:
            self.style_combo.setCurrentIndex(index)
        start = task.get("start_chapter", None)
        end = task.get("end_chapter", None)
        if start is not None:
            self.start_spin.setValue(int(start))
            self.start_spin.show()
            self.start_spin_label.show()
            self.chapter_range_btn.setChecked(True)
        else:
            self.start_spin.hide()
            self.start_spin_label.hide()
            self.chapter_range_btn.setChecked(False)
        if end is not None:
            self.end_spin.setValue(int(end))
            self.end_spin.show()
            self.end_spin_label.show()
        else:
            self.end_spin.hide()
            self.end_spin_label.hide()
        self.output_edit.setText(task.get("output_directory", str(Path.home() / "Downloads")))


##############################
# Translation History Dialog
##############################
class TranslationHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translation History")
        self.resize(800, 400)
        self.history_tasks = []  # Will store the loaded tasks.
        self.init_ui()
        self.load_history()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Book URL", "Model", "Prompt Style",
                                              "Start Chapter", "End Chapter", "Output Directory", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget { background-color: white; alternate-background-color: #f9f9f9; }")
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        load_btn = QPushButton("Load Selected Task")
        load_btn.clicked.connect(self.load_selected_task)
        remove_btn = QPushButton("Remove Selected Task")
        remove_btn.clicked.connect(self.remove_selected_task)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_history)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def load_history(self):
        history = HistoryManager.load_history()
        self.history_tasks = history  # Save the loaded tasks.
        self.table.setRowCount(0)
        for task in history:
            rowPosition = self.table.rowCount()
            self.table.insertRow(rowPosition)
            timestamp_item = QTableWidgetItem(task.get("timestamp", ""))
            url_item = QTableWidgetItem(task.get("book_url", ""))
            model_item = QTableWidgetItem(task.get("model_name", ""))
            prompt_item = QTableWidgetItem(str(task.get("prompt_style", "")))
            start_item = QTableWidgetItem(str(task.get("start_chapter", "")))
            end_item = QTableWidgetItem(str(task.get("end_chapter", "")))
            output_item = QTableWidgetItem(task.get("output_directory", ""))
            status_item = QTableWidgetItem(task.get("status", ""))
            self.table.setItem(rowPosition, 0, timestamp_item)
            self.table.setItem(rowPosition, 1, url_item)
            self.table.setItem(rowPosition, 2, model_item)
            self.table.setItem(rowPosition, 3, prompt_item)
            self.table.setItem(rowPosition, 4, start_item)
            self.table.setItem(rowPosition, 5, end_item)
            self.table.setItem(rowPosition, 6, output_item)
            self.table.setItem(rowPosition, 7, status_item)

    def remove_selected_task(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No selection", "Please select a task to remove.")
            return
        for index in sorted(selected_rows, key=lambda x: x.row(), reverse=True):
            row = index.row()
            HistoryManager.remove_task(row)
        self.load_history()

    def load_selected_task(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No selection", "Please select a task to load.")
            return
        row = selected_rows[0].row()
        task = self.history_tasks[row]
        # Use the singleton TranslationDialog instance to load the task.
        dialog = TranslationDialog.get_instance(self)
        dialog.load_task(task)
        dialog.setModal(False)
        dialog.show()


##############################
# Main Window
##############################
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Novel Translator")
        self.resize(500, 300)
        self.init_ui()
        self.load_settings()
        self.setWindowModality(Qt.NonModal)

    def init_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Novel Translator")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        translate_btn = QPushButton("Translate from URL")
        translate_btn.clicked.connect(self.show_translate_dialog)

        config_btn = QPushButton("Configuration")
        config_btn.clicked.connect(self.show_settings)

        history_btn = QPushButton("Translation History")
        history_btn.clicked.connect(self.show_history_dialog)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(translate_btn)
        layout.addWidget(config_btn)
        layout.addWidget(history_btn)
        layout.addStretch()

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def show_translate_dialog(self):
        dialog = TranslationDialog.get_instance(self)
        dialog.setModal(False)
        dialog.show()

    def show_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_settings()

    def show_history_dialog(self):
        dialog = TranslationHistoryDialog(self)
        dialog.exec_()

    def load_settings(self):
        settings = QSettings("NovelTranslator", "Config")
        api_key = settings.value("APIKey", "")
        if api_key:
            import os
            os.environ["GEMINI_API_KEY"] = api_key


##############################
# Application Entry
##############################
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Global style sheet for a modern and clean look
    global_stylesheet = """
    QWidget {
        font-family: 'Segoe UI', sans-serif;
        font-size: 14px;
        color: #333;
    }
    QPushButton {
        background-color: #5cb85c;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 5px;
    }
    QPushButton:hover {
        background-color: #4cae4c;
    }
    QPushButton:pressed {
        background-color: #449d44;
    }
    QLineEdit, QComboBox, QSpinBox, QTextEdit {
        border: 1px solid #ccc;
        padding: 5px;
        border-radius: 4px;
        background-color: #fff;
    }
    QProgressBar {
        border: 1px solid #ccc;
        border-radius: 5px;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #5cb85c;
        width: 10px;
        margin: 0.5px;
    }
    QTableWidget {
        background-color: #fff;
    }
    """
    app.setStyleSheet(global_stylesheet)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
