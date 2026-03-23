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

def main():
    parser = argparse.ArgumentParser(description="LedgerLens Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Insights Command
    subparsers.add_parser("insights", help="Print a summary of income, expenses, and top categories.")

    # Transactions Command
    parser_trans = subparsers.add_parser("transactions", help="List recent transactions.")
    parser_trans.add_argument("--limit", type=int, default=10, help="Number of transactions to show (default: 10)")

    args = parser.parse_args()

    if args.command == "insights":
        print_insights()
    elif args.command == "transactions":
        print_transactions(limit=args.limit)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
