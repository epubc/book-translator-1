from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
                             QTableWidgetItem)
from downloader.factory import DownloaderFactory

class SourceInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Supported Sources Information")
        self.resize(800, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        explanation = QLabel(
            "The following sources are supported with their respective configurations and estimated download speeds.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

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

        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)
