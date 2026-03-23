import pytest
import pandas as pd
import os
from core.analyzer import detect_subscriptions, generate_insights
from database import db_manager

TEST_DB = 'test_analyzer.db'

@pytest.fixture(autouse=True)
def setup_teardown_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    db_manager.DB_FILE = TEST_DB
    db_manager.init_db()
    yield
    if os.path.exists(TEST_DB):
        try: os.remove(TEST_DB)
        except Exception: pass

def test_detect_subscriptions():
    # Mock some basic transaction data representing a Netflix sub every 30 days
    data = [
        {"Date": "2026-01-01", "Description": "NETFLIX", "Amount": -15.99},
        {"Date": "2026-01-31", "Description": "NETFLIX", "Amount": -15.99},
        {"Date": "2026-03-02", "Description": "NETFLIX", "Amount": -15.99}, # roughly 30 days apart
        {"Date": "2026-01-01", "Description": "NOISE", "Amount": -50.0},
        {"Date": "2026-01-08", "Description": "SPOTIFY", "Amount": -9.99},
        {"Date": "2026-01-15", "Description": "SPOTIFY", "Amount": -9.99}, # Weekly (~7 days)
    ]
    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date'])
    
    subs = detect_subscriptions(df)
    
    assert len(subs) == 2, "Should detect exactly 2 subscriptions"
    
    # Check Netflix
    netflix = next(s for s in subs if s['description'] == 'NETFLIX')
    assert netflix['amount'] == -15.99
    assert netflix['frequency'] == 'Monthly'
    
    # Check Spotify
    spotify = next(s for s in subs if s['description'] == 'SPOTIFY')
    assert spotify['amount'] == -9.99
    assert spotify['frequency'] == 'Weekly'

def test_generate_insights_empty():
    empty_df = pd.DataFrame()
    insights = generate_insights(empty_df)
    
    assert insights['total_spent'] == 0.0
    assert insights['total_received'] == 0.0

def test_generate_insights_math():
    data = [
        {"Date": "2026-01-01", "Description": "Food", "Amount": -50.0, "Category": "Food"},
        {"Date": "2026-01-02", "Description": "Gas", "Amount": -40.0, "Category": "Transport"},
        {"Date": "2026-01-03", "Description": "Payday", "Amount": 1000.0, "Category": "Income"},
    ]
    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date'])
    
    insights = generate_insights(df)
    
    assert insights['total_spent'] == 90.0 # 50 + 40
    assert insights['total_received'] == 1000.0
    
    cat_breakdown = insights['category_breakdown']
    assert cat_breakdown['Food'] == 50.0
    assert cat_breakdown['Transport'] == 40.0

def test_parse_csv_statement(tmp_path):
    from core.analyzer import parse_csv_statement
    csv_file = tmp_path / "mock_statement.csv"
    
    # Create a messy CSV simulating real bank output
    content = 'Date,Description,Amount\n2026-03-01,AMAZON WEB SERVICES,$(15.25)\n2026-03-02,PAYROLL DEPOSIT,"$2,500.00"\n2026-03-03,CORRUPT ROW,\n'
    csv_file.write_text(content)
    
    df = parse_csv_statement(str(csv_file), "Test Account")
    
    assert len(df) == 2, "Corrupted rows should be dropped"
    
    aws = df[df['Description'] == 'AMAZON WEB SERVICES'].iloc[0]
    assert aws['Amount'] == -15.25, "Found $(15.25) but did not parse to -15.25"
    
    pay = df[df['Description'] == 'PAYROLL DEPOSIT'].iloc[0]
    assert pay['Amount'] == 2500.00, "Found $2,500.00 but did not parse to 2500.00"

def test_categorize_transaction_heuristics():
    from core.analyzer import categorize_transaction
    
    mock_cats = [
        {"name": "Food", "match_rules": "mcdonalds,starbucks"},
        {"name": "Entertainment", "match_rules": "netflix"}
    ]
    
    # Explicit Match
    assert categorize_transaction("STARBUCKS STORE 123", mock_cats) == "Food"
    
    # Heuristic Fallback Mock (from within analyzer.py)
    assert categorize_transaction("UBEREATS DELIVERY", mock_cats) == "Food"
    
    # Unknown
    assert categorize_transaction("RANDOM CHARGE 999", mock_cats) == "Other"

