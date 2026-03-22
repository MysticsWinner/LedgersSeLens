import sys
from PyQt6.QtWidgets import QApplication
from ui.windows.main_window import MainWindow
from database.db_manager import init_db
from ui.theme import MODERN_THEME

def main():
    # Initialize the database schema if needed
    init_db()
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(MODERN_THEME)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
