# 🗺️ Distributed Systems, Architecture & DSA Roadmap

Welcome to the **System Design & Scalability Roadmap**. This guide is designed to take you from standard application development to designing and building planet-scale, fault-tolerant infrastructure, heavily emphasizing the underlying **Data Structures & Algorithms (DSA)** that make massive scale possible.

## 🌟 The Capstone Project: "LedgerSeLens Distributed"

To ensure this feels like a true **System Design** endeavor, this roadmap is structured around evolving a standalone application into **LedgerSeLens Distributed**—a highly available, planet-scale financial processing engine.

**What it is:** A globally distributed system designed to ingest, process, classify, and query massive streams of financial transactions and statements simultaneously.

**What it does:**
- **Mass Ingestion:** Accepts thousands of concurrent statement batch uploads.
- **Fault Tolerance:** Ensures that even if two data centers go offline, no transaction data is structurally lost.
- **High Availability:** Automatically routes traffic and balances processing load during traffic spikes.
- **Distributed Consensus:** Guarantees correct global state across microservices without race conditions.
- **Optimization:** Caches aggregated insights for sub-millisecond AI-powered query performance.

---

## 🛤️ [COMPLETED] Phase 1: Scalability Foundations (Breaking Single-Node Limits)
*Before distributing, you must understand scale and bottlenecks.*

* **Core Concepts:** Vertical vs. Horizontal Scaling, Load Balancing Algorithms, Throughput vs. Latency, Amdahl's Law, Stateless vs. Stateful Architecture.
* **DSA Integrations:**
  - **Hashing:** Understanding hash functions for simple load balancing algorithms (like IP Hashing to stick sessions).
  - **Arrays & Deques (Sliding Window):** Implementing Rate Limiting (Token Bucket, Sliding Window Log) to protect your basic API from sudden traffic spikes or DDOS attacks.
* **✅ Project Milestone 1 (Completed):** 
  Take the core LedgerSeLens API and benchmark it using tools like `wrk` or `k6` to find its absolute breaking point. Introduce a Reverse Proxy/Load Balancer (e.g., Nginx, HAProxy) and run multiple stateless instances of your API. Implement a custom array-backed Rate Limiter algorithm. Ensure sessions and states are moved out of the application's memory.

## 🛤️ [COMPLETED] Phase 2: Distributed Data (Scaling the Database)
*When one database server isn't enough to handle the required read/write IOPS.*

* **Core Concepts:** CAP Theorem, PACELC Theorem, Data Partitioning/Sharding, Replication Strategies (Leader-Follower, Leaderless), Vector Clocks.
* **DSA Integrations:** 
  - **Consistent Hashing (Arrays & Binary Search):** Using an array mapped to a "hash ring" and `O(log n)` Binary Search to distribute users across sharded database nodes efficiently—without massive reshuffling when a node dies.
  - **Bloom Filters:** Probabilistic data structures composed of an array and multiple hash functions. Used to test if a transaction or keyword *might* exist in a database shard without doing an expensive disk read.
  - **Merkle Trees (Hash Trees):** Used in leaderless distributed databases (like Cassandra/Dynamo) to quickly find and repair data inconsistencies between replica nodes via anti-entropy synchronization.
* **✅ Project Milestone 2 (Completed):** 
  Shard the LedgerSeLens database. Split user transaction data across three separate database nodes using your own Consistent Hashing implementation. Implement read-replicas to offset the heavy read load.

## 🛤️ [COMPLETED] Phase 3: High Availability (HA) & Fault Tolerance
*Hardware will fail. Networks will partition. Your system must survive.*

* **Core Concepts:** Redundancy, Heartbeats, Gossip Protocol, Leader Election (Raft/Paxos), Circuit Breakers, Bulkheads, Retries with Exponential Backoff + Jitter.
* **DSA Integrations:**
  - **Graphs (Shortest Path Algorithms):** Building network topology maps and calculating optimal rerouting mechanisms when a network branch goes down.
  - **Priority Queues (Min-Heaps):** Managing timed heartbeats, processing timeouts, or orchestrating prioritized retry logic. Used in timer-wheels for expiring leases.
* **✅ Project Milestone 3 (Completed):** 
  Introduce chaos engineering. Write a script that randomly kills your database nodes or API servers. Implement a coordination service (like Zookeeper or etcd) to detect failures and automatically elect a new primary node without dropping user transactions. Implement Circuit Breakers in your API so it degrades gracefully.

## 🛤️ [COMPLETED] Phase 4: Event-Driven Systems & Asynchronous Processing
*Decoupling components for massive throughput and resilience.*

* **Core Concepts:** Message Queues vs. Event Streams (RabbitMQ vs. Kafka), Pub/Sub Systems, Event Sourcing, CQRS (Command Query Responsibility Segregation), Idempotency.
* **DSA Integrations:**
  - **Ring Buffers (Circular Queues):** High-performance, memory-efficient queued data structures frequently used in internal processing or log collection (e.g., LMAX Disruptor pattern).
  - **Log-Structured / Append-Only Arrays:** The fundamental O(1) insertion structure behind Apache Kafka that guarantees sequential disk writes for extreme ingestion speed.
* **✅ Project Milestone 4 (Completed):** 
  Decouple the heavy machine-learning and parsing tasks. Use a message broker like Apache Kafka. When a user uploads a statement, the API instantly accepts it, appends the task to an event log, and returns immediately. Worker nodes consume the queue asynchronously. Make the workers idempotent so retries don’t duplicate data.

## 🛤️ [COMPLETED] Phase 5: Optimization & Caching (The Need for Speed)
*Retrieving data should be instantaneous. This is where classical algorithms heavily dictate system boundaries.*

* **Core Concepts:** Cache Policies, Cache Invalidation Strategies (Write-through, Write-behind, Cache-aside), CDNs, Connection Pooling, Spatial/Temporal Locality.
* **DSA Integrations:**
  - **B-Trees vs. LSM Trees (Log-Structured Merge Trees):** Understanding these fundamental tree structures shows you how PostgreSQL (B-Tree optimized for reads) vs. Cassandra (LSM optimized for writes) operate on disk.
  - **Linked Lists + Hash Maps (LRU/LFU Caches):** Designing and building an O(1) Least Recently Used (LRU) cache from scratch teaches you cache eviction exactly as Redis handles it.
  - **Tries (Prefix Trees):** The core data structure used for autocompleting transaction categories, keyword tagging maps, or IP Routing tables.
  - **Inverted Indices:** Using hash maps linking strings to document arrays is how robust search engines (like Elasticsearch) execute full-text search across parsed statements instantly.
* **✅ Project Milestone 5 (Completed):** 
  Implement a distributed cache cluster (Redis/Memcached) for fetching pre-calculated balance summaries. Use a "Write-behind" cache strategy to batch database updates. Analyze database queries using `EXPLAIN` and optimize them using B-Tree compound indexing or an Inverted Index for statement analysis.

---

> [!TIP]
> **The Engineering Mindset**
> System design is largely about managing trade-offs. As you progress through this roadmap, constantly ask yourself: *"If I make this more fault-tolerant, do I sacrifice latency? If I speed up lookups with a Bloom Filter, what is my false positive rate?"*

## 📚 Recommended Tech Stack for the "System Design + DSA" Project
* **Databases:** PostgreSQL (Relational / B-Tree indexing), Cassandra (NoSQL / LSM Tree / Distributed)
* **Message Brokers:** Apache Kafka (High throughput append-only log arrays)
* **Caching:** Redis Cluster (O(1) Hash Map + LRU Eviction caching)
* **Search:** Elasticsearch or Solr (Inverted Indices for fast document queries)
* **Coordination / Service Discovery:** Consul or etcd
* **Infrastructure:** Docker, Kubernetes (for orchestration)
