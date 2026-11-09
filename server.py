"""
LedgerSeLens Distributed API Server
Features horizontally scalable, high-availability architecture:
  - Tiered Caching: Redis Cluster + O(1) Doubly-Linked List LRU Cache Fallback
  - Rate Limiting: Redis ZSET Sliding Window + O(1) Deque Sliding Window Fallback
  - SQL Push-Down Pagination with Min-Heap K-Way Merge across Shards
  - Full-Text Search (Inverted Index) & Category Autocomplete (Prefix Trie)
  - Hybrid Async Statement Ingestion (Kafka Streaming + Background Job Tracker)
  - Sharded PostgreSQL Connection Pools + Local SQLite Fallback
"""

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
import pandas as pd
import json
import time
import uuid
import os
import redis
import logging
from typing import Optional, Dict, Any

from core.analyzer import (
    load_all_transactions_df,
    generate_insights,
    detect_subscriptions,
    _process_transactions,
    prepare_categorized_records,
    search_transactions,
    autocomplete_categories,
    refresh_search_index,
)
from core.data_ingestion import ingest_file
from core.dsa_structures import LRUCache, SlidingWindowRateLimiter
from database.db_manager import (
    get_transactions_paginated,
    get_storage_metrics,
    save_transactions_batch,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LedgerSeLens API Distributed",
    description="A horizontally scalable REST API serving insights, full-text search, and transaction data with full resilience fallbacks.",
    version="5.0.0"
)

# Bounded O(1) Doubly-Linked List + Hash Map LRU Cache Fallback when Redis is offline
_lru_cache = LRUCache(capacity=512, default_ttl=60.0)
# Deque-backed Sliding Window Rate Limiter Fallback when Redis is offline
_local_rate_limiter = SlidingWindowRateLimiter(limit=200, window_seconds=60.0)
# Async Job Tracker Store (Backed by Redis + LRU Cache fallback)
_job_store = LRUCache(capacity=1024, default_ttl=3600.0)

# Connect to Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    redis_client.ping()
    logger.info("Connected to Redis successfully.")
except Exception as e:
    logger.info(f"Redis unavailable ({e}). Operating with O(1) LRU Cache & Deque Rate Limiter fallback.")
    redis_client = None

ZK_URL = os.environ.get("ZOOKEEPER_URL", "localhost:2181")
zk = None

# Connect to Kafka for async ingestion (with fast probe to avoid startup stalls)
KAFKA_URL = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
producer = None
if os.environ.get("ENABLE_KAFKA", "0") in ("1", "true", "yes"):
    try:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_URL,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks=1,
            linger_ms=10,
            batch_size=32768,
            request_timeout_ms=1000,
            api_version_auto_timeout_ms=1000
        )
        logger.info("Kafka Producer initialized successfully.")
    except Exception as e:
        logger.info(f"Kafka unavailable ({e}). Operating with direct in-process batch ingestion fallback.")
        producer = None


def _invalidate_caches():
    if redis_client:
        try:
            redis_client.delete("insights_cache_all")
        except Exception:
            pass
    _lru_cache.delete("insights_cache_all")


def _save_job_state(job_id: str, state: Dict[str, Any]) -> None:
    _job_store.put(job_id, state, ttl=3600.0)
    if redis_client:
        try:
            redis_client.setex(f"job:{job_id}", 3600, json.dumps(state))
        except Exception:
            pass


def _get_job_state(job_id: str) -> Optional[Dict[str, Any]]:
    if redis_client:
        try:
            raw = redis_client.get(f"job:{job_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return _job_store.get(job_id)


@app.on_event("startup")
def startup_event():
    from database.db_manager import init_db
    try:
        init_db()
    except Exception as e:
        logger.warning(f"Database startup init notice: {e}")

    try:
        from kazoo.client import KazooClient
        global zk
        zk = KazooClient(hosts=ZK_URL, timeout=1.0)
        zk.start(timeout=1.0)
        zk.ensure_path("/ledger/api_nodes")
        node_name = os.environ.get("HOSTNAME", f"node-{int(time.time())}")
        zk.create(f"/ledger/api_nodes/{node_name}", ephemeral=True)
    except Exception as e:
        logger.info(f"Running uncoordinated without Zookeeper: {e}")
        zk = None


@app.on_event("shutdown")
def shutdown_event():
    if zk:
        try:
            zk.stop()
        except Exception:
            pass
    if producer:
        try:
            producer.close()
        except Exception:
            pass


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    limit = 200
    window = 60
    current_time = time.time()

    # 1. Primary: Redis Sliding Window Rate Limiter
    if redis_client:
        redis_key = f"rate_limit:{client_ip}"
        try:
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(redis_key, 0, current_time - window)
            pipe.zcard(redis_key)
            pipe.zadd(redis_key, {str(current_time): current_time})
            pipe.expire(redis_key, window)
            results = pipe.execute()
            request_count = results[1]
            if request_count >= limit:
                return JSONResponse(status_code=429, content={"detail": "Too Many Requests - Rate Limit Exceeded"})
            return await call_next(request)
        except Exception as e:
            logger.debug(f"Redis rate limiter fallback to in-memory Deque: {e}")

    # 2. Fallback: In-Memory Deque Sliding Window Rate Limiter
    if not _local_rate_limiter.allow_request(client_ip, now=current_time):
        return JSONResponse(status_code=429, content={"detail": "Too Many Requests - Rate Limit Exceeded"})

    return await call_next(request)


@app.get("/")
def read_root():
    from database.db_manager import IS_FALLBACK_ACTIVE, CURRENTLY_DEGRADED
    return {
        "message": "Welcome to the LedgerSeLens Distributed API. Try /api/insights",
        "storage_mode": "SQLite Fallback" if IS_FALLBACK_ACTIVE else "Distributed PostgreSQL Shards",
        "degraded": CURRENTLY_DEGRADED
    }


@app.get("/api/transactions")
def get_transactions(
    limit: int = 50,
    offset: int = 0,
    account: str = "All Accounts",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Scalable SQL push-down paginated transaction listing.
    Avoids loading full tables into Pandas by pushing ORDER BY, LIMIT, and OFFSET to the storage layer.
    """
    records, total = get_transactions_paginated(
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
        account_filter=account,
    )
    from database.db_manager import CURRENTLY_DEGRADED, IS_FALLBACK_ACTIVE

    return {
        "data": records,
        "total": total,
        "limit": limit,
        "offset": offset,
        "degraded": CURRENTLY_DEGRADED,
        "fallback_mode": IS_FALLBACK_ACTIVE
    }


@app.get("/api/transactions/search")
def api_search_transactions(q: str = "", limit: int = 50):
    """
    Sub-millisecond full-text search across transaction descriptions, categories,
    accounts, and notes using an in-memory Inverted Index.
    """
    results = search_transactions(q, limit=limit)
    return {
        "query": q,
        "total": len(results),
        "limit": limit,
        "data": results,
    }


@app.get("/api/categories/autocomplete")
def api_autocomplete_categories(prefix: str = "", limit: int = 10):
    """
    Autocompletes transaction categories and keyword rules in O(P) time using a Prefix Trie.
    """
    matches = autocomplete_categories(prefix, limit=limit)
    return {
        "prefix": prefix,
        "matches": matches,
        "total": len(matches),
    }


@app.get("/api/insights")
def get_insights():
    from database import db_manager
    cache_key = f"insights_cache_all:{db_manager.DB_FILE}"

    # 1. Check Redis Cache
    if redis_client:
        try:
            cached_insights = redis_client.get(cache_key)
            if cached_insights:
                cached_data = json.loads(cached_insights)
                cached_data['status'] = "cached (Redis O(1) Memory read!)"
                return cached_data
        except Exception as e:
            logger.debug(f"Redis Cache read failed: {e}")

    # 2. Check Bounded O(1) In-Memory LRU Cache Fallback
    lru_hit = _lru_cache.get(cache_key)
    if lru_hit is not None:
        cached_copy = dict(lru_hit)
        cached_copy['status'] = "cached (O(1) Doubly-Linked LRU Fallback)"
        return cached_copy

    df = load_all_transactions_df()
    from database.db_manager import CURRENTLY_DEGRADED, IS_FALLBACK_ACTIVE

    if df.empty:
        if CURRENTLY_DEGRADED:
            return {"warning": "Storage cells are degraded. No data could be retrieved from the active shards."}
        raise HTTPException(status_code=404, detail="No transactions found")

    insights = generate_insights(df)

    response_data = {
        "status": "degraded" if CURRENTLY_DEGRADED else "fresh (MapReduce Execution)",
        "warning": "Data is partially incomplete due to an offline database shard!" if CURRENTLY_DEGRADED else None,
        "total_spent": float(insights["total_spent"]),
        "total_received": float(insights["total_received"]),
        "category_breakdown": insights["category_breakdown"].to_dict(),
        "timeline": {str(k): float(v) for k, v in insights["timeline"].items()},
        "forecast": {str(k): float(v) for k, v in insights["forecast"].items()},
        "fallback_mode": IS_FALLBACK_ACTIVE
    }

    # Cache in Redis and O(1) LRU Cache
    if not CURRENTLY_DEGRADED:
        if redis_client:
            try:
                redis_client.setex(cache_key, 60, json.dumps(response_data))
            except Exception:
                pass
        _lru_cache.put(cache_key, response_data, ttl=60.0)

    return response_data


@app.get("/api/subscriptions")
def get_subscriptions():
    """Detects recurring subscriptions across all recorded transactions."""
    df = load_all_transactions_df()
    subs = detect_subscriptions(df)
    return {"data": subs, "total": len(subs)}


@app.post("/api/plaid/sync")
def sync_plaid_data(access_token: str = "mock-sandbox-token"):
    """
    Syncs transactions from Plaid sandbox.
    Uses Kafka streaming when available, with immediate bulk batch
    database fallback when Kafka is offline.
    """
    import datetime

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    mock_plaid_data = [
        {"date": today, "desc": "AMAZON WEB SERVICES", "amount": -15.42, "category": "Payment: Subscription", "acct": "Chase Checking"},
        {"date": today, "desc": "PAYROLL DIRECT DEPOSIT", "amount": 2500.00, "category": "Income", "acct": "Wells Fargo"},
        {"date": today, "desc": "UBER TRIP SF", "amount": -22.50, "category": "Transport", "acct": "Amex Platinum"}
    ]

    # 1. Async Streaming via Kafka
    if producer:
        try:
            for tx in mock_plaid_data:
                producer.send('ledger-ingestion', key=tx["acct"], value=tx)
            producer.flush()
            return {
                "status": "success",
                "message": f"Successfully published {len(mock_plaid_data)} transactions to Kafka for async processing.",
                "transactions_imported": mock_plaid_data,
                "node": os.environ.get("HOSTNAME", "local")
            }
        except Exception as e:
            logger.warning(f"Kafka produce failed: {e}. Executing direct batch ingestion fallback.")

    # 2. Bulk Batch Ingestion Fallback
    save_transactions_batch(mock_plaid_data)
    _invalidate_caches()

    return {
        "status": "success",
        "message": f"Directly ingested {len(mock_plaid_data)} transactions via batch fallback.",
        "transactions_imported": mock_plaid_data,
        "mode": "in-process-fallback"
    }


def _execute_async_ingestion_job(job_id: str, raw_records: list, account_name: str):
    """Background worker routine for async statement uploads."""
    try:
        _save_job_state(job_id, {
            "job_id": job_id,
            "status": "processing",
            "account": account_name,
            "total_records": len(raw_records),
            "processed_records": 0,
            "updated_at": time.time(),
        })
        prepared = prepare_categorized_records(raw_records, account_name=account_name)
        if producer:
            try:
                for tx in prepared:
                    producer.send('ledger-ingestion', key=tx["acct"], value=tx)
                producer.flush()
                _save_job_state(job_id, {
                    "job_id": job_id,
                    "status": "queued_in_kafka",
                    "account": account_name,
                    "total_records": len(raw_records),
                    "processed_records": len(prepared),
                    "updated_at": time.time(),
                })
                return
            except Exception as e:
                logger.warning(f"Kafka streaming failed inside job {job_id}: {e}. Falling back to batch DB write.")

        inserted = save_transactions_batch(prepared, default_account=account_name)
        _invalidate_caches()
        _save_job_state(job_id, {
            "job_id": job_id,
            "status": "completed",
            "account": account_name,
            "total_records": len(raw_records),
            "processed_records": len(prepared),
            "inserted_records": inserted,
            "updated_at": time.time(),
        })
    except Exception as e:
        logger.error(f"Async ingestion job {job_id} failed: {e}")
        _save_job_state(job_id, {
            "job_id": job_id,
            "status": "failed",
            "account": account_name,
            "error": str(e),
            "updated_at": time.time(),
        })


@app.post("/api/upload")
async def upload_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    account_name: str = Form("Main Account"),
    async_mode: Optional[bool] = Form(None),
):
    """
    Ingests uploaded bank statements across PDF, Excel (.xlsx, .xls),
    CSV (.csv, .tsv), and receipt images (.png, .jpg, .jpeg).
    Supports Hybrid Auto-Offload:
      - If async_mode=True or (async_mode is None and valid_rows > 500 and Kafka is active),
        offloads persistence to background workers / Kafka with a pollable job_id.
      - Otherwise executes fast bulk batch persistence synchronously.
    """
    os.makedirs("uploads", exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{os.path.basename(file.filename or 'statement.csv')}"
    temp_path = os.path.join("uploads", safe_name)

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        ingestion_result = ingest_file(temp_path, account_name=account_name)
        if not ingestion_result.is_success or ingestion_result.dataframe.empty:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Failed to ingest statement",
                    "details": ingestion_result.errors,
                    "warnings": ingestion_result.warnings
                }
            )

        raw_records = ingestion_result.dataframe.to_dict(orient='records')
        job_id = f"job-{uuid.uuid4().hex[:12]}"

        should_offload = (
            async_mode is True
            or (async_mode is None and ingestion_result.valid_rows > 500 and producer is not None)
        )

        if should_offload:
            _save_job_state(job_id, {
                "job_id": job_id,
                "status": "queued",
                "account": account_name,
                "filename": file.filename,
                "total_records": ingestion_result.valid_rows,
                "processed_records": 0,
                "updated_at": time.time(),
            })
            background_tasks.add_task(_execute_async_ingestion_job, job_id, raw_records, account_name)
            return {
                "status": "accepted",
                "mode": "async",
                "job_id": job_id,
                "filename": file.filename,
                "account": account_name,
                "total_rows_detected": ingestion_result.total_rows,
                "valid_rows_imported": ingestion_result.valid_rows,
                "dropped_rows": ingestion_result.dropped_rows,
                "file_type": ingestion_result.file_type,
                "warnings": ingestion_result.warnings
            }

        # Synchronous Fast Batch Path
        _process_transactions(raw_records, account_name)
        _invalidate_caches()

        _save_job_state(job_id, {
            "job_id": job_id,
            "status": "completed",
            "account": account_name,
            "filename": file.filename,
            "total_records": ingestion_result.valid_rows,
            "processed_records": ingestion_result.valid_rows,
            "updated_at": time.time(),
        })

        return {
            "status": "success",
            "mode": "sync-batch",
            "job_id": job_id,
            "filename": file.filename,
            "account": account_name,
            "total_rows_detected": ingestion_result.total_rows,
            "valid_rows_imported": ingestion_result.valid_rows,
            "dropped_rows": ingestion_result.dropped_rows,
            "file_type": ingestion_result.file_type,
            "warnings": ingestion_result.warnings
        }
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    """Polls the status and progress of an asynchronous statement upload job."""
    state = _get_job_state(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return state


@app.get("/api/system/metrics")
def get_system_metrics():
    """
    Exposes real-time scalability & DSA telemetry:
    Connection Pools, Circuit Breakers, Bloom Filters, O(1) LRU Cache, and Inverted Index stats.
    """
    idx = refresh_search_index()
    return {
        "node": os.environ.get("HOSTNAME", "local"),
        "storage": get_storage_metrics(),
        "lru_cache": _lru_cache.stats(),
        "job_store": _job_store.stats(),
        "inverted_index": idx.stats(),
        "redis_connected": redis_client is not None,
        "kafka_producer_active": producer is not None,
    }


@app.post("/api/reconcile")
def post_reconcile():
    """
    Bidirectionally reconciles all historical and new data across local SQLite
    and distributed PostgreSQL shards using Merkle Tree bucket diffing.
    """
    from database.db_manager import reconcile_and_sync_all
    result = reconcile_and_sync_all()
    _invalidate_caches()
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
