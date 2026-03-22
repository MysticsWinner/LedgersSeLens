import sqlite3
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QColorDialog,
                             QMessageBox, QAbstractItemView, QGroupBox, QWidget, QScrollArea, QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor

from database.db_manager import get_connection

class TagBar(QWidget):
    def __init__(self, initial_tags="", parent=None):
        super().__init__(parent)
        self.tags = [t.strip() for t in initial_tags.split(',')] if initial_tags else []
        self.tags = [t for t in self.tags if t]
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self.scroll = QScrollArea()
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:horizontal { border: none; background: transparent; height: 6px; margin: 0px; }
            QScrollBar::handle:horizontal { background: #555555; min-width: 20px; border-radius: 3px; }
            QScrollBar::handle:horizontal:hover { background: #8e8e93; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; background: transparent; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
        """)
        
        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(6)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.scroll.setWidget(self.container)
        self.layout.addWidget(self.scroll)
        
        self.input = QLineEdit()
        self.input.setPlaceholderText("Add...")
        self.input.setStyleSheet("background-color: transparent; border: none; color: #8e8e93; padding: 0px;")
        self.input.setMinimumWidth(60)
        self.input.returnPressed.connect(self.add_tag_from_input)
        
        self.render_tags()
        
    def add_tag_from_input(self):
        text = self.input.text().strip()
        if text and text not in self.tags:
            self.tags.append(text)
            self.input.clear()
            self.render_tags()
            
    def remove_tag(self, tag):
        if tag in self.tags:
            self.tags.remove(tag)
            self.render_tags()
            
    def render_tags(self):
        while self.container_layout.count():
            child = self.container_layout.takeAt(0)
            w = child.widget()
            if w:
                if w == self.input:
                    w.setParent(None)
                else:
                    w.deleteLater()
                
        for tag in self.tags:
            chip = QFrame()
            chip.setStyleSheet("background-color: #0a84ff; border-radius: 6px;")
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(6, 2, 6, 2)
            chip_layout.setSpacing(4)
            
            lbl = QLabel(tag)
            lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 11px;")
            
            btn_rm = QPushButton("×")
            btn_rm.setStyleSheet("background-color: transparent; color: #ffffff; font-weight: bold; border: none; padding: 0px; font-size: 16px; margin-top: -2px;")
            btn_rm.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rm.setFixedSize(16, 16)
            btn_rm.clicked.connect(lambda checked, t=tag: self.remove_tag(t))
            
            chip_layout.addWidget(lbl)
            chip_layout.addWidget(btn_rm)
            self.container_layout.addWidget(chip)
            
        self.container_layout.addWidget(self.input)
        
    def get_rules_string(self):
        return ",".join(self.tags)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings - Categories & Budgets")
        self.resize(800, 500)
        self.setStyleSheet("""
            QDialog { background-color: #1c1c1e; color: #ffffff; }
            QLabel { color: #ffffff; font-family: "Inter", "Segoe UI", sans-serif; font-size: 14px;}
            QPushButton {
                background-color: #2c2c2e; color: #ffffff; border: 1px solid #3a3a3c;
                padding: 8px 16px; border-radius: 6px; font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a3c; }
            QPushButton#primary { background-color: #0a84ff; border: none; }
            QPushButton#primary:hover { background-color: #0070e0; }
            QPushButton#danger { background-color: #ff453a; border: none; }
            QPushButton#danger:hover { background-color: #d70015; }
            QTableWidget {
                background-color: #0f0f11; color: #ffffff;
                gridline-color: #2c2c2e; border: 1px solid #2c2c2e;
                border-radius: 8px; outline: 0;
            }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background-color: #3a3a3c; color: white; }
            QHeaderView::section {
                background-color: #1c1c1e; color: #8e8e93; padding: 5px;
                border: none; border-bottom: 1px solid #3a3a3c; font-weight: bold;
            }
            QLineEdit {
                background-color: #2c2c2e; color: #ffffff; border: 1px solid #3a3a3c;
                padding: 2px; border-radius: 2px;
                selection-background-color: #0a84ff; selection-color: #ffffff;
            }
            QLineEdit#TestSandbox {
                padding: 8px; border-radius: 6px;
            }
            QScrollArea { border: none; background-color: transparent; }
        """)

        # Wrapping settings inside a scroll area
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        from PyQt6.QtWidgets import QScrollArea, QWidget
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self.main_layout.addWidget(scroll)
        
        container = QWidget()
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Manage Categories & Budgets")
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Color (Hex)", "Match Keywords (comma-separated)", "Monthly Budget Limit"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(130)  # Ensures titles never collapse past readability
        self.table.setColumnHidden(0, True) # Hide ID
        self.table.verticalHeader().setDefaultSectionSize(48) # Ultra generous row height for chip spacing
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        layout.addWidget(self.table)
        
        # Test Sandbox
        sandbox_group = QGroupBox("Test Categorization Rule")
        sandbox_group.setStyleSheet("QGroupBox { color: #8e8e93; font-weight: bold; border: 1px solid #2c2c2e; border-radius: 8px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        sandbox_layout = QHBoxLayout()
        self.txt_test = QLineEdit()
        self.txt_test.setObjectName("TestSandbox")
        self.txt_test.setPlaceholderText("Type a mock transaction description here (e.g. 'Starbucks Seattle')...")
        self.txt_test.setStyleSheet("background-color: #1c1c1e; color: #ffffff; padding: 8px; border: 1px solid #2c2c2e; border-radius: 4px;")
        self.txt_test.textChanged.connect(self.test_rule)
        sandbox_layout.addWidget(self.txt_test)
        
        self.lbl_test_result = QLabel("Category: None")
        self.lbl_test_result.setStyleSheet("color: #8e8e93; font-weight: bold; padding: 8px; min-width: 150px;")
        sandbox_layout.addWidget(self.lbl_test_result)
        
        sandbox_group.setLayout(sandbox_layout)
        layout.addWidget(sandbox_group)

        btn_layout = QHBoxLayout()
        
        self.btn_add = QPushButton("Add Category")
        self.btn_add.clicked.connect(self.add_category)
        btn_layout.addWidget(self.btn_add)
        
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self.delete_category)
        btn_layout.addWidget(self.btn_delete)

        btn_layout.addStretch()

        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self.save_changes)
        btn_layout.addWidget(self.btn_save)

        self.btn_close = QPushButton("Cancel")
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        self.load_categories()

    def load_categories(self):
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT id, name, color, match_rules, budget_limit FROM categories')
        rows = c.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            cat_id = QTableWidgetItem(str(row[0]))
            cat_id.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row_idx, 0, cat_id)

            name = QTableWidgetItem(str(row[1]))
            self.table.setItem(row_idx, 1, name)

            color = QTableWidgetItem(str(row[2]))
            color.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            try:
                if row[2]:
                    color.setBackground(QColor(str(row[2])))
            except Exception:
                pass
            self.table.setItem(row_idx, 2, color)

            tag_bar = TagBar(str(row[3]))
            self.table.setCellWidget(row_idx, 3, tag_bar)
            
            budget = QTableWidgetItem(str(row[4]))
            self.table.setItem(row_idx, 4, budget)

    def add_category(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        self.table.setItem(row, 0, QTableWidgetItem("NEW"))
        self.table.setItem(row, 1, QTableWidgetItem("New Category"))
        
        color_item = QTableWidgetItem("#ffffff")
        color_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        color_item.setBackground(QColor("#ffffff"))
        self.table.setItem(row, 2, color_item)
        
        self.table.setCellWidget(row, 3, TagBar(""))
        self.table.setItem(row, 4, QTableWidgetItem("0.0"))

    def on_cell_double_clicked(self, row, col):
        if col == 2:
            item = self.table.item(row, col)
            current_color = item.text() if item else "#ffffff"
            
            color = QColorDialog.getColor(QColor(current_color), self, "Select Category Color")
            if color.isValid():
                hex_color = color.name()
                if item:
                    item.setText(hex_color)
                    item.setBackground(QColor(hex_color))
                else:
                    new_item = QTableWidgetItem(hex_color)
                    new_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    new_item.setBackground(QColor(hex_color))
                    self.table.setItem(row, col, new_item)

    def delete_category(self):
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            self.table.removeRow(curr_row)

    def save_changes(self):
        conn = get_connection()
        c = conn.cursor()
        
        # Sync changes back to SQLite
        c.execute('SELECT id FROM categories')
        existing_ids = {row[0] for row in c.fetchall()}
        
        kept_ids = set()
        
        try:
            for row in range(self.table.rowCount()):
                cat_id_item = self.table.item(row, 0)
                name_item = self.table.item(row, 1)
                color_item = self.table.item(row, 2)
                tag_widget = self.table.cellWidget(row, 3)
                budget_item = self.table.item(row, 4)
                
                cat_id_str = cat_id_item.text() if cat_id_item else "NEW"
                name = name_item.text() if name_item else ""
                color = color_item.text() if color_item else "#ffffff"
                rules = tag_widget.get_rules_string() if tag_widget else ""
                budget_str = budget_item.text() if budget_item else "0.0"
                
                try:
                     budget = float(budget_str)
                except ValueError:
                     budget = 0.0
                
                if not name.strip(): continue
                
                if cat_id_str == "NEW":
                    c.execute('INSERT INTO categories (name, color, match_rules, budget_limit) VALUES (?, ?, ?, ?)',
                              (name, color, rules, budget))
                else:
                    cat_id = int(cat_id_str)
                    kept_ids.add(cat_id)
                    c.execute('UPDATE categories SET name=?, color=?, match_rules=?, budget_limit=? WHERE id=?',
                              (name, color, rules, budget, cat_id))
            
            # Delete removed categories
            to_delete = existing_ids - kept_ids
            for del_id in to_delete:
                c.execute('DELETE FROM categories WHERE id=?', (del_id,))
                
            conn.commit()
            QMessageBox.information(self, "Success", "Settings saved successfully.")
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Error", "Category names must be unique.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
        finally:
            conn.close()

    def test_rule(self, text):
        if not text.strip():
            self.lbl_test_result.setText("Category: None")
            self.lbl_test_result.setStyleSheet("color: #8e8e93; font-weight: bold; padding: 8px; min-width: 150px;")
            return
            
        temp_cats = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            color_item = self.table.item(row, 2)
            tag_widget = self.table.cellWidget(row, 3)
            if name_item and tag_widget:
                temp_cats.append({
                    'name': name_item.text(),
                    'color': color_item.text() if color_item else '#ffffff',
                    'match_rules': tag_widget.get_rules_string()
                })
                
        from core.analyzer import categorize_transaction
        matched_cat = categorize_transaction(text, temp_cats)
        
        color = '#8e8e93'
        if matched_cat != 'Other':
            for c in temp_cats:
                if c['name'] == matched_cat:
                    color = c['color']
                    break
                    
        self.lbl_test_result.setText(f"Category: {matched_cat}")
        self.lbl_test_result.setStyleSheet(f"color: {color}; font-weight: bold; padding: 8px; min-width: 150px;")
