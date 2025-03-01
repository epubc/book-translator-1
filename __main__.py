import sys
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow
from gui.styles import light_stylesheet, dark_stylesheet
from PyQt5.QtCore import QSettings

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    settings = QSettings("NovelTranslator", "Config")
    theme = settings.value("Theme", "Light")
    if theme == "Dark":
        app.setStyleSheet(dark_stylesheet)
    else:
        app.setStyleSheet(light_stylesheet)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()