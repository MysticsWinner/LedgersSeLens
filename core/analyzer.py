"""
LedgerSeLens Financial Analyzer & Ingestion Dispatcher
Integrates data ingestion across PDF, Excel, CSV, and OCR Images with
multi-tier payment categorization and subscription detection.
"""

import re
import datetime
import logging
import pandas as pd
from typing import Dict, Any, List, Optional

from database.db_manager import get_categories, save_transaction, get_all_transactions, init_db
from core.payment_categorizer import classify_payment
from core.data_ingestion import ingest_file, IngestionResult

logger = logging.getLogger(__name__)

# Initialize database on module load
try:
    init_db()
except Exception as e:
    logger.debug(f"init_db deferred: {e}")

def categorize_transaction(description: str, categories_cache: Optional[List[Dict[str, Any]]] = None, amount: Optional[float] = None) -> str:
    """
    Categorizes a transaction description through a 5-tier fallback cascade:
      1. Explicit user/database match rules
      2. Specialized payment categorization (Credit Card, Loan, Transfer, Bill, Tax, Sub)
      3. Machine Learning classifier (Naive Bayes in ml_engine.py)
      4. Built-in merchant & keyword dictionary heuristics
      5. Safe default ('Other')
    """
    if not description:
        return 'Other'

    desc_str = str(description)
    desc_lower = desc_str.lower()
    
    if categories_cache is None:
        categories_cache = get_categories()

    # Tier 1: Explicit Database Rules
    for cat in categories_cache:
        rules = cat.get('match_rules')
        if not rules:
            continue
        keywords = [k.strip().lower() for k in rules.split(',')]
        for keyword in keywords:
            if keyword and keyword in desc_lower:
                return cat['name']

    # Tier 2: Payment Classification Engine
    payment_category = classify_payment(desc_str, amount)
    if payment_category:
        if any(c['name'] == payment_category for c in categories_cache):
            return payment_category

    # Tier 3: Machine Learning Model Fallback
    try:
        from core.ml_engine import predict_category
        ml_pred = predict_category(desc_str)
        if ml_pred and ml_pred != "Other":
            if any(c['name'] == ml_pred for c in categories_cache):
                return ml_pred
    except Exception as e:
        logger.debug(f"ML categorization skipped: {e}")

    # Tier 4: Heuristic Merchant Dictionary
    ai_guesses = {
        'doordash': 'Food', 'ubereats': 'Food', 'grubhub': 'Food', 'starbucks': 'Food',
        'mcdonalds': 'Food', 'chipotle': 'Food', 'panera': 'Food', 'subway': 'Food',
        'chevron': 'Transport', 'shell': 'Transport', 'arco': 'Transport', 'exxon': 'Transport',
        'delta': 'Transport', 'american airlines': 'Transport', 'united airlines': 'Transport',
        'uber': 'Transport', 'lyft': 'Transport', 'caltrain': 'Transport',
        'walmart': 'Shopping', 'target': 'Shopping', 'amazon': 'Shopping', 'costco': 'Shopping',
        'best buy': 'Shopping', 'apple store': 'Shopping', 'home depot': 'Shopping',
        'hospital': 'Healthcare', 'clinic': 'Healthcare', 'pharmacy': 'Healthcare', 'cvs': 'Healthcare', 'walgreens': 'Healthcare',
        'comcast': 'Utilities', 'pg&e': 'Utilities', 'verizon': 'Utilities', 'at&t': 'Utilities', 'coned': 'Utilities',
        'payroll': 'Income', 'direct deposit': 'Income', 'salary': 'Income', 'tax refund': 'Income',
        'netflix': 'Entertainment', 'spotify': 'Entertainment', 'hulu': 'Entertainment', 'steam': 'Entertainment',
        'venmo': 'Payment: Transfer & P2P', 'zelle': 'Payment: Transfer & P2P', 'paypal': 'Payment: Transfer & P2P'
    }
    for key, val in ai_guesses.items():
        if key in desc_lower:
            if any(c['name'] == val for c in categories_cache):
                return val

    # Tier 5: Safe Default
    return 'Other'

def parse_statement(file_path: str, account_name: str = "Main Account") -> pd.DataFrame:
    """
    Universal ingestion dispatcher:
    Accepts CSV, TSV, Excel (.xlsx, .xls), PDF, and Images (.png, .jpg, .jpeg).
    """
    result = ingest_file(file_path, account_name)
    df_parsed = result.dataframe
    
    if df_parsed.empty:
        return load_all_transactions_df(account_filter="All Accounts")
        
    return _process_transactions(df_parsed.to_dict(orient='records'), account_name)

def parse_csv_statement(file_path: str, account_name: str = "Main Account") -> pd.DataFrame:
    """Specific CSV statement parser with automatic fallbacks."""
    from core.data_ingestion import ingest_csv
    result = ingest_csv(file_path, account_name)
    return _process_transactions(result.dataframe.to_dict(orient='records'), account_name)

def parse_excel_statement(file_path: str, account_name: str = "Main Account") -> pd.DataFrame:
    """Specific Excel statement parser."""
    from core.data_ingestion import ingest_excel
    result = ingest_excel(file_path, account_name)
    return _process_transactions(result.dataframe.to_dict(orient='records'), account_name)

def parse_pdf_statement(file_path: str, account_name: str = "Main Account") -> pd.DataFrame:
    """Specific PDF statement parser with layout and OCR fallbacks."""
    from core.data_ingestion import ingest_pdf
    result = ingest_pdf(file_path, account_name)
    return _process_transactions(result.dataframe.to_dict(orient='records'), account_name)

def _process_transactions(transactions: List[Dict[str, Any]], account_name: str) -> pd.DataFrame:
    """
    Normalizes, categorizes, and saves transactions to the database.
    """
    cats = get_categories()
    
    if transactions:
        df = pd.DataFrame(transactions)
        if not df.empty and 'Date' in df.columns and 'Amount' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df = df.dropna(subset=['Date', 'Amount'])
            
            # Categorize any rows where category is missing or 'Other'
            def _ensure_category(row):
                existing_cat = row.get('Category')
                if existing_cat and str(existing_cat).strip().lower() not in ('none', 'nan', '', 'other'):
                    # Validate against known categories
                    if any(c['name'] == existing_cat for c in cats):
                        return existing_cat
                return categorize_transaction(row.get('Description', ''), cats, row.get('Amount'))

            df['Category'] = df.apply(_ensure_category, axis=1)
            
            # Persist to DB
            for _, row in df.iterrows():
                save_transaction(
                    date=row['Date'].strftime('%Y-%m-%d'), 
                    desc=str(row['Description']), 
                    amount=float(row['Amount']), 
                    category_name=str(row['Category']),
                    account_name=str(row.get('Account', account_name)),
                    notes=str(row.get('Notes', '')),
                    receipt_path=str(row.get('Receipt', ''))
                )
            
    result_df = load_all_transactions_df(account_filter="All Accounts")
    
    # Budget Notification Check
    if not result_df.empty:
        try:
            from plyer import notification
            current_month = datetime.datetime.now().strftime('%Y-%m')
            this_month = result_df[result_df['Date'].dt.strftime('%Y-%m') == current_month]
            monthly_expenses = this_month[this_month['Amount'] < 0]['Amount'].abs().sum()
            
            if monthly_expenses > 2500.0:
                notification.notify(
                    title='LedgerLens Budget Alert',
                    message=f'Warning: Monthly expenses have reached ${monthly_expenses:,.2f}, exceeding the $2,500 budget!',
                    app_name='LedgerLens',
                    timeout=5
                )
        except Exception as e:
            logger.debug(f"Notification skipped: {e}")
            
    return result_df

def load_all_transactions_df(start_date=None, end_date=None, account_filter="All Accounts") -> pd.DataFrame:
    rows = get_all_transactions(start_date, end_date, account_filter)
    if not rows:
        return pd.DataFrame(columns=['ID', 'Date', 'Description', 'Amount', 'Category', 'Account', 'Notes', 'Receipt'])
        
    df = pd.DataFrame(rows, columns=['ID', 'Date', 'Description', 'Amount', 'Category', 'Account', 'Notes', 'Receipt'])
    df['Date'] = pd.to_datetime(df['Date'])
    df['Amount'] = df['Amount'].astype(float)
    df = df.sort_values(by='Date', ascending=False).reset_index(drop=True)
    return df

def generate_insights(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or df.get('empty', False) is True:
        return {
            'total_spent': 0.0,
            'total_received': 0.0,
            'category_breakdown': pd.Series(dtype=float),
            'timeline': pd.Series(dtype=float),
            'forecast': pd.Series(dtype=float),
            'transactions': pd.DataFrame()
        }
        
    total_spent = df[df['Amount'] < 0]['Amount'].abs().sum() if not df.empty else 0.0
    total_received = df[df['Amount'] >= 0]['Amount'].sum() if not df.empty else 0.0
    
    # Category breakdown (expenses only)
    expenses_df = df[df['Amount'] < 0]
    if not expenses_df.empty:
        category_breakdown = expenses_df.groupby('Category')['Amount'].apply(lambda x: x.abs().sum())
    else:
        category_breakdown = pd.Series(dtype=float)
    
    # Timeline
    timeline = df.groupby(df['Date'].dt.date)['Amount'].sum()
    
    # Forecast / Trendline (Rolling 7-Day Average curve)
    expenses_timeline = df[df['Amount'] < 0].groupby(df['Date'].dt.date)['Amount'].sum()
    forecast = expenses_timeline.rolling(window=7, min_periods=1).mean().abs() if not expenses_timeline.empty else pd.Series(dtype=float)
    
    return {
        'total_spent': float(total_spent),
        'total_received': float(total_received),
        'category_breakdown': category_breakdown,
        'timeline': timeline,
        'forecast': forecast,
        'transactions': df
    }

def detect_subscriptions(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Detects recurring transactions occurring approximately every 30 days or 7 days.
    """
    if df.empty:
        return []
    
    expenses = df[df['Amount'] < 0].copy()
    if expenses.empty:
        return []
        
    expenses = expenses.sort_values(by='Date')
    subscriptions = []
    
    grouped = expenses.groupby(['Description', 'Amount'])
    
    for (desc, amount), group in grouped:
        if len(group) >= 2:
            dates = group['Date'].dt.date.tolist()
            diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
            if not diffs: 
                continue
            avg_diff = sum(diffs) / len(diffs)
            
            if (6 <= avg_diff <= 8) or (27 <= avg_diff <= 33):
                freq = "Weekly" if avg_diff < 10 else "Monthly"
                subscriptions.append({
                    "description": str(desc),
                    "amount": float(amount),
                    "frequency": freq,
                    "avg_days_between": round(avg_diff, 1),
                    "last_charged": str(dates[-1])
                })
                
    return sorted(subscriptions, key=lambda x: x['amount'])
