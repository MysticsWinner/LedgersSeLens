"""
LedgerSeLens Bidirectional Synchronization & Reconciliation Manager
Handles offline-first replication, forward replay, catch-up replication,
and Merkle Tree anti-entropy convergence across Local SQLite and Multi-Shard PostgreSQL.

Solves the 4-Phase Lifecycle:
  1. Primary online -> writes to shards
  2. Primary offline -> writes to local fallback store
  3. Isolated local execution -> continues accumulating local transactions
  4. Full recovery -> Computes (account, YYYY-MM) Merkle Trees and bidirectionally
     reconciles only divergent buckets without duplication, resolving any field conflicts.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime

from core.dsa_structures import MerkleTree

logger = logging.getLogger(__name__)


def _normalize_date_str(date_val: Any) -> str:
    """Converts diverse date representations to a canonical 'YYYY-MM-DD' string."""
    if not date_val:
        return "1970-01-01"
    if hasattr(date_val, 'strftime'):
        return date_val.strftime('%Y-%m-%d')
    s = str(date_val).strip()
    return s[:10]


def _build_tx_identity_key(date_val: Any, desc: Any, amount: Any, account_name: Any) -> Tuple[str, str, float, str]:
    """Generates an idempotent collision-resistant composite key for a transaction."""
    d = _normalize_date_str(date_val)
    descr = str(desc or '').strip().lower()
    amt = round(float(amount or 0.0), 2)
    acct = str(account_name or 'Main Account').strip().lower()
    return (d, descr, amt, acct)


def _bucket_key_for_tx(date_str: str, account_name: str) -> Tuple[str, str]:
    acct_lower = str(account_name or 'Main Account').strip().lower()
    ym = (date_str or '1970-01')[:7]
    return (acct_lower, ym)


def reconcile_and_sync() -> Dict[str, Any]:
    """
    Performs bidirectional data reconciliation between local SQLite
    and all distributed PostgreSQL shards using a Merkle Tree partitioned
    by (account_name, YYYY-MM) buckets.
    """
    from database import db_manager

    # 1. Probe if remote PostgreSQL cluster is available
    if not db_manager._probe_postgres():
        return {
            "status": "offline_mode",
            "message": "PostgreSQL cluster is currently offline. Operating purely on local storage.",
            "pushed_to_remote": 0,
            "pulled_to_local": 0,
            "conflicts_resolved": 0,
            "divergent_buckets_synced": 0,
            "total_unified_transactions": db_manager.get_transaction_count(),
            "synced": False
        }

    pushed_to_remote = 0
    pulled_to_local = 0
    conflicts_resolved = 0

    local_conn = db_manager.get_sqlite_connection()
    local_c = local_conn.cursor()

    try:
        # ---------------- 2. Reconcile Categories ----------------
        local_c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
        local_cats = {r[0]: {'color': r[1], 'match_rules': r[2], 'budget_limit': r[3]} for r in local_c.fetchall()}

        remote_cats = {}
        for url in db_manager.SHARD_URLS:
            conn = None
            try:
                conn = db_manager.get_connection_for_url(url)
                c = conn.cursor()
                c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
                for r in c.fetchall():
                    if r[0] not in remote_cats:
                        remote_cats[r[0]] = {'color': r[1], 'match_rules': r[2], 'budget_limit': r[3]}
            except Exception:
                continue
            finally:
                db_manager.release_connection(conn)

        # Push local categories to remote shards
        for cat_name, cat_data in local_cats.items():
            if cat_name not in remote_cats:
                for url in db_manager.SHARD_URLS:
                    conn = None
                    try:
                        conn = db_manager.get_connection_for_url(url)
                        c = conn.cursor()
                        is_sql = db_manager.is_sqlite_conn(conn)
                        cat_sql = 'INSERT OR IGNORE INTO categories (name, color, match_rules, budget_limit) VALUES (?, ?, ?, ?)' if is_sql else \
                                  'INSERT INTO categories (name, color, match_rules, budget_limit) VALUES (%s, %s, %s, %s) ON CONFLICT (name) DO NOTHING'
                        c.execute(cat_sql, (cat_name, cat_data['color'], cat_data['match_rules'], cat_data['budget_limit']))
                        conn.commit()
                    except Exception:
                        pass
                    finally:
                        db_manager.release_connection(conn)

        # Pull remote categories to local
        for cat_name, cat_data in remote_cats.items():
            if cat_name not in local_cats:
                local_c.execute(
                    'INSERT OR IGNORE INTO categories (name, color, match_rules, budget_limit) VALUES (?, ?, ?, ?)',
                    (cat_name, cat_data['color'], cat_data['match_rules'], cat_data['budget_limit'])
                )
        local_conn.commit()

        # ---------------- 3. Query Local Transactions & Build Local Merkle Tree ----------------
        local_c.execute('SELECT id, date, description, amount, category_name, account_name, notes, receipt_path FROM transactions')
        local_rows = local_c.fetchall()

        local_tx_map = {}
        local_merkle_records = []
        for r in local_rows:
            key = _build_tx_identity_key(r[1], r[2], r[3], r[5])
            if key not in local_tx_map:
                d_norm = _normalize_date_str(r[1])
                acct_str = r[5] or 'Main Account'
                notes_str = r[6] or ''
                receipt_str = r[7] or ''
                local_tx_map[key] = {
                    'id': r[0],
                    'date': d_norm,
                    'description': r[2],
                    'amount': float(r[3]),
                    'category_name': r[4],
                    'account_name': acct_str,
                    'notes': notes_str,
                    'receipt_path': receipt_str,
                    'bucket': _bucket_key_for_tx(d_norm, acct_str),
                }
                local_merkle_records.append((key[0], key[1], key[2], key[3], notes_str, receipt_str))

        local_tree = MerkleTree.from_records(local_merkle_records)

        # ---------------- 4. Query Remote Transactions & Build Remote Merkle Tree ----------------
        remote_tx_map = {}
        remote_merkle_records = []
        for url in db_manager.SHARD_URLS:
            conn = None
            try:
                conn = db_manager.get_connection_for_url(url)
                c = conn.cursor()
                c.execute('SELECT id, date, description, amount, category_name, account_name, notes, receipt_path FROM transactions')
                for r in c.fetchall():
                    key = _build_tx_identity_key(r[1], r[2], r[3], r[5])
                    if key not in remote_tx_map:
                        d_norm = _normalize_date_str(r[1])
                        acct_str = r[5] or 'Main Account'
                        notes_str = r[6] or ''
                        receipt_str = r[7] or ''
                        remote_tx_map[key] = {
                            'id': r[0],
                            'shard_url': url,
                            'date': d_norm,
                            'description': r[2],
                            'amount': float(r[3]),
                            'category_name': r[4],
                            'account_name': acct_str,
                            'notes': notes_str,
                            'receipt_path': receipt_str,
                            'bucket': _bucket_key_for_tx(d_norm, acct_str),
                        }
                        remote_merkle_records.append((key[0], key[1], key[2], key[3], notes_str, receipt_str))
            except Exception as e:
                logger.warning(f"Could not read from shard {url} during reconciliation: {e}")
            finally:
                db_manager.release_connection(conn)

        remote_tree = MerkleTree.from_records(remote_merkle_records)

        # ---------------- 5. Merkle Tree Anti-Entropy Diff ----------------
        divergent_buckets = local_tree.diff_buckets(remote_tree)

        if not divergent_buckets:
            # O(1) Merkle Root Match: Zero divergent buckets!
            return {
                "status": "success",
                "message": "Merkle Tree root hashes match! Stores are already 100% converged.",
                "pushed_to_remote": 0,
                "pulled_to_local": 0,
                "conflicts_resolved": 0,
                "divergent_buckets_synced": 0,
                "merkle_root_hash": local_tree.root_hash,
                "total_unified_transactions": len(remote_tx_map),
                "synced": True,
                "timestamp": datetime.now().isoformat()
            }

        # ---------------- 6. Forward Replay on Divergent Buckets: Push Local -> Remote ----------------
        for key, local_tx in local_tx_map.items():
            if local_tx['bucket'] not in divergent_buckets:
                continue

            if key not in remote_tx_map:
                target_url = db_manager.shard_ring.get_node(local_tx['account_name'])
                conn = None
                try:
                    conn = db_manager.get_connection_for_url(target_url)
                    c = conn.cursor()
                    insert_sql = '''INSERT INTO transactions 
                           (date, description, amount, category_name, account_name, notes, receipt_path) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s)'''
                    db_manager.execute_adapted_query(
                        c, insert_sql,
                        (local_tx['date'], local_tx['description'], local_tx['amount'],
                         local_tx['category_name'], local_tx['account_name'], local_tx['notes'], local_tx['receipt_path'])
                    )
                    conn.commit()
                    pushed_to_remote += 1
                except Exception as e:
                    logger.error(f"Failed to push local tx {key} to shard {target_url}: {e}")
                finally:
                    db_manager.release_connection(conn)
            else:
                remote_tx = remote_tx_map[key]
                needs_remote_update = False
                new_notes = remote_tx['notes']
                new_receipt = remote_tx['receipt_path']

                if local_tx['notes'] and not remote_tx['notes']:
                    new_notes = local_tx['notes']
                    needs_remote_update = True
                if local_tx['receipt_path'] and not remote_tx['receipt_path']:
                    new_receipt = local_tx['receipt_path']
                    needs_remote_update = True

                if needs_remote_update:
                    conn = None
                    try:
                        conn = db_manager.get_connection_for_url(remote_tx['shard_url'])
                        c = conn.cursor()
                        update_sql = 'UPDATE transactions SET notes=%s, receipt_path=%s WHERE id=%s'
                        db_manager.execute_adapted_query(c, update_sql, (new_notes, new_receipt, remote_tx['id']))
                        conn.commit()
                        conflicts_resolved += 1
                    except Exception as e:
                        logger.error(f"Failed updating remote transaction during conflict resolution: {e}")
                    finally:
                        db_manager.release_connection(conn)

        # ---------------- 7. Catch-up Replication on Divergent Buckets: Pull Remote -> Local ----------------
        for key, remote_tx in remote_tx_map.items():
            if remote_tx['bucket'] not in divergent_buckets:
                continue

            if key not in local_tx_map:
                local_c.execute(
                    '''INSERT INTO transactions 
                       (date, description, amount, category_name, account_name, notes, receipt_path) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (remote_tx['date'], remote_tx['description'], remote_tx['amount'],
                     remote_tx['category_name'], remote_tx['account_name'], remote_tx['notes'], remote_tx['receipt_path'])
                )
                pulled_to_local += 1
            else:
                local_tx = local_tx_map[key]
                needs_local_update = False
                new_notes = local_tx['notes']
                new_receipt = local_tx['receipt_path']

                if remote_tx['notes'] and not local_tx['notes']:
                    new_notes = remote_tx['notes']
                    needs_local_update = True
                if remote_tx['receipt_path'] and not local_tx['receipt_path']:
                    new_receipt = remote_tx['receipt_path']
                    needs_local_update = True

                if needs_local_update:
                    local_c.execute(
                        'UPDATE transactions SET notes=?, receipt_path=? WHERE id=?',
                        (new_notes, new_receipt, local_tx['id'])
                    )
                    conflicts_resolved += 1

        local_conn.commit()

    finally:
        local_conn.close()

    total_unified = len(remote_tx_map) + pushed_to_remote

    logger.info(
        f"Merkle Reconciliation completed: "
        f"pushed={pushed_to_remote}, pulled={pulled_to_local}, "
        f"conflicts_resolved={conflicts_resolved}, divergent_buckets={len(divergent_buckets)}, total_unified={total_unified}"
    )

    return {
        "status": "success",
        "message": "Bidirectional Merkle Tree reconciliation converged local and remote datasets.",
        "pushed_to_remote": pushed_to_remote,
        "pulled_to_local": pulled_to_local,
        "conflicts_resolved": conflicts_resolved,
        "divergent_buckets_synced": len(divergent_buckets),
        "merkle_root_hash": local_tree.root_hash,
        "total_unified_transactions": total_unified,
        "synced": True,
        "timestamp": datetime.now().isoformat()
    }
