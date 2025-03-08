light_stylesheet = """
QWidget {
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    color: #212121;
}
QPushButton {
    background-color: #4CAF50;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 5px;
}
QPushButton:hover {
    background-color: #43A047;
}
QPushButton:pressed {
    background-color: #388E3C;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    border: 1px solid #BDBDBD;
    padding: 5px;
    border-radius: 4px;
    background-color: white;
    color: #212121;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border: 1px solid #2196F3;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 20px;
    border-left: 1px solid #BDBDBD;
}
QComboBox QAbstractItemView {
    border: 1px solid #BDBDBD;
    background-color: white;
    selection-background-color: #E3F2FD;
    selection-color: #0D47A1;
}
QProgressBar {
    border: 1px solid #BDBDBD;
    border-radius: 5px;
    text-align: center;
    color: #212121;
}
QProgressBar::chunk {
    background-color: #4CAF50;
    width: 10px;
    margin: 0.5px;
}
QTableWidget {
    background-color: white;
    alternate-background-color: #F5F5F5;
    gridline-color: #E0E0E0;
}
QTableWidget::item:selected {
    background-color: #E3F2FD;
    color: #0D47A1;
}
"""

dark_stylesheet = """
QWidget {
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    color: #E0E0E0;
    background-color: #2D2D2D;
}
QPushButton {
    background-color: #4CAF50;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 5px;
}
QPushButton:hover {
    background-color: #43A047;
}
QPushButton:pressed {
    background-color: #388E3C;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    border: 1px solid #616161;
    padding: 5px;
    border-radius: 4px;
    background-color: #3D3D3D;
    color: #E0E0E0;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border: 1px solid #64B5F6;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 20px;
    border-left: 1px solid #616161;
}
QComboBox QAbstractItemView {
    border: 1px solid #616161;
    background-color: #3D3D3D;
    selection-background-color: #1565C0;
    selection-color: white;
}
QProgressBar {
    border: 1px solid #616161;
    border-radius: 5px;
    text-align: center;
    color: #E0E0E0;
}
QProgressBar::chunk {
    background-color: #4CAF50;
    width: 10px;
    margin: 0.5px;
}
QTableWidget {
    background-color: #3D3D3D;
    alternate-background-color: #4D4D4D;
    gridline-color: #616161;
    color: #E0E0E0;
}
QTableWidget::item:selected {
    background-color: #1565C0;
    color: white;
}
"""
