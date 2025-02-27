import logging
import sys
import json
import uuid
import datetime
from pathlib import Path
from typing import Dict

from PyQt5 import sip
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox, QFileDialog,
                             QDialog, QFormLayout, QTextEdit, QMessageBox, QProgressBar, QTableWidget, QTableWidgetItem,
                             QScrollArea, QStyle, QSizePolicy, QFrame, QTabWidget)  # Added QStyle
from PyQt5.QtCore import Qt, QSettings, QThread, pyqtSignal, pyqtSlot, QObject, QStandardPaths, QUrl
from PyQt5.QtGui import QFont, QTextCursor, QDesktopServices

from logger import logging_utils  # Assuming this is your custom logger setup
from translator.core import Translator
from translator.file_handler import FileHandler
from downloader.factory import DownloaderFactory
from config.models import get_model_config

# Define stylesheets for light and dark themes
light_stylesheet = """
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
    alternate-background-color: #f9f9f9;
}
"""

dark_stylesheet = """
QWidget {
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    color: #ddd;
    background-color: #333;
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
    border: 1px solid #555;
    padding: 5px;
    border-radius: 4px;
    background-color: #444;
    color: #ddd;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 5px;
    text-align: center;
    color: #ddd;
}
QProgressBar::chunk {
    background-color: #5cb85c;
    width: 10px;
    margin: 0.5px;
}
QTableWidget {
    background-color: #444;
    alternate-background-color: #555;
    color: #ddd;
}
"""

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
        history = cls.load_history()
        for existing in history:
            if existing.get("book_url") == task.get("book_url"):
                existing.update(task)
                cls.save_history(history)
                return existing.get("id")
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
    def remove_task_by_id(cls, task_id):
        history = cls.load_history()
        history = [task for task in history if task.get("id") != task_id]
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
    finished = pyqtSignal(bool, str)  # Updated to include EPUB path
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

            book_url = self.params['book_url']
            output_dir = Path(self.params['output_directory'])
            start_chapter = self.params['start_chapter']
            end_chapter = self.params['end_chapter']
            model_config = get_model_config(self.params['model_name'])

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

            self.stage_update.emit("Downloading chapters")
            self.update_progress.emit(25)
            if not self._is_running:
                return
            self.downloader.download_book()

            self.stage_update.emit("Creating prompts")
            self.update_progress.emit(50)
            if not self._is_running:
                return
            self.file_handler.create_prompt_files_from_chapters()

            self.stage_update.emit("Translating content")
            self.update_progress.emit(75)
            if not self._is_running:
                return
            self.translator.process_book_translation(prompt_style=self.params['prompt_style'],
                                                     start_chapter=start_chapter, end_chapter=end_chapter)

            self.stage_update.emit("Generating EPUB")
            self.update_progress.emit(95)
            if not self._is_running:
                return
            epub_path = self.file_handler.generate_epub(book_info.title, book_info.author)
            self.update_log.emit(f"EPUB generated at: {epub_path}")

            self.update_progress.emit(100)
            self.finished.emit(True, str(epub_path))  # Emit success with EPUB path

        except Exception as e:
            logging.exception("An error occurred during translation:")
            self.update_log.emit(f"Error: {e}")
            self.finished.emit(False, "")  # Emit failure with empty path
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
# Enhanced Progress Visualization
##############################

class EnhancedProgressDialog(QDialog):
    def __init__(self, get_status_func, parent=None):
        super().__init__(parent)
        self.get_status_func = get_status_func
        self.chapter_status = self.get_status_func()  # Initial data
        self.setWindowTitle("Chapter Translation Progress")
        self.resize(700, 500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Summary section
        summary_frame = QFrame()
        summary_frame.setFrameShape(QFrame.StyledPanel)
        summary_frame.setFrameShadow(QFrame.Raised)
        summary_layout = QHBoxLayout(summary_frame)

        total_chapters = len(self.chapter_status)
        completed_chapters = sum(1 for _, info in self.chapter_status.items() if info.get("progress", 0) == 100)
        in_progress = sum(1 for _, info in self.chapter_status.items() if 0 < info.get("progress", 0) < 100)
        avg_progress = sum(info.get("progress", 0) for _, info in self.chapter_status.items()) / max(1, total_chapters)

        total_label = QLabel(f"<b>Total Chapters:</b><br>{total_chapters}")
        total_label.setAlignment(Qt.AlignCenter)
        completed_label = QLabel(f"<b>Completed:</b><br>{completed_chapters}")
        completed_label.setAlignment(Qt.AlignCenter)
        pending_label = QLabel(f"<b>In Progress:</b><br>{in_progress}")
        pending_label.setAlignment(Qt.AlignCenter)
        overall_progress = QProgressBar()
        overall_progress.setValue(int(avg_progress))
        overall_progress.setFormat(f"Overall: {avg_progress:.1f}%")

        summary_layout.addWidget(total_label)
        summary_layout.addWidget(completed_label)
        summary_layout.addWidget(pending_label)
        summary_layout.addWidget(overall_progress)
        layout.addWidget(summary_frame)

        # Tab widget for chapter details and progress chart
        tab_widget = QTabWidget()

        # Tab 1: Chapter Details
        chapter_tab = QWidget()
        chapter_layout = QVBoxLayout(chapter_tab)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(350)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(5, 5, 5, 5)
        scroll_layout.setSpacing(10)

        sorted_chapters = sorted(self.chapter_status.items(),
                                 key=lambda x: int(x[0].split()[-1].isdigit() and x[0].split()[-1] or 0) if x[0].split() else 0)

        for chapter, info in sorted_chapters:
            chapter_frame = QFrame()
            chapter_frame.setFrameShape(QFrame.StyledPanel)
            chapter_layout_inner = QVBoxLayout(chapter_frame)
            chapter_layout_inner.setSpacing(5)

            header_layout = QHBoxLayout()
            chapter_label = QLabel(f"<b>{chapter}</b>")
            status_label = QLabel(info.get("status", "Not Started"))
            progress_value = int(info.get("progress", 0))
            if progress_value == 100:
                status_label.setStyleSheet("color: green;")
            elif progress_value > 0:
                status_label.setStyleSheet("color: blue;")
            else:
                status_label.setStyleSheet("color: gray;")
            header_layout.addWidget(chapter_label)
            header_layout.addStretch(1)
            header_layout.addWidget(status_label)
            chapter_layout_inner.addLayout(header_layout)

            progress_layout = QHBoxLayout()
            progress_bar = QProgressBar()
            progress_bar.setValue(progress_value)
            translated_shards = info.get("translated_shards", 0)
            total_shards = info.get("total_shards", 0)
            if total_shards > 0:
                progress_bar.setFormat(f"{progress_value}% ({translated_shards}/{total_shards} shards)")
            else:
                progress_bar.setFormat(f"{progress_value}%")
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #bbb;
                    border-radius: 4px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                               stop:0 #76b852, stop:1 #8DC26F);
                    width: 10px;
                    margin: 0.5px;
                }
            """)
            if "estimated_time" in info:
                time_label = QLabel(f"Est. completion: {info['estimated_time']}")
                progress_layout.addWidget(progress_bar, 4)
                progress_layout.addWidget(time_label, 1)
            else:
                progress_layout.addWidget(progress_bar)
            chapter_layout_inner.addLayout(progress_layout)

            scroll_layout.addWidget(chapter_frame)

        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        chapter_layout.addWidget(scroll_area)
        tab_widget.addTab(chapter_tab, "Chapter Details")


        layout.addWidget(tab_widget)

        button_layout = QHBoxLayout()
        button_layout.addStretch() # Add stretch to center the button
        close_btn = QPushButton("Close")
        close_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        button_layout.addStretch() # Add stretch to center the button
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def refresh_data(self):
        """Update data from source and refresh UI"""
        self.chapter_status = self.get_status_func()
        # Clear existing widgets and rebuild
        # sip.delete(self.tab_widget)
        self.init_ui()

    def export_progress(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Progress Report", "", "CSV Files (*.csv);;All Files (*)")
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("Chapter,Progress,Status,Translated Shards,Total Shards\n")
                    for chapter, info in self.chapter_status.items():
                        progress = info.get("progress", 0)
                        status = info.get("status", "Not Started")
                        translated = info.get("translated_shards", 0)
                        total = info.get("total_shards", 0)
                        f.write(f'"{chapter}",{progress},"{status}",{translated},{total}\n')
                QMessageBox.information(self, "Export Successful",
                                        f"Progress data exported to {filename}")
            except Exception as e:
                QMessageBox.warning(self, "Export Failed", f"Error: {str(e)}")

##############################
# Configuration Dialog
##############################
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.setMinimumSize(450, 250)  # Increased minimum size
        self.init_ui()
        self.setWindowModality(Qt.ApplicationModal)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)  # Increased spacing

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)  # Allow fields to grow

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter Gemini API Key")
        self.api_key_edit.setEchoMode(QLineEdit.Normal)
        self.api_key_edit.setMinimumWidth(300)  # Set minimum width

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        form_layout.addRow(QLabel("Gemini API Key:"), self.api_key_edit)
        form_layout.addRow(QLabel("Theme:"), self.theme_combo)

        self.load_settings()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(20)
        btn_box.addStretch(1)  # Add stretch to center buttons

        save_btn = QPushButton("Save")
        save_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        save_btn.clicked.connect(self.save_settings)
        save_btn.setMinimumWidth(100)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogCancelButton))
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setMinimumWidth(100)

        btn_box.addWidget(save_btn)
        btn_box.addWidget(cancel_btn)
        btn_box.addStretch(1)  # Add stretch to center buttons

        layout.addLayout(form_layout)
        layout.addStretch(1)  # Add stretch between form and buttons
        layout.addLayout(btn_box)
        self.setLayout(layout)

    def load_settings(self):
        settings = QSettings("NovelTranslator", "Config")
        self.api_key_edit.setText(settings.value("APIKey", ""))
        theme = settings.value("Theme", "Light")
        index = self.theme_combo.findText(theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

    def save_settings(self):
        settings = QSettings("NovelTranslator", "Config")
        settings.setValue("APIKey", self.api_key_edit.text())
        settings.setValue("Theme", self.theme_combo.currentText())
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
        self.current_history_id = None
        self.init_ui()
        self.setup_logging()
        TranslationDialog.active_instance = self

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
        layout.setSpacing(10)  # Added consistent spacing

        # URL input with better stretching
        url_layout = QHBoxLayout()
        url_label = QLabel("Book URL:")
        url_label.setFixedWidth(100)  # Fixed width for labels
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Enter book URL")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit, 1)  # Stretch factor of 1
        layout.addLayout(url_layout)

        # Model selection
        model_layout = QHBoxLayout()
        model_label = QLabel("Model:")
        model_label.setFixedWidth(100)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.0-flash", "gemini-2.0-flash-lite"])
        self.model_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Expand horizontally
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo, 1)
        layout.addLayout(model_layout)

        # Style selection
        style_layout = QHBoxLayout()
        style_label = QLabel("Style:")
        style_label.setFixedWidth(100)
        self.style_combo = QComboBox()
        self.style_combo.addItem("Modern Style", 1)
        self.style_combo.addItem("China Fantasy Style", 2)
        self.style_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        style_layout.addWidget(style_label)
        style_layout.addWidget(self.style_combo, 1)
        layout.addLayout(style_layout)

        # Chapter range toggle button
        range_layout = QHBoxLayout()
        range_spacer = QWidget()
        range_spacer.setFixedWidth(100)
        self.chapter_range_btn = QPushButton("Set Chapter Range")
        self.chapter_range_btn.setCheckable(True)
        self.chapter_range_btn.clicked.connect(self.toggle_chapter_range)
        range_layout.addWidget(range_spacer)
        range_layout.addWidget(self.chapter_range_btn)
        range_layout.addStretch(1)  # Add stretch at the end for proper alignment
        layout.addLayout(range_layout)

        # Start chapter spinner (initially hidden)
        start_layout = QHBoxLayout()
        self.start_spin_label = QLabel("Start Chapter:")
        self.start_spin_label.setFixedWidth(100)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 9999)
        self.start_spin.setValue(0)
        start_layout.addWidget(self.start_spin_label)
        start_layout.addWidget(self.start_spin)
        start_layout.addStretch(1)
        layout.addLayout(start_layout)
        self.start_spin.hide()
        self.start_spin_label.hide()

        # End chapter spinner (initially hidden)
        end_layout = QHBoxLayout()
        self.end_spin_label = QLabel("End Chapter:")
        self.end_spin_label.setFixedWidth(100)
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, 9999)
        self.end_spin.setValue(0)
        end_layout.addWidget(self.end_spin_label)
        end_layout.addWidget(self.end_spin)
        end_layout.addStretch(1)
        layout.addLayout(end_layout)
        self.end_spin.hide()
        self.end_spin_label.hide()

        # Output directory selection with browse button
        output_layout = QHBoxLayout()
        output_label = QLabel("Output Directory:")
        output_label.setFixedWidth(100)
        self.output_edit = QLineEdit()
        self.output_edit.setText(str(Path.home() / "Downloads"))
        browse_btn = QPushButton("Browse...")
        browse_btn.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        browse_btn.clicked.connect(self.choose_directory)
        browse_btn.setFixedWidth(100)  # Fixed width for browse button
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_edit, 1)  # Give stretch factor
        output_layout.addWidget(browse_btn)
        layout.addLayout(output_layout)

        # Progress bar and stage label
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.stage_label = QLabel("Current Stage: Idle")
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(5)
        progress_layout.addWidget(self.stage_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        # Chapter progress and log toggle buttons
        progress_buttons_layout = QHBoxLayout()
        progress_buttons_layout.setSpacing(10)
        self.chapter_progress_btn = QPushButton("Show Chapter Progress")
        self.chapter_progress_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.toggle_log_btn = QPushButton("Collapse Log")
        self.toggle_log_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.chapter_progress_btn.clicked.connect(self.show_chapter_progress)
        self.toggle_log_btn.clicked.connect(self.toggle_log)
        progress_buttons_layout.addWidget(self.chapter_progress_btn)
        progress_buttons_layout.addWidget(self.toggle_log_btn)
        layout.addLayout(progress_buttons_layout)

        # Log area with better sizing
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("Progress Log:"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(150)  # Increased minimum height
        self.log_area.setFont(QFont("Consolas", 10))  # Smaller font
        log_layout.addWidget(self.log_area)
        layout.addLayout(log_layout)

        # Start and cancel buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch(1)  # Add stretch to center buttons
        self.start_btn = QPushButton("Start Translation")
        self.start_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_btn.clicked.connect(self.start_translation)
        self.start_btn.setMinimumWidth(150)  # Set minimum width
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.cancel_btn.setMinimumWidth(100)  # Set minimum width
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch(1)  # Add stretch to center buttons
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
                self.accept()
        else:
            self.reject()

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            event.ignore()
            QMessageBox.warning(self, "Operation in Progress",
                                "Please cancel the current translation before closing.")
        else:
            logging.root.removeHandler(self.log_handler)
            TranslationDialog.active_instance = None
            super().closeEvent(event)
            self.deleteLater()

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_edit.setText(directory)

    def start_translation(self):
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

    def on_finished(self, success, epub_path):
        self.start_btn.setEnabled(True)
        if success:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Translation Completed")
            msg_box.setText("Translation completed successfully!")
            msg_box.setInformativeText(f"EPUB generated at: {epub_path}")
            open_button = msg_box.addButton("Open EPUB Folder", QMessageBox.ActionRole)
            close_button = msg_box.addButton("Close", QMessageBox.RejectRole)
            msg_box.exec_()
            if msg_box.clickedButton() == open_button:
                directory_path = str(Path(epub_path).parent)
                QDesktopServices.openUrl(QUrl.fromLocalFile(directory_path))
        else:
            QMessageBox.warning(self, "Warning", "Translation completed with errors!")
        if self.current_history_id:
            HistoryManager.update_task(self.current_history_id, {"status": "Success" if success else "Error"})

    def show_chapter_progress(self):
        if not self.thread or not self.thread.file_handler:
            QMessageBox.warning(self, "Unavailable", "Chapter progress is not available at this time.")
            return

        def status_getter():
            if self.thread and self.thread.file_handler:
                return self.thread.file_handler.get_chapter_status(
                    self.start_spin.value() if self.start_spin.isVisible() else None,
                    self.end_spin.value() if self.end_spin.isVisible() else None
                )
            return self.chapter_status  # Fallback to last known status

        dialog = EnhancedProgressDialog(status_getter, self)
        dialog.exec_()

    def toggle_log(self):
        if self.log_area.isVisible():
            self.log_area.hide()
            self.toggle_log_btn.setText("Expand Log")
        else:
            self.log_area.show()
            self.toggle_log_btn.setText("Collapse Log")

    def load_task(self, task):
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

    def setup_enhanced_progress(self):
        """Set up enhanced progress tracking UI components"""

        # Replace simple progress bar with a more detailed one
        progress_frame = QFrame()
        progress_frame.setFrameShape(QFrame.StyledPanel)
        progress_layout = QVBoxLayout(progress_frame)

        # Stage and time info layout
        stage_time_layout = QHBoxLayout()
        self.stage_label = QLabel("Current Stage: Idle")
        self.time_label = QLabel("Elapsed: 00:00:00")
        self.time_label.setAlignment(Qt.AlignRight)
        stage_time_layout.addWidget(self.stage_label)
        stage_time_layout.addStretch()
        stage_time_layout.addWidget(self.time_label)
        progress_layout.addLayout(stage_time_layout)

        # Progress bar with percentage
        progress_bar_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% (%v of %m)")
        self.current_task_label = QLabel("")
        progress_bar_layout.addWidget(self.progress_bar)
        progress_bar_layout.addWidget(self.current_task_label)
        progress_layout.addLayout(progress_bar_layout)

        # Add detailed sub-progress for current operation
        self.sub_progress_label = QLabel("Current Operation:")
        self.sub_progress_bar = QProgressBar()
        self.sub_progress_bar.setRange(0, 100)
        self.sub_progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.sub_progress_label)
        progress_layout.addWidget(self.sub_progress_bar)

        # Stats layout
        stats_layout = QHBoxLayout()
        self.chapters_done_label = QLabel("Chapters: 0/0")
        self.est_completion_label = QLabel("Est. Completion: --:--:--")
        self.avg_speed_label = QLabel("Speed: -- chars/sec")
        stats_layout.addWidget(self.chapters_done_label)
        stats_layout.addWidget(self.avg_speed_label)
        stats_layout.addWidget(self.est_completion_label)
        progress_layout.addLayout(stats_layout)

        return progress_frame

    def update_elapsed_time(self):
        """Update elapsed time display"""
        if hasattr(self, 'start_time'):
            elapsed = datetime.datetime.now() - self.start_time
            hours, remainder = divmod(elapsed.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.time_label.setText(f"Elapsed: {hours:02}:{minutes:02}:{seconds:02}")

    def update_progress_stats(self, progress, sub_progress=None, current_task=None):
        """Update progress statistics with more detailed information"""
        if not hasattr(self, 'start_time'):
            self.start_time = datetime.datetime.now()
            self.last_progress_update = self.start_time
            self.last_progress_value = 0

        # Update main progress bar
        self.progress_bar.setValue(progress)

        # Update sub-progress if provided
        if sub_progress is not None:
            self.sub_progress_bar.setValue(sub_progress)

        # Update current task label if provided
        if current_task:
            self.current_task_label.setText(current_task)

        # Calculate speed and ETA
        now = datetime.datetime.now()
        time_diff = (now - self.last_progress_update).total_seconds()
        if time_diff > 1:  # Only update calculations if more than a second has passed
            # Calculate progress speed (progress points per second)
            progress_diff = progress - self.last_progress_value
            if progress_diff > 0:
                speed = progress_diff / time_diff
                self.avg_speed_label.setText(f"Speed: {speed:.2f} %/sec")

                # Estimate completion time
                if progress > 0 and progress < 100:
                    remaining_progress = 100 - progress
                    eta_seconds = remaining_progress / max(speed, 0.001)  # Avoid division by zero
                    eta = datetime.timedelta(seconds=int(eta_seconds))
                    self.est_completion_label.setText(f"Est. Completion: {eta}")

            # Update last progress values
            self.last_progress_update = now
            self.last_progress_value = progress

        # Update elapsed time
        self.update_elapsed_time()

        # Update HistoryManager if we have an ID
        if self.current_history_id:
            updates = {
                "progress": progress,
                "elapsed_time": str(datetime.datetime.now() - self.start_time),
            }
            if current_task:
                updates["current_task"] = current_task

            HistoryManager.update_task(self.current_history_id, updates)


##############################
# Translation History Dialog
##############################
class TranslationHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translation History")
        self.resize(800, 400)
        self.history_tasks = []
        self.init_ui()
        self.load_history()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by URL")
        self.search_edit.textChanged.connect(self.update_table)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        # Table setup
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Book URL", "Model", "Prompt Style",
                                              "Start Chapter", "End Chapter", "Output Directory", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)  # Enable sorting by clicking headers
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        load_btn = QPushButton("Load Selected Task")
        load_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))  # Added icon
        load_btn.clicked.connect(self.load_selected_task)
        remove_btn = QPushButton("Remove Selected Task")
        remove_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))  # Added icon
        remove_btn.clicked.connect(self.remove_selected_task)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))  # Added icon
        refresh_btn.clicked.connect(self.load_history)
        close_btn = QPushButton("Close")
        close_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))  # Added icon
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def load_history(self):
        self.history_tasks = HistoryManager.load_history()
        self.update_table()

    def update_table(self):
        # Temporarily disable sorting while updating the table.
        self.table.setSortingEnabled(False)

        # Filter tasks based on search text
        search_text = self.search_edit.text().lower()
        display_tasks = [
            task for task in self.history_tasks
            if search_text in task.get("book_url", "").lower()
        ]

        # Clear and populate the table
        self.table.setRowCount(0)
        for task in display_tasks:
            rowPosition = self.table.rowCount()
            self.table.insertRow(rowPosition)
            timestamp_item = QTableWidgetItem(task.get("timestamp", ""))
            timestamp_item.setData(Qt.UserRole, task["id"])
            self.table.setItem(rowPosition, 0, timestamp_item)
            self.table.setItem(rowPosition, 1, QTableWidgetItem(task.get("book_url", "")))
            self.table.setItem(rowPosition, 2, QTableWidgetItem(task.get("model_name", "")))
            self.table.setItem(rowPosition, 3, QTableWidgetItem(str(task.get("prompt_style", ""))))
            self.table.setItem(rowPosition, 4, QTableWidgetItem(str(task.get("start_chapter", ""))))
            self.table.setItem(rowPosition, 5, QTableWidgetItem(str(task.get("end_chapter", ""))))
            self.table.setItem(rowPosition, 6, QTableWidgetItem(task.get("output_directory", "")))
            self.table.setItem(rowPosition, 7, QTableWidgetItem(task.get("status", "")))

        # Re-enable sorting after updating the table.
        self.table.setSortingEnabled(True)

    def load_selected_task(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No selection", "Please select a task to load.")
            return
        row = selected_rows[0].row()
        task_id = self.table.item(row, 0).data(Qt.UserRole)
        task = next((t for t in self.history_tasks if t["id"] == task_id), None)
        if task:
            dialog = TranslationDialog.get_instance(self)
            dialog.load_task(task)
            dialog.setModal(False)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        else:
            QMessageBox.warning(self, "Error", "Selected task not found.")

    def remove_selected_task(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "No selection", "Please select a task to remove.")
            return
        row = selected_rows[0].row()
        task_id = self.table.item(row, 0).data(Qt.UserRole)
        HistoryManager.remove_task_by_id(task_id)
        self.load_history()

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
        translate_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))  # Added icon
        translate_btn.clicked.connect(self.show_translate_dialog)

        history_btn = QPushButton("Translation History")
        history_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))  # Added icon
        history_btn.clicked.connect(self.show_history_dialog)

        config_btn = QPushButton("Configuration")
        config_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogInfoView))  # Added icon
        config_btn.clicked.connect(self.show_settings)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(translate_btn)
        layout.addWidget(history_btn)
        layout.addWidget(config_btn)
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
        theme = settings.value("Theme", "Light")
        app = QApplication.instance()
        if theme == "Dark":
            app.setStyleSheet(dark_stylesheet)
        else:
            app.setStyleSheet(light_stylesheet)

##############################
# Application Entry
##############################
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Load initial settings
    settings = QSettings("NovelTranslator", "Config")
    theme = settings.value("Theme", "Light")
    if theme == "Dark":
        app.setStyleSheet(dark_stylesheet)
    else:
        app.setStyleSheet(light_stylesheet)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()