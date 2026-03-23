import pytest
import subprocess
import os

def test_cli_insights_command():
    # Ensure cli.py runs gracefully and generates output without segfaulting
    result = subprocess.run(['python', 'cli.py', 'insights'], capture_output=True, text=True)
    assert result.returncode == 0, f"CLI command failed with {result.stderr}"
    
    # Verify standard output format handles empty/non-empty cases beautifully
    assert "LEDGERLENS INSIGHTS" in result.stdout or "No transactions found" in result.stdout

def test_cli_transactions_command():
    # Test the Transactions sub-command with a limit argument
    result = subprocess.run(['python', 'cli.py', 'transactions', '--limit', '2'], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Showing the latest" in result.stdout or "No transactions found" in result.stdout
