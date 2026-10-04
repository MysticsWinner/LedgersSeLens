"""
LedgerSeLens - Main Unified Application Orchestrator
Provides complete, unified access to all system features:
  - Default: Modern PyQt6 Desktop GUI Dashboard with Charts, OCR, Subscriptions, Services Hub, and Reconcile
  - Interactive Terminal Menu: Numbered interactive console providing full feature access
  - Subcommands: GUI, Server, Worker, Web, Ingest, OCR, Sync/Reconcile, Insights, Transactions, Subscriptions, Plaid, Export, Status, Mock-Data, Chaos, Test, and Menu
"""

import sys
import os
import argparse
import logging
import subprocess

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("main")

def run_gui():
    """Launches the full-featured modern Desktop GUI Dashboard."""
    try:
        from PyQt6.QtWidgets import QApplication
        from ui.windows.main_window import MainWindow
        from database.db_manager import init_db
        from ui.theme import MODERN_THEME
        
        init_db()
        
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setStyleSheet(MODERN_THEME)
        
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"[!] Note: GUI display could not be initialized ({e}).")
        print("[*] Automatically falling back to the interactive terminal menu...")
        run_interactive_menu()

def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Starts the Distributed FastAPI REST API Server."""
    import uvicorn
    from database.db_manager import init_db
    init_db()
    print(f"[*] Starting LedgerSeLens API Server on http://{host}:{port}...")
    uvicorn.run("server:app", host=host, port=port, reload=reload)

def run_worker():
    """Runs the asynchronous queue ingestion worker."""
    print("[*] Starting background worker daemon...")
    subprocess.run([sys.executable, "worker.py"])

def run_web():
    """Runs the React/Vite Frontend Web Application."""
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
    if not os.path.exists(frontend_dir):
        print("[ERROR] Frontend directory not found.")
        return
    print("[*] Starting React/Vite Frontend Web Server on http://localhost:5173 ...")
    subprocess.run(["npm", "run", "dev"], cwd=frontend_dir, shell=True)

def run_ingest(file_path: str, account_name: str = "Main Account"):
    """Ingests any PDF, Excel (.xlsx, .xls), CSV (.csv, .tsv), or Receipt Image."""
    from core.data_ingestion import ingest_file
    from core.analyzer import _process_transactions
    
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found at '{file_path}'")
        return
        
    print(f"[*] Ingesting statement: {file_path} for account '{account_name}'...")
    result = ingest_file(file_path, account_name=account_name)
    
    if not result.is_success or result.dataframe.empty:
        print(f"[ERROR] Ingestion failed: {result.errors}")
        for w in result.warnings:
            print(f"   [!] Warning: {w}")
        return
        
    processed_df = _process_transactions(result.dataframe.to_dict(orient="records"), account_name)
    print("=" * 50)
    print("         DATA INGESTION REPORT")
    print("=" * 50)
    print(f"File Type:              {result.file_type.upper()}")
    print(f"Total Rows Scanned:     {result.total_rows}")
    print(f"Valid Rows Ingested:    {result.valid_rows}")
    print(f"Dropped / Noise Rows:   {result.dropped_rows}")
    print(f"Target Account:         {account_name}")
    for w in result.warnings:
        print(f"[!] Note: {w}")
    print(f"[OK] Successfully persisted {result.valid_rows} transactions into the ledger!")
    print("=" * 50)

def run_ocr(file_path: str):
    """Runs Optical Character Recognition (OCR) on a receipt or scanned PDF."""
    from core.ocr_engine import parse_receipt, is_tesseract_available
    
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found at '{file_path}'")
        return
        
    has_tess = is_tesseract_available()
    print(f"[*] Running OCR Engine ({'Tesseract Binary' if has_tess else 'Heuristic Fallback Engine'})...")
    parsed = parse_receipt(file_path)
    
    print("=" * 50)
    print("          OCR PARSED RECEIPT DATA")
    print("=" * 50)
    print(f"Merchant / Vendor:  {parsed['description']}")
    print(f"Transaction Date:   {parsed['date']}")
    print(f"Total Amount:       ${abs(parsed['amount']):,.2f}")
    print(f"Detected Category:  {parsed['category']}")
    print(f"OCR Engine Used:    {parsed['engine']}")
    print(f"Notes / Method:     {parsed.get('notes', '')}")
    print("=" * 50)

def run_sync():
    """Runs bidirectional data reconciliation across local SQLite and remote shards."""
    from database.db_manager import reconcile_and_sync_all
    print("[*] Initiating Bidirectional Data Reconciliation...")
    result = reconcile_and_sync_all()
    print("=" * 50)
    print("       DATA RECONCILIATION SUMMARY")
    print("=" * 50)
    print(f"Reconciliation Status:       {result.get('status')}")
    print(f"Pushed Local -> Remote:      {result.get('pushed_to_remote', 0)}")
    print(f"Pulled Remote -> Local:      {result.get('pulled_to_local', 0)}")
    print(f"Field Conflicts Resolved:    {result.get('conflicts_resolved', 0)}")
    print(f"Total Unified Transactions:  {result.get('total_unified_transactions', 0)}")
    print("=" * 50)

def run_insights(account_filter: str = "All Accounts"):
    """Prints financial overview, totals, and top categories."""
    from core.analyzer import load_all_transactions_df, generate_insights
    df = load_all_transactions_df(account_filter=account_filter)
    if df.empty:
        print("No transactions found in the database. Ingest some statements first!")
        return
        
    insights = generate_insights(df)
    print("=" * 45)
    print(f"        LEDGERLENS INSIGHTS ({account_filter})")
    print("=" * 45)
    print(f"Total Income:    ${insights['total_received']:,.2f}")
    print(f"Total Spent:     ${insights['total_spent']:,.2f}")
    net = insights['total_received'] - insights['total_spent']
    print(f"Net Total:       ${net:,.2f}")
    
    print("\n--- Top Expense Categories ---")
    cat_breakdown = insights['category_breakdown'].sort_values(ascending=False).head(5)
    for cat, amt in cat_breakdown.items():
        print(f"{cat:25} ${amt:,.2f}")
    print("=" * 45)

def run_transactions(limit: int = 10, account_filter: str = "All Accounts"):
    """Prints recent transactions table."""
    from core.analyzer import load_all_transactions_df
    df = load_all_transactions_df(account_filter=account_filter)
    if df.empty:
        print("No transactions found.")
        return
        
    print(f"Showing latest {limit} transactions for {account_filter}:")
    print("-" * 80)
    print(f"{'Date':12} | {'Amount':10} | {'Category':22} | {'Description'}")
    print("-" * 80)
    for _, row in df.head(limit).iterrows():
        desc = (row['Description'][:35] + '...') if len(row['Description']) > 35 else row['Description']
        print(f"{row['Date'].strftime('%Y-%m-%d'):12} | ${row['Amount']:<9.2f} | {row['Category']:22} | {desc}")
    print("-" * 80)

def run_subscriptions():
    """Detects and prints recurring subscriptions."""
    from core.analyzer import load_all_transactions_df, detect_subscriptions
    df = load_all_transactions_df()
    subs = detect_subscriptions(df)
    if not subs:
        print("No recurring subscriptions detected.")
        return
        
    print(f"Found {len(subs)} recurring subscription(s):")
    print("-" * 65)
    print(f"{'Service / Description':25} | {'Amount':9} | {'Frequency':10} | {'Last Charged'}")
    print("-" * 65)
    for s in subs:
        print(f"{s['description'][:25]:25} | ${abs(s['amount']):<8.2f} | {s['frequency']:10} | {s['last_charged']}")
    print("-" * 65)

def run_plaid(access_token: str = "mock-sandbox-token"):
    """Syncs Plaid sandbox bank feeds."""
    import datetime
    from database.db_manager import save_transaction
    
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    mock_plaid_data = [
        {"date": today, "desc": "AMAZON WEB SERVICES", "amount": -15.42, "category": "Payment: Subscription", "acct": "Chase Checking"},
        {"date": today, "desc": "PAYROLL DIRECT DEPOSIT", "amount": 2500.00, "category": "Income", "acct": "Wells Fargo"},
        {"date": today, "desc": "UBER TRIP SF", "amount": -22.50, "category": "Transport", "acct": "Amex Platinum"},
        {"date": today, "desc": "STARBUCKS STORE", "amount": -6.75, "category": "Food", "acct": "Citi Double Cash"}
    ]
    for tx in mock_plaid_data:
        save_transaction(tx['date'], tx['desc'], tx['amount'], tx['category'], tx['acct'])
    print(f"[OK] Successfully synced {len(mock_plaid_data)} transactions from Plaid sandbox.")

def run_export(output_path: str, format_type: str = "csv"):
    """Exports transactions to CSV, Excel, or PDF."""
    from utils.export_utils import export_to_csv, export_to_excel, export_to_pdf
    fmt = format_type.lower()
    if fmt == "csv":
        export_to_csv(output_path)
    elif fmt in ("excel", "xlsx"):
        export_to_excel(output_path)
    elif fmt == "pdf":
        export_to_pdf(output_path)
    else:
        print(f"[ERROR] Unsupported format: {format_type}. Choose from csv, excel, pdf.")
        return
    print(f"[OK] Data exported successfully to {output_path} ({fmt.upper()})")

def run_status():
    """Prints current system, database, and cluster health status."""
    from database import db_manager
    from core.ocr_engine import is_tesseract_available
    import redis
    
    print("=" * 50)
    print("         LEDGERSELENS SYSTEM STATUS")
    print("=" * 50)
    # Storage status
    has_pg = db_manager._probe_postgres()
    print(f"Database Mode:       {'Distributed PostgreSQL Shards' if has_pg else 'Local SQLite Fallback'}")
    print(f"Fallback Active:     {'YES (Offline resilience)' if db_manager.IS_FALLBACK_ACTIVE else 'No'}")
    print(f"Degraded Shards:     {'YES' if db_manager.CURRENTLY_DEGRADED else 'No'}")
    print(f"SQLite DB File:      {db_manager.DB_FILE}")
    print(f"Total Transactions:  {len(db_manager.get_all_transactions())}")
    print(f"Distinct Accounts:   {', '.join(db_manager.get_accounts()) or 'None'}")
    
    # OCR Engine
    tess_available = is_tesseract_available()
    print(f"OCR Engine:          {'Tesseract Binary (Ready)' if tess_available else 'Heuristic Fallback Engine'}")
    
    # Redis
    try:
        r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"), socket_connect_timeout=0.2)
        r.ping()
        redis_status = "Connected (Healthy)"
    except Exception:
        redis_status = "Offline (RAM Cache Fallback Active)"
    print(f"Redis Cache:         {redis_status}")
    print("=" * 50)

def run_mock_data(filename: str = "mock_statement.pdf"):
    """Generates synthetic mock PDF bank statements for testing."""
    from mock_data_generator import generate_mock_statement
    generate_mock_statement(filename)
    print(f"[OK] Synthetic mock bank statement generated: {filename}")

def run_chaos():
    """Runs Chaos Monkey fault injector for testing resilience."""
    print("[*] Launching Chaos Monkey resilience tester...")
    subprocess.run([sys.executable, "chaos_monkey.py"])

def run_tests():
    """Runs the full automated pytest suite."""
    print("🧪 Running full automated test suite...")
    subprocess.run([sys.executable, "-m", "pytest", "-v"])

def run_interactive_menu():
    """Interactive console dashboard providing menu access to all features."""
    while True:
        print("\n" + "=" * 65)
        print("    LEDGERSELENS - UNIFIED FINANCIAL SYSTEM & ANALYTICS")
        print("=" * 65)
        print(" [1]  Launch Modern Desktop GUI Dashboard")
        print(" [2]  Start Distributed REST API Server (FastAPI / Uvicorn)")
        print(" [3]  Start Background Ingestion Worker Daemon")
        print(" [4]  Start Frontend Web Application (React / Vite)")
        print(" [5]  Ingest Bank Statement (PDF, Excel, CSV, TSV, Images)")
        print(" [6]  Run OCR Receipt Scanner / Scanned Document Parser")
        print(" [7]  Bidirectional Sync & Reconcile (Postgres <-> SQLite)")
        print(" [8]  View Financial Insights, Overview & Categories")
        print(" [9]  View Recent Transactions")
        print(" [10] Detect & List Recurring Subscriptions")
        print(" [11] Sync Plaid Sandbox Bank Feeds")
        print(" [12] Export Transactions (CSV, Excel, PDF)")
        print(" [13] System Status & Cluster Health")
        print(" [14] Generate Mock PDF Bank Statement")
        print(" [15] Run Chaos Monkey Fault Injection")
        print(" [16] Run Full Automated Pytest Suite")
        print(" [0]  Exit")
        print("=" * 65)
        
        try:
            choice = input("Select an option (0-16): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
            
        if choice == "0":
            print("Goodbye.")
            break
        elif choice == "1":
            run_gui()
            break
        elif choice == "2":
            port = input("Enter port (default 8000): ").strip() or "8000"
            run_server(port=int(port))
            break
        elif choice == "3":
            run_worker()
            break
        elif choice == "4":
            run_web()
            break
        elif choice == "5":
            fpath = input("Enter path to statement/receipt file: ").strip()
            acct = input("Enter account name (default 'Main Account'): ").strip() or "Main Account"
            if fpath:
                run_ingest(fpath, account_name=acct)
        elif choice == "6":
            fpath = input("Enter path to receipt image or scanned PDF: ").strip()
            if fpath:
                run_ocr(fpath)
        elif choice == "7":
            run_sync()
        elif choice == "8":
            acct = input("Filter by account (or press Enter for 'All Accounts'): ").strip() or "All Accounts"
            run_insights(account_filter=acct)
        elif choice == "9":
            lim = input("Limit rows (default 10): ").strip() or "10"
            run_transactions(limit=int(lim))
        elif choice == "10":
            run_subscriptions()
        elif choice == "11":
            run_plaid()
        elif choice == "12":
            out = input("Enter destination file path: ").strip()
            fmt = input("Format (csv, excel, pdf) [default: csv]: ").strip() or "csv"
            if out:
                run_export(out, format_type=fmt)
        elif choice == "13":
            run_status()
        elif choice == "14":
            out = input("Enter output pdf name (default 'mock_statement.pdf'): ").strip() or "mock_statement.pdf"
            run_mock_data(out)
        elif choice == "15":
            run_chaos()
        elif choice == "16":
            run_tests()
        else:
            print("Invalid option. Please choose a number between 0 and 16.")

def main():
    parser = argparse.ArgumentParser(
        description="LedgerSeLens - High-Availability Distributed Financial Ledger & Analytics",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--cli", "--menu", "-i", action="store_true", dest="interactive_flag",
        help="Launch the interactive terminal dashboard menu to access all features"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available Commands")
    
    # GUI Command
    subparsers.add_parser("gui", help="Launch the Desktop GUI Dashboard (Default)")
    
    # Menu / Interactive Command
    subparsers.add_parser("menu", help="Launch the interactive terminal menu")
    subparsers.add_parser("interactive", help="Alias for 'menu'")
    
    # Server Command
    p_server = subparsers.add_parser("server", help="Launch the Distributed REST API Server")
    p_server.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    p_server.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    p_server.add_argument("--reload", action="store_true", help="Enable live auto-reload")
    
    # Worker Command
    subparsers.add_parser("worker", help="Launch the async Kafka/Queue ingestion worker")
    
    # Web Command
    subparsers.add_parser("web", help="Launch the React/Vite Frontend Web Application")
    
    # Ingest Command
    p_ingest = subparsers.add_parser("ingest", help="Ingest a statement file (PDF, Excel, CSV, or Image Receipt)")
    p_ingest.add_argument("file", help="Path to statement or receipt file")
    p_ingest.add_argument("--account", default="Main Account", help="Account name to assign (default: Main Account)")
    
    # OCR Command
    p_ocr = subparsers.add_parser("ocr", help="Run OCR text extraction on receipt image or scanned PDF")
    p_ocr.add_argument("file", help="Path to image or PDF file")
    
    # Sync / Reconcile Command
    subparsers.add_parser("sync", help="Bidirectionally reconcile local SQLite with PostgreSQL shards")
    subparsers.add_parser("reconcile", help="Alias for 'sync'")
    
    # Insights Command
    p_ins = subparsers.add_parser("insights", help="View financial overview, income, expenses, and top categories")
    p_ins.add_argument("--account", default="All Accounts", help="Filter by account (default: All Accounts)")
    
    # Transactions Command
    p_tx = subparsers.add_parser("transactions", help="List recent transactions")
    p_tx.add_argument("--limit", type=int, default=10, help="Number of rows to show (default: 10)")
    p_tx.add_argument("--account", default="All Accounts", help="Filter by account (default: All Accounts)")
    
    # Subscriptions Command
    subparsers.add_parser("subscriptions", help="Detect and list recurring subscriptions")
    
    # Plaid Sync Command
    p_plaid = subparsers.add_parser("plaid", help="Sync transactions from Plaid sandbox bank feeds")
    p_plaid.add_argument("--token", default="mock-sandbox-token", help="Plaid access token")
    
    # Export Command
    p_export = subparsers.add_parser("export", help="Export transaction data to file (CSV, Excel, PDF)")
    p_export.add_argument("output", help="Destination file path")
    p_export.add_argument("--format", default="csv", choices=["csv", "excel", "pdf"], help="File format")
    
    # Status Command
    subparsers.add_parser("status", help="Display cluster, database, and system status")
    
    # Mock Data Generator Command
    p_mock = subparsers.add_parser("mock-data", help="Generate synthetic mock PDF bank statements")
    p_mock.add_argument("--output", default="mock_statement.pdf", help="Destination PDF file name")
    
    # Chaos Monkey Command
    subparsers.add_parser("chaos", help="Run Chaos Monkey fault injection resilience test")
    
    # Test Command
    subparsers.add_parser("test", help="Run full pytest test suite")

    args = parser.parse_args()

    # If --cli or -i flag was passed, open interactive menu directly
    if getattr(args, 'interactive_flag', False):
        run_interactive_menu()
        return

    # Dispatch commands
    if not args.command or args.command == "gui":
        run_gui()
    elif args.command in ("menu", "interactive"):
        run_interactive_menu()
    elif args.command == "server":
        run_server(host=args.host, port=args.port, reload=args.reload)
    elif args.command == "worker":
        run_worker()
    elif args.command == "web":
        run_web()
    elif args.command == "ingest":
        run_ingest(args.file, account_name=args.account)
    elif args.command == "ocr":
        run_ocr(args.file)
    elif args.command in ("sync", "reconcile"):
        run_sync()
    elif args.command == "insights":
        run_insights(account_filter=args.account)
    elif args.command == "transactions":
        run_transactions(limit=args.limit, account_filter=args.account)
    elif args.command == "subscriptions":
        run_subscriptions()
    elif args.command == "plaid":
        run_plaid(access_token=args.token)
    elif args.command == "export":
        run_export(args.output, format_type=args.format)
    elif args.command == "status":
        run_status()
    elif args.command == "mock-data":
        run_mock_data(filename=args.output)
    elif args.command == "chaos":
        run_chaos()
    elif args.command == "test":
        run_tests()

if __name__ == "__main__":
    main()
