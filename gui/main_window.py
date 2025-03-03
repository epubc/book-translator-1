from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QDialog
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QSize, QSettings, Qt
import qtawesome as qta
from gui.web_translation_dialog import WebTranslationDialog
from gui.file_translation_dialog import FileTranslationDialog
from gui.history_dialog import TranslationHistoryDialog
from gui.settings_dialog import SettingsDialog
from gui.styles import light_stylesheet, dark_stylesheet
import os
from PyQt5.QtWidgets import QApplication

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
        layout.setSpacing(15)

        title = QLabel("Novel Translator")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)

        translate_btn = self.create_styled_button("Translate from Web", 'mdi.web')
        translate_btn.clicked.connect(self.show_translate_dialog)

        file_translate_btn = self.create_styled_button("Translate From File", 'mdi.file-document')
        file_translate_btn.clicked.connect(self.show_file_translate_dialog)

        history_btn = self.create_styled_button("Translation History", 'mdi.history')
        history_btn.clicked.connect(self.show_history_dialog)

        config_btn = self.create_styled_button("Configuration", 'msc.settings-gear')
        config_btn.clicked.connect(self.show_settings)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(translate_btn)
        layout.addWidget(file_translate_btn)
        layout.addWidget(history_btn)
        layout.addWidget(config_btn)
        layout.addStretch()

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def create_styled_button(self, text, icon_name):
        button = QPushButton(text)
        icon = qta.icon(icon_name, color='#505050')
        button.setIcon(icon)
        button.setIconSize(QSize(24, 24))
        button.setStyleSheet("""
            QPushButton {
                text-align: center; padding: 10px; font-size: 14px;
                font-weight: bold; border-radius: 5px; min-height: 45px;
            }
        """)
        button.setLayoutDirection(Qt.LeftToRight)
        return button

    def show_translate_dialog(self):
        dialog = WebTranslationDialog.get_instance(self)
        dialog.setModal(False)
        dialog.show()

    def show_file_translate_dialog(self):
        dialog = FileTranslationDialog.get_instance(self)
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
            os.environ["GEMINI_API_KEY"] = api_key
        theme = settings.value("Theme", "Light")
        app = QApplication.instance()
        if theme == "Dark":
            app.setStyleSheet(dark_stylesheet)
        else:
            app.setStyleSheet(light_stylesheet)
