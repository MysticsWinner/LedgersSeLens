import argparse
import sys
import pandas as pd
from core.analyzer import load_all_transactions_df, generate_insights

def print_insights():
    df = load_all_transactions_df()
    if df.empty:
        print("No transactions found in the database. Please ingest some data first.")
        return

    insights = generate_insights(df)
    
    print("=" * 40)
    print("        LEDGERLENS INSIGHTS")
    print("=" * 40)
    print(f"Total Spent:    ${insights['total_spent']:,.2f}")
    print(f"Total Received: ${insights['total_received']:,.2f}")
    
    print("\n--- Top Expense Categories ---")
    cat_breakdown = insights['category_breakdown'].sort_values(ascending=False).head(5)
    for cat, amt in cat_breakdown.items():
        print(f"{cat:15} ${amt:,.2f}")
    print("=" * 40)

def print_transactions(limit=10):
    df = load_all_transactions_df()
    if df.empty:
        print("No transactions found.")
        return
        
    print(f"Showing the latest {limit} transactions:")
    print("-" * 80)
    print(f"{'Date':12} | {'Amount':10} | {'Category':15} | {'Description'}")
    print("-" * 80)
    
    for _, row in df.head(limit).iterrows():
        # Truncate description for neatness
        desc = (row['Description'][:40] + '...') if len(row['Description']) > 40 else row['Description']
        print(f"{row['Date'].strftime('%Y-%m-%d'):12} | ${row['Amount']:<9.2f} | {row['Category']:15} | {desc}")
    print("-" * 80)

def print_reconcile():
    from database.db_manager import reconcile_and_sync_all
    print("Initiating Bidirectional Data Reconciliation...")
    result = reconcile_and_sync_all()
    print("=" * 45)
    print("       DATA RECONCILIATION SUMMARY")
    print("=" * 45)
    print(f"Status:                      {result.get('status')}")
    print(f"Pushed Local -> Remote:      {result.get('pushed_to_remote', 0)}")
    print(f"Pulled Remote -> Local:      {result.get('pulled_to_local', 0)}")
    print(f"Field Conflicts Resolved:    {result.get('conflicts_resolved', 0)}")
    print(f"Total Unified Transactions:  {result.get('total_unified_transactions', 0)}")
    print("=" * 45)

def main():
    parser = argparse.ArgumentParser(description="LedgerLens Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Insights Command
    subparsers.add_parser("insights", help="Print a summary of income, expenses, and top categories.")

    # Transactions Command
    parser_trans = subparsers.add_parser("transactions", help="List recent transactions.")
    parser_trans.add_argument("--limit", type=int, default=10, help="Number of transactions to show (default: 10)")

    # Sync / Reconcile Command
    subparsers.add_parser("sync", help="Bidirectionally reconcile and sync all historical and local transactions.")

    args = parser.parse_args()

    if args.command == "insights":
        print_insights()
    elif args.command == "transactions":
        print_transactions(limit=args.limit)
    elif args.command == "sync":
        print_reconcile()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
