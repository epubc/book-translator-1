from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QTableWidget, QTableWidgetItem, QMessageBox, QFrame, QFormLayout, QDialogButtonBox)
from PyQt5.QtCore import Qt, QSize
import qtawesome as qta
from core.history_manager import HistoryManager
from gui.ui_styles import ButtonStyles
from gui.web_translation_dialog import WebTranslationDialog
from gui.file_translation_dialog import FileTranslationDialog
from text_processing.text_processing import normalize_unicode_text


class TranslationHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translation History")
        self.resize(900, 500)
        self.history_tasks = []
        self.init_ui()
        self.load_history()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header with title and search
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.StyledPanel)
        header_frame.setFrameShadow(QFrame.Raised)
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #f7f7f7;
                border-radius: 8px;
                border: 1px solid #ddd;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi.history", color="#505050").pixmap(32, 32))
        title_label = QLabel("<h2>Translation History</h2>")
        title_layout.addWidget(icon_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        header_layout.addLayout(title_layout)

        # Search layout
        search_layout = QHBoxLayout()
        search_icon = QLabel()
        search_icon.setPixmap(qta.icon("mdi.magnify", color="#505050").pixmap(18, 18))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by Title, Author, URL, or File Path")
        self.search_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #bbb;
                border-radius: 5px;
                padding: 8px;
                padding-left: 8px;
                background-color: white;
            }
            QLineEdit:focus {
                border: 1px solid #4CAF50;
            }
        """)
        self.search_edit.textChanged.connect(self.update_table)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_edit)
        header_layout.addLayout(search_layout)

        layout.addWidget(header_frame)

        # Table widget
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: white;
            }
        """)
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(5, 5, 5, 5)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Task Type", "Book Title", "Author", "Source", "Model", "Prompt Style",
                                              "Start Chapter", "End Chapter", "Output Directory", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                selection-background-color: #E8F5E9;
                selection-color: #2E7D32;
                gridline-color: #e0e0e0;
                border: none;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 8px;
                border: 1px solid #ddd;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 6px;
            }
        """)

        table_layout.addWidget(self.table)
        layout.addWidget(table_frame)

        # Buttons layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)  # Increased spacing between buttons
        btn_layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)  # Increased spacing between buttons
        btn_layout.addStretch()

        # Primary Button (Load)
        load_btn = QPushButton("Load Selected Task")
        load_btn.setIcon(qta.icon("mdi.folder-open", color="#FFFFFF"))
        load_btn.setIconSize(QSize(20, 20))
        load_btn.setStyleSheet(ButtonStyles.get_primary_style())
        load_btn.clicked.connect(self.load_selected_task)
        
        # Edit Button
        edit_btn = QPushButton("Edit Task")
        edit_btn.setIcon(qta.icon("mdi.pencil", color="#FFFFFF"))
        edit_btn.setIconSize(QSize(20, 20))
        edit_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        edit_btn.clicked.connect(self.edit_selected_task)

        # Danger Button (Remove)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.setIcon(qta.icon("mdi.delete", color="#FFFFFF"))
        remove_btn.setIconSize(QSize(20, 20))
        remove_btn.setStyleSheet(ButtonStyles.get_danger_style())
        remove_btn.clicked.connect(self.remove_selected_task)

        # Secondary Button (Refresh)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(qta.icon("mdi.refresh", color="#0D47A1"))
        refresh_btn.setIconSize(QSize(20, 20))
        refresh_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        refresh_btn.clicked.connect(self.load_history)

        # Neutral Button (Close)
        close_btn = QPushButton("Close")
        close_btn.setIcon(qta.icon("mdi.close", color="#424242"))
        close_btn.setIconSize(QSize(20, 20))
        close_btn.setStyleSheet(ButtonStyles.get_neutral_style())
        close_btn.clicked.connect(self.close)

        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()

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
            if search_text in normalize_unicode_text(task.get("book_title", "").lower())
               or search_text in normalize_unicode_text(task.get("author", "").lower())
               or (task.get('task_type') == 'web' and search_text in task.get("book_url", "").lower())
               or (task.get('task_type') == 'file' and search_text in task.get("file_path", "").lower())
        ]

        self.table.setRowCount(0)
        for task in display_tasks:
            rowPosition = self.table.rowCount()
            self.table.insertRow(rowPosition)

            timestamp_item = QTableWidgetItem(task.get("timestamp", ""))
            timestamp_item.setData(Qt.UserRole, task["id"])
            self.table.setItem(rowPosition, 0, timestamp_item)

            # Add task type with appropriate icon
            task_type = task.get("task_type", "")
            task_type_item = QTableWidgetItem(task_type)
            if task_type == "web":
                task_type_item.setIcon(qta.icon("mdi.web"))
            elif task_type == "file":
                task_type_item.setIcon(qta.icon("mdi.file-document"))
            self.table.setItem(rowPosition, 1, task_type_item)

            self.table.setItem(rowPosition, 2, QTableWidgetItem(task.get("book_title", "")))
            self.table.setItem(rowPosition, 3, QTableWidgetItem(task.get("author", "")))
            source = task.get("book_url", task.get("file_path", ""))
            self.table.setItem(rowPosition, 4, QTableWidgetItem(source))
            self.table.setItem(rowPosition, 5, QTableWidgetItem(task.get("model_name", "")))
            self.table.setItem(rowPosition, 6, QTableWidgetItem(str(task.get("prompt_style", ""))))
            self.table.setItem(rowPosition, 7, QTableWidgetItem(str(task.get("start_chapter", ""))))
            self.table.setItem(rowPosition, 8, QTableWidgetItem(str(task.get("end_chapter", ""))))
            self.table.setItem(rowPosition, 9, QTableWidgetItem(task.get("output_directory", "")))

            # Status with color coding
            status = task.get("status", "")
            status_item = QTableWidgetItem(status)
            if status == "Completed":
                status_item.setIcon(qta.icon("mdi.check-circle", color="green"))
                status_item.setForeground(Qt.green)
            elif status == "In Progress":
                status_item.setIcon(qta.icon("mdi.progress-clock", color="blue"))
                status_item.setForeground(Qt.blue)
            elif status == "Failed":
                status_item.setIcon(qta.icon("mdi.alert-circle", color="red"))
                status_item.setForeground(Qt.red)
            else:
                status_item.setIcon(qta.icon("mdi.help-circle", color="gray"))
            self.table.setItem(rowPosition, 10, status_item)

        self.table.setSortingEnabled(True)

        # Resize columns for better readability
        for i in range(self.table.columnCount()):
            self.table.resizeColumnToContents(i)

    def load_selected_task(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            message_box = QMessageBox()
            message_box.setIcon(QMessageBox.Warning)
            message_box.setWindowTitle("No Selection")
            message_box.setText("Please select a task to load.")
            message_box.setStandardButtons(QMessageBox.Ok)
            message_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 5px;
                    border: 1px solid #1976D2;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)
            message_box.exec_()
            return

        row = selected_rows[0].row()
        task_id = self.table.item(row, 0).data(Qt.UserRole)
        task = next((t for t in self.history_tasks if t["id"] == task_id), None)

        if task:
            if task.get("task_type") == "web":
                dialog = WebTranslationDialog.get_instance(self.parent())
            elif task.get("task_type") == "file":
                dialog = FileTranslationDialog.get_instance(self.parent())
            else:
                message_box = QMessageBox()
                message_box.setIcon(QMessageBox.Warning)
                message_box.setWindowTitle("Error")
                message_box.setText("Invalid task type.")
                message_box.setStandardButtons(QMessageBox.Ok)
                message_box.setStyleSheet("""
                    QMessageBox {
                        background-color: white;
                    }
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        padding: 8px 15px;
                        border-radius: 5px;
                        border: 1px solid #1976D2;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #1565C0;
                    }
                """)
                message_box.exec_()
                return

            dialog.load_task(task)
            dialog.setModal(False)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        else:
            message_box = QMessageBox()
            message_box.setIcon(QMessageBox.Warning)
            message_box.setWindowTitle("Error")
            message_box.setText("Selected task not found.")
            message_box.setStandardButtons(QMessageBox.Ok)
            message_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 5px;
                    border: 1px solid #1976D2;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)
            message_box.exec_()

    def remove_selected_task(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            message_box = QMessageBox()
            message_box.setIcon(QMessageBox.Warning)
            message_box.setWindowTitle("No Selection")
            message_box.setText("Please select a task to remove.")
            message_box.setStandardButtons(QMessageBox.Ok)
            message_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 5px;
                    border: 1px solid #1976D2;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)
            message_box.exec_()
            return

        row = selected_rows[0].row()
        task_id = self.table.item(row, 0).data(Qt.UserRole)

        confirm_box = QMessageBox()
        confirm_box.setIcon(QMessageBox.Question)
        confirm_box.setWindowTitle("Confirm Deletion")
        confirm_box.setText("Are you sure you want to remove this task?")
        confirm_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm_box.setDefaultButton(QMessageBox.No)
        confirm_box.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QPushButton {
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton[text="&Yes"] {
                background-color: #F44336;
                color: white;
                border: 1px solid #D32F2F;
            }
            QPushButton[text="&No"] {
                background-color: #F5F5F5;
                color: #424242;
                border: 1px solid #E0E0E0;
            }
            QPushButton[text="&Yes"]:hover {
                background-color: #C62828;
            }
            QPushButton[text="&No"]:hover {
                background-color: #BDBDBD;
            }
        """)

        if confirm_box.exec_() == QMessageBox.Yes:
            HistoryManager.remove_task_by_id(task_id)
            self.load_history()

    def edit_selected_task(self):
        """Allow the user to edit the Title and Author fields of a selected task."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            message_box = QMessageBox()
            message_box.setIcon(QMessageBox.Warning)
            message_box.setWindowTitle("No Selection")
            message_box.setText("Please select a task to edit.")
            message_box.setStandardButtons(QMessageBox.Ok)
            message_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 5px;
                    border: 1px solid #1976D2;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)
            message_box.exec_()
            return

        row = selected_rows[0].row()
        task_id = self.table.item(row, 0).data(Qt.UserRole)
        task = next((t for t in self.history_tasks if t["id"] == task_id), None)

        if task:
            # Create a dialog for editing
            edit_dialog = QDialog(self)
            edit_dialog.setWindowTitle("Edit Task")
            edit_dialog.setFixedWidth(400)
            edit_dialog.setStyleSheet("""
                QDialog {
                    background-color: white;
                }
            """)
            
            layout = QVBoxLayout(edit_dialog)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Form layout for the fields
            form_layout = QFormLayout()
            form_layout.setVerticalSpacing(12)
            form_layout.setHorizontalSpacing(15)
            
            # Book Title field
            title_edit = QLineEdit(task.get("book_title", ""))
            title_edit.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #bbb;
                    border-radius: 5px;
                    padding: 8px;
                    background-color: white;
                }
                QLineEdit:focus {
                    border: 1px solid #4CAF50;
                }
            """)
            form_layout.addRow("Book Title:", title_edit)
            
            # Author field - add only if the task structure has this field
            author_edit = QLineEdit(task.get("author", ""))
            author_edit.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #bbb;
                    border-radius: 5px;
                    padding: 8px;
                    background-color: white;
                }
                QLineEdit:focus {
                    border: 1px solid #4CAF50;
                }
            """)
            form_layout.addRow("Author:", author_edit)
            
            layout.addLayout(form_layout)
            
            # Add a note that other fields can't be edited
            note_label = QLabel("Note: Other fields cannot be modified from the history screen.")
            note_label.setStyleSheet("color: #757575; font-style: italic;")
            layout.addWidget(note_label)
            
            # Buttons
            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Save).setStyleSheet(ButtonStyles.get_primary_style())
            buttons.button(QDialogButtonBox.Cancel).setStyleSheet(ButtonStyles.get_neutral_style())
            buttons.accepted.connect(edit_dialog.accept)
            buttons.rejected.connect(edit_dialog.reject)
            layout.addWidget(buttons)
            
            # Show the dialog and process the result
            if edit_dialog.exec_() == QDialog.Accepted:
                # Update the task with new values
                updates = {
                    "book_title": title_edit.text(),
                    "author": author_edit.text()
                }
                HistoryManager.update_task(task_id, updates)
                
                # Also update the book_info in state.json of the book directory
                book_dir = task.get("book_dir")
                if book_dir:
                    HistoryManager.update_book_state_json(
                        book_dir=book_dir,
                        book_title=title_edit.text(),
                        author=author_edit.text()
                    )
                
                self.load_history()  # Refresh the table
                
                # Show a success message
                QMessageBox.information(
                    self, 
                    "Task Updated", 
                    "The task details have been updated successfully.",
                    QMessageBox.Ok
                )
        else:
            message_box = QMessageBox()
            message_box.setIcon(QMessageBox.Warning)
            message_box.setWindowTitle("Error")
            message_box.setText("Selected task not found.")
            message_box.setStandardButtons(QMessageBox.Ok)
            message_box.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 5px;
                    border: 1px solid #1976D2;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1565C0;
                }
            """)
            message_box.exec_()
