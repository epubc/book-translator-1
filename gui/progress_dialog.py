from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar,
                             QFrame, QScrollArea, QTabWidget, QWidget)
from PyQt5.QtCore import Qt, QSize
import qtawesome as qta

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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

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
        summary_layout.setSpacing(20)

        total_chapters = len(self.chapter_status)
        completed_chapters = sum(1 for _, info in self.chapter_status.items() if info.get("progress", 0) == 100)
        in_progress = sum(1 for _, info in self.chapter_status.items() if 0 < info.get("progress", 0) < 100)
        avg_progress = sum(info.get("progress", 0) for _, info in self.chapter_status.items()) / max(1, total_chapters)

        total_label = self.create_stat_widget("Total Chapters", str(total_chapters), "mdi.book-open-variant")
        completed_label = self.create_stat_widget("Completed", str(completed_chapters), "mdi.check-circle", "green")
        pending_label = self.create_stat_widget("In Progress", str(in_progress), "mdi.progress-clock", "blue")

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
        scroll_layout.setSpacing(15)

        sorted_chapters = sorted(self.chapter_status.items(),
                                 key=lambda x: int(x[0].split()[-1].isdigit() and x[0].split()[-1] or 0) if x[0].split() else 0)

        for chapter, info in sorted_chapters:
            chapter_frame = self.create_chapter_frame(chapter, info)
            scroll_layout.addWidget(chapter_frame)

        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        chapter_layout.addWidget(scroll_area)
        tab_widget.addTab(chapter_tab, "Chapter Details")

        layout.addWidget(tab_widget)

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
        self.chapter_status = self.get_status_func()
        self.close()
        new_dialog = EnhancedProgressDialog(self.get_status_func, self.parent())
        new_dialog.show()
        self.accept()
