light_stylesheet = """
QWidget {
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    color: #333;
}
QPushButton {
    background-color: #5cb85c;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 5px;
}
QPushButton:hover {
    background-color: #4cae4c;
}
QPushButton:pressed {
    background-color: #449d44;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    border: 1px solid #ccc;
    padding: 5px;
    border-radius: 4px;
    background-color: #fff;
}
QProgressBar {
    border: 1px solid #ccc;
    border-radius: 5px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #5cb85c;
    width: 10px;
    margin: 0.5px;
}
QTableWidget {
    background-color: #fff;
    alternate-background-color: #f9f9f9;
}
"""

dark_stylesheet = """
QWidget {
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
    color: #ddd;
    background-color: #333;
}
QPushButton {
    background-color: #5cb85c;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 5px;
}
QPushButton:hover {
    background-color: #4cae4c;
}
QPushButton:pressed {
    background-color: #449d44;
}
QLineEdit, QComboBox, QSpinBox, QTextEdit {
    border: 1px solid #555;
    padding: 5px;
    border-radius: 4px;
    background-color: #444;
    color: #ddd;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 5px;
    text-align: center;
    color: #ddd;
}
QProgressBar::chunk {
    background-color: #5cb85c;
    width: 10px;
    margin: 0.5px;
}
QTableWidget {
    background-color: #444;
    alternate-background-color: #555;
    color: #ddd;
}
"""
