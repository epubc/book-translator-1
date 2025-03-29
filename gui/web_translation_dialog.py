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
from gui.ui_styles import ButtonStyles, WidgetStyles
from gui.progress_dialog import EnhancedProgressDialog
from gui.source_info_dialog import SourceInfoDialog
from downloader.factory import DownloaderFactory
import qtawesome as qta
from PyQt5.QtCore import QSettings


class WebTranslationDialog(QDialog):
    active_instance = None

    @classmethod
    def get_instance(cls, parent=None):
        if cls.active_instance is None or sip.isdeleted(cls.active_instance):
            cls.active_instance = WebTranslationDialog(parent)
        return cls.active_instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translate from URL")
        self.setMinimumSize(650, 550)
        self.thread = None
        self.log_handler = None
        self.current_history_id = None
        self.qta = qta
        self.settings = QSettings("NovelTranslator", "Config")
        self.init_ui()
        self.setup_logging()
        self.load_default_settings()
        self.setWindowModality(Qt.NonModal)
        WebTranslationDialog.active_instance = self

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
        title_label.setStyleSheet(WidgetStyles.get_title_label_style("primary"))
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        content_layout.addLayout(title_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet(WidgetStyles.get_separator_style())
        content_layout.addWidget(separator)

        # Form layout
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 10, 0, 10)
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # URL input with Source Info button
        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Enter book URL")
        self.url_edit.setMinimumHeight(30)
        self.url_edit.setStyleSheet(WidgetStyles.get_input_style("primary"))
        self.source_info_btn = QPushButton("Source Info")
        self.source_info_btn.setIcon(self.qta.icon('fa5s.info-circle', color='#4a86e8'))
        self.source_info_btn.setFixedWidth(120)
        self.source_info_btn.clicked.connect(self.show_source_info)
        self.source_info_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        url_layout.addWidget(self.url_edit, 1)
        url_layout.addWidget(self.source_info_btn)
        form_layout.addRow(QLabel("Book URL:"), url_layout)

        # Model selection (unchanged)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash-thinking", "gemini-2.5-pro"])
        self.model_combo.setMinimumHeight(30)
        self.model_combo.setMinimumWidth(200)
        self.model_combo.setStyleSheet(WidgetStyles.get_combo_box_style("primary"))
        form_layout.addRow(QLabel("Model:"), self.model_combo)

        # Style selection (unchanged)
        self.style_combo = QComboBox()
        self.style_combo.addItem("Modern Style", 1)
        self.style_combo.addItem("China Fantasy Style", 2)
        self.style_combo.setMinimumHeight(30)
        self.style_combo.setMinimumWidth(200)
        self.style_combo.setStyleSheet(WidgetStyles.get_combo_box_style("primary"))
        form_layout.addRow(QLabel("Style:"), self.style_combo)

        # Chapter range
        range_layout = QVBoxLayout()
        self.chapter_range_btn = QPushButton("Set Chapter Range")
        self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#555'))
        self.chapter_range_btn.setCheckable(True)
        self.chapter_range_btn.setStyleSheet(ButtonStyles.get_secondary_style() + WidgetStyles.get_checkable_button_style())
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
        self.start_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        chapter_range_inner.addRow(QLabel("Start Chapter:"), self.start_spin)

        self.end_spin = QSpinBox()
        self.end_spin.setRange(1, 9999)
        self.end_spin.setValue(1)
        self.end_spin.setMinimumHeight(28)
        self.end_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        chapter_range_inner.addRow(QLabel("End Chapter:"), self.end_spin)

        range_layout.addWidget(self.chapter_range_container)
        self.chapter_range_container.hide()
        form_layout.addRow("", range_layout)

        # Output directory with Browse button
        output_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setText(str(Path.home() / "Downloads"))
        self.output_edit.setMinimumHeight(30)
        self.output_edit.setStyleSheet(WidgetStyles.get_input_style("primary"))
        browse_btn = QPushButton("Browse")
        browse_btn.setIcon(self.qta.icon('fa5s.folder-open', color='#555'))
        browse_btn.clicked.connect(self.choose_directory)
        browse_btn.setFixedWidth(100)
        browse_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(browse_btn)
        form_layout.addRow(QLabel("Output Directory:"), output_layout)
        content_layout.addWidget(form_widget)

        # Progress card
        progress_card = QFrame()
        progress_card.setFrameShape(QFrame.StyledPanel)
        progress_card.setStyleSheet(WidgetStyles.get_frame_style("neutral"))
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setSpacing(10)

        # Progress header
        progress_header = QHBoxLayout()
        progress_icon = QLabel()
        progress_icon.setPixmap(self.qta.icon('fa5s.tasks', color='#4a86e8').pixmap(20, 20))
        progress_header_label = QLabel("Progress")
        progress_header_label.setStyleSheet(WidgetStyles.get_header_label_style("primary"))
        progress_header.addWidget(progress_icon)
        progress_header.addWidget(progress_header_label)
        progress_header.addStretch(1)
        progress_layout.addLayout(progress_header)

        # Stage info
        stage_layout = QHBoxLayout()
        stage_icon = QLabel()
        stage_icon.setPixmap(self.qta.icon('fa5s.info-circle', color='#555').pixmap(16, 16))
        self.stage_label = QLabel("Current Stage: Idle")
        stage_layout.addWidget(stage_icon)
        stage_layout.addWidget(self.stage_label)
        stage_layout.addStretch(1)
        progress_layout.addLayout(stage_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(WidgetStyles.get_progress_bar_style("primary"))
        progress_layout.addWidget(self.progress_bar)

        # Progress buttons
        progress_buttons_layout = QHBoxLayout()
        self.chapter_progress_btn = QPushButton("Chapter Progress")
        self.chapter_progress_btn.setIcon(self.qta.icon('fa5s.chart-bar', color='#555'))
        self.chapter_progress_btn.clicked.connect(self.show_chapter_progress)
        self.chapter_progress_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        self.toggle_log_btn = QPushButton("Collapse Log")
        self.toggle_log_btn.setIcon(self.qta.icon('fa5s.chevron-up', color='#555'))
        self.toggle_log_btn.clicked.connect(self.toggle_log)
        self.toggle_log_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        progress_buttons_layout.addWidget(self.chapter_progress_btn)
        progress_buttons_layout.addWidget(self.toggle_log_btn)
        progress_layout.addLayout(progress_buttons_layout)
        content_layout.addWidget(progress_card)

        log_header = QHBoxLayout()
        log_icon = QLabel()
        log_icon.setPixmap(self.qta.icon('fa5s.terminal', color='#4a86e8').pixmap(16, 16))
        log_header_label = QLabel("Progress Log")
        log_header_label.setStyleSheet(WidgetStyles.get_header_label_style("primary"))
        log_header.addWidget(log_icon)
        log_header.addWidget(log_header_label)
        log_header.addStretch(1)
        content_layout.addLayout(log_header)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(150)
        self.log_area.setFont(QFont("Consolas", 10))
        self.log_area.setStyleSheet(WidgetStyles.get_text_edit_style("neutral"))
        content_layout.addWidget(self.log_area)

        # Scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

        # Main buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        btn_layout.addStretch(1)

        self.start_btn = QPushButton("Start Translation")
        self.start_btn.setIcon(self.qta.icon('fa5s.play', color='white'))
        self.start_btn.clicked.connect(self.start_translation)
        self.start_btn.setMinimumWidth(160)
        self.start_btn.setMinimumHeight(36)
        self.start_btn.setStyleSheet(ButtonStyles.get_primary_style())

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setIcon(self.qta.icon('fa5s.times', color='white'))
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setStyleSheet(ButtonStyles.get_danger_style())

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
            message_box.setStyleSheet(WidgetStyles.get_message_box_style())
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
            # Instead of rejecting (which closes dialog), just hide the dialog
            self.hide()

    def choose_directory(self):
        # Explicitly specify the parent and options to ensure dialog stays on top
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Output Directory",
            options=QFileDialog.DontUseNativeDialog
        )
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
        msg_box.setStyleSheet(WidgetStyles.get_message_box_style())
        msg_box.exec_()

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
        # Unregister task from active tasks
        if self.current_history_id:
            HistoryManager.unregister_active_task(self.current_history_id)

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
            open_button.setStyleSheet(WidgetStyles.get_action_button_style())
            close_button = QPushButton("Close")
            close_button.setStyleSheet(WidgetStyles.get_action_button_style())
            msg_box.addButton(open_button, QMessageBox.ActionRole)
            msg_box.addButton(close_button, QMessageBox.RejectRole)
            msg_box.setStyleSheet(WidgetStyles.get_success_message_style())
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
            msg_box.setStyleSheet(WidgetStyles.get_message_box_style())
            msg_box.exec_()
        if self.current_history_id:
            HistoryManager.update_task(self.current_history_id, {"status": "Success" if success else "Error"})

    def closeEvent(self, event):
        active_task_count = HistoryManager.get_active_task_count()

        if active_task_count > 0:
            event.ignore()
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Operations in Progress")

            if active_task_count == 1 and self.thread and self.thread.isRunning():
                # Just our task is running
                msg_box.setText("Translation is in progress. What would you like to do?")
                continue_btn = msg_box.addButton("Continue in Background", QMessageBox.ActionRole)
                stop_btn = msg_box.addButton("Stop and Close", QMessageBox.DestructiveRole)
                cancel_btn = msg_box.addButton("Cancel", QMessageBox.RejectRole)

                continue_btn.setIcon(self.qta.icon('fa5s.external-link-alt', color='#4a86e8'))
                stop_btn.setIcon(self.qta.icon('fa5s.stop', color='#f44336'))
                cancel_btn.setIcon(self.qta.icon('fa5s.times', color='#555'))
            else:
                # Multiple tasks are running
                msg_box.setText(f"{active_task_count} translations are in progress. What would you like to do?")
                continue_btn = msg_box.addButton("Continue All in Background", QMessageBox.ActionRole)
                stop_btn = msg_box.addButton("Stop All and Close", QMessageBox.DestructiveRole)
                cancel_btn = msg_box.addButton("Cancel", QMessageBox.RejectRole)

                continue_btn.setIcon(self.qta.icon('fa5s.external-link-alt', color='#4a86e8'))
                stop_btn.setIcon(self.qta.icon('fa5s.stop', color='#f44336'))
                cancel_btn.setIcon(self.qta.icon('fa5s.times', color='#555'))

            msg_box.setDefaultButton(continue_btn)
            msg_box.setStyleSheet(WidgetStyles.get_message_box_style())

            reply = msg_box.exec_()

            if msg_box.clickedButton() == continue_btn:
                # Detach from current thread but keep it running
                if self.thread and self.thread.isRunning():
                    # Disconnect all signals but don't stop the thread
                    try:
                        self.thread.update_log.disconnect(self.update_log)
                        self.thread.finished.disconnect(self.on_finished)
                        self.thread.stage_update.disconnect(self.on_stage_update)
                        self.thread.update_progress.disconnect(self.on_progress_update)
                    except (TypeError, RuntimeError):
                        pass  # Signals may already be disconnected

                # Close the dialog but let tasks continue
                logging.root.removeHandler(self.log_handler)
                WebTranslationDialog.active_instance = None
                super().closeEvent(event)
                self.deleteLater()
            elif msg_box.clickedButton() == stop_btn:
                # Stop all tasks
                HistoryManager.stop_all_active_tasks()
                self.log_area.append("Stopping all translation tasks...")

                # Give a moment for tasks to clean up
                QMessageBox.information(self, "Stopping Tasks",
                                        "Stopping all translation tasks. Please wait a moment...")

                # Actually close
                logging.root.removeHandler(self.log_handler)
                WebTranslationDialog.active_instance = None
                super().closeEvent(event)
                self.deleteLater()
            else:  # User clicked Cancel
                pass  # Don't close
        else:
            # No tasks running, close normally
            logging.root.removeHandler(self.log_handler)
            WebTranslationDialog.active_instance = None
            super().closeEvent(event)
            self.deleteLater()

    def show_chapter_progress(self):
        file_handler = None
        start_chapter = self.start_spin.value() if self.chapter_range_btn.isChecked() else None
        end_chapter = self.end_spin.value() if self.chapter_range_btn.isChecked() else None
        
        if self.thread and self.thread.file_handler:
            # Use the existing thread's file handler
            file_handler = self.thread.file_handler
        else:
            # No active thread, try to get book_dir from task history
            from pathlib import Path
            from translator.file_handler import FileHandler
            
            book_dir = None
            
            # Try to get book_dir from current task history if we have a task ID
            if self.current_history_id:
                task = HistoryManager.get_task_by_id(self.current_history_id)
                if task and "book_dir" in task:
                    book_dir_str = task.get("book_dir")
                    potential_book_dir = Path(book_dir_str)
                    if potential_book_dir.exists() and potential_book_dir.is_dir():
                        book_dir = potential_book_dir
            
            # If we couldn't get book_dir from history, try to find it in output directory
            if not book_dir and hasattr(self, 'output_edit') and self.output_edit.text().strip():
                output_dir = Path(self.output_edit.text().strip())
                
                # Look for any subdirectory with a progress.json file
                for subdir in output_dir.glob("*"):
                    if subdir.is_dir() and (subdir / "progress.json").exists():
                        book_dir = subdir
                        break
            
            # Create file handler if we found a valid book directory
            if book_dir:
                file_handler = FileHandler(book_dir)
        
        if not file_handler:
            # No file handler available
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Information")
            msg_box.setText("No progress data found. Please ensure you've selected a valid output directory containing book data.")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setStyleSheet(WidgetStyles.get_message_box_style())
            msg_box.exec_()
            return
        
        def status_getter():
            return file_handler.get_chapter_status(start_chapter, end_chapter)
            
        dialog = EnhancedProgressDialog(status_getter, self, file_handler)
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

    def start_translation(self):
        if not self.validate_inputs():
            return

        # If there's already a thread running, stop it
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.log_area.append("Stopping previous translation...")

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
            'author': 'Unknown',  # Default author until we get it from the downloader
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
            "author": "Unknown",  # Default author until we get it from the downloader
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

        # Register this task as active with the HistoryManager
        HistoryManager.register_active_task(self.current_history_id, self.thread)

        self.thread.start()

    def load_task(self, task):
        task_id = task.get("id")

        # Check if this task is already running
        if HistoryManager.is_task_active(task_id):
            # If it's the same as our current task, just update UI
            if self.current_history_id == task_id and self.thread and self.thread.isRunning():
                self.log_area.append("Task is already running.")
                return

            # If it's a different task that's running, ask user what to do
            message_box = QMessageBox(self)
            message_box.setWindowTitle('Task In Progress')
            message_box.setText('This task is already running in another window. What would you like to do?')
            message_box.setIcon(QMessageBox.Question)

            connect_btn = message_box.addButton("Connect to Task", QMessageBox.ActionRole)
            stop_btn = message_box.addButton("Stop Current Task", QMessageBox.DestructiveRole)
            cancel_btn = message_box.addButton("Cancel", QMessageBox.RejectRole)

            connect_btn.setIcon(self.qta.icon('fa5s.link', color='#4a86e8'))
            stop_btn.setIcon(self.qta.icon('fa5s.stop', color='#f44336'))
            cancel_btn.setIcon(self.qta.icon('fa5s.times', color='#555'))

            message_box.setDefaultButton(connect_btn)
            message_box.setStyleSheet(WidgetStyles.get_message_box_style())

            reply = message_box.exec_()

            if message_box.clickedButton() == stop_btn:
                # Stop the existing task
                HistoryManager.stop_task_if_active(task_id)
                self.log_area.append(f"Stopped task: {task_id}")
            elif message_box.clickedButton() == cancel_btn:
                return
            # else: connect to the task

        # If we have an active thread, disconnect and clean up
        if self.thread and self.thread.isRunning() and self.current_history_id != task_id:
            # Disconnect signals
            self.thread.update_log.disconnect(self.update_log)
            self.thread.finished.disconnect(self.on_finished)
            self.thread.stage_update.disconnect(self.on_stage_update)
            self.thread.update_progress.disconnect(self.on_progress_update)

            self.log_area.append("Disconnected from previous task.")

        # Set form fields
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

        # Update the UI based on task status
        status = task.get("status", "Idle")
        progress = task.get("progress", 0)
        current_stage = task.get("current_stage", "Idle")

        # Update UI based on task status
        self.current_history_id = task_id
        self.progress_bar.setValue(progress)
        self.stage_label.setText(f"Current Stage: {current_stage}")

        # Try to connect to existing thread if task is active
        if HistoryManager.is_task_active(task_id):
            active_thread = HistoryManager._active_tasks.get(task_id)
            if active_thread:
                self.thread = active_thread
                self.log_area.clear()
                self.log_area.append(f"Connected to running task: {task_id}")
                self.log_area.append(f"Current stage: {current_stage}")

                # Connect signals
                self.thread.update_log.connect(self.update_log)
                self.thread.finished.connect(self.on_finished)
                self.thread.stage_update.connect(self.on_stage_update)
                self.thread.update_progress.connect(self.on_progress_update)

                # Update UI
                self.start_btn.setEnabled(False)
                self.start_btn.setText("Translating...")
                self.start_btn.setIcon(
                    self.qta.icon('fa5s.spinner', color='white', animation=self.qta.Spin(self.start_btn)))
            else:
                # Something's wrong with tracking
                self.log_area.append("Warning: Task marked active but thread not found!")
                self.start_btn.setEnabled(True)
                self.start_btn.setText("Start Translation")
                self.start_btn.setIcon(self.qta.icon('fa5s.play', color='white'))
        elif status == "In Progress":
            # Task is marked as in progress but not tracked as active - might have crashed
            self.log_area.append("Warning: Task was in progress but is no longer running. It may have crashed.")
            self.start_btn.setEnabled(True)
            self.start_btn.setText("Restart Translation")
            self.start_btn.setIcon(self.qta.icon('fa5s.redo', color='white'))
        else:
            # Normal inactive task
            self.start_btn.setEnabled(True)
            self.start_btn.setText("Start Translation")
            self.start_btn.setIcon(self.qta.icon('fa5s.play', color='white'))
            if status == "Success":
                self.log_area.append("This task completed successfully.")
            elif status == "Error":
                self.log_area.append("This task completed with errors.")

    def load_default_settings(self):
        """Load default settings from QSettings"""
        # Set default model
        default_model = self.settings.value("DefaultModel", "gemini-2.0-flash")
        index = self.model_combo.findText(default_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

        # Set default style
        default_style = self.settings.value("DefaultStyle", 1, type=int)
        index = self.style_combo.findData(default_style)
        if index >= 0:
            self.style_combo.setCurrentIndex(index)

        # Set default output directory
        default_output_dir = self.settings.value("DefaultOutputDir", str(Path.home() / "Downloads"))
        self.output_edit.setText(default_output_dir)
