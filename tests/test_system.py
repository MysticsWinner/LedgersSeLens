import pytest
import time
from collections import Counter
import sys
import os

# Append root to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import ConsistentHashRing, CircuitBreaker

def test_consistent_hash_ring_distribution():
    """Verify that the Consistent Hashing DSA distributes accounts evenly across shards."""
    nodes = ["shard-1", "shard-2", "shard-3"]
    ring = ConsistentHashRing(nodes, replicas=200) # 200 virtual nodes for smooth distribution
    
    distribution = Counter()
    total_keys = 5000
    
    for i in range(total_keys):
        node = ring.get_node(f"UserAccountKey_Test_UUID_{i}")
        distribution[node] += 1
        
    # Verify uniformity: Each shard should theoretically get ~33%.
    # We test that it falls within a safe statistical margin.
    for node in nodes:
        node_share = distribution[node] / total_keys
        assert 0.20 <= node_share <= 0.45, f"Algorithm poorly distributed {node}: {node_share*100}%"

def test_circuit_breaker_transitions():
    """Verify the Finite State Machine transitions of the Circuit Breaker pattern."""
    # Create with a tiny 1-second timeout for rapid testing
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=1) 
    
    assert cb.state == "CLOSED", "Initial state must be CLOSED"
    assert cb.allow_request() is True, "Must allow requests when CLOSED"
    
    # Simulate database timing out or refusing connection
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "CLOSED", "State must remain CLOSED until threshold is breached"
    
    cb.record_failure() # 3rd strike!
    assert cb.state == "OPEN", "Circuit must TRIP and open after threshold breached!"
    assert cb.allow_request() is False, "Must forcefully REJECT requests when OPEN"
    
    # Wait for the network to hypothetically heal
    time.sleep(1.1)
    
    # Circuit transitions softly to test the waters
    assert cb.allow_request() is True, "Must allow a probe request when HALF_OPEN"
    assert cb.state == "HALF_OPEN", "Circuit transitions to HALF_OPEN after timeout"
    
    # Probe succeeds!
    cb.record_success()
    assert cb.state == "CLOSED", "Circuit fully HEALS and closes."
