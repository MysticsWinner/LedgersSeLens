MODERN_THEME = """
QWidget {
    background-color: #121212;
    color: #E0E0E0;
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 13px;
}

/* ScrollBars */
QScrollBar:horizontal, QScrollBar:vertical {
    background: transparent;
    border: none;
    width: 8px;
    height: 8px;
    margin: 0px;
}
QScrollBar::handle {
    background-color: #424242;
    border-radius: 4px;
}
QScrollBar::handle:hover {
    background-color: #616161;
}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    background: none; width: 0px; height: 0px; border: none;
}

/* Buttons */
QPushButton {
    background-color: #1E1E1E;
    color: #FFFFFF;
    border: 1px solid #333333;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2C2C2C;
    border: 1px solid #007ACC;
}
QPushButton#primary {
    background-color: #007ACC;
    border: none;
}
QPushButton#primary:hover {
    background-color: #005F9E;
}
QPushButton#danger {
    background-color: #D32F2F;
    border: none;
}
QPushButton#danger:hover {
    background-color: #B71C1C;
}

/* Table */
QTableWidget, QTreeWidget {
    background-color: #1E1E1E;
    border: 1px solid #333333;
    border-radius: 8px;
    gridline-color: transparent;
    outline: none;
}
QTableWidget::item, QTreeWidget::item {
    padding: 8px;
    border-bottom: 1px solid #2D2D30;
}
QTableWidget::item:selected, QTreeWidget::item:selected {
    background-color: #264F78;
    color: #FFFFFF;
}
QHeaderView::section {
    background-color: #121212;
    color: #A0A0A0;
    padding: 10px;
    border: none;
    font-weight: bold;
    text-transform: uppercase;
}

/* Inputs / Combos */
QLineEdit, QComboBox {
    background-color: #1E1E1E;
    border: 1px solid #333333;
    padding: 8px 12px;
    border-radius: 6px;
    color: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #007ACC;
}
QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox QAbstractItemView {
    background-color: #1E1E1E;
    border: 1px solid #333333;
    selection-background-color: #264F78;
}

/* Tabs */
QTabWidget::pane {
    border: none;
    border-top: 1px solid #333333;
}
QTabBar::tab {
    background-color: transparent;
    color: #A0A0A0;
    padding: 10px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}
QTabBar::tab:selected {
    color: #007ACC;
    border-bottom: 2px solid #007ACC;
}
QTabBar::tab:hover:!selected {
    color: #E0E0E0;
}

/* Dock Widgets & Cards */
QDockWidget {
    color: #A0A0A0;
    font-weight: bold;
    text-transform: uppercase;
}
QDockWidget::title {
    background: #121212;
    padding: 6px;
}
QFrame#DashboardCard {
    background-color: #1E1E1E;
    border-radius: 12px;
    border: 1px solid #333333;
}

/* Menus */
QMenu {
    background-color: #1E1E1E;
    color: #FFFFFF;
    border: 1px solid #333333;
}
QMenu::item:selected {
    background-color: #007ACC;
}
"""
