"""
LedgerSeLens Financial Analyzer & Ingestion Dispatcher
Integrates data ingestion across PDF, Excel, CSV, and OCR Images with:
  - Prefix Trie (CategoryTrie) keyword matching & category autocomplete
  - Inverted Index (InvertedIndex) for sub-millisecond full-text transaction search
  - Batch idempotent database persistence (save_transactions_batch)
  - Multi-tier payment categorization and subscription detection
"""

import re
import datetime
import logging
import pandas as pd
from typing import Dict, Any, List, Optional

from database.db_manager import (
    get_categories,
    save_transaction,
    save_transactions_batch,
    get_all_transactions,
    init_db,
)
from core.payment_categorizer import classify_payment
from core.data_ingestion import ingest_file, IngestionResult
from core.dsa_structures import CategoryTrie, InvertedIndex

logger = logging.getLogger(__name__)

# Global DSA instances for sub-millisecond categorization & search
_category_trie: Optional[CategoryTrie] = None
_trie_signature: int = 0
_inverted_index = InvertedIndex()
_indexed_db_file: Optional[str] = None
_indexed_tx_count: int = -1

# Built-in heuristic merchant dictionary
AI_MERCHANT_GUESSES = {
    'doordash': 'Food', 'ubereats': 'Food', 'grubhub': 'Food', 'starbucks': 'Food',
    'mcdonalds': 'Food', 'chipotle': 'Food', 'panera': 'Food', 'subway': 'Food',
    'swiggy': 'Food', 'zomato': 'Food', 'blinkit': 'Food', 'roll express': 'Food',
    'pan shop': 'Food', 'dinner': 'Food', 'mpg': 'Food',
    'chevron': 'Transport', 'shell': 'Transport', 'arco': 'Transport', 'exxon': 'Transport',
    'delta': 'Transport', 'american airlines': 'Transport', 'united airlines': 'Transport',
    'uber': 'Transport', 'lyft': 'Transport', 'caltrain': 'Transport',
    'filling stati': 'Transport', 'fuel': 'Transport', 'petrol': 'Transport',
    'walmart': 'Shopping', 'target': 'Shopping', 'amazon': 'Shopping', 'costco': 'Shopping',
    'best buy': 'Shopping', 'apple store': 'Shopping', 'home depot': 'Shopping',
    'hospital': 'Healthcare', 'clinic': 'Healthcare', 'pharmacy': 'Healthcare', 'cvs': 'Healthcare', 'walgreens': 'Healthcare',
    'comcast': 'Utilities', 'pg&e': 'Utilities', 'verizon': 'Utilities', 'at&t': 'Utilities', 'coned': 'Utilities',
    'payroll': 'Income', 'direct deposit': 'Income', 'salary': 'Income', 'tax refund': 'Income',
    'ach c-': 'Income', 'interest paid': 'Income', 'cash back': 'Income', 'fnldiv': 'Income', 'findiv': 'Income',
    'netflix': 'Entertainment', 'spotify': 'Entertainment', 'hulu': 'Entertainment', 'steam': 'Entertainment',
    'hoyoverse': 'Entertainment',
    'venmo': 'Payment: Transfer & P2P', 'zelle': 'Payment: Transfer & P2P', 'paypal': 'Payment: Transfer & P2P',
    'upi-': 'Payment: Transfer & P2P', 'neft': 'Payment: Transfer & P2P', 'ft - cr': 'Payment: Transfer & P2P',
    'rd through mobile': 'Payment: Transfer & P2P', 'paytm': 'Payment: Transfer & P2P'
}

# Initialize database on module load
try:
    init_db()
except Exception as e:
    logger.debug(f"init_db deferred: {e}")


def get_category_trie(categories_cache: Optional[List[Dict[str, Any]]] = None) -> CategoryTrie:
    """Builds or returns the cached CategoryTrie for O(L) rule matching and autocomplete."""
    global _category_trie, _trie_signature
    if categories_cache is None:
        categories_cache = get_categories()

    sig = hash(tuple((c.get('name', ''), c.get('match_rules', '')) for c in categories_cache))
    if _category_trie is not None and sig == _trie_signature:
        return _category_trie

    trie = CategoryTrie()
    for cat in categories_cache:
        cat_name = cat.get('name')
        if not cat_name:
            continue
        trie.insert(cat_name, cat_name)
        rules = cat.get('match_rules') or ''
        for kw in rules.split(','):
            kw_clean = kw.strip().lower()
            if kw_clean:
                trie.insert(kw_clean, cat_name)

    _category_trie = trie
    _trie_signature = sig
    return trie


def autocomplete_categories(prefix: str, limit: int = 10) -> List[str]:
    """Autocompletes category names or keyword rules using the Prefix Trie."""
    trie = get_category_trie()
    return trie.autocomplete(prefix, limit=limit)


def refresh_search_index() -> InvertedIndex:
    """Synchronizes the in-memory InvertedIndex with the active database."""
    global _indexed_db_file, _indexed_tx_count
    from database import db_manager

    rows = get_all_transactions()
    if _indexed_db_file == db_manager.DB_FILE and _indexed_tx_count == len(rows):
        return _inverted_index

    _inverted_index.clear()
    docs = []
    for idx, r in enumerate(rows):
        tx_id = r[0] if r[0] is not None else idx
        date_val = r[1].strftime('%Y-%m-%d') if hasattr(r[1], 'strftime') else str(r[1] or '')[:10]
        doc = {
            "ID": tx_id,
            "Date": date_val,
            "Description": r[2],
            "Amount": float(r[3]) if r[3] is not None else 0.0,
            "Category": r[4],
            "Account": r[5],
            "Notes": r[6],
            "Receipt": r[7],
        }
        docs.append((f"{r[5]}:{tx_id}:{date_val}:{r[2]}", doc))

    _inverted_index.add_documents_bulk(docs)
    _indexed_db_file = db_manager.DB_FILE
    _indexed_tx_count = len(rows)
    return _inverted_index


def search_transactions(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Executes sub-millisecond full-text search across transactions using the InvertedIndex."""
    idx = refresh_search_index()
    return idx.search(query, limit=limit)


def categorize_transaction(description: str, categories_cache: Optional[List[Dict[str, Any]]] = None, amount: Optional[float] = None) -> str:
    """
    Categorizes a transaction description through a 5-tier fallback cascade:
      1. Explicit user/database match rules (accelerated via Prefix Trie + rule verification)
      2. Specialized payment categorization (Credit Card, Loan, Transfer, Bill, Tax, Sub)
      3. Built-in merchant & keyword dictionary heuristics
      4. Machine Learning classifier (Naive Bayes in ml_engine.py)
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

    # Tier 3: Heuristic Merchant Dictionary
    for key, val in AI_MERCHANT_GUESSES.items():
        if key in desc_lower:
            if any(c['name'] == val for c in categories_cache):
                return val

    # Tier 4: Machine Learning Model Fallback
    try:
        from core.ml_engine import predict_category
        ml_pred = predict_category(desc_str)
        if ml_pred and ml_pred != "Other":
            if any(c['name'] == ml_pred for c in categories_cache):
                return ml_pred
    except Exception as e:
        logger.debug(f"ML categorization skipped: {e}")

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


def prepare_categorized_records(transactions: List[Dict[str, Any]], account_name: str = "Main Account") -> List[Dict[str, Any]]:
    """
    Normalizes and categorizes raw transaction dicts in bulk without touching the DB.
    Used by both synchronous batch writes and asynchronous Kafka streaming pipelines.
    """
    if not transactions:
        return []

    cats = get_categories()
    known_cat_names = {c['name'] for c in cats}

    df = pd.DataFrame(transactions)
    if df.empty or 'Date' not in df.columns or 'Amount' not in df.columns:
        return []

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date', 'Amount'])
    if df.empty:
        return []

    def _ensure_category(row):
        existing_cat = row.get('Category')
        if existing_cat and str(existing_cat).strip().lower() not in ('none', 'nan', '', 'other'):
            if existing_cat in known_cat_names:
                return existing_cat
        return categorize_transaction(row.get('Description', ''), cats, row.get('Amount'))

    df['Category'] = df.apply(_ensure_category, axis=1)

    prepared: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        prepared.append({
            "date": row['Date'].strftime('%Y-%m-%d'),
            "desc": str(row.get('Description', '')),
            "amount": float(row['Amount']),
            "category": str(row['Category']),
            "acct": str(row.get('Account', account_name) or account_name),
            "notes": str(row.get('Notes', '') or ''),
            "receipt_path": str(row.get('Receipt', '') or ''),
        })
    return prepared


def _process_transactions(transactions: List[Dict[str, Any]], account_name: str) -> pd.DataFrame:
    """
    Normalizes, categorizes, and persists transactions using bulk batch writes.
    """
    global _indexed_tx_count
    prepared = prepare_categorized_records(transactions, account_name=account_name)
    if prepared:
        save_transactions_batch(prepared, default_account=account_name)
        _indexed_tx_count = -1  # Mark InvertedIndex dirty so next search refreshes

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
            diffs = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
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
