import logging
from PyQt5 import sip
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QComboBox, QSpinBox, QTextEdit, QProgressBar, QScrollArea, QFrame,
                             QMessageBox, QFileDialog, QWidget, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSlot, QUrl
from PyQt5.QtGui import QFont, QTextCursor, QDesktopServices
import datetime
from pathlib import Path
from core.translation_thread import TranslationThread
from core.history_manager import HistoryManager
from core.utils import QTextEditLogHandler
from gui.progress_dialog import EnhancedProgressDialog
from gui.source_info_dialog import SourceInfoDialog
from downloader.factory import DownloaderFactory
import qtawesome as qta

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
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(12)

        title_layout = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(self.qta.icon('fa5s.book-reader', color='#4a86e8').pixmap(32, 32))
        title_label = QLabel("Book Translator")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4a86e8;")
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        content_layout.addLayout(title_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #e0e0e0;")
        content_layout.addWidget(separator)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 10, 0, 10)
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

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
                background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                border-radius: 6px; padding: 6px 12px; font-size: 13px;
            }
            QPushButton:hover { background-color: #e0f0ff; }
            QPushButton:pressed { background-color: #d0e0ff; }
        """)
        url_layout.addWidget(self.url_edit, 1)
        url_layout.addWidget(self.source_info_btn)
        form_layout.addRow(QLabel("Book URL:"), url_layout)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.0-flash", "gemini-2.0-flash-lite"])
        self.model_combo.setMinimumHeight(30)
        self.model_combo.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        form_layout.addRow(QLabel("Model:"), self.model_combo)

        self.style_combo = QComboBox()
        self.style_combo.addItem("Modern Style", 1)
        self.style_combo.addItem("China Fantasy Style", 2)
        self.style_combo.setMinimumHeight(30)
        self.style_combo.setStyleSheet("padding: 2px 8px; border-radius: 4px; border: 1px solid #ccc;")
        form_layout.addRow(QLabel("Style:"), self.style_combo)

        range_layout = QVBoxLayout()
        self.chapter_range_btn = QPushButton("Set Chapter Range")
        self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#555'))
        self.chapter_range_btn.setCheckable(True)
        self.chapter_range_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                border-radius: 6px; padding: 6px 12px; font-size: 13px;
            }
            QPushButton:checked { background-color: #e0f0ff; }
            QPushButton:hover { background-color: #e0f0ff; }
            QPushButton:pressed { background-color: #d0e0ff; }
        """)
        self.chapter_range_btn.clicked.connect(self.toggle_chapter_range)
        range_header = QHBoxLayout()
        range_header.addWidget(self.chapter_range_btn)
        range_header.addStretch(1)
        range_layout.addLayout(range_header)

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
        self.chapter_range_container.hide()
        form_layout.addRow("", range_layout)

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
                background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                border-radius: 6px; padding: 6px 12px; font-size: 13px;
            }
            QPushButton:hover { background-color: #e0f0ff; }
            QPushButton:pressed { background-color: #d0e0ff; }
        """)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(browse_btn)
        form_layout.addRow(QLabel("Output Directory:"), output_layout)
        content_layout.addWidget(form_widget)

        progress_card = QFrame()
        progress_card.setFrameShape(QFrame.StyledPanel)
        progress_card.setStyleSheet("""
            QFrame {
                background-color: #f9f9f9; border: 1px solid #e0e0e0;
                border-radius: 6px; padding: 12px;
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
                border: 1px solid #ccc; border-radius: 4px; text-align: center; height: 20px;
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
                background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                border-radius: 6px; padding: 6px 12px; font-size: 13px;
            }
            QPushButton:hover { background-color: #e0f0ff; }
            QPushButton:pressed { background-color: #d0e0ff; }
        """)
        self.toggle_log_btn = QPushButton("Collapse Log")
        self.toggle_log_btn.setIcon(self.qta.icon('fa5s.chevron-up', color='#555'))
        self.toggle_log_btn.clicked.connect(self.toggle_log)
        self.toggle_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                border-radius: 6px; padding: 6px 12px; font-size: 13px;
            }
            QPushButton:hover { background-color: #e0f0ff; }
            QPushButton:pressed { background-color: #d0e0ff; }
        """)
        progress_buttons_layout.addWidget(self.chapter_progress_btn)
        progress_buttons_layout.addWidget(self.toggle_log_btn)
        progress_layout.addLayout(progress_buttons_layout)
        content_layout.addWidget(progress_card)

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
                background-color: #f8f8f8; border: 1px solid #ddd; border-radius: 4px; padding: 6px;
            }
        """)
        content_layout.addWidget(self.log_area)

        scroll_area = QScrollArea()
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

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
                background-color: #4a86e8; color: #ffffff; font-weight: bold; border: 1px solid #3366cc;
                border-radius: 6px; padding: 10px 20px; font-size: 14px;
            }
            QPushButton:hover { background-color: #3b78de; border: 1px solid #3366cc; }
            QPushButton:pressed { background-color: #3366cc; border: 1px solid #3366cc; }
            QPushButton:disabled { background-color: #a0c0e8; color: #ffffff; border: 1px solid #a0c0e8; }
        """)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setIcon(self.qta.icon('fa5s.times', color='white'))
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336; color: #ffffff; font-weight: bold; border: 1px solid #c62828;
                border-radius: 6px; padding: 10px 20px; font-size: 14px;
            }
            QPushButton:hover { background-color: #d32f2f; border: 1px solid #c62828; }
            QPushButton:pressed { background-color: #c62828; border: 1px solid #c62828; }
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
                QMessageBox { background-color: white; }
                QPushButton {
                    background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                    border-radius: 6px; padding: 6px 12px; font-size: 13px;
                }
                QPushButton:hover { background-color: #e0f0ff; }
                QPushButton:pressed { background-color: #d0e0ff; }
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
                QMessageBox { background-color: white; }
                QPushButton {
                    background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                    border-radius: 6px; padding: 6px 12px; font-size: 13px;
                }
                QPushButton:hover { background-color: #e0f0ff; }
                QPushButton:pressed { background-color: #d0e0ff; }
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
            QMessageBox { background-color: white; }
            QPushButton {
                background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                border-radius: 6px; padding: 6px 12px; font-size: 13px;
            }
            QPushButton:hover { background-color: #e0f0ff; }
            QPushButton:pressed { background-color: #d0e0ff; }
        """)
        msg_box.exec_()

    def start_translation(self):
        if not self.validate_inputs():
            return
        start_chapter = self.start_spin.value() if self.chapter_range_btn.isChecked() else None
        end_chapter = self.end_spin.value() if self.chapter_range_btn.isChecked() else None
        params = {
            'task_type': 'web',
            'book_url': self.url_edit.text(),
            'model_name': self.model_combo.currentText(),
            'prompt_style': self.style_combo.currentData(),
            'start_chapter': start_chapter,
            'end_chapter': end_chapter,
            'output_directory': self.output_edit.text(),
        }
        self.current_history_id = HistoryManager.add_task({
            "timestamp": datetime.datetime.now().isoformat(),
            "task_type": "web",
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
        params['task_id'] = self.current_history_id
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
                    background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                    border-radius: 6px; padding: 8px 16px; font-size: 13px;
                }
                QPushButton:hover { background-color: #e0f0ff; }
                QPushButton:pressed { background-color: #d0e0ff; }
            """)
            close_button = QPushButton("Close")
            close_button.setStyleSheet("""
                QPushButton {
                    background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                    border-radius: 6px; padding: 8px 16px; font-size: 13px;
                }
                QPushButton:hover { background-color: #e0f0ff; }
                QPushButton:pressed { background-color: #d0e0ff; }
            """)
            msg_box.addButton(open_button, QMessageBox.ActionRole)
            msg_box.addButton(close_button, QMessageBox.RejectRole)
            msg_box.setStyleSheet("""
                QMessageBox { background-color: white; }
                QLabel { margin-bottom: 10px; }
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
                QMessageBox { background-color: white; }
                QPushButton {
                    background-color: #f0f8ff; color: #333333; border: 1px solid #ccc;
                    border-radius: 6px; padding: 6px 12px; font-size: 13px;
                }
                QPushButton:hover { background-color: #e0f0ff; }
                QPushButton:pressed { background-color: #d0e0ff; }
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
        self.start_btn.setEnabled(True)
        self.start_btn.setText("Start Translation")
        self.start_btn.setIcon(self.qta.icon('fa5s.play', color='white'))
        self.progress_bar.setValue(0)
        self.stage_label.setText("Current Stage: Idle")
