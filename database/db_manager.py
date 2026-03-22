import sqlite3
import os

DB_FILE = 'bank_data.db'

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Create Categories table
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT,
            match_rules TEXT,
            budget_limit REAL DEFAULT 0.0
        )
    ''')
    
    # Create Transactions table (Legacy fields)
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            amount REAL,
            category_name TEXT
        )
    ''')
    
    # V2 Migrations
    try:
        c.execute('ALTER TABLE transactions ADD COLUMN account_name TEXT DEFAULT "Main Account"')
    except sqlite3.OperationalError:
        pass # Column exists

    try:
        c.execute('ALTER TABLE transactions ADD COLUMN notes TEXT DEFAULT ""')
    except sqlite3.OperationalError:
        pass

    try:
        c.execute('ALTER TABLE transactions ADD COLUMN receipt_path TEXT DEFAULT ""')
    except sqlite3.OperationalError:
        pass
    
    # Seed default categories if empty
    c.execute('SELECT COUNT(*) FROM categories')
    if c.fetchone()[0] == 0:
        seed_categories(c)
        
    conn.commit()
    conn.close()

def seed_categories(c):
    default_categories = {
        'Food': '#ff9f0a', 
        'Transport': '#64d2ff', 
        'Utilities': '#ffd60a', 
        'Shopping': '#bf5af2', 
        'Entertainment': '#ff453a', 
        'Income': '#32d74b', 
        'Housing': '#0a84ff',
        'Other': '#8e8e93'
    }
    
    default_rules = {
        'Food': 'restaurant,cafe,starbucks,mcdonalds,grocery,whole foods,trader joe',
        'Transport': 'uber,lyft,transit,gas,shell,chevron,mta',
        'Utilities': 'electric,water,internet,comcast,pg&e,verizon',
        'Shopping': 'amazon,walmart,target,apple,best buy',
        'Entertainment': 'netflix,spotify,hulu,steam,amc',
        'Income': 'salary,payroll,deposit,transfer from,dividend,refund,credit',
        'Housing': 'rent,mortgage',
        'Other': ''
    }
    
    for cat_name, color in default_categories.items():
        rules = default_rules.get(cat_name, '')
        c.execute('INSERT INTO categories (name, color, match_rules) VALUES (?, ?, ?)', (cat_name, color, rules))

def get_categories():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
    cats = c.fetchall()
    conn.close()
    return [{'name': row[0], 'color': row[1], 'match_rules': row[2], 'budget_limit': row[3]} for row in cats]

def save_transaction(date, desc, amount, category_name, account_name="Main Account", notes="", receipt_path=""):
    conn = get_connection()
    c = conn.cursor()
    # Check if a transaction exists to avoid duplicates
    c.execute('SELECT COUNT(*) FROM transactions WHERE date=? AND description=? AND amount=? AND account_name=?', 
              (date, desc, amount, account_name))
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (date, desc, amount, category_name, account_name, notes, receipt_path))
        conn.commit()
        added = True
    else:
        added = False
    conn.close()
    return added

def get_all_transactions(start_date=None, end_date=None, account_filter="All Accounts"):
    conn = get_connection()
    c = conn.cursor()
    
    query = 'SELECT id, date, description, amount, category_name, account_name, notes, receipt_path FROM transactions WHERE 1=1'
    params = []
    
    if account_filter and account_filter != "All Accounts":
        query += ' AND account_name=?'
        params.append(account_filter)
        
    if start_date:
        query += ' AND date >= ?'
        params.append(start_date)
        
    if end_date:
        query += ' AND date <= ?'
        params.append(end_date)
        
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def get_accounts():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL')
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]
