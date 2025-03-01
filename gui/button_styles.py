
class ButtonStyles:
    """Centralized button styles for consistent UI across the application"""

    BASE_STYLE = """
        QPushButton {{
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid {border_color};
            font-weight: bold;
            spacing: 8px;
            min-width: 120px;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
            border-color: {hover_border};
        }}
        QPushButton:focus {{
            outline: none;
            border: 2px solid {focus_border};
        }}
    """

    @staticmethod
    def get_primary_style():
        return f"""
            {ButtonStyles.BASE_STYLE.format(
            border_color="#1976D2",
            hover_bg="#1565C0",
            hover_border="#0D47A1",
            focus_border="#82B1FF"
        )}
            QPushButton {{
                background-color: #2196F3;
                color: white;
            }}
            QPushButton:hover {{
                color: white;
            }}
            QPushButton:pressed {{ 
                background-color: #3366cc; border: 1px solid #3366cc;
            }}
            QPushButton:disabled {{
                background-color: #a0c0e8; color: #ffffff; border: 1px solid #a0c0e8; 
            }}
        """

    @staticmethod
    def get_danger_style():
        return f"""
            {ButtonStyles.BASE_STYLE.format(
            border_color="#D32F2F",
            hover_bg="#C62828",
            hover_border="#B71C1C",
            focus_border="#FF8A80"
        )}
            QPushButton {{
                background-color: #F44336;
                color: white;
            }}
            QPushButton:hover {{
                color: white;
            }}
        """

    @staticmethod
    def get_secondary_style():
        return f"""
            {ButtonStyles.BASE_STYLE.format(
            border_color="#BBDEFB",
            hover_bg="#90CAF9",
            hover_border="#64B5F6",
            focus_border="#2196F3"
        )}
            QPushButton {{
                background-color: #E3F2FD;
                color: #0D47A1;
            }}
        """

    @staticmethod
    def get_neutral_style():
        return f"""
            {ButtonStyles.BASE_STYLE.format(
            border_color="#E0E0E0",
            hover_bg="#BDBDBD",
            hover_border="#9E9E9E",
            focus_border="#757575"
        )}
            QPushButton {{
                background-color: #F5F5F5;
                color: #424242;
            }}
        """

    @staticmethod
    def get_success_style():
        return f"""
            {ButtonStyles.BASE_STYLE.format(
            border_color="#2E7D32",
            hover_bg="#1B5E20",
            hover_border="#0A280B",
            focus_border="#A5D6A7"
        )}
            QPushButton {{
                background-color: #4CAF50;
                color: white;
            }}
            QPushButton:hover {{
                color: white;
            }}
        """

    @staticmethod
    def get_warning_style():
        return f"""
            {ButtonStyles.BASE_STYLE.format(
            border_color="#FFA000",
            hover_bg="#FF8F00",
            hover_border="#FF6F00",
            focus_border="#FFE082"
        )}
            QPushButton {{
                background-color: #FFC107;
                color: #212121;
            }}
        """


class WidgetStyles:
    """A class containing comprehensive style definitions for various PyQt5 widgets
    that follows the same color scheme as ButtonStyles."""

    # Color palette to match ButtonStyles
    COLORS = {
        "primary": {
            "main": "#2196F3",
            "dark": "#1976D2",
            "darker": "#1565C0",
            "darkest": "#0D47A1",
            "light": "#BBDEFB",
            "lighter": "#E3F2FD",
            "accent": "#82B1FF",
            "text": "white",
            "text_light": "#0D47A1"
        },
        "danger": {
            "main": "#F44336",
            "dark": "#D32F2F",
            "darker": "#C62828",
            "darkest": "#B71C1C",
            "light": "#FFCDD2",
            "lighter": "#FFEBEE",
            "accent": "#FF8A80",
            "text": "white"
        },
        "success": {
            "main": "#4CAF50",
            "dark": "#2E7D32",
            "darker": "#1B5E20",
            "darkest": "#0A280B",
            "light": "#C8E6C9",
            "lighter": "#E8F5E9",
            "accent": "#A5D6A7",
            "text": "white"
        },
        "warning": {
            "main": "#FFC107",
            "dark": "#FFA000",
            "darker": "#FF8F00",
            "darkest": "#FF6F00",
            "light": "#FFECB3",
            "lighter": "#FFF8E1",
            "accent": "#FFE082",
            "text": "#212121"
        },
        "neutral": {
            "main": "#F5F5F5",
            "dark": "#E0E0E0",
            "darker": "#BDBDBD",
            "darkest": "#9E9E9E",
            "light": "#EEEEEE",
            "lighter": "#FAFAFA",
            "accent": "#757575",
            "text": "#424242"
        }
    }

    # Base styles for common widgets
    @staticmethod
    def get_input_style(style_type="primary"):
        """Style for input widgets like QLineEdit, QComboBox, and QSpinBox.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["primary"])
        return f"""
            padding: 4px 8px; 
            border-radius: 4px; 
            border: 1px solid {colors["dark"]}; 
            background-color: white;
            selection-background-color: {colors["light"]};
        """

    @staticmethod
    def get_progress_bar_style(style_type="primary"):
        """Style for QProgressBar widgets.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["primary"])
        return f"""
            QProgressBar {{
                border: 1px solid {colors["dark"]}; 
                border-radius: 4px; 
                text-align: center; 
                height: 20px;
                background-color: white;
                color: {colors["darkest"]};
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 {colors["dark"]}, stop:1 {colors["main"]});
                border-radius: 3px;
            }}
        """

    @staticmethod
    def get_text_edit_style(style_type="neutral"):
        """Style for QTextEdit widgets.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["neutral"])
        return f"""
            QTextEdit {{
                background-color: {colors["lighter"]}; 
                border: 1px solid {colors["dark"]}; 
                border-radius: 4px; 
                padding: 8px;
                selection-background-color: {colors["light"]};
            }}
            QTextEdit:focus {{
                border: 2px solid {colors["main"]};
            }}
        """

    @staticmethod
    def get_frame_style(style_type="neutral")->str:
        """Style for QFrame widgets used as cards.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["neutral"])
        return f"""
            QFrame {{
                background-color: {colors["lighter"]}; 
                border: 1px solid {colors["dark"]}; 
                border-radius: 6px; 
                padding: 12px;
            }}
        """

    @staticmethod
    def get_separator_style(style_type="neutral"):
        """Style for QFrame separators.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["neutral"])
        return f"background-color: {colors['dark']};"

    @staticmethod
    def get_label_style(style_type="primary", is_header=False, is_title=False):
        """Style for QLabel widgets.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
            is_header: Whether this is a header label
            is_title: Whether this is a title label
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["primary"])
        font_size = "18px" if is_title else ("14px" if is_header else "inherit")
        font_weight = "bold" if is_header or is_title else "normal"

        return f"""
            font-size: {font_size}; 
            font-weight: {font_weight}; 
            color: {colors["darkest"]};
        """

    @staticmethod
    def get_header_label_style(style_type="primary"):
        """Style for header labels."""
        return WidgetStyles.get_label_style(style_type, is_header=True)

    @staticmethod
    def get_title_label_style(style_type="primary"):
        """Style for the main title label."""
        return WidgetStyles.get_label_style(style_type, is_title=True)

    @staticmethod
    def get_tab_widget_style(style_type="primary"):
        """Style for QTabWidget.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["primary"])
        return f"""
            QTabWidget::pane {{
                border: 1px solid {colors["dark"]};
                border-radius: 4px;
                padding: 5px;
                background-color: white;
            }}
            QTabBar::tab {{
                background-color: {colors["lighter"]};
                border: 1px solid {colors["dark"]};
                border-bottom-color: {colors["dark"]};
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 12px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {colors["main"]};
                color: {colors["text"]};
                border: 1px solid {colors["darkest"]};
                border-bottom-color: {colors["main"]};
            }}
            QTabBar::tab:!selected {{
                margin-top: 2px;
            }}
            QTabBar::tab:hover {{
                background-color: {colors["light"]};
            }}
        """

    @staticmethod
    def get_list_view_style(style_type="neutral"):
        """Style for QListView, QListWidget.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["neutral"])
        return f"""
            QListView {{
                background-color: {colors["lighter"]};
                border: 1px solid {colors["dark"]};
                border-radius: 4px;
                padding: 2px;
                outline: none;
            }}
            QListView::item {{
                border-radius: 2px;
                padding: 6px;
                margin: 2px;
            }}
            QListView::item:hover {{
                background-color: {colors["light"]};
            }}
            QListView::item:selected {{
                background-color: {colors["main"]};
                color: {colors["text"]};
            }}
        """

    @staticmethod
    def get_combo_box_style(style_type="primary"):
        """Style for QComboBox.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["primary"])
        return f"""
            QComboBox {{
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid {colors["dark"]};
                background-color: white;
                min-width: 120px;
            }}
            QComboBox:hover {{
                border-color: {colors["darker"]};
            }}
            QComboBox:focus {{
                border: 2px solid {colors["main"]};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: right center;
                width: 20px;
                border-left: 1px solid {colors["dark"]};
            }}
            QComboBox QAbstractItemView {{
                background-color: white;
                border: 1px solid {colors["dark"]};
                border-radius: 0px;
                selection-background-color: {colors["main"]};
                selection-color: {colors["text"]};
            }}
        """

    @staticmethod
    def get_checkbox_style(style_type="primary"):
        """Style for QCheckBox.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["primary"])
        return f"""
            QCheckBox {{
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {colors["dark"]};
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked:hover {{
                border: 2px solid {colors["main"]};
            }}
            QCheckBox::indicator:checked {{
                background-color: {colors["main"]};
                border: 1px solid {colors["main"]};
                image: url(:/icons/check.png);
            }}
        """

    @staticmethod
    def get_radio_button_style(style_type="primary"):
        """Style for QRadioButton.

        Args:
            style_type: One of 'primary', 'danger', 'success', 'warning', 'neutral'
        """
        colors = WidgetStyles.COLORS.get(style_type, WidgetStyles.COLORS["primary"])
        return f"""
            QRadioButton {{
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {colors["dark"]};
                border-radius: 9px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                border: 2px solid {colors["main"]};
            }}
            QRadioButton::indicator:checked {{
                background-color: white;
                border: 2px solid {colors["main"]};
            }}
            QRadioButton::indicator:checked::disabled {{
                background-color: {colors["lighter"]};
                border: 2px solid {colors["dark"]};
            }}
            QRadioButton::indicator:checked::middle {{
                image: url(:/icons/radio_inner.png);
            }}
        """
