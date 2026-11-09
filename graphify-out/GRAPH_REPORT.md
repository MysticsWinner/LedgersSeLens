# Graph Report - LedgersSeLens  (2026-11-09)

## Corpus Check
- 48 files · ~29,050 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .css 1, .conf 1)

## Summary
- 657 nodes · 1376 edges · 44 communities (31 shown, 13 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 33 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `fa6a28b2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_data_ingestion.py
- os
- db_manager.py
- main.py
- main_window.py
- _process_transactions
- test_system.py
- package.json
- server.py
- test_scalability.py
- environment
- environment
- 🗺️ Distributed Systems, Architecture & DSA Roadmap
- services
- zookeeper
- CategoryTrie
- nginx
- worker1
- worker2
- api1
- api2
- api3
- volumes
- LRUCache
- postgres-shard-2
- InvertedIndex
- BloomFilter
- MerkleTree
- steps
- worker.py
- SettingsDialog
- upload_statement
- categorize_transaction
- test_analyzer.py
- get
- autocomplete_categories
- refresh_search_index
- verify-and-deploy.md

## God Nodes (most connected - your core abstractions)
1. `init_db()` - 24 edges
2. `save_transaction()` - 22 edges
3. `MainWindow` - 22 edges
4. `get_all_transactions()` - 20 edges
5. `load_all_transactions_df()` - 19 edges
6. `save_transactions_batch()` - 19 edges
7. `reconcile_and_sync()` - 19 edges
8. `run_interactive_menu()` - 19 edges
9. `ingest_file()` - 18 edges
10. `main()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `Expanding the Phase 2 Consistent Hash Ring` --references--> `ConsistentHashRing`  [INFERRED]
  CONFIGURATION.md → database/db_manager.py
- `✨ Distributed Architecture Enhancements` --references--> `ConsistentHashRing`  [INFERRED]
  README.md → database/db_manager.py
- `_get_active_bloom_filter()` --uses--> `BloomFilter`  [INFERRED]
  database/db_manager.py → core/dsa_structures.py
- `reconcile_and_sync()` --uses--> `MerkleTree`  [INFERRED]
  database/sync_manager.py → core/dsa_structures.py
- `test_api_search_autocomplete_and_metrics_endpoints()` --calls--> `save_transactions_batch()`  [EXTRACTED]
  tests/test_scalability.py → database/db_manager.py

## Import Cycles
- None detected.

## Communities (44 total, 13 thin omitted)

### Community 0 - "test_data_ingestion.py"
Cohesion: 0.06
Nodes (34): parse_pdf_statement(), clean_currency_string(), find_header_row_csv(), ingest_csv(), ingest_excel(), ingest_file(), ingest_image_receipt(), ingest_pdf() (+26 more)

### Community 1 - "os"
Cohesion: 0.07
Nodes (11): predict_category(), train_model(), test_cli_insights_command(), test_cli_transactions_command(), test_main_help_and_subcommands(), test_main_status_and_sync_commands(), setup_teardown_db(), setup_teardown_db() (+3 more)

### Community 2 - "db_manager.py"
Cohesion: 0.06
Nodes (39): execute_adapted_query(), get_accounts(), _get_active_bloom_filter(), get_all_transactions(), _query_shard(), get_categories(), get_connection(), get_connection_for_url() (+31 more)

### Community 3 - "main.py"
Cohesion: 0.07
Nodes (29): main(), print_insights(), print_reconcile(), print_transactions(), load_all_transactions_df(), reconcile_and_sync_all(), main(), run_chaos() (+21 more)

### Community 4 - "main_window.py"
Cohesion: 0.08
Nodes (5): MplCanvas, SystemStatusDialog, run(), TransactionDetailDialog, MainWindow

### Community 5 - "_process_transactions"
Cohesion: 0.27
Nodes (5): parse_csv_statement(), parse_excel_statement(), parse_statement(), _process_transactions(), test_parse_csv_statement()

### Community 6 - "test_system.py"
Cohesion: 0.08
Nodes (19): 1. Modifying the Rate Limiter (Redis Token-Bucket), 2. Horizontal Scaling of the Microservices, 3. Database Sharding Topologies, 4. Phase 5 Cache Engineering, Adding another Kafka Background Daemon (`worker3`), Expanding API Gateways (`api4`), Expanding the Phase 2 Consistent Hash Ring, ⚙️ LedgerSeLens Configuration Manual (+11 more)

### Community 7 - "package.json"
Cohesion: 0.11
Nodes (19): dependencies, react@^18.2.0, react-dom@^18.2.0, devDependencies, vite@^5.2.0, @vitejs/plugin-react@^4.2.1, name, private (+11 more)

### Community 8 - "server.py"
Cohesion: 0.15
Nodes (5): _get_job_state(), get_job_status(), rate_limit_middleware(), shutdown_event(), startup_event()

### Community 9 - "test_scalability.py"
Cohesion: 0.14
Nodes (4): SlidingWindowRateLimiter, setup_teardown_scalability_db(), test_api_search_autocomplete_and_metrics_endpoints(), test_sliding_window_rate_limiter_deque()

### Community 10 - "environment"
Cohesion: 0.18
Nodes (11): KAFKA_ADVERTISED_LISTENERS, KAFKA_BROKER_ID, KAFKA_INTER_BROKER_LISTENER_NAME, KAFKA_LISTENER_SECURITY_PROTOCOL_MAP, KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR, KAFKA_ZOOKEEPER_CONNECT, depends_on, environment (+3 more)

### Community 11 - "environment"
Cohesion: 0.33
Nodes (9): POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, environment, image, volumes, environment, environment (+1 more)

### Community 12 - "🗺️ Distributed Systems, Architecture & DSA Roadmap"
Cohesion: 0.22
Nodes (8): 🛤️ [COMPLETED] Phase 1: Scalability Foundations (Breaking Single-Node Limits), 🛤️ [COMPLETED] Phase 2: Distributed Data (Scaling the Database), 🛤️ [COMPLETED] Phase 3: High Availability (HA) & Fault Tolerance, 🛤️ [COMPLETED] Phase 4: Event-Driven Systems & Asynchronous Processing, 🛤️ [COMPLETED] Phase 5: Optimization & Caching (The Need for Speed), 🗺️ Distributed Systems, Architecture & DSA Roadmap, 📚 Recommended Tech Stack for the "System Design + DSA" Project, 🌟 The Capstone Project: "LedgerSeLens Distributed"

### Community 13 - "services"
Cohesion: 0.22
Nodes (8): image, volumes, image, ports, services, postgres-shard-3, redis, version

### Community 14 - "zookeeper"
Cohesion: 0.33
Nodes (6): ZOOKEEPER_CLIENT_PORT, ZOOKEEPER_TICK_TIME, zookeeper, environment, image, ports

### Community 15 - "CategoryTrie"
Cohesion: 0.22
Nodes (4): get_category_trie(), CategoryTrie, _TrieNode, test_category_trie_autocomplete_and_keyword_match()

### Community 16 - "nginx"
Cohesion: 0.40
Nodes (5): depends_on, image, ports, volumes, nginx

### Community 17 - "worker1"
Cohesion: 0.40
Nodes (5): worker1, build, command, depends_on, environment

### Community 18 - "worker2"
Cohesion: 0.40
Nodes (5): worker2, build, command, depends_on, environment

### Community 19 - "api1"
Cohesion: 0.50
Nodes (4): build, depends_on, environment, api1

### Community 20 - "api2"
Cohesion: 0.50
Nodes (4): build, depends_on, environment, api2

### Community 21 - "api3"
Cohesion: 0.50
Nodes (4): build, depends_on, environment, api3

### Community 22 - "volumes"
Cohesion: 0.50
Nodes (4): volumes, pgdata1, pgdata2, pgdata3

### Community 23 - "LRUCache"
Cohesion: 0.31
Nodes (3): LRUCache, _LRUNode, test_lru_cache_o1_eviction_and_ttl()

### Community 24 - "postgres-shard-2"
Cohesion: 0.67
Nodes (3): image, volumes, postgres-shard-2

### Community 34 - "steps"
Cohesion: 0.09
Nodes (21): FORCE_SQLITE, SQLITE_DB_FILE, jobs, test-and-verify-workflows, name, branches, branches, env (+13 more)

### Community 35 - "worker.py"
Cohesion: 0.16
Nodes (5): CircuitBreakerOpenException, test_worker_micro_batch_and_dlq_routing(), connect_kafka_with_backoff(), process_worker_batch(), run_worker()

### Community 37 - "upload_statement"
Cohesion: 0.19
Nodes (6): _execute_async_ingestion_job(), _invalidate_caches(), post_reconcile(), _save_job_state(), sync_plaid_data(), upload_statement()

### Community 38 - "categorize_transaction"
Cohesion: 0.22
Nodes (6): categorize_transaction(), prepare_categorized_records(), _ensure_category(), search_transactions(), test_categorize_transaction_heuristics(), test_analyzer_categorization_with_payments()

### Community 39 - "test_analyzer.py"
Cohesion: 0.31
Nodes (6): detect_subscriptions(), generate_insights(), setup_teardown_db(), test_detect_subscriptions(), test_generate_insights_empty(), test_generate_insights_math()

### Community 40 - "get"
Cohesion: 0.22
Nodes (5): api_search_transactions(), get_insights(), get_subscriptions(), get_transactions(), read_root()

## Knowledge Gaps
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConsistentHashRing` connect `test_system.py` to `db_manager.py`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `MainWindow` (e.g. with `MplCanvas` and `SettingsDialog`) actually correct?**
  _`MainWindow` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_data_ingestion.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05593803786574871 - nodes in this community are weakly interconnected._
- **Why does `init_db()` connect `db_manager.py` to `test_data_ingestion.py`, `os`, `main.py`, `main_window.py`, `worker.py`, `test_analyzer.py`, `server.py`, `test_scalability.py`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Should `os` be split into smaller, more focused modules?**
  _Cohesion score 0.0708245243128964 - nodes in this community are weakly interconnected._
- **Why does `BloomFilter` connect `BloomFilter` to `test_scalability.py`, `db_manager.py`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Should `db_manager.py` be split into smaller, more focused modules?**
  _Cohesion score 0.056790123456790124 - nodes in this community are weakly interconnected._