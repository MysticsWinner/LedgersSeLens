import shutil
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt
from database.db_manager import get_transaction_by_id, update_transaction_details

class TransactionDetailDialog(QDialog):
    def __init__(self, tx_id, parent=None):
        super().__init__(parent)
        self.tx_id = tx_id
        self.setWindowTitle("Transaction Details")
        self.setMinimumWidth(400)
        self.setStyleSheet("background-color: #1c1c1e; color: #ffffff;")
        
        self.receipt_path = ""
        
        layout = QVBoxLayout(self)
        
        # Fetch data via database manager abstraction
        row = get_transaction_by_id(self.tx_id)
        
        if not row:
            QMessageBox.critical(self, "Error", "Transaction not found.")
            self.reject()
            return
            
        date, desc, amt, cat, acc, notes, receipt = row
        self.receipt_path = receipt if receipt else ""
        
        # Read-only details
        lbl_info = QLabel(f"<b>{desc}</b><br>{date} | {cat} | {acc}<br><h2>${amt:.2f}</h2>")
        lbl_info.setStyleSheet("padding: 10px; background-color: #2c2c2e; border-radius: 8px;")
        lbl_info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl_info)
        
        # Notes
        layout.addWidget(QLabel("Notes / Memo:"))
        self.txt_notes = QLineEdit(notes if notes else "")
        self.txt_notes.setStyleSheet("padding: 8px; border: 1px solid #3a3a3c; border-radius: 4px; background-color: #0f0f11;")
        layout.addWidget(self.txt_notes)
        
        # Receipt
        layout.addWidget(QLabel("Receipt Image:"))
        receipt_layout = QHBoxLayout()
        self.lbl_receipt = QLabel("No receipt attached." if not self.receipt_path else f"Attached: {os.path.basename(self.receipt_path)}")
        receipt_layout.addWidget(self.lbl_receipt)
        
        btn_attach = QPushButton("Attach File")
        btn_attach.setStyleSheet("background-color: #0a84ff; padding: 5px 10px; border-radius: 4px; color: white;")
        btn_attach.clicked.connect(self.attach_receipt)
        receipt_layout.addWidget(btn_attach)
        layout.addLayout(receipt_layout)
        
        # Save Button
        btn_save = QPushButton("Save Changes")
        btn_save.setStyleSheet("background-color: #32d74b; font-weight: bold; padding: 10px; border-radius: 8px; margin-top: 10px; color: white;")
        btn_save.clicked.connect(self.save_details)
        layout.addWidget(btn_save)

    def attach_receipt(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Receipt Image", "", "Images (*.png *.jpg *.jpeg *.tiff *.bmp *.webp);;PDF Files (*.pdf);;All Files (*.*)")
        if file_path:
            os.makedirs('receipts', exist_ok=True)
            filename = os.path.basename(file_path)
            dest_path = os.path.join('receipts', f"{self.tx_id}_{filename}")
            try:
                shutil.copy2(file_path, dest_path)
                self.receipt_path = dest_path
                self.lbl_receipt.setText(f"Attached: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not copy file: {e}")

    def save_details(self):
        notes = self.txt_notes.text().strip()
        update_transaction_details(self.tx_id, notes, self.receipt_path)
        self.accept()
