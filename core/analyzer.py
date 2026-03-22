import pdfplumber
import pandas as pd
import re
from database.db_manager import get_categories, save_transaction, get_all_transactions, init_db

# Initialize database on module load
init_db()

def categorize_transaction(description, categories_cache):
    description_lower = str(description).lower()
    for cat in categories_cache:
        rules = cat['match_rules']
        if not rules:
            continue
        keywords = [k.strip().lower() for k in rules.split(',')]
        for keyword in keywords:
            if keyword and keyword in description_lower:
                return cat['name']
    
    # AI Fallback Mock / Advanced Heuristic Matching
    ai_guesses = {
        'doordash': 'Food', 'ubereats': 'Food', 'grubhub': 'Food',
        'chevron': 'Transport', 'shell': 'Transport', 'arco': 'Transport',
        'delta': 'Transport', 'american airlines': 'Transport',
        'walmart': 'Shopping', 'target': 'Shopping', 'amazon': 'Shopping',
        'hospital': 'Other', 'clinic': 'Other', 'pharmacy': 'Other',
        'comcast': 'Utilities', 'pg&e': 'Utilities', 'verizon': 'Utilities',
        'payroll': 'Income', 'deposit': 'Income', 'venmo': 'Other'
    }
    for key, val in ai_guesses.items():
        if key in description_lower:
            if any(c['name'] == val for c in categories_cache):
                return val
    
    return 'Other'

def parse_statement(file_path, account_name="Main Account"):
    """
    Dispatcher to handle PDF or CSV files.
    """
    if str(file_path).lower().endswith('.csv'):
        return parse_csv_statement(file_path, account_name)
    else:
        return parse_pdf_statement(file_path, account_name)

def _process_transactions(transactions, account_name):
    cats = get_categories()
    
    df = pd.DataFrame(transactions)
    if not df.empty:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        
        # Categorize
        df['Category'] = df['Description'].apply(lambda d: categorize_transaction(d, cats))
        
        # Save to DB
        for _, row in df.iterrows():
            save_transaction(
                row['Date'].strftime('%Y-%m-%d'), 
                str(row['Description']), 
                float(row['Amount']), 
                str(row['Category']),
                account_name
            )
            
    return load_all_transactions_df(account_filter="All Accounts")

def load_all_transactions_df(start_date=None, end_date=None, account_filter="All Accounts"):
    rows = get_all_transactions(start_date, end_date, account_filter)
    if not rows:
        return pd.DataFrame()
    # id, date, description, amount, category_name, account_name, notes, receipt_path
    df = pd.DataFrame(rows, columns=['ID', 'Date', 'Description', 'Amount', 'Category', 'Account', 'Notes', 'Receipt'])
    df['Date'] = pd.to_datetime(df['Date'])
    df['Amount'] = df['Amount'].astype(float)
    # Sort chronologically
    df = df.sort_values(by='Date', ascending=False).reset_index(drop=True)
    return df

def parse_pdf_statement(file_path, account_name):
    transactions = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                start_idx = 0
                if "Date" in str(table[0]) or "Description" in str(table[0]):
                    start_idx = 1
                for row in table[start_idx:]:
                    if len(row) >= 3 and row[0] and row[1]:
                        date = row[0]
                        desc = row[1]
                        amount_str = row[2]
                        if not amount_str: 
                            continue
                        amount_str = amount_str.replace('$', '').replace(',', '').strip()
                        try:
                            if amount_str.startswith('(') and amount_str.endswith(')'):
                                amount = -float(amount_str[1:-1])
                            else:
                                amount = float(amount_str)
                            transactions.append({
                                'Date': date,
                                'Description': desc,
                                'Amount': amount
                            })
                        except ValueError:
                            pass
    return _process_transactions(transactions, account_name)

def parse_csv_statement(file_path, account_name):
    transactions = []
    try:
        df_csv = pd.read_csv(file_path)
        if all(col in df_csv.columns for col in ['Date', 'Description', 'Amount']):
            for _, row in df_csv.iterrows():
                 try:
                     amt_str = str(row['Amount']).replace('$', '').replace(',', '').strip()
                     if amt_str.startswith('(') and amt_str.endswith(')'):
                         amount = -float(amt_str[1:-1])
                     else:
                         amount = float(amt_str)
                     transactions.append({
                         'Date': row['Date'],
                         'Description': row['Description'],
                         'Amount': amount
                     })
                 except ValueError:
                     pass
    except Exception as e:
        print(f"Error parsing CSV: {e}")

    return _process_transactions(transactions, account_name)

def generate_insights(df):
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
        'total_spent': total_spent,
        'total_received': total_received,
        'category_breakdown': category_breakdown,
        'timeline': timeline,
        'forecast': forecast,
        'transactions': df
    }
