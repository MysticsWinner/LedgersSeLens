# LedgerSeLens Distributed

> **Problem Statement:** The original LedgerLens was a monolithic desktop application. While it guaranteed privacy, it couldn't scale. What happens when we need to ingest 100,000 transactions a second from thousands of concurrent clients? We evolve.

LedgerSeLens Distributed is a **Planet-Scale, Horizontally Scalable, Event-Driven Financial API**. It has been re-architected from the ground up using classical **System Design** and **Distributed Systems Data Structures (DSA)** patterns to survive catastrophic failures and handle massive throughput workloads.

## ✨ Distributed Architecture Enhancements

- **Phase 1: Load Balancing & Rate Limiting**
  - **NGINX:** Routes traffic across multiple stateless Python API nodes.
  - **Redis Token-Bucket:** Protects endpoints from DDOS attacks globally using an atomic Lua script in Redis.
- **Phase 2: Database Sharding & Data Partitioning**
  - **Consistent Hashing API:** Our custom `ConsistentHashRing` DSA algorithm natively distributes incoming accounts across multiple PostgreSQL database nodes using `O(log n)` Binary Search lookups.
  - **Scatter/Gather Insights:** Querying aggregates triggers an instantaneous map-reduce parallel execution across all database shards.
- **Phase 3: Chaos Resiliency & Zookeeper Coordination**
  - **Circuit Breakers:** The database managers employ a strict Finite State Machine (Closed -> Open -> Half-Open). If a shard goes down entirely, the API instantly degrades gracefully rather than bottlenecking server threads waiting for timeouts.
  - **Zookeeper Ephemeral Nodes:** Each stateless API registers itself locally via Zookeeper for realtime service discovery.
- **Phase 4: Event-Driven Apache Kafka Streaming**
  - **O(1) Memory Ingestion:** The ingestion endpoints were stripped of database writes entirely. They immediately dump payload metadata into a Kafka topic and return `HTTP 202 Accepted` to guarantee sub-millisecond wait times.
  - **Consumer Fleets (Idempotency):** Background Python daemon scripts (`worker.py`) drain the Kafka queues securely and execute the expensive disk IOPS against the PostgreSQL shards in a separate process.
- **Phase 5: Cache Aside O(1) Reads & B-Tree Optimization**
  - **Redis Read-Through:** Aggregated insights are cached directly into memory in Redis. 
  - **Dynamic Cache Invalidation:** `worker.py` safely destroys the Redis cache the exact millisecond a successful DB-write completes, ensuring Eventual Consistency isn't abused.
  - **Compound B-Trees:** Heavy read loads now skip Linear Table Scans directly bypassing PostgreSQL queries.

## 🛠️ Tech Stack 

- **Orchestration:** Docker, Docker Compose
- **Routing:** NGINX
- **Caching & Rate Limiting:** Redis
- **Message Broker:** Apache Kafka
- **Discovery:** Apache Zookeeper
- **Database:** PostgreSQL (Sharded array)
- **API Environment:** FastAPI, Uvicorn, Python, Pandas

## 🚀 Unified Execution & Feature Hub (`main.py`)

All features of LedgerSeLens—Desktop GUI, Distributed API Server, Data Ingestion, OCR Scanner, Sharding, Offline Fallbacks, Reconciler, and Diagnostics—are accessible via the **main entrypoint command**:

```bash
# Default: Launches the Modern PyQt6 Desktop GUI Dashboard
python main.py

# Interactive Mode: Terminal menu with all 16 features
python main.py --cli
# (or: python main.py menu)
```

### Direct CLI Subcommands

Every feature is also accessible via direct CLI commands:

| Feature / Command | Usage | Description |
| :--- | :--- | :--- |
| **Desktop GUI** | `python main.py gui` | Full-featured PyQt6 dashboard with dark theme, docks, and charts |
| **REST API Server** | `python main.py server [--port 8000]` | Starts FastAPI Uvicorn distributed server |
| **Ingestion Worker** | `python main.py worker` | Background queue ingestion daemon |
| **Frontend Web** | `python main.py web` | Runs React/Vite development web UI |
| **Universal Ingestion**| `python main.py ingest <file> [--account ...]` | Ingests PDF, Excel (.xlsx/.xls), CSV (.csv/.tsv), or Receipt images |
| **OCR Scanner** | `python main.py ocr <image_or_pdf>` | Extracts merchant, date, amount, category using Tesseract / Heuristics |
| **Sync & Reconcile** | `python main.py sync` (or `reconcile`) | Bidirectional sync between local SQLite and PostgreSQL shards |
| **Financial Insights** | `python main.py insights [--account ...]` | Computes totals, net savings, and top spending categories |
| **Transactions** | `python main.py transactions [--limit 10]` | Shows recent transactions with custom limits & account filter |
| **Subscriptions** | `python main.py subscriptions` | Auto-detects recurring bills and subscriptions |
| **Plaid Bank Feed** | `python main.py plaid` | Imports transactions from Plaid sandbox bank feeds |
| **Data Export** | `python main.py export <file> --format csv\|excel\|pdf` | Exports ledger to CSV, Excel, or PDF report |
| **System Status** | `python main.py status` | Inspects Postgres shards, SQLite fallback, Redis, and OCR status |
| **Mock Statement** | `python main.py mock-data [--output file.pdf]` | Generates synthetic bank statement for testing |
| **Chaos Monkey** | `python main.py chaos` | Fault-injection resilience tester targeting container nodes |
| **Automated Tests** | `python main.py test` | Runs the full 31-test pytest validation suite |

---

## 📥 Installation & Running

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MysticsWinner/LedgersSeLens.git
   cd LedgersSeLens
   ```

2. **Setup Python Environment:**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate     # Windows PowerShell
   pip install -r requirements.txt
   ```

3. **Run the Project:**
   ```bash
   # Launch Desktop Dashboard
   python main.py

   # Or launch the interactive terminal menu
   python main.py --cli
   ```

4. **Boot Global Distributed Cluster (Optional Docker Mode):**
   ```bash
   docker-compose up --build -d
   ```
   *Automatically provisions Zookeeper, Kafka, Redis, 3x Postgres Shards, 3x Stateless API Replicas, Worker Daemons, and NGINX Reverse Proxy.*

5. **Run the Automated Test Suite:**
   ```bash
   python main.py test
   ```

## ⚙️ Configuration
For advanced cluster node modification, rate limits, manual MapReduce configurations, and Sharded DB routing policies, read the dedicated tuning manual: [CONFIGURATION.md](CONFIGURATION.md).
