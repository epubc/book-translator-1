from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QLineEdit, QComboBox, QFormLayout, QCheckBox, QTabWidget,
                             QWidget, QGroupBox, QSpinBox, QFileDialog, QMessageBox,
                             QDoubleSpinBox, QSlider)
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtGui import QFont
import qtawesome as qta
import os
from pathlib import Path
from gui.ui_styles import ButtonStyles, WidgetStyles


class SettingsDialog(QDialog):
    """Dialog for configuring application settings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(550, 450)
        self.settings = QSettings("NovelTranslator", "Config")
        self.qta = qta
        self.init_ui()
        self.load_settings()
        self.setWindowModality(Qt.ApplicationModal)
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header_layout = QHBoxLayout()
        header_icon = QLabel()
        header_icon.setPixmap(self.qta.icon('fa5s.cog', color='#4a86e8').pixmap(24, 24))
        header_label = QLabel("Application Settings")
        header_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header_layout.addWidget(header_icon)
        header_layout.addWidget(header_label)
        header_layout.addStretch(1)
        layout.addLayout(header_layout)
        
        # Tabs for different categories
        tab_widget = QTabWidget()
        
        # General settings tab
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        
        # API Key section
        api_group = QGroupBox("Gemini API Access")
        api_layout = QFormLayout(api_group)
        
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter your Gemini API key")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setMinimumHeight(30)
        self.api_key_edit.setStyleSheet(WidgetStyles.get_input_style("primary"))
        
        toggle_visibility_btn = QPushButton()
        toggle_visibility_btn.setIcon(self.qta.icon('fa5s.eye', color='#555'))
        toggle_visibility_btn.setFixedSize(30, 30)
        toggle_visibility_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        toggle_visibility_btn.setCheckable(True)
        
        def toggle_password_visibility():
            if toggle_visibility_btn.isChecked():
                self.api_key_edit.setEchoMode(QLineEdit.Normal)
                toggle_visibility_btn.setIcon(self.qta.icon('fa5s.eye-slash', color='#555'))
            else:
                self.api_key_edit.setEchoMode(QLineEdit.Password)
                toggle_visibility_btn.setIcon(self.qta.icon('fa5s.eye', color='#555'))
        
        toggle_visibility_btn.clicked.connect(toggle_password_visibility)
        
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(self.api_key_edit)
        api_key_layout.addWidget(toggle_visibility_btn)
        
        api_layout.addRow(QLabel("API Key:"), api_key_layout)
        
        # Add a help text
        help_label = QLabel("Get your API key from <a href='https://aistudio.google.com/app/apikey'>Google AI Studio</a>")
        help_label.setOpenExternalLinks(True)
        help_label.setStyleSheet("color: #555; font-size: 12px;")
        api_layout.addRow("", help_label)
        
        general_layout.addWidget(api_group)
        
        # UI settings section
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout(ui_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark"])
        self.theme_combo.setStyleSheet(WidgetStyles.get_combo_box_style("primary"))
        ui_layout.addRow(QLabel("Theme:"), self.theme_combo)
        
        self.confirm_exit_check = QCheckBox("Confirm before exiting")
        self.confirm_exit_check.setStyleSheet("""
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        ui_layout.addRow("", self.confirm_exit_check)
        
        general_layout.addWidget(ui_group)
        
        # Translation defaults section
        translation_group = QGroupBox("Translation Defaults")
        translation_layout = QFormLayout(translation_group)
        
        self.default_model_combo = QComboBox()
        self.default_model_combo.addItems(["gemini-2.0-flash", "gemini-2.0-flash-lite"])
        self.default_model_combo.setStyleSheet(WidgetStyles.get_combo_box_style("primary"))
        translation_layout.addRow(QLabel("Default Model:"), self.default_model_combo)
        
        self.default_style_combo = QComboBox()
        self.default_style_combo.addItem("Modern Style", 1)
        self.default_style_combo.addItem("China Fantasy Style", 2)
        self.default_style_combo.setStyleSheet(WidgetStyles.get_combo_box_style("primary"))
        translation_layout.addRow(QLabel("Default Style:"), self.default_style_combo)
        
        general_layout.addWidget(translation_group)
        general_layout.addStretch(1)
        
        # Add general tab
        tab_widget.addTab(general_tab, "General")
        
        # Advanced settings tab
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        
        # Performance settings
        performance_group = QGroupBox("Performance")
        performance_layout = QFormLayout(performance_group)
        
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 8)
        self.threads_spin.setValue(2)
        self.threads_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        performance_layout.addRow(QLabel("Parallel Threads:"), self.threads_spin)
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 300)
        self.timeout_spin.setValue(120)
        self.timeout_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        performance_layout.addRow(QLabel("Request Timeout (seconds):"), self.timeout_spin)
        
        advanced_layout.addWidget(performance_group)
        
        # Gemini Model Parameters
        model_params_group = QGroupBox("Gemini Model Parameters")
        model_params_layout = QFormLayout(model_params_group)
        
        # Temperature parameter (0.0 to 1.0)
        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 1.0)
        self.temperature_spin.setValue(0.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        model_params_layout.addRow(QLabel("Temperature:"), self.temperature_spin)
        temp_help = QLabel("Controls randomness: 0 is deterministic, 1 is most random")
        temp_help.setStyleSheet("color: #555; font-size: 12px;")
        model_params_layout.addRow("", temp_help)
        
        # Top-p parameter (0.0 to 1.0)
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setValue(0.95)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setDecimals(2)
        self.top_p_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        model_params_layout.addRow(QLabel("Top-p:"), self.top_p_spin)
        top_p_help = QLabel("Controls diversity via nucleus sampling (0.95 recommended)")
        top_p_help.setStyleSheet("color: #555; font-size: 12px;")
        model_params_layout.addRow("", top_p_help)
        
        # Top-k parameter (1 to 100)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 100)
        self.top_k_spin.setValue(40)
        self.top_k_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        model_params_layout.addRow(QLabel("Top-k:"), self.top_k_spin)
        top_k_help = QLabel("Limits vocabulary to top k tokens (40-64 recommended)")
        top_k_help.setStyleSheet("color: #555; font-size: 12px;")
        model_params_layout.addRow("", top_k_help)
        
        advanced_layout.addWidget(model_params_group)
        
        # Storage settings
        storage_group = QGroupBox("Storage")
        storage_layout = QFormLayout(storage_group)
        
        # Default output directory
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setMinimumHeight(30)
        self.output_dir_edit.setStyleSheet(WidgetStyles.get_input_style("primary"))
        
        browse_btn = QPushButton("Browse")
        browse_btn.setIcon(self.qta.icon('fa5s.folder-open', color='#555'))
        browse_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        browse_btn.clicked.connect(self.choose_output_dir)
        
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(browse_btn)
        
        storage_layout.addRow(QLabel("Default Output Directory:"), output_dir_layout)
        
        self.history_limit_spin = QSpinBox()
        self.history_limit_spin.setRange(10, 1000)
        self.history_limit_spin.setValue(100)
        self.history_limit_spin.setStyleSheet(WidgetStyles.get_input_style("primary"))
        storage_layout.addRow(QLabel("History Entries Limit:"), self.history_limit_spin)
        
        advanced_layout.addWidget(storage_group)
        advanced_layout.addStretch(1)
        
        # Add advanced tab
        tab_widget.addTab(advanced_tab, "Advanced")
        
        layout.addWidget(tab_widget)
        
        # Buttons at the bottom
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.setIcon(self.qta.icon('fa5s.undo', color='#555'))
        self.reset_btn.setStyleSheet(ButtonStyles.get_secondary_style())
        self.reset_btn.clicked.connect(self.reset_defaults)
        
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setIcon(self.qta.icon('fa5s.save', color='white'))
        self.save_btn.setStyleSheet(ButtonStyles.get_primary_style())
        self.save_btn.clicked.connect(self.save_settings)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setIcon(self.qta.icon('fa5s.times', color='#555'))
        self.cancel_btn.setStyleSheet(ButtonStyles.get_neutral_style())
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.reset_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.save_btn)
        
        layout.addLayout(button_layout)
    
    def load_settings(self):
        """Load settings from QSettings."""
        api_key = self.settings.value("APIKey", "")
        self.api_key_edit.setText(api_key)
        
        theme = self.settings.value("Theme", "Light")
        index = self.theme_combo.findText(theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        confirm_exit = self.settings.value("ConfirmExit", True, type=bool)
        self.confirm_exit_check.setChecked(confirm_exit)
        
        default_model = self.settings.value("DefaultModel", "gemini-2.0-flash")
        index = self.default_model_combo.findText(default_model)
        if index >= 0:
            self.default_model_combo.setCurrentIndex(index)
        
        default_style = self.settings.value("DefaultStyle", 1, type=int)
        index = self.default_style_combo.findData(default_style)
        if index >= 0:
            self.default_style_combo.setCurrentIndex(index)
        
        threads = self.settings.value("Threads", 2, type=int)
        self.threads_spin.setValue(threads)
        
        timeout = self.settings.value("Timeout", 120, type=int)
        self.timeout_spin.setValue(timeout)
        
        # Load Gemini model parameters
        temperature = self.settings.value("ModelTemperature", 0.0, type=float)
        self.temperature_spin.setValue(temperature)
        
        top_p = self.settings.value("ModelTopP", 0.95, type=float)
        self.top_p_spin.setValue(top_p)
        
        top_k = self.settings.value("ModelTopK", 40, type=int)
        self.top_k_spin.setValue(top_k)
        
        default_output_dir = self.settings.value("DefaultOutputDir", str(Path.home() / "Downloads"))
        self.output_dir_edit.setText(default_output_dir)
        
        history_limit = self.settings.value("HistoryLimit", 100, type=int)
        self.history_limit_spin.setValue(history_limit)
    
    def save_settings(self):
        """Save settings to QSettings."""
        # Set API Key as environment variable for immediate use
        os.environ["GEMINI_API_KEY"] = self.api_key_edit.text()
        
        # Save all settings
        self.settings.setValue("APIKey", self.api_key_edit.text())
        self.settings.setValue("Theme", self.theme_combo.currentText())
        self.settings.setValue("ConfirmExit", self.confirm_exit_check.isChecked())
        self.settings.setValue("DefaultModel", self.default_model_combo.currentText())
        self.settings.setValue("DefaultStyle", self.default_style_combo.currentData())
        self.settings.setValue("Threads", self.threads_spin.value())
        self.settings.setValue("Timeout", self.timeout_spin.value())
        
        # Save output directory if set
        if hasattr(self, 'output_dir_edit') and self.output_dir_edit.text():
            self.settings.setValue("OutputDirectory", self.output_dir_edit.text())
        
        # Save history limit if set
        if hasattr(self, 'history_limit_spin'):
            self.settings.setValue("HistoryLimit", self.history_limit_spin.value())
        
        # Save Gemini model parameters
        self.settings.setValue("ModelTemperature", self.temperature_spin.value())
        self.settings.setValue("ModelTopP", self.top_p_spin.value())
        self.settings.setValue("ModelTopK", self.top_k_spin.value())
        
        self.settings.sync()
        self.show_success("Settings Saved", "Your settings have been saved successfully.")
        self.accept()
    
    def reset_defaults(self):
        """Reset all settings to default values."""
        if self.show_confirmation("Reset Settings", 
                                  "Are you sure you want to reset all settings to their default values?"):
            # Clear all settings
            self.settings.clear()
            
            # Reload the default values
            self.load_settings()
            
            self.show_success("Settings Reset", "All settings have been reset to their default values.")
    
    def choose_output_dir(self):
        """Open directory chooser dialog for output directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Choose Default Output Directory", 
            self.output_dir_edit.text(),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if dir_path:
            self.output_dir_edit.setText(dir_path)
    
    def show_success(self, title, message):
        """Show a success message dialog."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setStyleSheet(WidgetStyles.get_success_message_style())
        msg_box.exec_()
    
    def show_confirmation(self, title, message):
        """Show a confirmation dialog and return True if user confirms."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.setStyleSheet(WidgetStyles.get_message_box_style())
        
        yes_button = msg_box.button(QMessageBox.Yes)
        yes_button.setIcon(self.qta.icon('fa5s.check', color='#4caf50'))
        
        no_button = msg_box.button(QMessageBox.No)
        no_button.setIcon(self.qta.icon('fa5s.times', color='#f44336'))
        
        return msg_box.exec_() == QMessageBox.Yes
