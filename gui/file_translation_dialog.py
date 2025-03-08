import logging
from PyQt5 import sip
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QComboBox, QSpinBox, QTextEdit, QProgressBar, QScrollArea, QFrame,
                             QMessageBox, QFileDialog, QWidget, QFormLayout, QRadioButton, QButtonGroup)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QUrl, QSettings
from PyQt5.QtGui import QFont, QTextCursor, QDesktopServices
import datetime
from pathlib import Path
from core.translation_thread import TranslationThread
from core.history_manager import HistoryManager
from core.utils import QTextEditLogHandler
from gui.ui_styles import WidgetStyles, ButtonStyles
from gui.progress_dialog import EnhancedProgressDialog
import qtawesome as qta

class FileTranslationDialog(QDialog):
    active_instance = None

    @classmethod
    def get_instance(cls, parent=None):
        if cls.active_instance is None or sip.isdeleted(cls.active_instance):
            cls.active_instance = FileTranslationDialog(parent)
        return cls.active_instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translate from File")
        self.setMinimumSize(650, 550)
        self.file_path = None
        self.input_type = "file"  # Can be "file" or "folder"
        self.thread = None
        self.log_handler = None
        self.current_history_id = None
        self.qta = qta
        self.settings = QSettings("NovelTranslator", "Config")
        self.init_ui()
        self.setup_logging()
        self.load_default_settings()
        self.setWindowModality(Qt.NonModal)
        FileTranslationDialog.active_instance = self

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

        # Title layout
        title_layout = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(self.qta.icon('fa5s.book-reader', color='#4a86e8').pixmap(32, 32))
        title_label = QLabel("File Translator")
        title_label.setStyleSheet(WidgetStyles.get_title_label_style("primary"))
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)
        content_layout.addLayout(title_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet(WidgetStyles.get_separator_style("neutral"))
        content_layout.addWidget(separator)

        # Form layout
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 10, 0, 10)
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # Input type selection
        input_type_layout = QHBoxLayout()
        self.file_radio = QRadioButton("Single File")
        self.file_radio.setChecked(True)
        self.file_radio.toggled.connect(self.toggle_input_type)
        self.folder_radio = QRadioButton("Folder (Each file as chapter)")
        self.folder_radio.toggled.connect(self.toggle_input_type)
        input_type_layout.addWidget(self.file_radio)
        input_type_layout.addWidget(self.folder_radio)
        input_type_layout.addStretch(1)
        input_type_label = QLabel("Input Type:")
        input_type_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        form_layout.addRow(input_type_label, input_type_layout)

        # File selection layout
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setMinimumHeight(30)
        self.file_edit.setStyleSheet(WidgetStyles.get_input_style("primary"))
        self.select_file_btn = QPushButton("Select File")
        self.select_file_btn.setIcon(self.qta.icon('fa5s.folder-open', color='#555'))
        self.select_file_btn.clicked.connect(self.select_file)
        self.select_file_btn.setFixedWidth(120)
        self.select_file_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        self.select_folder_btn = QPushButton("Select Folder")
        self.select_folder_btn.setIcon(self.qta.icon('fa5s.folder-open', color='#555'))
        self.select_folder_btn.clicked.connect(self.select_folder)
        self.select_folder_btn.setFixedWidth(120)
        self.select_folder_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        self.select_folder_btn.hide()  # Initially hidden
        file_layout.addWidget(self.file_edit, 1)
        file_layout.addWidget(self.select_file_btn)
        file_layout.addWidget(self.select_folder_btn)
        self.file_path_label = QLabel("File Path:")
        self.file_path_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        form_layout.addRow(self.file_path_label, file_layout)

        # Book title
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Enter book title")
        self.title_edit.setMinimumHeight(30)
        self.title_edit.setStyleSheet(WidgetStyles.get_input_style("primary"))
        title_label = QLabel("Book Title:")
        title_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        form_layout.addRow(title_label, self.title_edit)

        # Book author
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("Enter book author")
        self.author_edit.setMinimumHeight(30)
        self.author_edit.setStyleSheet(WidgetStyles.get_input_style("primary"))
        author_label = QLabel("Book Author:")
        author_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        form_layout.addRow(author_label, self.author_edit)

        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gemini-2.0-flash", "gemini-2.0-flash-lite"])
        self.model_combo.setMinimumHeight(30)
        self.model_combo.setMinimumWidth(200)
        self.model_combo.setStyleSheet(WidgetStyles.get_combo_box_style("primary"))
        model_label = QLabel("Model:")
        model_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        form_layout.addRow(model_label, self.model_combo)

        # Style selection
        self.style_combo = QComboBox()
        self.style_combo.addItem("Modern Style", 1)
        self.style_combo.addItem("China Fantasy Style", 2)
        self.style_combo.setMinimumHeight(30)
        self.style_combo.setMinimumWidth(200)
        self.style_combo.setStyleSheet(WidgetStyles.get_combo_box_style("primary"))
        style_label = QLabel("Style:")
        style_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        form_layout.addRow(style_label, self.style_combo)

        # Chapter range
        range_layout = QVBoxLayout()
        self.chapter_range_btn = QPushButton("Set Chapter Range")
        self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#555'))
        self.chapter_range_btn.setCheckable(True)
        self.chapter_range_btn.setStyleSheet(
            ButtonStyles.get_secondary_style() + WidgetStyles.get_checkable_button_style()
        )
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
        start_label = QLabel("Start Chapter:")
        start_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        chapter_range_inner.addRow(start_label, self.start_spin)
        self.end_spin = QSpinBox()
        self.end_spin.setRange(1, 9999)
        self.end_spin.setValue(1)
        self.end_spin.setMinimumHeight(28)
        self.end_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        end_label = QLabel("End Chapter:")
        end_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        chapter_range_inner.addRow(end_label, self.end_spin)
        range_layout.addWidget(self.chapter_range_container)
        self.chapter_range_container.hide()
        form_layout.addRow("", range_layout)

        # Output directory
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
        output_label = QLabel("Output Directory:")
        output_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        form_layout.addRow(output_label, output_layout)
        content_layout.addWidget(form_widget)

        # Progress card
        progress_card = QFrame()
        progress_card.setFrameShape(QFrame.StyledPanel)
        progress_card.setStyleSheet(WidgetStyles.get_frame_style("neutral"))
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setSpacing(10)
        progress_header = QHBoxLayout()
        progress_icon = QLabel()
        progress_icon.setPixmap(self.qta.icon('fa5s.tasks', color='#4a86e8').pixmap(20, 20))
        progress_header_label = QLabel("Progress")
        progress_header_label.setStyleSheet(WidgetStyles.get_header_label_style("primary"))
        progress_header.addWidget(progress_icon)
        progress_header.addWidget(progress_header_label)
        progress_header.addStretch(1)
        progress_layout.addLayout(progress_header)
        stage_layout = QHBoxLayout()
        stage_icon = QLabel()
        stage_icon.setPixmap(self.qta.icon('fa5s.info-circle', color='#555').pixmap(16, 16))
        self.stage_label = QLabel("Current Stage: Idle")
        self.stage_label.setStyleSheet(WidgetStyles.get_label_style("primary"))
        stage_layout.addWidget(stage_icon)
        stage_layout.addWidget(self.stage_label)
        stage_layout.addStretch(1)
        progress_layout.addLayout(stage_layout)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(WidgetStyles.get_progress_bar_style("primary"))
        progress_layout.addWidget(self.progress_bar)
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

        # Log area
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

        # Main layout setup
        scroll_area = QScrollArea()
        scroll_area.setWidget(content_widget)
        scroll_area.setWidgetResizable(True)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

        # Bottom buttons
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

    def toggle_input_type(self):
        """Toggle between file and folder input types."""
        if self.file_radio.isChecked():
            self.input_type = "file"
            self.file_path_label.setText("File Path:")
            self.select_file_btn.show()
            self.select_folder_btn.hide()
            self.chapter_range_btn.setEnabled(True)
        else:  # Folder is selected
            self.input_type = "folder"
            self.file_path_label.setText("Folder Path:")
            self.select_file_btn.hide()
            self.select_folder_btn.show()
            # Disable chapter range for folder input as each file is a chapter
            self.chapter_range_btn.setChecked(False)
            self.chapter_range_container.hide()
            self.chapter_range_btn.setEnabled(False)

    def toggle_chapter_range(self):
        if self.chapter_range_btn.isChecked():
            self.chapter_range_container.show()
            self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#4a86e8'))
        else:
            self.chapter_range_container.hide()
            self.chapter_range_btn.setIcon(self.qta.icon('fa5s.list-ol', color='#555'))

    def select_folder(self):
        """Open dialog to select a folder containing chapter files."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder with Chapter Files",
            "",
            options=QFileDialog.DontUseNativeDialog
        )
        if folder_path:
            self.file_path = folder_path
            self.file_edit.setText(folder_path)

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

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            event.ignore()
            message_box = QMessageBox(self)
            message_box.setWindowTitle("Operation in Progress")
            message_box.setText("Please cancel the current translation before closing.")
            message_box.setIcon(QMessageBox.Warning)
            message_box.setStandardButtons(QMessageBox.Ok)
            message_box.setStyleSheet(WidgetStyles.get_message_box_style())
            message_box.exec_()
        else:
            logging.root.removeHandler(self.log_handler)
            FileTranslationDialog.active_instance = None
            super().closeEvent(event)
            self.deleteLater()

    def choose_directory(self):
        # Explicitly specify the parent and options to ensure dialog stays on top
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Output Directory",
            options=QFileDialog.DontUseNativeDialog
        )
        if directory:
            self.output_edit.setText(directory)

    def select_file(self):
        # Explicitly specify the parent and options to ensure dialog stays on top
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Text File", 
            "", 
            "Text Files (*.txt)",
            options=QFileDialog.DontUseNativeDialog
        )
        if file_path:
            self.file_path = file_path
            self.file_edit.setText(file_path)

    def set_file_path(self, file_path):
        self.file_path = file_path
        self.file_edit.setText(file_path)

    def validate_inputs(self):
        if not self.file_path:
            self.show_error_message("Input Error", 
                f"Please select a {'folder' if self.input_type == 'folder' else 'file'} first.")
            return False

        if self.input_type == "folder":
            folder_path = Path(self.file_path)
            if not folder_path.is_dir():
                self.show_error_message("Folder Error", "Selected path is not a valid folder.")
                return False
            
            # Check if folder contains text files
            txt_files = list(folder_path.glob("*.txt"))
            if not txt_files:
                self.show_error_message("Folder Error", "Selected folder doesn't contain any .txt files.")
                return False

        else:  # file mode
            file_path = Path(self.file_path)
            if not file_path.is_file():
                self.show_error_message("File Error", "Selected file does not exist.")
                return False
            
            if file_path.suffix.lower() != ".txt":
                self.show_error_message("File Error", "Selected file must be a .txt file.")
                return False

        if not self.title_edit.text().strip():
            self.show_error_message("Input Error", "Please enter a book title.")
            return False
            
        if self.chapter_range_btn.isChecked():
            start_chapter = self.start_spin.value()
            end_chapter = self.end_spin.value()
            if start_chapter > end_chapter:
                self.show_error_message("Chapter Range Error",
                                     "Start chapter cannot be greater than end chapter.")
                return False

        output_dir = Path(self.output_edit.text())
        if not output_dir.exists() or not output_dir.is_dir():
            self.show_error_message("Output Error", "Output directory does not exist.")
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

    def start_translation(self):
        if not self.validate_inputs():
            return
        start_chapter = self.start_spin.value() if self.chapter_range_btn.isChecked() else None
        end_chapter = self.end_spin.value() if self.chapter_range_btn.isChecked() else None
        params = {
            'task_type': 'file',
            'file_path': self.file_path,
            'input_type': self.input_type,  # Add input_type parameter
            'book_title': self.title_edit.text().strip(),
            'author': self.author_edit.text().strip() or 'Unknown',
            'model_name': self.model_combo.currentText(),
            'prompt_style': self.style_combo.currentData(),
            'start_chapter': start_chapter,
            'end_chapter': end_chapter,
            'output_directory': self.output_edit.text(),
        }
        self.current_history_id = HistoryManager.add_task({
            "timestamp": datetime.datetime.now().isoformat(),
            "task_type": "file",
            "file_path": self.file_path,
            "input_type": self.input_type,  # Add input_type to history
            "book_title": self.title_edit.text().strip(),
            "author": self.author_edit.text().strip() or 'Unknown',
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
            
            # If we couldn't get book_dir from history, try to find it
            if not book_dir and hasattr(self, 'output_edit') and self.output_edit.text().strip():
                output_dir = Path(self.output_edit.text().strip())
                
                # Try to find book directory based on title
                if self.title_edit.text().strip():
                    sanitized_title = self.title_edit.text().strip().replace('/', '_').replace('\\', '_')
                    potential_book_dir = output_dir / sanitized_title
                    if potential_book_dir.exists() and potential_book_dir.is_dir():
                        book_dir = potential_book_dir
                
                # If still not found, search for any book directories with progress.json
                if not book_dir:
                    for subdir in output_dir.glob("*"):
                        if subdir.is_dir() and (subdir / "progress.json").exists():
                            book_dir = subdir
                            break
            
            # Create file handler if we found a valid book directory
            if book_dir:
                file_handler = FileHandler(book_dir, start_chapter, end_chapter)
        
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

    def load_task(self, task):
        self.file_path = task.get("file_path", "")
        self.file_edit.setText(self.file_path)
        self.title_edit.setText(task.get("book_title", ""))
        self.author_edit.setText(task.get("author", ""))
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
