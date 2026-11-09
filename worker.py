"""
LedgerSeLens Scalable Kafka Worker Pool
Features:
  - Exponential-backoff readiness probe (replaces static 30s sleep)
  - High-throughput Micro-Batch Polling (max_records=500) + Bulk Upsert (save_transactions_batch)
  - Dead-Letter Queue (DLQ) routing for poison-pill payloads
  - At-Least-Once Delivery safeguard when a database shard Circuit Breaker trips
"""

import os
import json
import time
import logging
from typing import List, Dict, Any
import redis
from kafka import KafkaConsumer, KafkaProducer

from database.db_manager import save_transactions_batch, init_db, CircuitBreakerOpenException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
KAFKA_URL = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
INGESTION_TOPIC = "ledger-ingestion"
DLQ_TOPIC = "ledger-ingestion-dlq"


def connect_kafka_with_backoff(max_attempts: int = 15):
    """Connects to Kafka consumer & DLQ producer using exponential backoff + jitter."""
    delay = 1.0
    for attempt in range(1, max_attempts + 1):
        try:
            consumer = KafkaConsumer(
                INGESTION_TOPIC,
                bootstrap_servers=KAFKA_URL,
                group_id='ledger-workers',
                value_deserializer=lambda m: json.loads(m.decode('utf-8')) if m else None,
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                max_poll_records=500,
            )
            dlq_producer = KafkaProducer(
                bootstrap_servers=KAFKA_URL,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks=1,
            )
            return consumer, dlq_producer
        except Exception as e:
            logger.info(f"Waiting for Kafka broker at {KAFKA_URL} (attempt {attempt}/{max_attempts}): {e}")
            time.sleep(min(delay, 10.0))
            delay *= 1.5
    raise RuntimeError(f"Could not connect to Kafka at {KAFKA_URL} after {max_attempts} attempts")


def process_worker_batch(
    messages: List[Any],
    redis_client=None,
    dlq_producer=None,
) -> int:
    """
    Processes a batch of Kafka messages using save_transactions_batch().
    Routes malformed messages to DLQ and returns the count of newly inserted records.
    """
    valid_batch: List[Dict[str, Any]] = []
    for msg in messages:
        tx = getattr(msg, "value", msg)
        if not isinstance(tx, dict) or ("amount" not in tx and "Amount" not in tx):
            if dlq_producer:
                try:
                    dlq_producer.send(DLQ_TOPIC, value={"error": "Malformed payload", "raw": str(tx)})
                except Exception:
                    pass
            continue

        valid_batch.append({
            "date": tx.get("date") or tx.get("Date"),
            "desc": tx.get("desc") or tx.get("description") or tx.get("Description", ""),
            "amount": tx.get("amount") if tx.get("amount") is not None else tx.get("Amount", 0.0),
            "category": tx.get("category") or tx.get("Category", "Other"),
            "acct": tx.get("acct") or tx.get("Account", "Unknown Account"),
            "notes": tx.get("notes") or tx.get("Notes", ""),
            "receipt_path": tx.get("receipt_path") or tx.get("Receipt", ""),
        })

    if not valid_batch:
        return 0

    inserted = save_transactions_batch(valid_batch)
    if inserted > 0 and redis_client:
        try:
            for key in redis_client.scan_iter("insights_cache_all*"):
                redis_client.delete(key)
            redis_client.delete("insights_cache_all")
            logger.info(f"Batch inserted {inserted} transactions & invalidated insights cache.")
        except Exception:
            pass
    return inserted


def run_worker():
    try:
        init_db()
    except Exception:
        pass

    try:
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
    except Exception:
        redis_client = None

    consumer, dlq_producer = connect_kafka_with_backoff()
    logger.info("Successfully connected! Listening for micro-batches of transactions...")

    while True:
        records_by_partition = consumer.poll(timeout_ms=500, max_records=500)
        if not records_by_partition:
            continue

        flat_messages = [msg for partition_msgs in records_by_partition.values() for msg in partition_msgs]
        try:
            process_worker_batch(flat_messages, redis_client=redis_client, dlq_producer=dlq_producer)
            consumer.commit()
        except CircuitBreakerOpenException:
            logger.warning("Storage shard circuit open. Refusing to commit batch offset; pausing 5s for recovery...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Worker Batch Error: {e}")


if __name__ == "__main__":
    run_worker()
