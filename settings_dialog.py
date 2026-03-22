import sqlite3
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QColorDialog,
                             QMessageBox, QAbstractItemView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from database import get_connection

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
            QHeaderView::section {
                background-color: #1c1c1e; color: #8e8e93; padding: 5px;
                border: none; border-bottom: 1px solid #3a3a3c; font-weight: bold;
            }
            QLineEdit {
                background-color: #2c2c2e; color: #ffffff; border: 1px solid #3a3a3c;
                padding: 8px; border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
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
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        layout.addWidget(self.table)

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
            try:
                if row[2]:
                    color.setBackground(QColor(str(row[2])))
            except Exception:
                pass
            self.table.setItem(row_idx, 2, color)

            rules = QTableWidgetItem(str(row[3]))
            self.table.setItem(row_idx, 3, rules)
            
            budget = QTableWidgetItem(str(row[4]))
            self.table.setItem(row_idx, 4, budget)

    def add_category(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        self.table.setItem(row, 0, QTableWidgetItem("NEW"))
        self.table.setItem(row, 1, QTableWidgetItem("New Category"))
        
        color_item = QTableWidgetItem("#ffffff")
        color_item.setBackground(QColor("#ffffff"))
        self.table.setItem(row, 2, color_item)
        
        self.table.setItem(row, 3, QTableWidgetItem(""))
        self.table.setItem(row, 4, QTableWidgetItem("0.0"))

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
                rules_item = self.table.item(row, 3)
                budget_item = self.table.item(row, 4)
                
                cat_id_str = cat_id_item.text() if cat_id_item else "NEW"
                name = name_item.text() if name_item else ""
                color = color_item.text() if color_item else "#ffffff"
                rules = rules_item.text() if rules_item else ""
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
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Error", "Category names must be unique.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
        finally:
            conn.close()
