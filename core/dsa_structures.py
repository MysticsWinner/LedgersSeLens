"""
LedgerSeLens Distributed Data Structures & Algorithms (DSA) Engine
Implements production-grade, thread-safe data structures from the System Design Roadmap:
  1. BloomFilter: Probabilistic O(k) membership filter using Kirsch-Mitzenmacher double hashing
  2. LRUCache: O(1) Doubly-Linked List + Hash Map cache with TTL expiration
  3. SlidingWindowRateLimiter: O(1) amortized Deque-backed sliding window log rate limiter
  4. CategoryTrie: O(L) Prefix Tree for category autocomplete & fast keyword matching
  5. InvertedIndex: Tokenized full-text search index over transaction descriptions & notes
  6. MerkleTree: Cryptographic hash tree partitioned by (account_name, YYYY-MM) buckets
"""

import hashlib
import math
import re
import threading
import time
from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# =============================================================================
# 1. Probabilistic Bloom Filter (Bit Array + Double Hashing)
# =============================================================================

class BloomFilter:
    """
    Space-efficient probabilistic data structure to test whether an element
    is a member of a set. Guarantees zero false negatives and a configurable
    false positive probability.
    """

    def __init__(self, expected_items: int = 50_000, false_positive_rate: float = 0.01):
        self.expected_items = max(100, expected_items)
        self.false_positive_rate = max(1e-6, min(0.5, false_positive_rate))

        # Optimal bit array size m = - (n * ln(p)) / (ln(2)^2)
        self.num_bits = max(
            1024,
            int(-self.expected_items * math.log(self.false_positive_rate) / (math.log(2) ** 2))
        )
        # Optimal number of hash functions k = (m / n) * ln(2)
        self.num_hashes = max(2, int(round((self.num_bits / self.expected_items) * math.log(2))))

        self._byte_array = bytearray((self.num_bits + 7) // 8)
        self._lock = threading.RLock()
        self.items_added = 0
        self.checks_performed = 0
        self.definite_negatives = 0
        self.probable_positives = 0

    def _hashes(self, item: str) -> Iterable[int]:
        """
        Uses Kirsch-Mitzenmacher double hashing: h_i(x) = (h1(x) + i * h2(x)) % m
        from a single SHA-256 digest split into two 128-bit integers.
        """
        raw = item.encode("utf-8", errors="ignore")
        digest = hashlib.sha256(raw).digest()
        h1 = int.from_bytes(digest[:16], "big")
        h2 = int.from_bytes(digest[16:], "big") or 1
        for i in range(self.num_hashes):
            yield (h1 + i * h2) % self.num_bits

    def add(self, item: str) -> None:
        with self._lock:
            for bit_idx in self._hashes(item):
                self._byte_array[bit_idx >> 3] |= (1 << (bit_idx & 7))
            self.items_added += 1

    def add_many(self, items: Iterable[str]) -> None:
        with self._lock:
            for item in items:
                for bit_idx in self._hashes(item):
                    self._byte_array[bit_idx >> 3] |= (1 << (bit_idx & 7))
                self.items_added += 1

    def might_contain(self, item: str) -> bool:
        with self._lock:
            self.checks_performed += 1
            for bit_idx in self._hashes(item):
                if not (self._byte_array[bit_idx >> 3] & (1 << (bit_idx & 7))):
                    self.definite_negatives += 1
                    return False
            self.probable_positives += 1
            return True

    def clear(self) -> None:
        with self._lock:
            self._byte_array = bytearray((self.num_bits + 7) // 8)
            self.items_added = 0
            self.checks_performed = 0
            self.definite_negatives = 0
            self.probable_positives = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "num_bits": self.num_bits,
                "num_hashes": self.num_hashes,
                "items_added": self.items_added,
                "checks_performed": self.checks_performed,
                "definite_negatives_skipped_db": self.definite_negatives,
                "probable_positives": self.probable_positives,
            }


# =============================================================================
# 2. O(1) Doubly-Linked List + Hash Map LRU Cache with TTL
# =============================================================================

class _LRUNode:
    __slots__ = ("key", "value", "expire_at", "prev", "next")

    def __init__(self, key: str, value: Any, expire_at: float):
        self.key = key
        self.value = value
        self.expire_at = expire_at
        self.prev: Optional["_LRUNode"] = None
        self.next: Optional["_LRUNode"] = None


class LRUCache:
    """
    Thread-safe O(1) Least Recently Used (LRU) Cache backed by a custom
    Doubly-Linked List and Hash Map with per-key TTL support.
    """

    def __init__(self, capacity: int = 256, default_ttl: float = 60.0):
        self.capacity = max(1, capacity)
        self.default_ttl = default_ttl
        self._map: Dict[str, _LRUNode] = {}
        self._lock = threading.RLock()

        # Sentinel head (most recent) and tail (least recent)
        self._head = _LRUNode("__HEAD__", None, float("inf"))
        self._tail = _LRUNode("__TAIL__", None, float("inf"))
        self._head.next = self._tail
        self._tail.prev = self._head

        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _remove(self, node: _LRUNode) -> None:
        prev_node = node.prev
        next_node = node.next
        if prev_node:
            prev_node.next = next_node
        if next_node:
            next_node.prev = prev_node
        node.prev = None
        node.next = None

    def _insert_front(self, node: _LRUNode) -> None:
        first = self._head.next
        node.next = first
        node.prev = self._head
        if first:
            first.prev = node
        self._head.next = node

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self.misses += 1
                return None
            if now >= node.expire_at:
                self._remove(node)
                del self._map[key]
                self.misses += 1
                return None
            self._remove(node)
            self._insert_front(node)
            self.hits += 1
            return node.value

    def put(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        expire_at = time.time() + (self.default_ttl if ttl is None else ttl)
        with self._lock:
            if key in self._map:
                node = self._map[key]
                node.value = value
                node.expire_at = expire_at
                self._remove(node)
                self._insert_front(node)
                return

            if len(self._map) >= self.capacity:
                lru = self._tail.prev
                if lru and lru is not self._head:
                    self._remove(lru)
                    self._map.pop(lru.key, None)
                    self.evictions += 1

            new_node = _LRUNode(key, value, expire_at)
            self._map[key] = new_node
            self._insert_front(new_node)

    def delete(self, key: str) -> bool:
        with self._lock:
            node = self._map.pop(key, None)
            if node:
                self._remove(node)
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._map.clear()
            self._head.next = self._tail
            self._tail.prev = self._head

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = round(self.hits / total, 4) if total > 0 else 0.0
            return {
                "size": len(self._map),
                "capacity": self.capacity,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "hit_rate": hit_rate,
            }


# =============================================================================
# 3. Deque-Backed Sliding Window Rate Limiter
# =============================================================================

class SlidingWindowRateLimiter:
    """
    In-memory O(1) amortized Sliding Window Log rate limiter using per-client Deques.
    Serves as a high-speed local rate limiter when Redis is unreachable.
    """

    def __init__(self, limit: int = 200, window_seconds: float = 60.0):
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow_request(self, client_key: str, now: Optional[float] = None) -> bool:
        current_time = now if now is not None else time.time()
        cutoff = current_time - self.window_seconds

        with self._lock:
            dq = self._windows.get(client_key)
            if dq is None:
                dq = deque()
                self._windows[client_key] = dq

            while dq and dq[0] <= cutoff:
                dq.popleft()

            if len(dq) >= self.limit:
                return False

            dq.append(current_time)
            return True

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


# =============================================================================
# 4. Prefix Trie for Category Autocomplete & Keyword Matching
# =============================================================================

class _TrieNode:
    __slots__ = ("children", "categories", "is_end", "matched_keyword")

    def __init__(self):
        self.children: Dict[str, "_TrieNode"] = {}
        self.categories: Set[str] = set()
        self.is_end: bool = False
        self.matched_keyword: Optional[str] = None


class CategoryTrie:
    """
    Prefix Tree (Trie) supporting:
      - Sub-millisecond prefix autocomplete for category names & keywords
      - Fast O(L) keyword extraction across transaction descriptions
    """

    def __init__(self):
        self.root = _TrieNode()
        self._lock = threading.RLock()
        self.keyword_count = 0

    def insert(self, keyword: str, category_name: str) -> None:
        cleaned = str(keyword or "").strip().lower()
        if not cleaned or not category_name:
            return
        with self._lock:
            node = self.root
            node.categories.add(category_name)
            for ch in cleaned:
                if ch not in node.children:
                    node.children[ch] = _TrieNode()
                node = node.children[ch]
                node.categories.add(category_name)
            if not node.is_end:
                self.keyword_count += 1
            node.is_end = True
            node.matched_keyword = category_name

    def autocomplete(self, prefix: str, limit: int = 10) -> List[str]:
        """Returns matching category names for a given keyword or category prefix in O(P)."""
        cleaned = str(prefix or "").strip().lower()
        with self._lock:
            if not cleaned:
                return sorted(self.root.categories)[:limit]
            node = self.root
            for ch in cleaned:
                if ch not in node.children:
                    return []
                node = node.children[ch]
            return sorted(node.categories)[:limit]

    def match_description(self, description: str) -> Optional[str]:
        """
        Scans description characters through the Trie to find the first matching
        keyword rule in O(N * max_keyword_len) without iterating over all categories.
        """
        text = str(description or "").lower()
        n = len(text)
        if not n:
            return None

        with self._lock:
            for start_idx in range(n):
                node = self.root
                for idx in range(start_idx, n):
                    ch = text[idx]
                    nxt = node.children.get(ch)
                    if nxt is None:
                        break
                    node = nxt
                    if node.is_end and node.matched_keyword:
                        return node.matched_keyword
        return None


# =============================================================================
# 5. Inverted Index for Full-Text Transaction Search
# =============================================================================

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class InvertedIndex:
    """
    In-memory Inverted Index mapping normalized word tokens to transaction document IDs.
    Supports instant multi-term AND/prefix search across transaction descriptions,
    categories, accounts, and notes.
    """

    def __init__(self):
        self._postings: Dict[str, Set[Any]] = {}
        self._documents: Dict[Any, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def tokenize(text: str) -> List[str]:
        if not text:
            return []
        return _TOKEN_RE.findall(str(text).lower())

    def add_document(self, doc_id: Any, document: Dict[str, Any]) -> None:
        searchable_fields = " ".join(
            str(document.get(k, "") or "")
            for k in ("Description", "description", "Category", "category_name", "Account", "account_name", "Notes", "notes", "Date", "date")
        )
        tokens = set(self.tokenize(searchable_fields))
        with self._lock:
            self._documents[doc_id] = document
            for token in tokens:
                bucket = self._postings.get(token)
                if bucket is None:
                    bucket = set()
                    self._postings[token] = bucket
                bucket.add(doc_id)

    def add_documents_bulk(self, docs: Iterable[Tuple[Any, Dict[str, Any]]]) -> int:
        count = 0
        with self._lock:
            for doc_id, document in docs:
                searchable_fields = " ".join(
                    str(document.get(k, "") or "")
                    for k in ("Description", "description", "Category", "category_name", "Account", "account_name", "Notes", "notes", "Date", "date")
                )
                tokens = set(self.tokenize(searchable_fields))
                self._documents[doc_id] = document
                for token in tokens:
                    bucket = self._postings.get(token)
                    if bucket is None:
                        bucket = set()
                        self._postings[token] = bucket
                    bucket.add(doc_id)
                count += 1
        return count

    def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        with self._lock:
            matched_doc_ids: Optional[Set[Any]] = None
            for q_tok in query_tokens:
                # Exact token match + prefix expansion
                tok_matches: Set[Any] = set()
                if q_tok in self._postings:
                    tok_matches.update(self._postings[q_tok])
                else:
                    for indexed_tok, doc_ids in self._postings.items():
                        if indexed_tok.startswith(q_tok):
                            tok_matches.update(doc_ids)

                if matched_doc_ids is None:
                    matched_doc_ids = tok_matches
                else:
                    matched_doc_ids &= tok_matches

                if not matched_doc_ids:
                    return []

            results = [self._documents[doc_id] for doc_id in matched_doc_ids if doc_id in self._documents]
            # Sort by Date descending if available
            results.sort(key=lambda d: str(d.get("Date") or d.get("date") or ""), reverse=True)
            return results[:limit]

    def clear(self) -> None:
        with self._lock:
            self._postings.clear()
            self._documents.clear()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "indexed_documents": len(self._documents),
                "unique_tokens": len(self._postings),
            }


# =============================================================================
# 6. Cryptographic Merkle Tree for Anti-Entropy Synchronization
# =============================================================================

class MerkleTree:
    """
    Cryptographic Hash Tree partitioned by (account_name, YYYY-MM) buckets.
    Enables O(1) root convergence verification and O(B) bucket-level diffing
    between local SQLite and distributed PostgreSQL shards.
    """

    def __init__(self, bucket_hashes: Optional[Dict[Tuple[str, str], str]] = None):
        """
        bucket_hashes maps (account_name_lower, 'YYYY-MM') -> sha256 hex digest of sorted records in that bucket.
        """
        self.bucket_hashes: Dict[Tuple[str, str], str] = dict(bucket_hashes or {})
        self.levels: List[List[str]] = []
        self.root_hash: str = self._build_tree()

    @staticmethod
    def _sha256(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @classmethod
    def from_records(
        cls,
        records: Iterable[Tuple[str, str, float, str, str, str]],
    ) -> "MerkleTree":
        """
        Constructs a MerkleTree from canonical transaction tuples:
          (date_yyyy_mm_dd, description_lower, amount_rounded, account_lower, notes, receipt_path)
        Groups them into (account_lower, YYYY-MM) buckets and hashes each bucket deterministically.
        """
        buckets: Dict[Tuple[str, str], List[str]] = {}
        for date_str, desc, amt, acct, notes, receipt in records:
            ym = (date_str or "1970-01")[:7]
            bucket_key = (acct, ym)
            canonical_row = f"{date_str}|{desc}|{amt:.2f}|{acct}|{notes}|{receipt}"
            buckets.setdefault(bucket_key, []).append(canonical_row)

        bucket_hashes: Dict[Tuple[str, str], str] = {}
        for b_key, rows in buckets.items():
            rows.sort()
            payload = f"{b_key[0]}:{b_key[1]}#" + "\n".join(rows)
            bucket_hashes[b_key] = cls._sha256(payload)

        return cls(bucket_hashes)

    def _build_tree(self) -> str:
        if not self.bucket_hashes:
            empty_hash = self._sha256("EMPTY_MERKLE_TREE")
            self.levels = [[empty_hash]]
            return empty_hash

        # Sort leaves by (account, YYYY-MM) for deterministic tree construction
        sorted_keys = sorted(self.bucket_hashes.keys())
        current_level = [
            self._sha256(f"{k[0]}|{k[1]}|{self.bucket_hashes[k]}")
            for k in sorted_keys
        ]
        self.levels = [current_level]

        while len(current_level) > 1:
            next_level: List[str] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                next_level.append(self._sha256(f"{left}:{right}"))
            self.levels.append(next_level)
            current_level = next_level

        return current_level[0]

    def diff_buckets(self, other: "MerkleTree") -> Set[Tuple[str, str]]:
        """
        Returns the set of (account_lower, YYYY-MM) buckets that differ between
        this MerkleTree and `other`. If root hashes match, returns an empty set in O(1).
        """
        if self.root_hash == other.root_hash:
            return set()

        divergent: Set[Tuple[str, str]] = set()
        all_keys = set(self.bucket_hashes.keys()) | set(other.bucket_hashes.keys())
        for key in all_keys:
            if self.bucket_hashes.get(key) != other.bucket_hashes.get(key):
                divergent.add(key)
        return divergent

