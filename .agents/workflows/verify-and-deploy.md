---
name: verify-and-deploy
description: Run full automated pytest suite, verify all LedgerSeLens CLI/API/Worker/Reconciliation workflows end-to-end, update the graphify knowledge graph, and execute the git commit/pull/push cycle.
---

# Workflow: Verify All Workflows & Git Cycle

1. **Run Automated Test Suite**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -v
   ```
2. **Verify End-to-End Application Workflows**:
   - Verify `status`, `plaid`, `mock-data`, `ingest`, `ocr`, `insights`, `transactions`, `subscriptions`, `sync`, `export` (`csv`, `excel`, `pdf`), and `cli.py` subcommands.
3. **Update Knowledge Graph**:
   ```powershell
   graphify update .
   ```
4. **Git Cycle (Stage, Commit, Pull/Rebase, Push)**:
   ```powershell
   git add -A
   git commit -m "<descriptive message>"
   git pull --rebase origin main
   git push origin main
   ```

