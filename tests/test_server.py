import pytest
from fastapi.testclient import TestClient
from server import app
from database import db_manager

import os

TEST_DB = 'test_server_data.db'

@pytest.fixture(autouse=True)
def setup_teardown_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    db_manager.DB_FILE = TEST_DB
    db_manager.init_db()
    
    # Seed mock data for REST endpoints to retrieve
    db_manager.save_transaction("2026-03-01", "Netflix", -15.99, "Entertainment")
    db_manager.save_transaction("2026-04-01", "Netflix", -15.99, "Entertainment")
    db_manager.save_transaction("2026-03-15", "Salary", 2000.0, "Income")
    
    yield
    
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass

client = TestClient(app)

def test_get_transactions():
    response = client.get("/api/transactions?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["data"]) == 3
    # Transactions are sorted descending by date implicitly
    assert data["data"][0]["Category"] == "Entertainment"

def test_get_insights():
    response = client.get("/api/insights")
    assert response.status_code == 200
    data = response.json()
    assert data["total_received"] == 2000.0
    assert data["total_spent"] > 30.0
    
def test_get_subscriptions():
    response = client.get("/api/subscriptions")
    assert response.status_code == 200
    data = response.json()
    subs = data["data"]
    assert len(subs) == 1
    assert subs[0]["description"].lower() == "netflix"
    assert subs[0]["frequency"] == "Monthly"

def test_post_plaid_sync():
    response = client.post("/api/plaid/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["transactions_imported"]) == 3
