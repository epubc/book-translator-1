from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QDialog, QHBoxLayout
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QSize, QSettings, Qt
import qtawesome as qta
from gui.web_translation_dialog import WebTranslationDialog
from gui.file_translation_dialog import FileTranslationDialog
from gui.history_dialog import TranslationHistoryDialog
from gui.settings_dialog import SettingsDialog
from gui.styles import light_stylesheet, dark_stylesheet
from gui.ui_styles import ButtonStyles, WidgetStyles
import os
from PyQt5.QtWidgets import QApplication

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Novel Translator")
        self.resize(600, 500)  # Increased default size
        self.setMinimumSize(500, 400)  # Set minimum size
        self.init_ui()
        self.load_settings()
        self.setWindowModality(Qt.NonModal)

    def init_ui(self):
        central_widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header section with logo and version
        header_layout = QHBoxLayout()
        logo_label = QLabel()
        logo_icon = qta.icon('mdi.translate', color='#4a86e8')
        logo_label.setPixmap(logo_icon.pixmap(32, 32))
        
        title = QLabel("Novel Translator")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(WidgetStyles.get_title_label_style("primary"))
        
        version_label = QLabel("v1.0.0")
        version_label.setStyleSheet("color: #888; font-size: 12px;")
        
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(version_label)
        
        # Actions section
        actions_widget = QWidget()
        actions_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 10px;
            }
        """)
        actions_layout = QVBoxLayout(actions_widget)
        actions_layout.setContentsMargins(15, 15, 15, 15)
        actions_layout.setSpacing(12)
        
        section_label = QLabel("Translate")
        section_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        actions_layout.addWidget(section_label)
        
        translate_btn = self.create_styled_button("Translate from Web", 'mdi.web')
        translate_btn.clicked.connect(self.show_translate_dialog)
        
        file_translate_btn = self.create_styled_button("Translate From File", 'mdi.file-document')
        file_translate_btn.clicked.connect(self.show_file_translate_dialog)
        
        actions_layout.addWidget(translate_btn)
        actions_layout.addWidget(file_translate_btn)
        
        # Tools section
        tools_widget = QWidget()
        tools_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border-radius: 10px;
            }
        """)
        tools_layout = QVBoxLayout(tools_widget)
        tools_layout.setContentsMargins(15, 15, 15, 15)
        tools_layout.setSpacing(12)
        
        tools_label = QLabel("Tools")
        tools_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        tools_layout.addWidget(tools_label)
        
        history_btn = self.create_styled_button("Translation History", 'mdi.history')
        history_btn.clicked.connect(self.show_history_dialog)
        
        config_btn = self.create_styled_button("Configuration", 'msc.settings-gear')
        config_btn.clicked.connect(self.show_settings)
        
        tools_layout.addWidget(history_btn)
        tools_layout.addWidget(config_btn)

        layout.addLayout(header_layout)
        layout.addSpacing(20)
        layout.addWidget(actions_widget)
        layout.addSpacing(10)
        layout.addWidget(tools_widget)
        layout.addStretch()

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        # Apply some general styling to the central widget
        central_widget.setStyleSheet("""
            QWidget#centralWidget {
                background-color: #ffffff;
            }
        """)
        central_widget.setObjectName("centralWidget")

    def create_styled_button(self, text, icon_name):
        button = QPushButton(text)
        icon = qta.icon(icon_name, color='#505050')
        button.setIcon(icon)
        button.setIconSize(QSize(24, 24))
        button.setStyleSheet(ButtonStyles.get_secondary_style())
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
        
        # Apply theme to application
        if theme == "Dark":
            app.setStyleSheet(dark_stylesheet)
            # Update custom widgets for dark mode
            central_widget = self.centralWidget()
            central_widget.setStyleSheet("""
                QWidget#centralWidget {
                    background-color: #333333;
                }
            """)
            
            # Update section widgets
            for widget in central_widget.findChildren(QWidget):
                if widget.styleSheet() and "background-color: #f8f9fa;" in widget.styleSheet():
                    widget.setStyleSheet("""
                        QWidget {
                            background-color: #444444;
                            border-radius: 10px;
                        }
                    """)
        else:
            app.setStyleSheet(light_stylesheet)
            # Reset custom widgets for light mode
            central_widget = self.centralWidget()
            central_widget.setStyleSheet("""
                QWidget#centralWidget {
                    background-color: #ffffff;
                }
            """)
            
            # Update section widgets
            for widget in central_widget.findChildren(QWidget):
                if widget.styleSheet() and "background-color: #444444;" in widget.styleSheet():
                    widget.setStyleSheet("""
                        QWidget {
                            background-color: #f8f9fa;
                            border-radius: 10px;
                        }
                    """)

    def resizeEvent(self, event):
        """Handle window resize events to adjust UI elements if needed"""
        super().resizeEvent(event)
        # You could adjust UI elements based on window size here
        
        # Example: Adjust button sizes based on window width
        width = self.width()
        if width < 550:
            # For smaller windows, make buttons take full width
            for button in self.findChildren(QPushButton):
                button.setMinimumWidth(0)
        else:
            # For larger windows, set a minimum button width
            for button in self.findChildren(QPushButton):
                button.setMinimumWidth(120)
