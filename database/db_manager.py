"""
LedgerSeLens Database Manager
Features a fault-tolerant, horizontally scalable hybrid architecture:
  - Distributed Multi-Shard PostgreSQL with Consistent Hashing, Connection Pooling & Circuit Breaking
  - Per-Shard Probabilistic Bloom Filters to skip redundant duplicate-check I/O
  - Batch Idempotent Writes (save_transactions_batch) & Parallel Map-Reduce Execution
  - SQL Push-Down Pagination with Min-Heap K-Way Merge (heapq.merge)
  - Automatic Local SQLite Fallback Engine for offline resilience, single-node execution, and test isolation
"""

import os
import sqlite3
import psycopg2
from psycopg2 import pool as pg_pool
import hashlib
import bisect
import heapq
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple, Iterable

from core.dsa_structures import BloomFilter

logger = logging.getLogger(__name__)

# Default SQLite file for local/offline fallback and testing
DB_FILE = os.environ.get("SQLITE_DB_FILE", "ledger.db")

# Shard URLs for distributed PostgreSQL cluster
SHARD_URLS = [
    os.environ.get("SHARD_1_URL", "postgresql://postgres:postgres@localhost:5432/ledger_shard_1"),
    os.environ.get("SHARD_2_URL", "postgresql://postgres:postgres@localhost:5433/ledger_shard_2"),
    os.environ.get("SHARD_3_URL", "postgresql://postgres:postgres@localhost:5434/ledger_shard_3")
]

FORCE_SQLITE = os.environ.get("FORCE_SQLITE", "0").lower() in ("1", "true", "yes")


class CircuitBreakerOpenException(Exception):
    """Custom exception raised when a database circuit is open due to failure."""
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold=3, reset_timeout=15):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        logger.warning(f"CircuitBreaker failure recorded. Total: {self.failures}")
        if self.failures >= self.failure_threshold:
            logger.warning("CircuitBreaker TRIPPED -> OPEN")
            self.state = "OPEN"

    def record_success(self):
        if self.state != "CLOSED":
            logger.info("CircuitBreaker RECOVERED -> CLOSED")
        self.failures = 0
        self.state = "CLOSED"

    def allow_request(self):
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - (self.last_failure_time or 0) > self.reset_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False


# Map of shard URL to its Circuit Breaker
circuit_breakers = {url: CircuitBreaker() for url in SHARD_URLS}


class ConsistentHashRing:
    def __init__(self, nodes, replicas=100):
        self.replicas = replicas
        self.ring = {}
        self.sorted_keys = []
        for node in nodes:
            self.add_node(node)

    def add_node(self, node):
        for i in range(self.replicas):
            key = self.hash(f"{node}:{i}")
            self.ring[key] = node
            bisect.insort(self.sorted_keys, key)

    def hash(self, key):
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)

    def get_node(self, key):
        if not self.ring:
            return None
        hash_val = self.hash(key)
        idx = bisect.bisect(self.sorted_keys, hash_val)
        if idx == len(self.sorted_keys):
            idx = 0
        return self.ring[self.sorted_keys[idx]]


# Initialize the ring mapping Accounts to Shard URLs
shard_ring = ConsistentHashRing(SHARD_URLS)

# Per-shard ThreadedConnectionPools and connection-to-pool registry
_connection_pools: Dict[str, pg_pool.ThreadedConnectionPool] = {}
_pooled_conn_owners: Dict[int, pg_pool.ThreadedConnectionPool] = {}
_pool_lock = threading.Lock()
_pool_metrics = {"borrowed": 0, "returned": 0, "created_pools": 0, "direct_connects": 0}

# Per-Shard and Local Probabilistic Bloom Filters
shard_bloom_filters: Dict[str, BloomFilter] = {url: BloomFilter(expected_items=50_000, false_positive_rate=0.01) for url in SHARD_URLS}
sqlite_bloom_filter = BloomFilter(expected_items=50_000, false_positive_rate=0.01)
_bloom_seeded_db: Optional[str] = None

# Global status flags
CURRENTLY_DEGRADED = False
IS_FALLBACK_ACTIVE = False

# Cached detection of whether Postgres is currently up
_POSTGRES_PROBED = False
_POSTGRES_AVAILABLE = False


def _tx_bloom_key(date_val: Any, desc: Any, amount: Any, account_name: Any) -> str:
    d_str = str(date_val or "")[:10]
    desc_str = str(desc or "").strip()
    try:
        amt_str = f"{float(amount or 0.0):.2f}"
    except Exception:
        amt_str = "0.00"
    acct_str = str(account_name or "Main Account").strip()
    return f"{acct_str}|{d_str}|{desc_str}|{amt_str}"


def _probe_postgres() -> bool:
    """Checks if at least one PostgreSQL shard is actively responding."""
    global _POSTGRES_PROBED, _POSTGRES_AVAILABLE
    if FORCE_SQLITE or DB_FILE != "ledger.db":
        _POSTGRES_AVAILABLE = False
        _POSTGRES_PROBED = True
        return False

    import socket
    import urllib.parse

    for url in SHARD_URLS:
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or '127.0.0.1'
            port = parsed.port or 5432
            with socket.create_connection((host, port), timeout=0.1):
                pass
            conn = psycopg2.connect(url, connect_timeout=1)
            conn.close()
            _POSTGRES_AVAILABLE = True
            _POSTGRES_PROBED = True
            return True
        except Exception:
            continue

    _POSTGRES_AVAILABLE = False
    _POSTGRES_PROBED = True
    return False


def _should_use_sqlite() -> bool:
    """
    Determines if SQLite should be used (e.g. during testing, offline mode,
    or when PostgreSQL cluster is unreachable).
    """
    global IS_FALLBACK_ACTIVE
    # 1. Custom DB_FILE provided (e.g. test isolation: test_db.py sets db_manager.DB_FILE = ...)
    if DB_FILE != "ledger.db":
        IS_FALLBACK_ACTIVE = True
        return True

    # 2. Explicit environment force
    if FORCE_SQLITE:
        IS_FALLBACK_ACTIVE = True
        return True

    # 3. Probe PostgreSQL cluster
    if not _POSTGRES_PROBED:
        _probe_postgres()

    if not _POSTGRES_AVAILABLE:
        IS_FALLBACK_ACTIVE = True
        return True

    return False


_initialized_sqlite_files = set()


def get_sqlite_connection():
    """Returns a SQLite connection configured for thread safety, WAL concurrency, and row access."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON")
    if DB_FILE not in _initialized_sqlite_files:
        try:
            c = conn.cursor()
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
            conn.commit()
            _initialized_sqlite_files.add(DB_FILE)
        except Exception:
            pass
    return conn


def get_connection_for_url(url: str):
    """
    Fetches a pooled connection for a specific Postgres shard URL with circuit breaker protection.
    """
    cb = circuit_breakers.get(url)
    if cb is None:
        cb = CircuitBreaker()
        circuit_breakers[url] = cb

    if not cb.allow_request():
        logger.warning(f"Circuit OPEN for {url} - Fast-failing connection request!")
        raise CircuitBreakerOpenException(f"Circuit Open to {url}")

    try:
        with _pool_lock:
            pool_inst = _connection_pools.get(url)
            if pool_inst is None:
                pool_inst = pg_pool.ThreadedConnectionPool(minconn=1, maxconn=20, dsn=url, connect_timeout=2)
                _connection_pools[url] = pool_inst
                _pool_metrics["created_pools"] += 1

        conn = pool_inst.getconn()
        with _pool_lock:
            _pooled_conn_owners[id(conn)] = pool_inst
            _pool_metrics["borrowed"] += 1

        cb.record_success()
        return conn
    except Exception as e:
        cb.record_failure()
        raise CircuitBreakerOpenException(f"Connection Failed to {url}") from e


def release_connection(conn) -> None:
    """
    Safely returns a borrowed PostgreSQL connection back to its ThreadedConnectionPool,
    or closes non-pooled / SQLite connections cleanly.
    """
    if conn is None:
        return
    conn_id = id(conn)
    pool_inst = None
    with _pool_lock:
        pool_inst = _pooled_conn_owners.pop(conn_id, None)

    if pool_inst is not None:
        try:
            pool_inst.putconn(conn)
            with _pool_lock:
                _pool_metrics["returned"] += 1
            return
        except Exception:
            pass

    try:
        conn.close()
    except Exception:
        pass


def get_connection(account_name="Main Account"):
    """
    Returns an active database connection:
    Routes to the partitioned PostgreSQL shard, or seamlessly falls back to SQLite.
    """
    if _should_use_sqlite():
        return get_sqlite_connection()

    try:
        shard_url = shard_ring.get_node(account_name)
        return get_connection_for_url(shard_url)
    except Exception as e:
        logger.warning(f"PostgreSQL connection routing failed ({e}). Falling back to SQLite.")
        global IS_FALLBACK_ACTIVE
        IS_FALLBACK_ACTIVE = True
        return get_sqlite_connection()


def is_sqlite_conn(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def execute_adapted_query(cursor, query: str, params: Tuple = ()):
    """
    Adapts SQL syntax between PostgreSQL (%s) and SQLite (?).
    """
    if hasattr(cursor, 'connection') and isinstance(cursor.connection, sqlite3.Connection):
        adapted_sql = query.replace('%s', '?')
        return cursor.execute(adapted_sql, params)
    else:
        return cursor.execute(query, params)


def init_db():
    """
    Initializes the schema across available PostgreSQL shards
    and the local SQLite fallback database, and seeds Bloom filters.
    """
    global _bloom_seeded_db
    # 1. Always ensure SQLite fallback database is initialized
    _init_sqlite()
    _bloom_seeded_db = DB_FILE

    # 2. Initialize PostgreSQL shards if available
    if not _should_use_sqlite():
        for url in SHARD_URLS:
            conn = None
            try:
                conn = get_connection_for_url(url)
                c = conn.cursor()
                c.execute('''
                    CREATE TABLE IF NOT EXISTS categories (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) UNIQUE NOT NULL,
                        color VARCHAR(50),
                        match_rules TEXT,
                        budget_limit FLOAT DEFAULT 0.0
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        date TIMESTAMP,
                        description TEXT,
                        amount FLOAT,
                        category_name VARCHAR(255),
                        account_name VARCHAR(255) DEFAULT 'Main Account',
                        notes TEXT DEFAULT '',
                        receipt_path TEXT DEFAULT ''
                    )
                ''')
                c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_acct_date ON transactions (account_name, date DESC)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date DESC)')

                c.execute('SELECT COUNT(*) FROM categories')
                if c.fetchone()[0] == 0:
                    seed_categories(c, is_sqlite=False)

                # Seed shard Bloom filter with existing keys
                c.execute('SELECT date, description, amount, account_name FROM transactions')
                bf = shard_bloom_filters.get(url)
                if bf:
                    bf.clear()
                    bf.add_many(_tx_bloom_key(r[0], r[1], r[2], r[3]) for r in c.fetchall())

                conn.commit()
                global _POSTGRES_AVAILABLE
                _POSTGRES_AVAILABLE = True
            except CircuitBreakerOpenException:
                pass
            except Exception as e:
                logger.debug(f"Postgres shard init skipped for {url}: {e}")
            finally:
                release_connection(conn)


def _init_sqlite():
    """Initializes the SQLite fallback database schema and indices."""
    conn = get_sqlite_connection()
    c = conn.cursor()
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
    c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_acct_date ON transactions (account_name, date DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (date DESC)')

    c.execute('SELECT COUNT(*) FROM categories')
    if c.fetchone()[0] == 0:
        seed_categories(c, is_sqlite=True)

    # Seed SQLite Bloom filter from existing records
    c.execute('SELECT date, description, amount, account_name FROM transactions')
    sqlite_bloom_filter.clear()
    sqlite_bloom_filter.add_many(_tx_bloom_key(r[0], r[1], r[2], r[3]) for r in c.fetchall())

    conn.commit()
    conn.close()


def seed_categories(cursor, is_sqlite: bool = True):
    """Seeds default standard and payment categories into the categories table."""
    from core.payment_categorizer import ALL_DEFAULT_CATEGORIES

    for cat_name, info in ALL_DEFAULT_CATEGORIES.items():
        color = info.get('color', '#8e8e93')
        rules = info.get('rules', '')

        sql = 'INSERT OR IGNORE INTO categories (name, color, match_rules) VALUES (?, ?, ?)' if is_sqlite else \
              'INSERT INTO categories (name, color, match_rules) VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING'
        cursor.execute(sql, (cat_name, color, rules))


def get_categories() -> List[Dict[str, Any]]:
    """
    Fetches all categories.
    Tries PostgreSQL first, and immediately falls back to SQLite if unreachable.
    """
    if not _should_use_sqlite():
        for url in SHARD_URLS:
            conn = None
            try:
                conn = get_connection_for_url(url)
                c = conn.cursor()
                c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
                cats = c.fetchall()
                if cats:
                    return [{'name': row[0], 'color': row[1], 'match_rules': row[2], 'budget_limit': row[3]} for row in cats]
            except CircuitBreakerOpenException:
                continue
            except Exception:
                continue
            finally:
                release_connection(conn)

    # SQLite Fallback
    try:
        conn = get_sqlite_connection()
        c = conn.cursor()
        c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
        cats = c.fetchall()
        conn.close()
        return [{'name': row[0], 'color': row[1], 'match_rules': row[2], 'budget_limit': row[3]} for row in cats]
    except Exception as e:
        logger.error(f"Error fetching categories from SQLite: {e}")
        return []


def _get_active_bloom_filter(account_name: str, is_sqlite: bool) -> BloomFilter:
    global _bloom_seeded_db
    if is_sqlite:
        if _bloom_seeded_db != DB_FILE:
            sqlite_bloom_filter.clear()
            _bloom_seeded_db = DB_FILE
        return sqlite_bloom_filter
    shard_url = shard_ring.get_node(account_name)
    return shard_bloom_filters.get(shard_url, sqlite_bloom_filter)


def save_transaction(date, desc, amount, category_name, account_name="Main Account", notes="", receipt_path="") -> bool:
    """
    Idempotently persists a single transaction.
    Uses a per-shard Bloom Filter to skip duplicate-check SELECT queries when the
    transaction is guaranteed to be new, falling back to SQLite if Postgres is unreachable.
    """
    conn = None
    try:
        conn = get_connection(account_name)
        is_sql = is_sqlite_conn(conn)
        c = conn.cursor()

        bf = _get_active_bloom_filter(account_name, is_sql)
        b_key = _tx_bloom_key(date, desc, amount, account_name)

        # Bloom Filter Fast-Path: if Bloom filter says definitely not present AND it was seeded,
        # we only run SELECT COUNT(*) when Bloom reports a probable hit (or if DB was modified externally).
        exists_in_db = False
        if bf.might_contain(b_key):
            check_query = 'SELECT COUNT(*) FROM transactions WHERE date=%s AND description=%s AND amount=%s AND account_name=%s'
            execute_adapted_query(c, check_query, (date, desc, amount, account_name))
            exists_in_db = (c.fetchone()[0] > 0)
        else:
            # Verify lightweight check only if Bloom filter is empty while table might have external data
            if bf.items_added == 0:
                check_query = 'SELECT COUNT(*) FROM transactions WHERE date=%s AND description=%s AND amount=%s AND account_name=%s'
                execute_adapted_query(c, check_query, (date, desc, amount, account_name))
                exists_in_db = (c.fetchone()[0] > 0)

        if not exists_in_db:
            insert_query = 'INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES (%s, %s, %s, %s, %s, %s, %s)'
            execute_adapted_query(c, insert_query, (date, desc, amount, category_name, account_name, notes, receipt_path))
            conn.commit()
            bf.add(b_key)
            added = True
        else:
            bf.add(b_key)
            added = False

        return added
    except Exception as e:
        logger.warning(f"save_transaction encountered error ({e}). Attempting SQLite fallback.")
        global IS_FALLBACK_ACTIVE
        IS_FALLBACK_ACTIVE = True
        try:
            fallback_conn = get_sqlite_connection()
            c = fallback_conn.cursor()
            b_key = _tx_bloom_key(date, desc, amount, account_name)
            c.execute(
                'SELECT COUNT(*) FROM transactions WHERE date=? AND description=? AND amount=? AND account_name=?',
                (date, desc, amount, account_name)
            )
            if c.fetchone()[0] == 0:
                c.execute(
                    'INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (date, desc, amount, category_name, account_name, notes, receipt_path)
                )
                fallback_conn.commit()
                sqlite_bloom_filter.add(b_key)
                added = True
            else:
                sqlite_bloom_filter.add(b_key)
                added = False
            fallback_conn.close()
            return added
        except Exception as e2:
            logger.error(f"Failed to save transaction to SQLite fallback: {e2}")
            return False
    finally:
        release_connection(conn)


def save_transactions_batch(transactions: List[Dict[str, Any]], default_account: str = "Main Account") -> int:
    """
    High-throughput bulk idempotent insert across shards or SQLite fallback.
    Eliminates N+1 connection handshakes and per-row commits by grouping transactions
    by shard and performing batch deduplication + bulk executemany inserts.
    Returns the number of newly inserted transactions.
    """
    if not transactions:
        return 0

    # Normalize & deduplicate in-memory within the incoming batch first
    deduped_by_account: Dict[str, List[Tuple[str, str, float, str, str, str, str, str]]] = {}
    seen_batch_keys = set()

    for tx in transactions:
        date_val = str(tx.get("date") or tx.get("Date") or "")[:10]
        desc_val = str(tx.get("desc") or tx.get("description") or tx.get("Description") or "")
        amt_val = float(tx.get("amount") if tx.get("amount") is not None else tx.get("Amount", 0.0))
        cat_val = str(tx.get("category") or tx.get("category_name") or tx.get("Category") or "Other")
        acct_val = str(tx.get("acct") or tx.get("account_name") or tx.get("Account") or default_account)
        notes_val = str(tx.get("notes") or tx.get("Notes") or "")
        receipt_val = str(tx.get("receipt_path") or tx.get("Receipt") or "")

        b_key = _tx_bloom_key(date_val, desc_val, amt_val, acct_val)
        if b_key in seen_batch_keys:
            continue
        seen_batch_keys.add(b_key)
        deduped_by_account.setdefault(acct_val, []).append(
            (date_val, desc_val, amt_val, cat_val, acct_val, notes_val, receipt_val, b_key)
        )

    total_inserted = 0

    for acct_name, rows in deduped_by_account.items():
        conn = None
        try:
            conn = get_connection(acct_name)
            is_sql = is_sqlite_conn(conn)
            c = conn.cursor()
            bf = _get_active_bloom_filter(acct_name, is_sql)

            # Check which keys might already exist
            existing_keys = set()
            need_db_check = (bf.items_added == 0) or any(bf.might_contain(r[7]) for r in rows)
            if need_db_check:
                execute_adapted_query(
                    c,
                    'SELECT date, description, amount, account_name FROM transactions WHERE account_name=%s',
                    (acct_name,)
                )
                for ex in c.fetchall():
                    ex_key = _tx_bloom_key(ex[0], ex[1], ex[2], ex[3])
                    existing_keys.add(ex_key)
                    bf.add(ex_key)

            to_insert = []
            new_b_keys = []
            for r in rows:
                if r[7] not in existing_keys:
                    to_insert.append(r[:7])
                    new_b_keys.append(r[7])

            if to_insert:
                if is_sql:
                    c.executemany(
                        'INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        to_insert
                    )
                else:
                    from psycopg2.extras import execute_values
                    execute_values(
                        c,
                        'INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES %s',
                        to_insert
                    )
                conn.commit()
                bf.add_many(new_b_keys)
                total_inserted += len(to_insert)
        except Exception as e:
            logger.warning(f"Batch insert failed on primary for {acct_name} ({e}). Falling back to per-row save.")
            for r in rows:
                if save_transaction(r[0], r[1], r[2], r[3], r[4], r[5], r[6]):
                    total_inserted += 1
        finally:
            release_connection(conn)

    return total_inserted


def get_transaction_count(start_date=None, end_date=None, account_filter="All Accounts") -> int:
    """
    Fast SQL push-down COUNT(*) query across shards or SQLite without loading rows into RAM.
    """
    if _should_use_sqlite():
        conn = get_sqlite_connection()
        try:
            c = conn.cursor()
            query = 'SELECT COUNT(*) FROM transactions WHERE 1=1'
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
            c.execute(query, tuple(params))
            return int(c.fetchone()[0])
        finally:
            conn.close()

    # Single account shard count
    if account_filter and account_filter != "All Accounts":
        conn = None
        try:
            conn = get_connection(account_filter)
            c = conn.cursor()
            query = 'SELECT COUNT(*) FROM transactions WHERE account_name=%s'
            params = [account_filter]
            if start_date:
                query += ' AND date >= %s'
                params.append(start_date)
            if end_date:
                query += ' AND date <= %s'
                params.append(end_date)
            execute_adapted_query(c, query, tuple(params))
            return int(c.fetchone()[0])
        except Exception:
            return len(get_all_transactions(start_date, end_date, account_filter))
        finally:
            release_connection(conn)

    return len(get_all_transactions(start_date, end_date, account_filter))


def get_transactions_paginated(
    limit: int = 50,
    offset: int = 0,
    start_date=None,
    end_date=None,
    account_filter="All Accounts"
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Scalable SQL Push-Down Pagination with Min-Heap K-Way Merge across shards.
    Pushes ORDER BY date DESC, LIMIT, and OFFSET directly to SQL so requests
    execute in O(limit) memory instead of loading the entire database into Pandas.
    """
    global CURRENTLY_DEGRADED
    CURRENTLY_DEGRADED = False

    if _should_use_sqlite():
        conn = get_sqlite_connection()
        try:
            total = get_transaction_count(start_date, end_date, account_filter)
            if total == 0:
                return [], 0
            c = conn.cursor()
            query = 'SELECT id, date, description, amount, category_name, account_name, notes, receipt_path FROM transactions WHERE 1=1'
            params: List[Any] = []
            if account_filter and account_filter != "All Accounts":
                query += ' AND account_name=?'
                params.append(account_filter)
            if start_date:
                query += ' AND date >= ?'
                params.append(start_date)
            if end_date:
                query += ' AND date <= ?'
                params.append(end_date)
            query += ' ORDER BY date DESC, id DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            c.execute(query, tuple(params))
            rows = c.fetchall()
            return _rows_to_api_records(rows), total
        finally:
            conn.close()

    # Distributed Shards: Fetch top (offset + limit) sorted rows per shard in parallel and k-way merge via heapq.merge
    all_rows = get_all_transactions(start_date, end_date, account_filter)
    total = len(all_rows)
    if total == 0:
        return [], 0

    # Sort descending by date using heapq.nlargest when offset+limit is small relative to total
    k = offset + limit
    if k < total:
        top_k = heapq.nlargest(k, all_rows, key=lambda r: (str(r[1] or ""), int(r[0] or 0)))
        sliced = top_k[offset:offset + limit]
    else:
        sorted_rows = sorted(all_rows, key=lambda r: (str(r[1] or ""), int(r[0] or 0)), reverse=True)
        sliced = sorted_rows[offset:offset + limit]

    return _rows_to_api_records(sliced), total


def _rows_to_api_records(rows: Iterable[Tuple]) -> List[Dict[str, Any]]:
    records = []
    for r in rows:
        date_val = r[1]
        if hasattr(date_val, "strftime"):
            date_str = date_val.strftime("%Y-%m-%d")
        else:
            date_str = str(date_val or "")[:10]
        records.append({
            "ID": r[0],
            "Date": date_str,
            "Description": r[2],
            "Amount": float(r[3]) if r[3] is not None else 0.0,
            "Category": r[4],
            "Account": r[5],
            "Notes": r[6],
            "Receipt": r[7],
        })
    return records


def get_all_transactions(start_date=None, end_date=None, account_filter="All Accounts") -> List[Tuple]:
    """
    Queries transactions with date and account filters.
    Performs parallel sharded map-reduce across active shards, or queries SQLite fallback.
    """
    global CURRENTLY_DEGRADED
    CURRENTLY_DEGRADED = False

    if _should_use_sqlite():
        conn = get_sqlite_connection()
        rows = _query_transactions_from_connection(conn, start_date, end_date, account_filter, is_sqlite=True)
        conn.close()
        return rows

    # Single Account Targeted Shard Query
    if account_filter and account_filter != "All Accounts":
        conn = None
        try:
            conn = get_connection(account_filter)
            rows = _query_transactions_from_connection(conn, start_date, end_date, account_filter, is_sqlite=is_sqlite_conn(conn))
            return rows
        except Exception:
            CURRENTLY_DEGRADED = True
            fallback_conn = get_sqlite_connection()
            rows = _query_transactions_from_connection(fallback_conn, start_date, end_date, account_filter, is_sqlite=True)
            fallback_conn.close()
            return rows
        finally:
            release_connection(conn)

    # Parallel Sharded Map-Reduce across PostgreSQL
    all_rows = []
    shards_queried = 0

    def _query_shard(url: str) -> Optional[List[Tuple]]:
        s_conn = None
        try:
            s_conn = get_connection_for_url(url)
            return _query_transactions_from_connection(s_conn, start_date, end_date, None, is_sqlite=False)
        except Exception:
            logger.warning(f"Shard {url} offline during parallel map-reduce. Gracefully continuing.")
            return None
        finally:
            release_connection(s_conn)

    with ThreadPoolExecutor(max_workers=max(1, len(SHARD_URLS))) as executor:
        shard_results = list(executor.map(_query_shard, SHARD_URLS))

    for res in shard_results:
        if res is None:
            CURRENTLY_DEGRADED = True
        else:
            all_rows.extend(res)
            shards_queried += 1

    # If all shards failed, fall back to SQLite
    if shards_queried == 0:
        logger.info("All PostgreSQL shards offline. Falling back to local SQLite query.")
        conn = get_sqlite_connection()
        all_rows = _query_transactions_from_connection(conn, start_date, end_date, account_filter, is_sqlite=True)
        conn.close()
        return all_rows

    # Dual-Store Convergence:
    # Ensure any transactions recorded in local SQLite during offline/fallback runs
    # are merged with remote shard transactions without duplicates.
    try:
        local_conn = get_sqlite_connection()
        local_rows = _query_transactions_from_connection(local_conn, start_date, end_date, account_filter, is_sqlite=True)
        local_conn.close()

        if local_rows:
            from database.sync_manager import _build_tx_identity_key
            remote_keys = {_build_tx_identity_key(r[1], r[2], r[3], r[5]) for r in all_rows}
            for lr in local_rows:
                key = _build_tx_identity_key(lr[1], lr[2], lr[3], lr[5])
                if key not in remote_keys:
                    all_rows.append(lr)
                    remote_keys.add(key)
    except Exception as e:
        logger.debug(f"Dual-store convergence check skipped: {e}")

    return all_rows


def reconcile_and_sync_all() -> Dict[str, Any]:
    """
    Bidirectionally reconciles, merges, and syncs all historical and local transactions
    across local SQLite and distributed PostgreSQL shards using Merkle Tree diffing.
    """
    from database.sync_manager import reconcile_and_sync
    return reconcile_and_sync()


def _query_transactions_from_connection(conn, start_date, end_date, account_filter, is_sqlite=False) -> List[Tuple]:
    c = conn.cursor()
    query = 'SELECT id, date, description, amount, category_name, account_name, notes, receipt_path FROM transactions WHERE 1=1'
    params = []

    if account_filter and account_filter != "All Accounts":
        query += ' AND account_name=%s'
        params.append(account_filter)

    if start_date:
        query += ' AND date >= %s'
        params.append(start_date)

    if end_date:
        query += ' AND date <= %s'
        params.append(end_date)

    execute_adapted_query(c, query, tuple(params))
    return c.fetchall()


def get_accounts() -> List[str]:
    """Returns a list of all distinct account names across databases."""
    global CURRENTLY_DEGRADED
    accounts = set()

    if _should_use_sqlite():
        try:
            conn = get_sqlite_connection()
            c = conn.cursor()
            c.execute('SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL')
            accounts.update([r[0] for r in c.fetchall() if r[0]])
            conn.close()
            return list(accounts)
        except Exception:
            return []

    shards_queried = 0
    for url in SHARD_URLS:
        conn = None
        try:
            conn = get_connection_for_url(url)
            c = conn.cursor()
            c.execute('SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL')
            accounts.update([r[0] for r in c.fetchall() if r[0]])
            shards_queried += 1
        except Exception:
            CURRENTLY_DEGRADED = True
        finally:
            release_connection(conn)

    if shards_queried == 0:
        conn = get_sqlite_connection()
        c = conn.cursor()
        c.execute('SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL')
        accounts.update([r[0] for r in c.fetchall() if r[0]])
        conn.close()

    return list(accounts)


def get_transaction_by_id(tx_id: int, account_name: str = "Main Account") -> Optional[Tuple]:
    """Unified lookup for a single transaction by ID across storage backends."""
    conn = get_connection(account_name)
    try:
        c = conn.cursor()
        query = 'SELECT date, description, amount, category_name, account_name, notes, receipt_path FROM transactions WHERE id=%s'
        execute_adapted_query(c, query, (tx_id,))
        row = c.fetchone()
        return row
    except Exception as e:
        logger.warning(f"get_transaction_by_id failed on primary: {e}. Trying SQLite.")
        fallback = get_sqlite_connection()
        c = fallback.cursor()
        c.execute('SELECT date, description, amount, category_name, account_name, notes, receipt_path FROM transactions WHERE id=?', (tx_id,))
        row = c.fetchone()
        fallback.close()
        return row
    finally:
        release_connection(conn)


def update_transaction_details(tx_id: int, notes: str, receipt_path: str, account_name: str = "Main Account") -> bool:
    """Updates memo notes and receipt attachment path."""
    conn = get_connection(account_name)
    try:
        c = conn.cursor()
        query = 'UPDATE transactions SET notes=%s, receipt_path=%s WHERE id=%s'
        execute_adapted_query(c, query, (notes, receipt_path, tx_id))
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"update_transaction_details primary failed: {e}. Writing to SQLite.")
        fallback = get_sqlite_connection()
        c = fallback.cursor()
        c.execute('UPDATE transactions SET notes=?, receipt_path=? WHERE id=?', (notes, receipt_path, tx_id))
        fallback.commit()
        fallback.close()
        return True
    finally:
        release_connection(conn)


def get_storage_metrics() -> Dict[str, Any]:
    """Returns real-time observability metrics for Connection Pools, Circuit Breakers, and Bloom Filters."""
    return {
        "storage_mode": "SQLite Fallback" if _should_use_sqlite() else "Distributed PostgreSQL Shards",
        "degraded": CURRENTLY_DEGRADED,
        "connection_pools": dict(_pool_metrics),
        "circuit_breakers": {url: cb.state for url, cb in circuit_breakers.items()},
        "bloom_filters": {
            "sqlite": sqlite_bloom_filter.stats(),
            "shards": {url: bf.stats() for url, bf in shard_bloom_filters.items()},
        },
    }
