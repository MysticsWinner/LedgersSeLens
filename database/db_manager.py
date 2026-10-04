"""
LedgerSeLens Database Manager
Features a fault-tolerant hybrid architecture:
  - Distributed Multi-Shard PostgreSQL with Consistent Hashing & Circuit Breaking
  - Automatic Local SQLite Fallback Engine for offline resilience, single-node execution, and test isolation
"""

import os
import sqlite3
import psycopg2
import hashlib
import bisect
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

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
        self.state = "CLOSED" # CLOSED, OPEN, HALF_OPEN

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

# Global status flags
CURRENTLY_DEGRADED = False
IS_FALLBACK_ACTIVE = False

# Cached detection of whether Postgres is currently up
_POSTGRES_PROBED = False
_POSTGRES_AVAILABLE = False

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

def get_sqlite_connection():
    """Returns a SQLite connection configured for thread safety and row access."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def get_connection_for_url(url):
    """Fetches connection for a specific Postgres shard URL with circuit breaker."""
    cb = circuit_breakers[url]
    if not cb.allow_request():
        logger.warning(f"Circuit OPEN for {url} - Fast-failing connection request!")
        raise CircuitBreakerOpenException(f"Circuit Open to {url}")
        
    try:
        conn = psycopg2.connect(url, connect_timeout=2)
        cb.record_success()
        return conn
    except Exception as e:
        cb.record_failure()
        raise CircuitBreakerOpenException(f"Connection Failed to {url}") from e

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
    # Check if cursor belongs to SQLite
    if hasattr(cursor, 'connection') and isinstance(cursor.connection, sqlite3.Connection):
        adapted_sql = query.replace('%s', '?')
        return cursor.execute(adapted_sql, params)
    else:
        return cursor.execute(query, params)

def init_db():
    """
    Initializes the schema across available PostgreSQL shards
    and the local SQLite fallback database.
    """
    # 1. Always ensure SQLite fallback database is initialized
    _init_sqlite()

    # 2. Initialize PostgreSQL shards if available
    if not _should_use_sqlite():
        for url in SHARD_URLS:
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
                c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_acct_date ON transactions (account_name, date)')
                
                c.execute('SELECT COUNT(*) FROM categories')
                if c.fetchone()[0] == 0:
                    seed_categories(c, is_sqlite=False)
                    
                conn.commit()
                conn.close()
                global _POSTGRES_AVAILABLE
                _POSTGRES_AVAILABLE = True
            except CircuitBreakerOpenException:
                pass
            except Exception as e:
                logger.debug(f"Postgres shard init skipped for {url}: {e}")

def _init_sqlite():
    """Initializes the SQLite fallback database schema."""
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
    c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_acct_date ON transactions (account_name, date)')
    
    c.execute('SELECT COUNT(*) FROM categories')
    if c.fetchone()[0] == 0:
        seed_categories(c, is_sqlite=True)
        
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
            try:
                conn = get_connection_for_url(url)
                c = conn.cursor()
                c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
                cats = c.fetchall()
                conn.close()
                if cats:
                    return [{'name': row[0], 'color': row[1], 'match_rules': row[2], 'budget_limit': row[3]} for row in cats]
            except CircuitBreakerOpenException:
                continue
            except Exception:
                continue

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

def save_transaction(date, desc, amount, category_name, account_name="Main Account", notes="", receipt_path="") -> bool:
    """
    Idempotently persists a transaction.
    Writes to PostgreSQL shard if online, or cleanly falls back to SQLite.
    """
    conn = None
    try:
        conn = get_connection(account_name)
        is_sql = is_sqlite_conn(conn)
        c = conn.cursor()
        
        check_query = 'SELECT COUNT(*) FROM transactions WHERE date=%s AND description=%s AND amount=%s AND account_name=%s'
        execute_adapted_query(c, check_query, (date, desc, amount, account_name))
        
        if c.fetchone()[0] == 0:
            insert_query = 'INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES (%s, %s, %s, %s, %s, %s, %s)'
            execute_adapted_query(c, insert_query, (date, desc, amount, category_name, account_name, notes, receipt_path))
            conn.commit()
            added = True
        else:
            added = False
            
        return added
    except Exception as e:
        logger.warning(f"save_transaction encountered error ({e}). Attempting SQLite fallback.")
        global IS_FALLBACK_ACTIVE
        IS_FALLBACK_ACTIVE = True
        try:
            fallback_conn = get_sqlite_connection()
            c = fallback_conn.cursor()
            c.execute('SELECT COUNT(*) FROM transactions WHERE date=? AND description=? AND amount=? AND account_name=?', 
                      (date, desc, amount, account_name))
            if c.fetchone()[0] == 0:
                c.execute('INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES (?, ?, ?, ?, ?, ?, ?)',
                          (date, desc, amount, category_name, account_name, notes, receipt_path))
                fallback_conn.commit()
                added = True
            else:
                added = False
            fallback_conn.close()
            return added
        except Exception as e2:
            logger.error(f"Failed to save transaction to SQLite fallback: {e2}")
            return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def get_all_transactions(start_date=None, end_date=None, account_filter="All Accounts") -> List[Tuple]:
    """
    Queries transactions with date and account filters.
    Performs sharded map-reduce across active shards, or queries SQLite fallback.
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
        try:
            conn = get_connection(account_filter)
            rows = _query_transactions_from_connection(conn, start_date, end_date, account_filter, is_sqlite=is_sqlite_conn(conn))
            conn.close()
            return rows
        except Exception:
            CURRENTLY_DEGRADED = True
            # Fallback to SQLite
            conn = get_sqlite_connection()
            rows = _query_transactions_from_connection(conn, start_date, end_date, account_filter, is_sqlite=True)
            conn.close()
            return rows

    # Sharded Map-Reduce across PostgreSQL
    all_rows = []
    shards_queried = 0
    
    for url in SHARD_URLS:
        try:
            conn = get_connection_for_url(url)
            rows = _query_transactions_from_connection(conn, start_date, end_date, None, is_sqlite=False)
            all_rows.extend(rows)
            conn.close()
            shards_queried += 1
        except Exception:
            logger.warning(f"Shard {url} offline during map-reduce. Gracefully continuing.")
            CURRENTLY_DEGRADED = True

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
    across local SQLite and distributed PostgreSQL shards.
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
        try:
            conn = get_connection_for_url(url)
            c = conn.cursor()
            c.execute('SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL')
            accounts.update([r[0] for r in c.fetchall() if r[0]])
            conn.close()
            shards_queried += 1
        except Exception:
            CURRENTLY_DEGRADED = True

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
        try:
            conn.close()
        except Exception:
            pass

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
        try:
            conn.close()
        except Exception:
            pass
