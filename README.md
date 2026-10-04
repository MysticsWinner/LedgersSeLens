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

## 📥 Installation & Running

LedgerSeLens no longer boots a GUI window logic. It is a headless Distributed network designed for mass deployment.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/MysticsWinner/LedgersSeLens.git
   cd LedgersSeLens
   ```

2. **Boot the Global Cluster:**
   Ensure Docker Desktop is running on your machine, then:
   ```bash
   docker-compose down -v
   docker-compose up --build -d
   ```
   *This single command automatically provisions Zookeeper, Kafka, Redis, 3x Postgres Shards, 3x Stateless API Replicas, 2x Worker Queue Daemons, and the NGINX Reverse Proxy orchestrator.*

3. **Chaos Monkey (Optional Survivability Test):**
   Execute the Chaos Monkey script locally to watch the cluster survive Random Docker Node assassinations!
   ```bash
   python chaos_monkey.py
   ```
   *Spam the `/api/insights` endpoint while nodes die, and watch the Graceful Degradation logic switch the server state in real time!*

4. **Run the Mathematical Algorithmic Test Suite:**
   ```bash
   python -m pip install -r requirements.txt
   python -m pytest tests/test_system.py -v
   ```

## ⚙️ Configuration
For advanced cluster node modification, rate limits, manual MapReduce configurations, and Sharded DB routing policies, read the dedicated tuning manual: [CONFIGURATION.md](CONFIGURATION.md).
