import logging
import sys
import json
import uuid
import datetime
from pathlib import Path

from PyQt5 import sip
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox, QFileDialog,
                             QDialog, QFormLayout, QTextEdit, QMessageBox, QProgressBar, QTableWidget, QTableWidgetItem,
                             QScrollArea, QStyle, QSizePolicy, QFrame, QTabWidget)
from PyQt5.QtCore import Qt, QSettings, QThread, pyqtSignal, pyqtSlot, QObject, QStandardPaths, QUrl, QSize
from PyQt5.QtGui import QFont, QTextCursor, QDesktopServices

from logger import logging_utils
from translator.core import Translator
from translator.file_handler import FileHandler
from downloader.factory import DownloaderFactory
from config.models import get_model_config
import qtawesome as qta

# Stylesheets remain unchanged
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

# HistoryManager class remains unchanged
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
            self.file_handler.create_prompt_files_from_chapters(start_chapter=start_chapter, end_chapter=end_chapter)

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

class EnhancedProgressDialog(QDialog):
    def __init__(self, get_status_func, parent=None):
        super().__init__(parent)
        self.get_status_func = get_status_func
        self.chapter_status = self.get_status_func()
        self.setWindowTitle("Chapter Translation Progress")
        self.resize(700, 500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)  # Increased margins for better spacing
        layout.setSpacing(15)  # Increased spacing

        # Enhanced summary section with card-like appearance
        summary_frame = QFrame()
        summary_frame.setFrameShape(QFrame.StyledPanel)
        summary_frame.setFrameShadow(QFrame.Raised)
        summary_frame.setStyleSheet("""
            QFrame {
                background-color: #f7f7f7;
                border-radius: 8px;
                border: 1px solid #ddd;
            }
        """)
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setSpacing(20)  # Increased spacing between summary items

        total_chapters = len(self.chapter_status)
        completed_chapters = sum(1 for _, info in self.chapter_status.items() if info.get("progress", 0) == 100)
        in_progress = sum(1 for _, info in self.chapter_status.items() if 0 < info.get("progress", 0) < 100)
        avg_progress = sum(info.get("progress", 0) for _, info in self.chapter_status.items()) / max(1, total_chapters)

        # Enhanced status widgets with icons
        total_label = self.create_stat_widget("Total Chapters", str(total_chapters), "mdi.book-open-variant")
        completed_label = self.create_stat_widget("Completed", str(completed_chapters), "mdi.check-circle", "green")
        pending_label = self.create_stat_widget("In Progress", str(in_progress), "mdi.progress-clock", "blue")

        # Improved progress bar
        progress_frame = QFrame()
        progress_layout = QVBoxLayout(progress_frame)
        progress_title = QLabel("<b>Overall Progress</b>")
        progress_title.setAlignment(Qt.AlignCenter)
        overall_progress = QProgressBar()
        overall_progress.setValue(int(avg_progress))
        overall_progress.setFormat(f"{avg_progress:.1f}%")
        overall_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bbb;
                border-radius: 5px;
                text-align: center;
                height: 25px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                          stop:0 #4CAF50, stop:1 #8BC34A);
                border-radius: 5px;
            }
        """)
        progress_layout.addWidget(progress_title)
        progress_layout.addWidget(overall_progress)

        summary_layout.addWidget(total_label)
        summary_layout.addWidget(completed_label)
        summary_layout.addWidget(pending_label)
        summary_layout.addWidget(progress_frame)
        layout.addWidget(summary_frame)

        # Improved tab widget
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 5px;
            }
            QTabBar::tab {
                padding: 8px 15px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #f0f0f0;
                border-bottom: 2px solid #4CAF50;
            }
        """)

        chapter_tab = QWidget()
        chapter_layout = QVBoxLayout(chapter_tab)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(350)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(5, 5, 5, 5)
        scroll_layout.setSpacing(15)  # Increased spacing between chapters

        sorted_chapters = sorted(self.chapter_status.items(),
                                 key=lambda x: int(x[0].split()[-1].isdigit() and x[0].split()[-1] or 0) if x[
                                     0].split() else 0)

        for chapter, info in sorted_chapters:
            chapter_frame = self.create_chapter_frame(chapter, info)
            scroll_layout.addWidget(chapter_frame)

        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        chapter_layout.addWidget(scroll_area)
        tab_widget.addTab(chapter_tab, "Chapter Details")

        layout.addWidget(tab_widget)

        # Improved button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(qta.icon("mdi.refresh", color="#1565C0"))
        refresh_btn.setIconSize(QSize(16, 16))
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #E3F2FD;
                color: #1565C0;
                padding: 8px 15px;
                border-radius: 5px;
                border: 1px solid #BBDEFB;
            }
            QPushButton:hover {
                background-color: #BBDEFB;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_status)
        button_layout.addWidget(refresh_btn)

        # Close Button
        close_btn = QPushButton("Close")
        close_btn.setIcon(qta.icon("mdi.close", color="#424242"))
        close_btn.setIconSize(QSize(16, 16))
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #F5F5F5;
                color: #424242;
                padding: 8px 15px;
                border-radius: 5px;
                border: 1px solid #E0E0E0;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
            }
        """)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def create_stat_widget(self, title, value, icon_name, color=None):
        """Create a styled stat widget with icon and value"""
        widget = QFrame()
        layout = QVBoxLayout(widget)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)

        icon = qta.icon(icon_name, color=color or "#505050")
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(24, 24))
        icon_label.setAlignment(Qt.AlignCenter)

        title_label = QLabel(f"<b>{title}</b>")
        title_label.setAlignment(Qt.AlignCenter)

        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignCenter)
        if color:
            value_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        else:
            value_label.setStyleSheet("font-size: 18px; font-weight: bold;")

        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(value_label)

        return widget

    def create_chapter_frame(self, chapter, info):
        """Create a styled chapter frame"""
        chapter_frame = QFrame()
        chapter_frame.setFrameShape(QFrame.StyledPanel)
        chapter_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #ddd;
                border-radius: 6px;
                background-color: #fafafa;
            }
        """)
        chapter_layout_inner = QVBoxLayout(chapter_frame)
        chapter_layout_inner.setSpacing(8)

        header_layout = QHBoxLayout()

        # Chapter icon and title
        icon_label = QLabel()
        progress_value = int(info.get("progress", 0))
        if progress_value == 100:
            icon = qta.icon("mdi.check-circle", color="green")
        elif progress_value > 0:
            icon = qta.icon("mdi.progress-clock", color="blue")
        else:
            icon = qta.icon("mdi.book", color="gray")
        icon_label.setPixmap(icon.pixmap(20, 20))

        chapter_label = QLabel(f"<b>{chapter}</b>")
        chapter_label.setStyleSheet("font-size: 14px;")

        status_label = QLabel(info.get("status", "Not Started"))
        if progress_value == 100:
            status_label.setStyleSheet("color: green; font-weight: bold;")
        elif progress_value > 0:
            status_label.setStyleSheet("color: blue; font-weight: bold;")
        else:
            status_label.setStyleSheet("color: gray;")

        header_layout.addWidget(icon_label)
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
                height: 20px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                         stop:0 #76b852, stop:1 #8DC26F);
                border-radius: 4px;
            }
        """)

        if "estimated_time" in info:
            time_icon = QLabel()
            time_icon.setPixmap(qta.icon("mdi.clock-outline").pixmap(16, 16))
            time_label = QLabel(f"Est. completion: {info['estimated_time']}")
            time_layout = QHBoxLayout()
            time_layout.addWidget(time_icon)
            time_layout.addWidget(time_label)
            time_layout.addStretch()

            progress_layout.addWidget(progress_bar, 4)
            progress_layout.addLayout(time_layout, 1)
        else:
            progress_layout.addWidget(progress_bar)

        chapter_layout_inner.addLayout(progress_layout)

        return chapter_frame

    def refresh_status(self):
        """Refresh the status data and update UI"""
        self.chapter_status = self.get_status_func()
        # Clear and rebuild UI
        self.close()
        new_dialog = EnhancedProgressDialog(self.get_status_func, self.parent())
        new_dialog.show()
        self.accept()



class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.setMinimumSize(450, 250)
        self.init_ui()
        self.setWindowModality(Qt.ApplicationModal)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter Gemini API Key")
        self.api_key_edit.setEchoMode(QLineEdit.Normal)
        self.api_key_edit.setMinimumWidth(300)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        form_layout.addRow(QLabel("Gemini API Key:"), self.api_key_edit)
        form_layout.addRow(QLabel("Theme:"), self.theme_combo)

        self.load_settings()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(20)
        btn_box.addStretch(1)

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
        btn_box.addStretch(1)

        layout.addLayout(form_layout)
        layout.addStretch(1)
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
        self.setMinimumSize(650, 550)
        self.thread = None
        self.log_handler = None
        self.current_history_id = None

        # Setup QtAwesome
        import qtawesome as qta
        self.qta = qta

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
        # Main content widget for scrollable area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(12)

        # Title section
        title_layout = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(self.qta.icon('fa5s.book-reader', color='#4a86e8').pixmap(32, 32))
        title_label = QLabel("Book Translator")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4a86e8;")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        content_layout.addLayout(title_layout)

        # Add a separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #e0e0e0;")
        content_layout.addWidget(separator)

        # Create a form layout for input fields
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 10, 0, 10)
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # URL input with "Source Info" button
        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Enter book URL")
        self.url_edit.setMinimumHeight(30)
        self.url_edit.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        self.source_info_btn = QPushButton("Source Info")
        self.source_info_btn.setIcon(self.qta.icon('fa5s.info-circle', color='#4a86e8'))
        self.source_info_btn.setFixedWidth(120)
        self.source_info_btn.clicked.connect(self.show_source_info)
        self.source_info_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f8ff;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0f0ff;
            }
            QPushButton:pressed {
                background-color: #d0e0ff;
            }
        """)
        url_layout.addWidget(self.url_edit, 1)
        url_layout.addWidget(self.source_info_btn)
        form_layout.addRow(QLabel("Book URL:"), url_layout)

        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.0-flash", "gemini-2.0-flash-lite"])
        self.model_combo.setMinimumHeight(30)
        self.model_combo.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        form_layout.addRow(QLabel("Model:"), self.model_combo)

        # Style selection
        self.style_combo = QComboBox()
        self.style_combo.addItem("Modern Style", 1)
        self.style_combo.addItem("China Fantasy Style", 2)
        self.style_combo.setMinimumHeight(30)
        self.style_combo.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        form_layout.addRow(QLabel("Style:"), self.style_combo)

        # Chapter range section
        range_layout = QVBoxLayout()
        self.chapter_range_btn = QPushButton("Set Chapter Range")
        self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#555'))
        self.chapter_range_btn.setCheckable(True)
        self.chapter_range_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f8ff;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:checked {
                background-color: #e0f0ff;
            }
            QPushButton:hover {
                background-color: #e0f0ff;
            }
            QPushButton:pressed {
                background-color: #d0e0ff;
            }
        """)
        self.chapter_range_btn.clicked.connect(self.toggle_chapter_range)
        range_header = QHBoxLayout()
        range_header.addWidget(self.chapter_range_btn)
        range_header.addStretch(1)
        range_layout.addLayout(range_header)

        # Chapter spinners container
        self.chapter_range_container = QWidget()
        chapter_range_inner = QFormLayout(self.chapter_range_container)
        chapter_range_inner.setContentsMargins(10, 10, 10, 0)
        chapter_range_inner.setSpacing(10)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, 9999)
        self.start_spin.setValue(1)
        self.start_spin.setMinimumHeight(28)
        self.start_spin.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        chapter_range_inner.addRow(QLabel("Start Chapter:"), self.start_spin)
        self.end_spin = QSpinBox()
        self.end_spin.setRange(1, 9999)
        self.end_spin.setValue(1)
        self.end_spin.setMinimumHeight(28)
        self.end_spin.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        chapter_range_inner.addRow(QLabel("End Chapter:"), self.end_spin)
        range_layout.addWidget(self.chapter_range_container)
        self.chapter_range_container.hide()  # Initially hidden
        form_layout.addRow("", range_layout)

        # Output directory selection with browse button
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setText(str(Path.home() / "Downloads"))
        self.output_edit.setMinimumHeight(30)
        self.output_edit.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        browse_btn = QPushButton("Browse")
        browse_btn.setIcon(self.qta.icon('fa5s.folder-open', color='#555'))
        browse_btn.clicked.connect(self.choose_directory)
        browse_btn.setFixedWidth(100)
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f8ff;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0f0ff;
            }
            QPushButton:pressed {
                background-color: #d0e0ff;
            }
        """)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(browse_btn)
        form_layout.addRow(QLabel("Output Directory:"), output_layout)
        content_layout.addWidget(form_widget)

        # Card-style progress section
        progress_card = QFrame()
        progress_card.setFrameShape(QFrame.StyledPanel)
        progress_card.setStyleSheet("""
            QFrame {
                background-color: #f9f9f9;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setSpacing(10)
        progress_header = QHBoxLayout()
        progress_icon = QLabel()
        progress_icon.setPixmap(self.qta.icon('fa5s.tasks', color='#4a86e8').pixmap(20, 20))
        progress_header_label = QLabel("Progress")
        progress_header_label.setStyleSheet("font-weight: bold; color: #4a86e8;")
        progress_header.addWidget(progress_icon)
        progress_header.addWidget(progress_header_label)
        progress_header.addStretch(1)
        progress_layout.addLayout(progress_header)
        stage_layout = QHBoxLayout()
        stage_icon = QLabel()
        stage_icon.setPixmap(self.qta.icon('fa5s.info-circle', color='#555').pixmap(16, 16))
        self.stage_label = QLabel("Current Stage: Idle")
        stage_layout.addWidget(stage_icon)
        stage_layout.addWidget(self.stage_label)
        stage_layout.addStretch(1)
        progress_layout.addLayout(stage_layout)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4a86e8, stop:1 #87b7ff);
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        progress_buttons_layout = QHBoxLayout()
        self.chapter_progress_btn = QPushButton("Chapter Progress")
        self.chapter_progress_btn.setIcon(self.qta.icon('fa5s.chart-bar', color='#555'))
        self.chapter_progress_btn.clicked.connect(self.show_chapter_progress)
        self.chapter_progress_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f8ff;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0f0ff;
            }
            QPushButton:pressed {
                background-color: #d0e0ff;
            }
        """)
        self.toggle_log_btn = QPushButton("Collapse Log")
        self.toggle_log_btn.setIcon(self.qta.icon('fa5s.chevron-up', color='#555'))
        self.toggle_log_btn.clicked.connect(self.toggle_log)
        self.toggle_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f8ff;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0f0ff;
            }
            QPushButton:pressed {
                background-color: #d0e0ff;
            }
        """)
        progress_buttons_layout.addWidget(self.chapter_progress_btn)
        progress_buttons_layout.addWidget(self.toggle_log_btn)
        progress_layout.addLayout(progress_buttons_layout)
        content_layout.addWidget(progress_card)

        # Log area with improved styling
        log_header = QHBoxLayout()
        log_icon = QLabel()
        log_icon.setPixmap(self.qta.icon('fa5s.terminal', color='#4a86e8').pixmap(16, 16))
        log_header_label = QLabel("Progress Log")
        log_header_label.setStyleSheet("font-weight: bold; color: #4a86e8;")
        log_header.addWidget(log_icon)
        log_header.addWidget(log_header_label)
        log_header.addStretch(1)
        content_layout.addLayout(log_header)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(150)
        self.log_area.setFont(QFont("Consolas", 10))
        self.log_area.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        content_layout.addWidget(self.log_area)

        # Setup scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

        # Action buttons (outside scroll area)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        btn_layout.addStretch(1)
        self.start_btn = QPushButton("Start Translation")
        self.start_btn.setIcon(self.qta.icon('fa5s.play', color='white'))
        self.start_btn.clicked.connect(self.start_translation)
        self.start_btn.setMinimumWidth(160)
        self.start_btn.setMinimumHeight(36)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a86e8;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #3366cc;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3b78de;
                border: 1px solid #3366cc;
            }
            QPushButton:pressed {
                background-color: #3366cc;
                border: 1px solid #3366cc;
            }
            QPushButton:disabled {
                background-color: #a0c0e8;
                color: #ffffff;
                border: 1px solid #a0c0e8;
            }
        """)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setIcon(self.qta.icon('fa5s.times', color='white'))
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #c62828;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                border: 1px solid #c62828;
            }
            QPushButton:pressed {
                background-color: #c62828;
                border: 1px solid #c62828;
            }
        """)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch(1)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

    def toggle_chapter_range(self):
        if self.chapter_range_btn.isChecked():
            self.chapter_range_container.show()
            self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#4a86e8'))
        else:
            self.chapter_range_container.hide()
            self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#555'))

    def on_cancel(self):
        if self.thread and self.thread.isRunning():
            message_box = QMessageBox(self)
            message_box.setWindowTitle('Cancel Translation')
            message_box.setText('Are you sure you want to cancel the current translation?')
            message_box.setIcon(QMessageBox.Question)
            message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            message_box.setDefaultButton(QMessageBox.No)
            message_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #f0f8ff;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e0f0ff;
                }
                QPushButton:pressed {
                    background-color: #d0e0ff;
                }
            """)
            yes_button = message_box.button(QMessageBox.Yes)
            yes_button.setIcon(self.qta.icon('fa5s.check', color='#4caf50'))
            no_button = message_box.button(QMessageBox.No)
            no_button.setIcon(self.qta.icon('fa5s.times', color='#f44336'))
            reply = message_box.exec_()
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
            message_box = QMessageBox(self)
            message_box.setWindowTitle("Operation in Progress")
            message_box.setText("Please cancel the current translation before closing.")
            message_box.setIcon(QMessageBox.Warning)
            message_box.setStandardButtons(QMessageBox.Ok)
            message_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #f0f8ff;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e0f0ff;
                }
                QPushButton:pressed {
                    background-color: #d0e0ff;
                }
            """)
            message_box.exec_()
        else:
            logging.root.removeHandler(self.log_handler)
            TranslationDialog.active_instance = None
            super().closeEvent(event)
            self.deleteLater()

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_edit.setText(directory)

    def validate_inputs(self):
        url = self.url_edit.text().strip()
        if not url:
            self.show_error_message("Validation Error", "URL cannot be empty.")
            return False
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            if not domain:
                raise ValueError("missing domain")
            supported_domains = DownloaderFactory.get_supported_domains()
            if domain not in supported_domains:
                self.show_error_message("Validation Error",
                                        f"Unsupported domain: {domain}. Please check list source info.")
                return False
        except Exception as e:
            self.show_error_message("Validation Error", f"Invalid URL: {e}")
            return False
        if self.chapter_range_btn.isChecked():
            start_chapter = self.start_spin.value()
            end_chapter = self.end_spin.value()
            if start_chapter > end_chapter:
                self.show_error_message("Validation Error",
                                        "Start chapter cannot be greater than end chapter.")
                return False
        return True

    def show_error_message(self, title, message):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Warning)
        icon_label = QLabel(msg_box)
        icon_label.setPixmap(self.qta.icon('fa5s.exclamation-triangle', color='#f44336').pixmap(32, 32))
        msg_box.setIconPixmap(icon_label.pixmap())
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QPushButton {
                background-color: #f0f8ff;
                color: #333333;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0f0ff;
            }
            QPushButton:pressed {
                background-color: #d0e0ff;
            }
        """)
        msg_box.exec_()

    def start_translation(self):
        if not self.validate_inputs():
            return
        start_chapter = self.start_spin.value() if self.chapter_range_btn.isChecked() else None
        end_chapter = self.end_spin.value() if self.chapter_range_btn.isChecked() else None
        params = {
            'book_url': self.url_edit.text(),
            'model_name': self.model_combo.currentText(),
            'prompt_style': self.style_combo.currentData(),
            'start_chapter': start_chapter,
            'end_chapter': end_chapter,
            'output_directory': self.output_edit.text()
        }
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
        self.start_btn.setEnabled(False)
        self.start_btn.setText("Translating...")
        self.start_btn.setIcon(self.qta.icon('fa5s.spinner', color='white', animation=self.qta.Spin(self.start_btn)))
        self.log_area.clear()
        self.log_area.append("Starting translation process...")
        self.stage_label.setText("Current Stage: Initializing")
        self.progress_bar.setValue(0)
        self.thread = TranslationThread(params)
        self.thread.update_log.connect(self.update_log)
        self.thread.finished.connect(self.on_finished)
        self.thread.stage_update.connect(self.on_stage_update)
        self.thread.update_progress.connect(self.on_progress_update)
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
        self.start_btn.setText("Start Translation")
        self.start_btn.setIcon(self.qta.icon('fa5s.play', color='white'))
        if success:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Translation Completed")
            msg_box.setText("Translation completed successfully!")
            msg_box.setInformativeText(f"EPUB generated at:\n{epub_path}")
            success_icon = QLabel(msg_box)
            success_icon.setPixmap(self.qta.icon('fa5s.check-circle', color='#4caf50').pixmap(48, 48))
            msg_box.setIconPixmap(success_icon.pixmap())
            open_button = QPushButton("Open EPUB Folder")
            open_button.setIcon(self.qta.icon('fa5s.folder-open', color='#4a86e8'))
            open_button.setStyleSheet("""
                QPushButton {
                    background-color: #f0f8ff;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e0f0ff;
                }
                QPushButton:pressed {
                    background-color: #d0e0ff;
                }
            """)
            close_button = QPushButton("Close")
            close_button.setStyleSheet("""
                QPushButton {
                    background-color: #f0f8ff;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e0f0ff;
                }
                QPushButton:pressed {
                    background-color: #d0e0ff;
                }
            """)
            msg_box.addButton(open_button, QMessageBox.ActionRole)
            msg_box.addButton(close_button, QMessageBox.RejectRole)
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QLabel {
                    margin-bottom: 10px;
                }
            """)
            msg_box.exec_()
            if msg_box.clickedButton() == open_button:
                directory_path = str(Path(epub_path).parent)
                QDesktopServices.openUrl(QUrl.fromLocalFile(directory_path))
        else:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Warning")
            msg_box.setText("Translation completed with errors!")
            error_icon = QLabel(msg_box)
            error_icon.setPixmap(self.qta.icon('fa5s.exclamation-triangle', color='#f44336').pixmap(48, 48))
            msg_box.setIconPixmap(error_icon.pixmap())
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #f0f8ff;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #e0f0ff;
                }
                QPushButton:pressed {
                    background-color: #d0e0ff;
                }
            """)
            msg_box.exec_()
        if self.current_history_id:
            HistoryManager.update_task(self.current_history_id, {"status": "Success" if success else "Error"})

    def show_chapter_progress(self):
        if not self.thread or not self.thread.file_handler:
            self.show_error_message("Unavailable", "Chapter progress is not available at this time.")
            return
        def status_getter():
            if self.thread and self.thread.file_handler:
                return self.thread.file_handler.get_chapter_status(
                    self.start_spin.value() if self.chapter_range_btn.isChecked() else None,
                    self.end_spin.value() if self.chapter_range_btn.isChecked() else None
                )
            return {}
        dialog = EnhancedProgressDialog(status_getter, self)
        dialog.exec_()

    def toggle_log(self):
        if self.log_area.isVisible():
            self.log_area.hide()
            self.toggle_log_btn.setText("Expand Log")
            self.toggle_log_btn.setIcon(self.qta.icon('fa5s.chevron-down', color='#555'))
        else:
            self.log_area.show()
            self.toggle_log_btn.setText("Collapse Log")
            self.toggle_log_btn.setIcon(self.qta.icon('fa5s.chevron-up', color='#555'))

    def show_source_info(self):
        dialog = SourceInfoDialog(self)
        dialog.exec_()

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
            start_value = max(1, int(start))
            self.start_spin.setValue(start_value)
            self.chapter_range_btn.setChecked(True)
            self.chapter_range_container.show()
        else:
            self.chapter_range_btn.setChecked(False)
            self.chapter_range_container.hide()
        if end is not None:
            end_value = max(1, int(end))
            self.end_spin.setValue(end_value)
        self.output_edit.setText(task.get("output_directory", str(Path.home() / "Downloads")))
        # Ensure the Start Translation button is reset to its initial state
        self.start_btn.setEnabled(True)
        self.start_btn.setText("Start Translation")
        self.start_btn.setIcon(self.qta.icon('fa5s.play', color='white'))
        # Reset progress indicators for consistency
        self.progress_bar.setValue(0)
        self.stage_label.setText("Current Stage: Idle")




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

        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by URL")
        self.search_edit.textChanged.connect(self.update_table)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Book URL", "Model", "Prompt Style",
                                              "Start Chapter", "End Chapter", "Output Directory", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        load_btn = QPushButton("Load Selected Task")
        load_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        load_btn.clicked.connect(self.load_selected_task)
        remove_btn = QPushButton("Remove Selected Task")
        remove_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        remove_btn.clicked.connect(self.remove_selected_task)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        refresh_btn.clicked.connect(self.load_history)
        close_btn = QPushButton("Close")
        close_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
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
        self.table.setSortingEnabled(False)
        search_text = self.search_edit.text().lower()
        display_tasks = [
            task for task in self.history_tasks
            if search_text in task.get("book_url", "").lower()
        ]
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
            dialog = TranslationDialog.get_instance(self.parent())
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


class SourceInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Supported Sources Information")
        self.resize(800, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Explanation label
        explanation = QLabel(
            "The following sources are supported with their respective configurations and estimated download speeds.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        # Table to display source information
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Source Name", "Domains", "Bulk Download", "Concurrent Downloads",
            "Request Delay (s)", "Source Language", "Download Speed (chapters/s)"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        # Populate table with data from DownloaderFactory.get_source_info()
        source_infos = DownloaderFactory.get_source_info()
        for info in source_infos:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(info.name))
            domains_str = ", ".join(info.domains)
            self.table.setItem(row, 1, QTableWidgetItem(domains_str))
            bulk_str = "Yes" if info.bulk_download else "No"
            self.table.setItem(row, 2, QTableWidgetItem(bulk_str))
            self.table.setItem(row, 3, QTableWidgetItem(str(info.concurrent_downloads)))
            self.table.setItem(row, 4, QTableWidgetItem(f"{info.request_delay:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(info.source_language))
            self.table.setItem(row, 6, QTableWidgetItem(f"{info.download_speed:.2f}"))

        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        # Close button
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

# MainWindow class remains unchanged
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
        layout.setSpacing(15)  # Increase spacing between widgets

        title = QLabel("Novel Translator")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        # Create styled buttons with proper alignment
        translate_btn = self.create_styled_button("Translate from Web", 'mdi.web')
        translate_btn.clicked.connect(self.show_translate_dialog)

        history_btn = self.create_styled_button("Translation History", 'mdi.history')
        history_btn.clicked.connect(self.show_history_dialog)

        config_btn = self.create_styled_button("Configuration", 'msc.settings-gear')
        config_btn.clicked.connect(self.show_settings)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(translate_btn)
        layout.addWidget(history_btn)
        layout.addWidget(config_btn)
        layout.addStretch()

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def create_styled_button(self, text, icon_name):
        """Create a styled button with centered text and icon"""
        button = QPushButton(text)

        # Set icon with proper size
        icon = qta.icon(icon_name, color='#505050')
        button.setIcon(icon)
        button.setIconSize(QSize(24, 24))  # Increase icon size

        # Center align text and icon
        button.setStyleSheet("""
            QPushButton {
                text-align: center;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                min-height: 45px;
            }
        """)

        # Ensure icon is positioned correctly with text
        button.setLayoutDirection(Qt.LeftToRight)

        return button

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
        dialog.show()

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

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
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
