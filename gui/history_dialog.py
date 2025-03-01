from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QTableWidget, QTableWidgetItem, QMessageBox, QStyle)
from PyQt5.QtCore import Qt
from core.history_manager import HistoryManager
from gui.translation_dialog import TranslationDialog
from gui.file_translation_dialog import FileTranslationDialog
from translator.text_processing import normalize_unicode_text

class TranslationHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translation History")
        self.resize(900, 400)
        self.history_tasks = []
        self.init_ui()
        self.load_history()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)

        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by Title, URL, or File Path")
        self.search_edit.textChanged.connect(self.update_table)
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Task Type", "Book Title", "Source", "Model", "Prompt Style",
                                              "Start Chapter", "End Chapter", "Output Directory", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
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
            if search_text in normalize_unicode_text(task.get("book_title", ""))
            or (task.get('task_type') == 'web' and search_text in task.get("book_url", ""))
            or (task.get('task_type') == 'file' and search_text in task.get("file_path", ""))
        ]
        self.table.setRowCount(0)
        for task in display_tasks:
            rowPosition = self.table.rowCount()
            self.table.insertRow(rowPosition)
            timestamp_item = QTableWidgetItem(task.get("timestamp", ""))
            timestamp_item.setData(Qt.UserRole, task["id"])
            self.table.setItem(rowPosition, 0, timestamp_item)
            self.table.setItem(rowPosition, 1, QTableWidgetItem(task.get("task_type", "")))
            self.table.setItem(rowPosition, 2, QTableWidgetItem(task.get("book_title", "")))
            source = task.get("book_url", task.get("file_path", ""))
            self.table.setItem(rowPosition, 3, QTableWidgetItem(source))
            self.table.setItem(rowPosition, 4, QTableWidgetItem(task.get("model_name", "")))
            self.table.setItem(rowPosition, 5, QTableWidgetItem(str(task.get("prompt_style", ""))))
            self.table.setItem(rowPosition, 6, QTableWidgetItem(str(task.get("start_chapter", ""))))
            self.table.setItem(rowPosition, 7, QTableWidgetItem(str(task.get("end_chapter", ""))))
            self.table.setItem(rowPosition, 8, QTableWidgetItem(task.get("output_directory", "")))
            self.table.setItem(rowPosition, 9, QTableWidgetItem(task.get("status", "")))
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
            if task.get("task_type") == "web":
                dialog = TranslationDialog.get_instance(self.parent())
            elif task.get("task_type") == "file":
                dialog = FileTranslationDialog.get_instance(self.parent())
            else:
                QMessageBox.warning(self, "Error", "Invalid task type.")
                return
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
