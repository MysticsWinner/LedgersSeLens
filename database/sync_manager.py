"""
LedgerSeLens Bidirectional Synchronization & Reconciliation Manager
Handles offline-first replication, forward replay, catch-up replication,
and eventual consistency across Local SQLite and Multi-Shard PostgreSQL.

Solves the 4-Phase Lifecycle:
  1. Primary online -> writes to shards
  2. Primary offline -> writes to local fallback store
  3. Isolated local execution -> continues accumulating local transactions
  4. Full recovery -> Bidirectionally reconciles all historical and new data
     without duplication, resolving any field conflicts.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime

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

def reconcile_and_sync() -> Dict[str, Any]:
    """
    Performs full bidirectional data reconciliation between local SQLite
    and all distributed PostgreSQL shards.
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
            "total_unified_transactions": len(db_manager.get_all_transactions()),
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
            try:
                conn = db_manager.get_connection_for_url(url)
                c = conn.cursor()
                c.execute('SELECT name, color, match_rules, budget_limit FROM categories')
                for r in c.fetchall():
                    if r[0] not in remote_cats:
                        remote_cats[r[0]] = {'color': r[1], 'match_rules': r[2], 'budget_limit': r[3]}
                conn.close()
            except Exception:
                continue

        # Push local categories to remote shards
        for cat_name, cat_data in local_cats.items():
            if cat_name not in remote_cats:
                for url in db_manager.SHARD_URLS:
                    try:
                        conn = db_manager.get_connection_for_url(url)
                        c = conn.cursor()
                        is_sql = db_manager.is_sqlite_conn(conn)
                        cat_sql = 'INSERT OR IGNORE INTO categories (name, color, match_rules, budget_limit) VALUES (?, ?, ?, ?)' if is_sql else \
                                  'INSERT INTO categories (name, color, match_rules, budget_limit) VALUES (%s, %s, %s, %s) ON CONFLICT (name) DO NOTHING'
                        c.execute(cat_sql, (cat_name, cat_data['color'], cat_data['match_rules'], cat_data['budget_limit']))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass

        # Pull remote categories to local
        for cat_name, cat_data in remote_cats.items():
            if cat_name not in local_cats:
                local_c.execute(
                    'INSERT OR IGNORE INTO categories (name, color, match_rules, budget_limit) VALUES (?, ?, ?, ?)',
                    (cat_name, cat_data['color'], cat_data['match_rules'], cat_data['budget_limit'])
                )
        local_conn.commit()

        # ---------------- 3. Query Local Transactions ----------------
        local_c.execute('SELECT id, date, description, amount, category_name, account_name, notes, receipt_path FROM transactions')
        local_rows = local_c.fetchall()
        
        local_tx_map = {}
        for r in local_rows:
            key = _build_tx_identity_key(r[1], r[2], r[3], r[5])
            local_tx_map[key] = {
                'id': r[0],
                'date': _normalize_date_str(r[1]),
                'description': r[2],
                'amount': float(r[3]),
                'category_name': r[4],
                'account_name': r[5] or 'Main Account',
                'notes': r[6] or '',
                'receipt_path': r[7] or ''
            }

        # ---------------- 4. Query Remote Transactions (Map-Reduce across Shards) ----------------
        remote_tx_map = {}
        for url in db_manager.SHARD_URLS:
            try:
                conn = db_manager.get_connection_for_url(url)
                c = conn.cursor()
                c.execute('SELECT id, date, description, amount, category_name, account_name, notes, receipt_path FROM transactions')
                for r in c.fetchall():
                    key = _build_tx_identity_key(r[1], r[2], r[3], r[5])
                    remote_tx_map[key] = {
                        'id': r[0],
                        'shard_url': url,
                        'date': _normalize_date_str(r[1]),
                        'description': r[2],
                        'amount': float(r[3]),
                        'category_name': r[4],
                        'account_name': r[5] or 'Main Account',
                        'notes': r[6] or '',
                        'receipt_path': r[7] or ''
                    }
                conn.close()
            except Exception as e:
                logger.warning(f"Could not read from shard {url} during reconciliation: {e}")

        # ---------------- 5. Forward Replay: Push Local -> Remote ----------------
        for key, local_tx in local_tx_map.items():
            if key not in remote_tx_map:
                # Local transaction missing on remote -> Route to target shard
                target_url = db_manager.shard_ring.get_node(local_tx['account_name'])
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
                    conn.close()
                    pushed_to_remote += 1
                except Exception as e:
                    logger.error(f"Failed to push local tx {key} to shard {target_url}: {e}")
            else:
                # Exists on both sides -> Check for field updates / conflict resolution
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
                    try:
                        conn = db_manager.get_connection_for_url(remote_tx['shard_url'])
                        c = conn.cursor()
                        update_sql = 'UPDATE transactions SET notes=%s, receipt_path=%s WHERE id=%s'
                        db_manager.execute_adapted_query(c, update_sql, (new_notes, new_receipt, remote_tx['id']))
                        conn.commit()
                        conn.close()
                        conflicts_resolved += 1
                    except Exception as e:
                        logger.error(f"Failed updating remote transaction during conflict resolution: {e}")

        # ---------------- 6. Catch-up Replication: Pull Remote -> Local ----------------
        for key, remote_tx in remote_tx_map.items():
            if key not in local_tx_map:
                # Remote transaction missing locally -> Insert into local SQLite
                local_c.execute(
                    '''INSERT INTO transactions 
                       (date, description, amount, category_name, account_name, notes, receipt_path) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (remote_tx['date'], remote_tx['description'], remote_tx['amount'], 
                     remote_tx['category_name'], remote_tx['account_name'], remote_tx['notes'], remote_tx['receipt_path'])
                )
                pulled_to_local += 1
            else:
                # If remote has notes/receipt and local does not, propagate to local
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
        f"Reconciliation completed successfully: "
        f"pushed={pushed_to_remote}, pulled={pulled_to_local}, "
        f"conflicts_resolved={conflicts_resolved}, total_unified={total_unified}"
    )

    return {
        "status": "success",
        "message": "Bidirectional reconciliation converged local and remote datasets.",
        "pushed_to_remote": pushed_to_remote,
        "pulled_to_local": pulled_to_local,
        "conflicts_resolved": conflicts_resolved,
        "total_unified_transactions": total_unified,
        "synced": True,
        "timestamp": datetime.now().isoformat()
    }
