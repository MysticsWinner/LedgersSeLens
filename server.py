from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import pandas as pd
import json
import time
import os
import redis
import logging
from kafka import KafkaProducer
from core.analyzer import load_all_transactions_df, generate_insights, detect_subscriptions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LedgerSeLens API Distributed",
    description="A horizontally scalable REST API serving insights and transaction data.",
    version="4.0.0" # Phase 4!
)

# Connect to Redis for distributed rate-limiting
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

ZK_URL = os.environ.get("ZOOKEEPER_URL", "localhost:2181")
zk = None

# Connect to Kafka for async ingestion
KAFKA_URL = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_URL,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda k: k.encode('utf-8') if k else None,
        acks=1
    )
    logger.info("Kafka Producer initialized successfully.")
except Exception as e:
    logger.error(f"Failed to connect to Kafka: {e}")
    producer = None


@app.on_event("startup")
def startup_event():
    from database.db_manager import init_db
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database (might be initializing in another node): {e}")

    try:
        from kazoo.client import KazooClient
        global zk
        zk = KazooClient(hosts=ZK_URL)
        zk.start()
        zk.ensure_path("/ledger/api_nodes")
        node_name = os.environ.get("HOSTNAME", f"node-{int(time.time())}")
        zk.create(f"/ledger/api_nodes/{node_name}", ephemeral=True)
    except Exception as e:
        logger.warning(f"Could not connect to Zookeeper. Running uncoordinated. Error: {e}")

@app.on_event("shutdown")
def shutdown_event():
    if zk:
        zk.stop()
    if producer:
        producer.close()

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if not redis_client:
        return await call_next(request)
        
    client_ip = request.client.host if request.client else "unknown"
    limit = 200
    window = 60
    current_time = time.time()
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
    except Exception as e:
        logger.error(f"Rate Limiter Redis Error: {e}")
    
    response = await call_next(request)
    return response

@app.get("/")
def read_root():
    return {"message": "Welcome to the LedgerSeLens Distributed API. Try /api/insights"}

@app.get("/api/transactions")
def get_transactions(limit: int = 50, offset: int = 0):
    df = load_all_transactions_df()
    from database.db_manager import CURRENTLY_DEGRADED
    
    if df.empty:
        return {"data": [], "total": 0, "degraded": CURRENTLY_DEGRADED}
        
    df_sliced = df.iloc[offset:offset+limit].copy()
    df_sliced['Date'] = df_sliced['Date'].dt.strftime('%Y-%m-%d')
    df_sliced = df_sliced.where(pd.notnull(df_sliced), None)
    
    records = df_sliced.to_dict(orient="records")
    return {"data": records, "total": len(df), "limit": limit, "offset": offset, "degraded": CURRENTLY_DEGRADED}

@app.get("/api/insights")
def get_insights():
    # ✨ PHASE 5: O(1) Distributed Cache-Aside (Read-Through) Pattern
    if redis_client:
        try:
            cached_insights = redis_client.get('insights_cache_all')
            if cached_insights:
                cached_data = json.loads(cached_insights)
                cached_data['status'] = "cached ✨ (O(1) Memory read!)" 
                return cached_data
        except Exception as e:
            logger.error(f"Redis Cache read failed: {e}")
            
    df = load_all_transactions_df()
    from database.db_manager import CURRENTLY_DEGRADED
    
    if df.empty:
        if CURRENTLY_DEGRADED:
           return {"warning": "Storage cells are degraded. No data could be retrieved from the active shards."} 
        raise HTTPException(status_code=404, detail="No transactions found")
        
    insights = generate_insights(df)
    
    response_data = {
        "status": "degraded" if CURRENTLY_DEGRADED else "fresh (Heavy MapReduce Execution)",
        "warning": "Data is partially incomplete due to an offline database shard!" if CURRENTLY_DEGRADED else None,
        "total_spent": float(insights["total_spent"]),
        "total_received": float(insights["total_received"]),
        "category_breakdown": insights["category_breakdown"].to_dict(),
        "timeline": {str(k): float(v) for k, v in insights["timeline"].items()},
        "forecast": {str(k): float(v) for k, v in insights["forecast"].items()}
    }
    
    # Store heavily map-reduced payload in RAM Cache for 60 seconds (TTL)
    if redis_client and not CURRENTLY_DEGRADED:
        try:
            redis_client.setex('insights_cache_all', 60, json.dumps(response_data))
        except Exception as e:
            pass
            
    return response_data

@app.post("/api/plaid/sync")
def sync_plaid_data(access_token: str = "mock-sandbox-token"):
    import datetime
    
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    mock_plaid_data = [
        {"date": today, "desc": "AMAZON WEB SERVICES", "amount": -15.42, "category": "Utilities", "acct": "Chase Checking"},
        {"date": today, "desc": "PAYROLL DIRECT DEPOSIT", "amount": 2500.00, "category": "Income", "acct": "Wells Fargo"},
        {"date": today, "desc": "UBER TRIP SF", "amount": -22.50, "category": "Transport", "acct": "Amex Platinum"},
        {"date": today, "desc": "STARBUCKS", "amount": -5.50, "category": "Food", "acct": "Citi Double Cash"}
    ]
    
    if not producer:
        return JSONResponse(status_code=503, content={"error": "Kafka Producer offline, cannot ingest data right now."})
        
    for tx in mock_plaid_data:
        # ✨ PHASE 4: ASYNCHRONOUS DECOUPLED MESSAGING ✨
        # The API no longer stops to wait for PostgreSQL to do string parsing or disk I/O.
        # It dumps the payload to Kafka grouped by exact partition keys to guarantee chronologies.
        producer.send('ledger-ingestion', key=tx["acct"], value=tx)
        
    producer.flush()
        
    return {
        "status": "accepted (HTTP 202)", 
        "message": f"Successfully published {len(mock_plaid_data)} transactions to Kafka for async processing.",
        "node": os.environ.get("HOSTNAME", "local")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
