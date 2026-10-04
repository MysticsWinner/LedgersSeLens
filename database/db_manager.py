import psycopg2
import os
import hashlib
import bisect
import time

# Load shards from environments
SHARD_URLS = [
    os.environ.get("SHARD_1_URL", "postgresql://postgres:postgres@localhost:5432/ledger_shard_1"),
    os.environ.get("SHARD_2_URL", "postgresql://postgres:postgres@localhost:5433/ledger_shard_2"),
    os.environ.get("SHARD_3_URL", "postgresql://postgres:postgres@localhost:5434/ledger_shard_3")
]

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
        print(f"CircuitBreaker failure recorded. Total: {self.failures}")
        if self.failures >= self.failure_threshold:
            print("CircuitBreaker TRIPPED -> OPEN")
            self.state = "OPEN"

    def record_success(self):
        if self.state != "CLOSED":
            print("CircuitBreaker RECOVERED -> CLOSED")
        self.failures = 0
        self.state = "CLOSED"

    def allow_request(self):
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
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

def get_connection_for_url(url):
    cb = circuit_breakers[url]
    if not cb.allow_request():
        print(f"Circuit OPEN for {url} - Fast-failing connection request!")
        raise CircuitBreakerOpenException(f"Circuit Open to {url}")
        
    try:
        # Crucial for Circuit Breaking: A fast connect_timeout prevents the whole thread from hanging
        conn = psycopg2.connect(url, connect_timeout=2)
        cb.record_success()
        return conn
    except psycopg2.OperationalError as e:
        cb.record_failure()
        raise CircuitBreakerOpenException(f"Connection Failed to {url}") from e

def get_connection(account_name="Main Account"):
    # Route connection based on consistent hashing of account_name (Data Partitioning)
    shard_url = shard_ring.get_node(account_name)
    return get_connection_for_url(shard_url)

def init_db():
    # Initialize the schema on EVERY shard
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
            
            # ✨ PHASE 5: COMPOUND B-TREE OPTIMIZATION (O(log n) lookups)
            c.execute('CREATE INDEX IF NOT EXISTS idx_transactions_acct_date ON transactions (account_name, date)')
            
            c.execute('SELECT COUNT(*) FROM categories')
            if c.fetchone()[0] == 0:
                seed_categories(c)
                
            conn.commit()
            conn.close()
        except CircuitBreakerOpenException:
            print(f"Skipping DB init for {url} since circuit is open.")
        except Exception as e:
            print(f"Warning: Failed to init shard {url} - {e}")

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
        c.execute('INSERT INTO categories (name, color, match_rules) VALUES (%s, %s, %s)', (cat_name, color, rules))

def get_categories():
    # Categories are homogeneous across shards, just fetch from the first *available* shard
    for url in SHARD_URLS:
        try:
            conn = get_connection_for_url(url)
            c = conn.cursor()
            c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
            cats = c.fetchall()
            conn.close()
            return [{'name': row[0], 'color': row[1], 'match_rules': row[2], 'budget_limit': row[3]} for row in cats]
        except CircuitBreakerOpenException:
            continue
    return []

def save_transaction(date, desc, amount, category_name, account_name="Main Account", notes="", receipt_path=""):
    # Sharded write. If the target shard is down, we have to fail the write.
    conn = get_connection(account_name)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM transactions WHERE date=%s AND description=%s AND amount=%s AND account_name=%s', 
              (date, desc, amount, account_name))
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO transactions (date, description, amount, category_name, account_name, notes, receipt_path) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                  (date, desc, amount, category_name, account_name, notes, receipt_path))
        conn.commit()
        added = True
    else:
        added = False
    conn.close()
    return added

# Global flag to signal the API that it is returning DEGRADED results due to a dead shard
CURRENTLY_DEGRADED = False

def get_all_transactions(start_date=None, end_date=None, account_filter="All Accounts"):
    global CURRENTLY_DEGRADED
    CURRENTLY_DEGRADED = False
    
    if account_filter and account_filter != "All Accounts":
        try:
            conn = get_connection(account_filter)
            return _query_transactions_from_connection(conn, start_date, end_date, account_filter)
        except CircuitBreakerOpenException:
            CURRENTLY_DEGRADED = True
            return [] # Can't fetch this user's data!
    
    # SHARDED MAP-REDUCE
    all_rows = []
    for url in SHARD_URLS:
        try:
            conn = get_connection_for_url(url)
            rows = _query_transactions_from_connection(conn, start_date, end_date, None)
            all_rows.extend(rows)
            conn.close()
        except CircuitBreakerOpenException:
            # Graceful Degradation: Skip this shard's data perfectly instead of crashing the process
            print(f"Warning: Shard {url} is offline. Degrading aggregate query results.")
            CURRENTLY_DEGRADED = True
            
    return all_rows

def _query_transactions_from_connection(conn, start_date, end_date, account_filter):
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
        
    c.execute(query, tuple(params))
    rows = c.fetchall()
    return rows

def get_accounts():
    global CURRENTLY_DEGRADED
    accounts = set()
    for url in SHARD_URLS:
        try:
            conn = get_connection_for_url(url)
            c = conn.cursor()
            c.execute('SELECT DISTINCT account_name FROM transactions WHERE account_name IS NOT NULL')
            accounts.update([r[0] for r in c.fetchall() if r[0]])
            conn.close()
        except CircuitBreakerOpenException:
            CURRENTLY_DEGRADED = True
    return list(accounts)
