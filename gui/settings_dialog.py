from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton,
                             QMessageBox, QHBoxLayout, QSizePolicy, QStyle, QLabel)
from PyQt5.QtCore import Qt, QSettings

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
