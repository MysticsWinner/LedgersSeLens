# Graph Report - LedgersSeLens  (2026-11-01)

## Corpus Check
- 44 files · ~23,197 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .css 1, .conf 1)

## Summary
- 506 nodes · 1053 edges · 31 communities (24 shown, 7 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 13 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6e3e7597`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_data_ingestion.py
- server.py
- db_manager.py
- main.py
- main_window.py
- analyzer.py
- test_system.py
- package.json
- SystemStatusDialog
- ml_engine.py
- environment
- environment
- 🗺️ Distributed Systems, Architecture & DSA Roadmap
- services
- zookeeper
- subprocess
- nginx
- worker1
- worker2
- api1
- api2
- api3
- volumes
- postgres-shard-1
- postgres-shard-2

## God Nodes (most connected - your core abstractions)
1. `save_transaction()` - 22 edges
2. `MainWindow` - 22 edges
3. `load_all_transactions_df()` - 21 edges
4. `init_db()` - 20 edges
5. `get_all_transactions()` - 19 edges
6. `run_interactive_menu()` - 19 edges
7. `ingest_file()` - 18 edges
8. `main()` - 18 edges
9. `_process_transactions()` - 17 edges
10. `generate_insights()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Expanding the Phase 2 Consistent Hash Ring` --references--> `ConsistentHashRing`  [INFERRED]
  CONFIGURATION.md → database/db_manager.py
- `✨ Distributed Architecture Enhancements` --references--> `ConsistentHashRing`  [INFERRED]
  README.md → database/db_manager.py
- `test_init_db_seeds_categories()` --calls--> `get_categories()`  [EXTRACTED]
  tests/test_db.py → database/db_manager.py
- `print_reconcile()` --calls--> `reconcile_and_sync_all()`  [EXTRACTED]
  cli.py → database/db_manager.py
- `test_categorize_transaction_heuristics()` --calls--> `categorize_transaction()`  [EXTRACTED]
  tests/test_analyzer.py → core/analyzer.py

## Import Cycles
- None detected.

## Communities (31 total, 7 thin omitted)

### Community 0 - "test_data_ingestion.py"
Cohesion: 0.05
Nodes (31): clean_currency_string(), find_header_row_csv(), ingest_csv(), ingest_excel(), ingest_file(), ingest_image_receipt(), ingest_pdf(), IngestionResult (+23 more)

### Community 1 - "server.py"
Cohesion: 0.05
Nodes (17): init_db(), save_transaction(), post_reconcile(), rate_limit_middleware(), shutdown_event(), startup_event(), sync_plaid_data(), upload_statement() (+9 more)

### Community 2 - "db_manager.py"
Cohesion: 0.07
Nodes (21): CircuitBreakerOpenException, execute_adapted_query(), get_accounts(), get_all_transactions(), get_connection(), get_connection_for_url(), get_sqlite_connection(), get_transaction_by_id() (+13 more)

### Community 3 - "main.py"
Cohesion: 0.08
Nodes (24): is_tesseract_available(), main(), run_chaos(), run_export(), run_gui(), run_ingest(), run_insights(), run_interactive_menu() (+16 more)

### Community 4 - "main_window.py"
Cohesion: 0.07
Nodes (7): reconcile_and_sync_all(), create_card(), MplCanvas, SettingsDialog, TagBar, TransactionDetailDialog, MainWindow

### Community 5 - "analyzer.py"
Cohesion: 0.10
Nodes (25): main(), print_insights(), print_reconcile(), print_transactions(), categorize_transaction(), detect_subscriptions(), generate_insights(), load_all_transactions_df() (+17 more)

### Community 6 - "test_system.py"
Cohesion: 0.08
Nodes (19): 1. Modifying the Rate Limiter (Redis Token-Bucket), 2. Horizontal Scaling of the Microservices, 3. Database Sharding Topologies, 4. Phase 5 Cache Engineering, Adding another Kafka Background Daemon (`worker3`), Expanding API Gateways (`api4`), Expanding the Phase 2 Consistent Hash Ring, ⚙️ LedgerSeLens Configuration Manual (+11 more)

### Community 7 - "package.json"
Cohesion: 0.11
Nodes (19): dependencies, react@^18.2.0, react-dom@^18.2.0, devDependencies, vite@^5.2.0, @vitejs/plugin-react@^4.2.1, name, private (+11 more)

### Community 9 - "ml_engine.py"
Cohesion: 0.22
Nodes (4): predict_category(), train_model(), test_predict_untrained_fallback(), test_train_and_predict_success()

### Community 10 - "environment"
Cohesion: 0.18
Nodes (11): KAFKA_ADVERTISED_LISTENERS, KAFKA_BROKER_ID, KAFKA_INTER_BROKER_LISTENER_NAME, KAFKA_LISTENER_SECURITY_PROTOCOL_MAP, KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR, KAFKA_ZOOKEEPER_CONNECT, depends_on, environment (+3 more)

### Community 11 - "environment"
Cohesion: 0.33
Nodes (9): POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER, environment, environment, environment, image, volumes (+1 more)

### Community 12 - "🗺️ Distributed Systems, Architecture & DSA Roadmap"
Cohesion: 0.22
Nodes (8): 🛤️ [COMPLETED] Phase 1: Scalability Foundations (Breaking Single-Node Limits), 🛤️ [COMPLETED] Phase 2: Distributed Data (Scaling the Database), 🛤️ [COMPLETED] Phase 3: High Availability (HA) & Fault Tolerance, 🛤️ [COMPLETED] Phase 4: Event-Driven Systems & Asynchronous Processing, 🛤️ [COMPLETED] Phase 5: Optimization & Caching (The Need for Speed), 🗺️ Distributed Systems, Architecture & DSA Roadmap, 📚 Recommended Tech Stack for the "System Design + DSA" Project, 🌟 The Capstone Project: "LedgerSeLens Distributed"

### Community 13 - "services"
Cohesion: 0.33
Nodes (5): image, ports, services, redis, version

### Community 14 - "zookeeper"
Cohesion: 0.33
Nodes (6): ZOOKEEPER_CLIENT_PORT, ZOOKEEPER_TICK_TIME, zookeeper, environment, image, ports

### Community 15 - "subprocess"
Cohesion: 0.60
Nodes (4): test_cli_insights_command(), test_cli_transactions_command(), test_main_help_and_subcommands(), test_main_status_and_sync_commands()

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

### Community 23 - "postgres-shard-1"
Cohesion: 0.67
Nodes (3): image, volumes, postgres-shard-1

### Community 24 - "postgres-shard-2"
Cohesion: 0.67
Nodes (3): image, volumes, postgres-shard-2

## Knowledge Gaps
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ConsistentHashRing` connect `test_system.py` to `db_manager.py`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `MainWindow` (e.g. with `MplCanvas` and `SettingsDialog`) actually correct?**
  _`MainWindow` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_data_ingestion.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05403508771929825 - nodes in this community are weakly interconnected._
- **Why does `save_transaction()` connect `server.py` to `db_manager.py`, `main.py`, `main_window.py`, `analyzer.py`, `ml_engine.py`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Should `server.py` be split into smaller, more focused modules?**
  _Cohesion score 0.053246753246753244 - nodes in this community are weakly interconnected._
- **Why does `init_db()` connect `server.py` to `db_manager.py`, `main.py`, `main_window.py`, `analyzer.py`, `SystemStatusDialog`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Should `db_manager.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06531986531986532 - nodes in this community are weakly interconnected._