import pytest
from database import db_manager

# Override the database file to use an in-memory SQLite DB for isolating test side-effects
import os

TEST_DB = 'test_bank_data.db'

@pytest.fixture(autouse=True)
def setup_teardown_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    db_manager.DB_FILE = TEST_DB
    db_manager.init_db()
    
    yield
    
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass

def test_init_db_seeds_categories():
    cats = db_manager.get_categories()
    assert len(cats) > 0, "Categories should be seeded upon init"
    
    # Check if 'Food' is seeded
    food_cat = next((c for c in cats if c['name'] == 'Food'), None)
    assert food_cat is not None
    assert 'restaurant' in food_cat['match_rules']

def test_save_and_get_transaction():
    added = db_manager.save_transaction(
        date="2026-03-23", 
        desc="Test Purchase", 
        amount=-15.00, 
        category_name="Shopping",
        account_name="Test Account"
    )
    
    assert added is True
    
    # Verify retrieval
    txs = db_manager.get_all_transactions()
    assert len(txs) == 1
    assert txs[0][2] == "Test Purchase"
    assert txs[0][3] == -15.00
    assert txs[0][4] == "Shopping"
    assert txs[0][5] == "Test Account"

def test_duplicate_transaction_is_ignored():
    added1 = db_manager.save_transaction("2026-03-23", "Dup", -10.0, "Food")
    added2 = db_manager.save_transaction("2026-03-23", "Dup", -10.0, "Food")
    
    assert added1 is True
    assert added2 is False # Duplicate should not be added
    
    assert len(db_manager.get_all_transactions()) == 1

def test_get_accounts():
    db_manager.save_transaction("2026-03-23", "Food", -10.0, "Food", "Chase Checking")
    db_manager.save_transaction("2026-03-24", "Food", -10.0, "Food", "Chase Checking")
    db_manager.save_transaction("2026-03-25", "Rent", -1000.0, "Housing", "BofA Savings")
    
    accounts = db_manager.get_accounts()
    assert len(accounts) == 2
    assert "Chase Checking" in accounts
    assert "BofA Savings" in accounts

