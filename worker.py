import os
import json
import time
import logging
import redis
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Wait for infrastructure to spin up
logger.info("Worker sleeping for 30 seconds to allow Kafka & Postgres to construct...")
time.sleep(30)

from database.db_manager import save_transaction, init_db, CircuitBreakerOpenException

try:
    init_db()
except:
    pass

# Connect to Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    redis_client = None

KAFKA_URL = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

logger.info(f"Connecting to Kafka at {KAFKA_URL}...")

# Robust scalable Consumer Group configuration
consumer = KafkaConsumer(
    'ledger-ingestion',
    bootstrap_servers=KAFKA_URL,
    group_id='ledger-workers',
    value_deserializer=lambda m: json.loads(m.decode('utf-8')) if m else None,
    auto_offset_reset='earliest',
    enable_auto_commit=False # Important! We only commit after the DB confirms write.
)

logger.info("Successfully connected! Listening for transactions...")

for message in consumer:
    tx = message.value
    if not tx:
        continue
        
    try:
        acct = tx.get("acct", "Unknown Account")
        # ✨ IDEMPOTENT DATABASE INSERT
        added = save_transaction(
            tx.get("date"), 
            tx.get("desc"), 
            tx.get("amount"), 
            tx.get("category"), 
            acct
        )
        
        if added:
            logger.info(f"✨ Parsed Async Event! Inserted new transaction for {acct}: {tx.get('desc')}")
            # ✨ PHASE 5: Cache Invalidation! 
            # If a new event is successfully processed, the global insights cache is stale! Delete it!
            if redis_client:
                redis_client.delete("insights_cache_all")
                logger.info("Executed Cache Invalidation!")
        else:
            logger.debug(f"Idempotent Ignored: Duplicate transaction for {acct} safely rejected.")
            
        # Commit to Kafka ONLY if write succeeds or was safely ignored via idempotency check
        consumer.commit()
        
    except CircuitBreakerOpenException:
        # AT-LEAST-ONCE DELIVERY SAFEGUARD:
        # If the shard for this specific user is down, we DO NOT COMMIT to Kafka.
        # The Kafka Broker will re-deliver this message until the Shard heals!
        logger.warning(f"Storage cell offline for {acct}. Refusing to consume message from queue. Pausing...")
        time.sleep(5)
    except Exception as e:
        logger.error(f"Worker Error Processing Message: {e}")
