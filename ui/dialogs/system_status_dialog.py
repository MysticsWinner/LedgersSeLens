import sys
import os
import threading
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QTextEdit, QGroupBox, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from database import db_manager
from core.ocr_engine import is_tesseract_available

# Global handle for in-GUI API server thread
_gui_api_server_process = None
_gui_api_server_running = False

class SystemStatusDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Status & Service Hub")
        self.resize(650, 520)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #ffffff; }
            QGroupBox { font-weight: bold; border: 1px solid #333333; border-radius: 8px; margin-top: 10px; padding-top: 15px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #0a84ff; }
            QLabel { color: #d1d1d6; font-size: 13px; }
            QPushButton { background-color: #2c2c2e; color: #ffffff; border: 1px solid #3a3a3c; border-radius: 6px; padding: 6px 14px; font-weight: 500; }
            QPushButton:hover { background-color: #3a3a3c; border-color: #0a84ff; }
            QTextEdit { background-color: #121212; color: #30d158; border: 1px solid #2c2c2e; font-family: monospace; font-size: 11px; border-radius: 6px; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        
        # Header
        header = QLabel("LedgerSeLens Service & Cluster Status")
        header.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        header.setStyleSheet("color: #ffffff;")
        layout.addWidget(header)
        
        # Group: Infrastructure & Storage
        grp_infra = QGroupBox("Storage & Distributed Cluster")
        infra_layout = QVBoxLayout(grp_infra)
        
        self.lbl_db_mode = QLabel()
        self.lbl_fallback = QLabel()
        self.lbl_tx_count = QLabel()
        self.lbl_ocr = QLabel()
        self.lbl_redis = QLabel()
        
        infra_layout.addWidget(self.lbl_db_mode)
        infra_layout.addWidget(self.lbl_fallback)
        infra_layout.addWidget(self.lbl_tx_count)
        infra_layout.addWidget(self.lbl_ocr)
        infra_layout.addWidget(self.lbl_redis)
        layout.addWidget(grp_infra)
        
        # Group: Services Management
        grp_services = QGroupBox("Service Control")
        srv_layout = QHBoxLayout(grp_services)
        
        self.btn_api_server = QPushButton("Start Local REST API Server")
        self.btn_api_server.clicked.connect(self.toggle_api_server)
        srv_layout.addWidget(self.btn_api_server)
        
        self.btn_run_tests = QPushButton("Run Diagnostic Tests (Pytest)")
        self.btn_run_tests.clicked.connect(self.run_diagnostics)
        srv_layout.addWidget(self.btn_run_tests)
        
        self.btn_refresh = QPushButton("Refresh Status")
        self.btn_refresh.clicked.connect(self.refresh_status)
        srv_layout.addWidget(self.btn_refresh)
        
        layout.addWidget(grp_services)
        
        # Output Console
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setPlaceholderText("Diagnostic and service logs will appear here...")
        layout.addWidget(self.console)
        
        # Close button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.refresh_status()

    def refresh_status(self):
        """Probes cluster health and refreshes status labels."""
        has_pg = db_manager._probe_postgres()
        is_fallback = db_manager.IS_FALLBACK_ACTIVE or not has_pg
        tx_count = len(db_manager.get_all_transactions())
        accounts = db_manager.get_accounts()
        tess = is_tesseract_available()
        
        db_text = f"<b>Database Mode:</b> <span style='color: {'#30d158' if has_pg else '#ffd60a'}'>{'PostgreSQL Cluster (Sharded)' if has_pg else 'Local SQLite Fallback (ledger.db)'}</span>"
        fallback_text = f"<b>Offline Resilience / Fallback:</b> <span style='color: {'#ffd60a' if is_fallback else '#30d158'}'>{'ACTIVE (Zero Data Loss Mode)' if is_fallback else 'Standby'}</span>"
        tx_text = f"<b>Total Records:</b> {tx_count} transactions across {len(accounts)} accounts ({', '.join(accounts) if accounts else 'None'})"
        ocr_text = f"<b>OCR Engine:</b> <span style='color: #30d158'>{'Tesseract Optical Engine' if tess else 'Heuristic Text Extractor Fallback'}</span>"
        
        import redis
        try:
            r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"), socket_connect_timeout=0.2)
            r.ping()
            redis_text = "<b>Redis Cache:</b> <span style='color: #30d158'>Connected (Online)</span>"
        except Exception:
            redis_text = "<b>Redis Cache:</b> <span style='color: #ffd60a'>Offline (In-Memory RAM Cache Fallback Active)</span>"
            
        self.lbl_db_mode.setText(db_text)
        self.lbl_fallback.setText(fallback_text)
        self.lbl_tx_count.setText(tx_text)
        self.lbl_ocr.setText(ocr_text)
        self.lbl_redis.setText(redis_text)
        
        global _gui_api_server_running
        if _gui_api_server_running:
            self.btn_api_server.setText("API Server Running (http://127.0.0.1:8000)")
            self.btn_api_server.setStyleSheet("color: #30d158; border-color: #30d158;")
        else:
            self.btn_api_server.setText("Start Local REST API Server")
            self.btn_api_server.setStyleSheet("")

    def toggle_api_server(self):
        """Starts or reports on the local FastAPI REST API server."""
        global _gui_api_server_running
        if _gui_api_server_running:
            self.console.append("[*] API Server is already running at http://127.0.0.1:8000\nEndpoints available: /api/transactions, /api/insights, /api/subscriptions, /api/reconcile, /docs")
            return
            
        def run():
            import uvicorn
            from database.db_manager import init_db
            init_db()
            uvicorn.run("server:app", host="127.0.0.1", port=8000, log_level="warning")
            
        t = threading.Thread(target=run, daemon=True)
        t.start()
        _gui_api_server_running = True
        self.console.append("[OK] FastAPI REST API Server started in background on http://127.0.0.1:8000\nAPI documentation available at http://127.0.0.1:8000/docs")
        self.refresh_status()

    def run_diagnostics(self):
        """Executes pytest suite in background thread and streams output."""
        self.console.clear()
        self.console.append("[*] Running full automated test suite...\n")
        
        def run():
            import subprocess
            proc = subprocess.Popen(
                [sys.executable, "-m", "pytest", "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            )
            for line in proc.stdout:
                line_str = line.strip()
                if line_str:
                    # Thread-safe queue or invoke
                    QTimer.singleShot(0, lambda s=line_str: self.console.append(s))
            proc.wait()
            QTimer.singleShot(0, lambda: self.console.append("\n[OK] Diagnostic run completed."))
            
        t = threading.Thread(target=run, daemon=True)
        t.start()
