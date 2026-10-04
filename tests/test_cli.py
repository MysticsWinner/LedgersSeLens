import pytest
import subprocess
import os
import sys

def test_cli_insights_command():
    # Ensure cli.py runs gracefully and generates output without segfaulting
    result = subprocess.run([sys.executable, 'cli.py', 'insights'], capture_output=True, text=True)
    assert result.returncode == 0, f"CLI command failed with {result.stderr}"
    
    # Verify standard output format handles empty/non-empty cases beautifully
    assert "LEDGERLENS INSIGHTS" in result.stdout or "No transactions found" in result.stdout

def test_cli_transactions_command():
    # Test the Transactions sub-command with a limit argument
    result = subprocess.run([sys.executable, 'cli.py', 'transactions', '--limit', '2'], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Showing the latest" in result.stdout or "No transactions found" in result.stdout

def test_main_help_and_subcommands():
    # Verify main.py help output lists available commands
    res_help = subprocess.run([sys.executable, 'main.py', '--help'], capture_output=True, text=True)
    assert res_help.returncode == 0
    assert "Available Commands" in res_help.stdout
    assert "sync" in res_help.stdout
    assert "status" in res_help.stdout

def test_main_status_and_sync_commands():
    # Verify main.py status executes cleanly
    res_status = subprocess.run([sys.executable, 'main.py', 'status'], capture_output=True, text=True)
    assert res_status.returncode == 0
    assert "LEDGERSELENS SYSTEM STATUS" in res_status.stdout

    # Verify main.py sync runs reconciliation cleanly
    res_sync = subprocess.run([sys.executable, 'main.py', 'sync'], capture_output=True, text=True)
    assert res_sync.returncode == 0
    assert "DATA RECONCILIATION SUMMARY" in res_sync.stdout
