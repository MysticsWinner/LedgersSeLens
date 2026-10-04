"""
End-to-End Test Suite for Offline Resilience & Bidirectional Reconciliation
Tests the exact 4-Phase System Scenario:
  Scenario 1: All distributed systems working (Transactions ingested to primary).
  Scenario 2: Outage occurs / no systems working (Transactions ingested via fallback store).
  Scenario 3: Solution executes in local-only / offline mode (Accumulating local statements).
  Scenario 4: All distributed services restored to perfect health -> The solution
              bidirectionally reconciles, merges historical + new data, eliminates duplicates,
              and generates the complete unified record.
"""

import pytest
import os
import sqlite3
import pandas as pd
from database import db_manager
from database.sync_manager import reconcile_and_sync, _build_tx_identity_key

TEST_LOCAL_DB = 'test_scenario_local.db'
TEST_SHARD_DB = 'test_scenario_shard.db'

@pytest.fixture(autouse=True)
def clean_databases():
    for f in [TEST_LOCAL_DB, TEST_SHARD_DB]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass
            
    db_manager.DB_FILE = TEST_LOCAL_DB
    db_manager._init_sqlite()
    
    # Initialize the mock shard database with identical schema
    shard_conn = sqlite3.connect(TEST_SHARD_DB)
    c = shard_conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT,
            match_rules TEXT,
            budget_limit REAL DEFAULT 0.0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            description TEXT,
            amount REAL,
            category_name TEXT,
            account_name TEXT DEFAULT 'Main Account',
            notes TEXT DEFAULT '',
            receipt_path TEXT DEFAULT ''
        )
    ''')
    shard_conn.commit()
    shard_conn.close()

    yield

    for f in [TEST_LOCAL_DB, TEST_SHARD_DB]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

def test_full_four_scenario_lifecycle(monkeypatch):
    """
    Validates complete data convergence across the 4 operational phases:
      Phase 1: Remote up -> Writes to remote shard.
      Phase 2: Remote down -> Graceful fallback writes to local SQLite.
      Phase 3: Local-only execution -> Accumulates local statements.
      Phase 4: Remote recovers -> Bidirectional reconciliation merges all data.
    """

    # Helper to simulate remote shard connection
    def mock_get_shard_connection(account_name="Main Account"):
        return sqlite3.connect(TEST_SHARD_DB)

    # =========================================================================
    # SCENARIO 1: All Systems Working
    # =========================================================================
    # Primary remote shard is healthy and accessible
    shard_conn = sqlite3.connect(TEST_SHARD_DB)
    sc = shard_conn.cursor()
    sc.execute('INSERT INTO transactions (date, description, amount, category_name, account_name) VALUES (?, ?, ?, ?, ?)',
               ('2026-01-10', 'SCENARIO 1: PAYROLL DEPOSIT', 3000.0, 'Income', 'Checking'))
    sc.execute('INSERT INTO transactions (date, description, amount, category_name, account_name) VALUES (?, ?, ?, ?, ?)',
               ('2026-01-12', 'SCENARIO 1: WHOLE FOODS MARKET', -85.50, 'Food', 'Checking'))
    shard_conn.commit()
    shard_conn.close()

    # Verify remote has Scenario 1 transactions
    shard_conn = sqlite3.connect(TEST_SHARD_DB)
    remote_rows_sc1 = shard_conn.cursor().execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    shard_conn.close()
    assert remote_rows_sc1 == 2, "Scenario 1 should have 2 transactions in remote store."

    # =========================================================================
    # SCENARIO 2: No Systems Working (Outage / Network Partition)
    # =========================================================================
    # Primary is unreachable. Save operations fallback safely to local SQLite.
    db_manager.save_transaction('2026-02-01', 'SCENARIO 2: EMERGENCY PLUMBING', -250.0, 'Housing', 'Checking', notes="Fallback write")
    db_manager.save_transaction('2026-02-02', 'SCENARIO 2: LOCAL PHARMACY', -35.0, 'Healthcare', 'Checking')

    # Verify local SQLite captured Scenario 2 transactions
    local_conn = sqlite3.connect(TEST_LOCAL_DB)
    local_rows_sc2 = local_conn.cursor().execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    local_conn.close()
    assert local_rows_sc2 == 2, "Scenario 2 should have 2 transactions in local fallback store."

    # =========================================================================
    # SCENARIO 3: Solution Ran in Local-Only Mode (Offline Laptop / Air-Gapped)
    # =========================================================================
    # User continues ingesting statements and receipts offline
    from core.data_ingestion import ingest_csv
    csv_data = (
        "Date,Description,Amount,Category\n"
        "2026-03-01,SCENARIO 3: FREELANCE INVOICE,1200.00,Income\n"
        "2026-03-05,SCENARIO 3: NETFLIX SUBSCRIPTION,-15.99,Payment: Subscription\n"
    )
    res_sc3 = ingest_csv(csv_data.encode('utf-8'), account_name="Checking")
    assert res_sc3.valid_rows == 2

    # Save to local store
    for _, row in res_sc3.dataframe.iterrows():
        db_manager.save_transaction(
            row['Date'].strftime('%Y-%m-%d'),
            row['Description'],
            row['Amount'],
            row['Category'],
            row['Account']
        )

    # Local store now has Scenario 2 + Scenario 3 transactions (4 total)
    local_conn = sqlite3.connect(TEST_LOCAL_DB)
    local_rows_sc3 = local_conn.cursor().execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    local_conn.close()
    assert local_rows_sc3 == 4, "Local store should have accumulated 4 transactions across Scenarios 2 & 3."

    # =========================================================================
    # SCENARIO 4: All Services Are Restored & Healthy!
    # =========================================================================
    # Remote shard is reachable again. Perform bidirectional reconciliation.
    # Monkeypatch db_manager connection routing to point to our mock shard
    monkeypatch.setattr(db_manager, "_probe_postgres", lambda: True)
    monkeypatch.setattr(db_manager, "get_connection_for_url", lambda url: sqlite3.connect(TEST_SHARD_DB))
    monkeypatch.setattr(db_manager, "get_connection", lambda acct="Main Account": sqlite3.connect(TEST_SHARD_DB))

    sync_result = reconcile_and_sync()

    assert sync_result["status"] == "success"
    assert sync_result["synced"] is True
    # 4 local transactions (from Scenarios 2 & 3) pushed to remote
    assert sync_result["pushed_to_remote"] == 4
    # 2 remote transactions (from Scenario 1) pulled to local
    assert sync_result["pulled_to_local"] == 2

    # Verify Remote Store has ALL 6 Transactions with Zero Duplicates
    shard_conn = sqlite3.connect(TEST_SHARD_DB)
    all_remote = shard_conn.cursor().execute('SELECT description, amount FROM transactions').fetchall()
    shard_conn.close()
    assert len(all_remote) == 6, f"Remote should have converged to exactly 6 transactions. Found: {len(all_remote)}"

    # Verify Local Store also has ALL 6 Transactions
    local_conn = sqlite3.connect(TEST_LOCAL_DB)
    all_local = local_conn.cursor().execute('SELECT description, amount FROM transactions').fetchall()
    local_conn.close()
    assert len(all_local) == 6, f"Local should have converged to exactly 6 transactions. Found: {len(all_local)}"

    # Verify descriptions from ALL 3 previous scenarios are present
    descriptions_remote = [r[0] for r in all_remote]
    assert any("SCENARIO 1: PAYROLL DEPOSIT" in d for d in descriptions_remote)
    assert any("SCENARIO 1: WHOLE FOODS" in d for d in descriptions_remote)
    assert any("SCENARIO 2: EMERGENCY PLUMBING" in d for d in descriptions_remote)
    assert any("SCENARIO 2: LOCAL PHARMACY" in d for d in descriptions_remote)
    assert any("SCENARIO 3: FREELANCE INVOICE" in d for d in descriptions_remote)
    assert any("SCENARIO 3: NETFLIX" in d for d in descriptions_remote)

    # Test Idempotency: Running reconciliation again should push 0 and pull 0
    idempotent_sync = reconcile_and_sync()
    assert idempotent_sync["pushed_to_remote"] == 0
    assert idempotent_sync["pulled_to_local"] == 0
    assert idempotent_sync["conflicts_resolved"] == 0
