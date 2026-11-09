"""
Comprehensive Test & Benchmark Suite for LedgerSeLens Scalability Overhaul:
  - Phase 1: Batch Upserts (save_transactions_batch), SQL Push-Down Pagination & Count
  - Phase 2: Async Upload Job Pipeline (/api/upload?async_mode=true, /api/jobs/{job_id}), Worker Batch & DLQ
  - Phase 3: Distributed DSA Structures (BloomFilter, LRUCache, SlidingWindowRateLimiter,
             CategoryTrie, InvertedIndex, MerkleTree Anti-Entropy Sync)
"""

import os
import time
import pytest
from fastapi.testclient import TestClient

from core.dsa_structures import (
    BloomFilter,
    LRUCache,
    SlidingWindowRateLimiter,
    CategoryTrie,
    InvertedIndex,
    MerkleTree,
)
from database import db_manager
from server import app
from worker import process_worker_batch

TEST_SCALABILITY_DB = "test_scalability_suite.db"


@pytest.fixture(autouse=True)
def setup_teardown_scalability_db():
    if os.path.exists(TEST_SCALABILITY_DB):
        try:
            os.remove(TEST_SCALABILITY_DB)
        except Exception:
            pass

    db_manager.DB_FILE = TEST_SCALABILITY_DB
    db_manager.init_db()

    yield

    if os.path.exists(TEST_SCALABILITY_DB):
        try:
            os.remove(TEST_SCALABILITY_DB)
        except Exception:
            pass


client = TestClient(app)


# =============================================================================
# 1. Distributed DSA Unit Tests
# =============================================================================

def test_bloom_filter_zero_false_negatives_and_low_fp_rate():
    bf = BloomFilter(expected_items=2000, false_positive_rate=0.01)
    inserted_keys = [f"acct-{i}|2026-03-01|MERCHANT-{i}|-{i}.50" for i in range(1000)]
    bf.add_many(inserted_keys)

    # Zero false negatives guaranteed
    for key in inserted_keys:
        assert bf.might_contain(key) is True

    # Check false positive rate on 2,000 unseen keys
    false_positives = sum(
        1 for i in range(1000, 3000)
        if bf.might_contain(f"acct-{i}|2026-03-01|UNSEEN-{i}|-{i}.50")
    )
    fp_rate = false_positives / 2000.0
    assert fp_rate < 0.03, f"False positive rate too high: {fp_rate:.4f}"
    stats = bf.stats()
    assert stats["definite_negatives_skipped_db"] > 1900


def test_lru_cache_o1_eviction_and_ttl():
    cache = LRUCache(capacity=3, default_ttl=10.0)
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    cache.put("k3", "v3")

    # Access k1 so k2 becomes Least Recently Used
    assert cache.get("k1") == "v1"

    # Insert k4 -> should evict k2
    cache.put("k4", "v4")
    assert cache.get("k2") is None
    assert cache.get("k1") == "v1"
    assert cache.get("k3") == "v3"
    assert cache.get("k4") == "v4"
    assert cache.stats()["evictions"] == 1

    # Test short TTL expiration
    cache.put("ephemeral", "temp", ttl=0.05)
    time.sleep(0.08)
    assert cache.get("ephemeral") is None


def test_sliding_window_rate_limiter_deque():
    limiter = SlidingWindowRateLimiter(limit=3, window_seconds=1.0)
    t0 = 1000.0
    assert limiter.allow_request("10.0.0.1", now=t0) is True
    assert limiter.allow_request("10.0.0.1", now=t0 + 0.1) is True
    assert limiter.allow_request("10.0.0.1", now=t0 + 0.2) is True
    # 4th request inside 1s window must be rejected
    assert limiter.allow_request("10.0.0.1", now=t0 + 0.3) is False
    # After window slides past t0, request is allowed again
    assert limiter.allow_request("10.0.0.1", now=t0 + 1.05) is True


def test_category_trie_autocomplete_and_keyword_match():
    trie = CategoryTrie()
    trie.insert("starbucks", "Food")
    trie.insert("subway", "Food")
    trie.insert("spotify", "Entertainment")
    trie.insert("shell", "Transport")

    matches = trie.autocomplete("s", limit=10)
    assert set(matches) == {"Food", "Entertainment", "Transport"}
    assert trie.autocomplete("st") == ["Food"]
    assert trie.match_description("POS DEBIT STARBUCKS STORE 1042") == "Food"
    assert trie.match_description("SPOTIFY USA MONTHLY") == "Entertainment"


def test_inverted_index_full_text_search():
    idx = InvertedIndex()
    idx.add_document(1, {"ID": 1, "Date": "2026-03-10", "Description": "AMAZON WEB SERVICES CLOUD", "Category": "Utilities", "Account": "Amex"})
    idx.add_document(2, {"ID": 2, "Date": "2026-03-12", "Description": "AMAZON MARKETPLACE SEATTLE", "Category": "Shopping", "Account": "Chase"})
    idx.add_document(3, {"ID": 3, "Date": "2026-03-15", "Description": "WHOLE FOODS MARKET", "Category": "Food", "Account": "Chase"})

    # Multi-term AND query
    aws_hits = idx.search("amazon cloud")
    assert len(aws_hits) == 1
    assert aws_hits[0]["ID"] == 1

    # Single-term prefix query
    amz_hits = idx.search("amaz")
    assert len(amz_hits) == 2
    assert amz_hits[0]["Date"] == "2026-03-12"  # Sorted descending by date


def test_merkle_tree_bucket_diffing():
    base_records = [
        ("2026-01-10", "payroll", 3000.0, "checking", "", ""),
        ("2026-01-15", "groceries", -120.0, "checking", "", ""),
        ("2026-02-05", "electric bill", -90.0, "checking", "", ""),
        ("2026-03-01", "flight ticket", -450.0, "travel card", "", ""),
    ]
    tree_a = MerkleTree.from_records(base_records)
    tree_b = MerkleTree.from_records(list(reversed(base_records)))

    # Order-independent identical datasets produce identical root hashes in O(1)
    assert tree_a.root_hash == tree_b.root_hash
    assert tree_a.diff_buckets(tree_b) == set()

    # Modify only 2026-02 bucket for 'checking'
    modified_records = list(base_records) + [
        ("2026-02-20", "coffee shop", -6.50, "checking", "", "")
    ]
    tree_c = MerkleTree.from_records(modified_records)
    assert tree_a.root_hash != tree_c.root_hash
    divergent = tree_a.diff_buckets(tree_c)
    assert divergent == {("checking", "2026-02")}


# =============================================================================
# 2. Batch Ingestion & Push-Down Pagination Benchmarks
# =============================================================================

def test_batch_upsert_throughput_and_idempotency():
    batch = [
        {
            "date": f"2026-03-{(i % 28) + 1:02d}",
            "desc": f"BULK_MERCHANT_{i}",
            "amount": -round((i + 1) * 1.25, 2),
            "category": "Shopping",
            "acct": f"Account_{i % 3}",
        }
        for i in range(1000)
    ]

    t0 = time.perf_counter()
    inserted_first = db_manager.save_transactions_batch(batch)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert inserted_first == 1000
    assert db_manager.get_transaction_count() == 1000
    assert elapsed_ms < 2500.0, f"Batch insert of 1,000 rows took too long: {elapsed_ms:.1f}ms"

    # Re-inserting the exact same 1,000 rows must insert 0 duplicates
    inserted_second = db_manager.save_transactions_batch(batch)
    assert inserted_second == 0
    assert db_manager.get_transaction_count() == 1000

    # Paginated push-down query check
    page1, total = db_manager.get_transactions_paginated(limit=25, offset=0)
    assert total == 1000
    assert len(page1) == 25
    assert page1[0]["Date"] >= page1[-1]["Date"]


# =============================================================================
# 3. Scalable REST API & Async Job Pipeline Tests
# =============================================================================

def test_api_search_autocomplete_and_metrics_endpoints():
    db_manager.save_transactions_batch([
        {"date": "2026-03-01", "desc": "STARBUCKS COFFEE", "amount": -6.45, "category": "Food", "acct": "Chase"},
        {"date": "2026-03-02", "desc": "NETFLIX STREAMING", "amount": -15.99, "category": "Entertainment", "acct": "Amex"},
        {"date": "2026-03-03", "desc": "UBER AIRPORT RIDE", "amount": -42.00, "category": "Transport", "acct": "Chase"},
    ])

    # 1. Full-Text Search via Inverted Index
    res_search = client.get("/api/transactions/search?q=starbucks")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert search_data["total"] == 1
    assert search_data["data"][0]["Description"] == "STARBUCKS COFFEE"

    # 2. Prefix Trie Category Autocomplete
    res_auto = client.get("/api/categories/autocomplete?prefix=ent")
    assert res_auto.status_code == 200
    auto_data = res_auto.json()
    assert "Entertainment" in auto_data["matches"]

    # 3. System Scalability Metrics
    res_metrics = client.get("/api/system/metrics")
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()
    assert "lru_cache" in metrics
    assert "inverted_index" in metrics
    assert metrics["inverted_index"]["indexed_documents"] >= 3


def test_async_upload_and_job_status_polling():
    csv_bytes = (
        b"Date,Description,Amount\n"
        b"2026-03-10,ASYNC MERCHANT ONE,-25.00\n"
        b"2026-03-11,ASYNC MERCHANT TWO,-75.50\n"
    )
    response = client.post(
        "/api/upload",
        files={"file": ("async_statement.csv", csv_bytes, "text/csv")},
        data={"account_name": "Async Checking", "async_mode": "true"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["mode"] == "async"
    job_id = payload["job_id"]

    # Poll job status endpoint
    job_res = client.get(f"/api/jobs/{job_id}")
    assert job_res.status_code == 200
    job_state = job_res.json()
    assert job_state["job_id"] == job_id
    assert job_state["status"] in ("completed", "processing", "queued_in_kafka")
    assert job_state["total_records"] == 2


def test_worker_micro_batch_and_dlq_routing():
    dlq_sent = []

    class DummyDLQProducer:
        def send(self, topic, value):
            dlq_sent.append((topic, value))

    messages = [
        {"date": "2026-03-20", "desc": "WORKER TX 1", "amount": -19.99, "category": "Shopping", "acct": "Checking"},
        {"date": "2026-03-21", "desc": "WORKER TX 2", "amount": -49.99, "category": "Food", "acct": "Checking"},
        {"invalid_payload": "missing_amount"},  # Poison pill -> should route to DLQ
    ]

    inserted = process_worker_batch(messages, redis_client=None, dlq_producer=DummyDLQProducer())
    assert inserted == 2
    assert len(dlq_sent) == 1
    assert dlq_sent[0][0] == "ledger-ingestion-dlq"

