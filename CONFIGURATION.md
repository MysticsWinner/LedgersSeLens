# ⚙️ LedgerSeLens Configuration Manual

Because LedgerSeLens operates as a decoupled microservices architecture, its structure is highly moldable. Use this page to configure and tune the system properties to your specific deployment capabilities.

## 1. Modifying the Rate Limiter (Redis Token-Bucket)

The Global Rate Limiter protects the APIs from DDoS attacks and bandwidth exhaustion. 
To manually modify the global user thresholds, inspect the HTTP middleware inside `server.py`:

```python
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Variables dictating maximum throughput allowed globally per user:
    limit = 200 # Edit this integer (Requests cap)
    window = 60 # Edit this integer (Timeframe in seconds)
```

## 2. Horizontal Scaling of the Microservices

To increase your throughput (if CPU maxes out under load), you do not need to rewrite any Python. You simply modify `docker-compose.yml`.

### Expanding API Gateways (`api4`)
Copy the `api3` block in the YAML file. Rename it to `api4`. To ensure traffic flows to it, you must tell the Reverse Proxy it exists:
Append `server api4:8000;` to the upstream map inside `nginx/nginx.conf`.

### Adding another Kafka Background Daemon (`worker3`)
Copy the `worker2` block in `docker-compose.yml`. 
The Kafka Event broker will magically and automatically identify the new worker container via the shared `ledger-workers` Consumer Group identifier entirely offline, instantly load balancing stream partition load away from the other nodes!

## 3. Database Sharding Topologies

The system natively uses 3 distinct PostgreSQL nodes internally (`postgres-shard-1`, `2`, `3`).

### Expanding the Phase 2 Consistent Hash Ring
If you provision and mount a 4th physical database server to the network:
1. Append the new postgres service to `docker-compose.yml`.
2. Insert its connection string into the environment parameters of `api` and `worker` node structures.
3. Open `database/db_manager.py` and simply append the new identifier to the `SHARD_URLS` array! 

Because LedgerSeLens incorporates a custom `ConsistentHashRing` DSA Structure, it will geometrically calculate the new node offsets and automatically start redirecting traffic fractions natively.

## 4. Phase 5 Cache Engineering 

The API leverages a Cache-Aside Read-Through architectural approach for `/api/insights`.
By default, the Time-To-Live (TTL) is set to 60 seconds.

If you are experiencing extreme Eventual Consistency drift or your Redis Memory (RAM) starts hitting capacity alarms, adjust the cache limits:
1. Open `server.py`
2. Navigate to the bottom of the `def get_insights()` endpoint logic.
3. Locate `redis_client.setex('insights_cache_all', 60, json.dumps(response_data))`
4. Decrease or increase the `60` parameter limit to tune memory eviction schedules.
