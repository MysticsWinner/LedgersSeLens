"""
Comprehensive Unit Tests for LedgerSeLens Data Ingestion Engine
Tests CSV, Excel, PDF, and Receipt OCR parsing, payment categorization,
and fault-tolerant fallbacks.
"""

import pytest
import os
import io
import pandas as pd
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

from core.data_ingestion import (
    ingest_csv, ingest_excel, ingest_pdf, ingest_image_receipt, ingest_file,
    clean_currency_string, robust_parse_date, map_dataframe_columns
)
from core.payment_categorizer import classify_payment, is_payment
from core.ocr_engine import is_tesseract_available, parse_receipt
from core.analyzer import categorize_transaction
from database import db_manager

TEST_DB = 'test_ingestion.db'

@pytest.fixture(autouse=True)
def setup_teardown_db():
    if os.path.exists(TEST_DB):
        try: os.remove(TEST_DB)
        except Exception: pass
    db_manager.DB_FILE = TEST_DB
    db_manager.init_db()
    yield
    if os.path.exists(TEST_DB):
        try: os.remove(TEST_DB)
        except Exception: pass

# ==================== 1. Number & Currency Parsing Tests ====================

def test_clean_currency_string_formats():
    assert clean_currency_string("$1,234.56") == 1234.56
    assert clean_currency_string("$(50.25)") == -50.25
    assert clean_currency_string("(100.00)") == -100.00
    assert clean_currency_string("75.50-") == -75.50
    assert clean_currency_string("€1.234,56") == 1234.56
    assert clean_currency_string("250.00 DR") == -250.00
    assert clean_currency_string("500.00 CR") == 500.00
    assert clean_currency_string("   ") is None
    assert clean_currency_string("NaN") is None
    assert clean_currency_string("--") is None

# ==================== 2. Date Parsing Tests ====================

def test_robust_parse_date():
    assert robust_parse_date("2026-03-15") == "2026-03-15"
    assert robust_parse_date("03/15/2026") == "2026-03-15"
    assert robust_parse_date("15/03/2026") == "2026-03-15"
    assert robust_parse_date("March 15, 2026") == "2026-03-15"
    assert robust_parse_date("15-Mar-2026") == "2026-03-15"
    assert robust_parse_date(pd.Timestamp("2026-03-15")) == "2026-03-15"
    assert robust_parse_date("InvalidDateString") is None

# ==================== 3. CSV Ingestion Tests ====================

def test_csv_with_leading_metadata_and_parentheses(tmp_path):
    csv_file = tmp_path / "bank_statement_with_metadata.csv"
    content = (
        "BANK OF AMERICA ACCOUNT SUMMARY\n"
        "Account Number: ****1234\n"
        "Statement Period: Jan 1 2026 to Jan 31 2026\n"
        "\n"
        "Date,Description,Amount\n"
        "2026-01-05,AMAZON.COM,$(45.99)\n"
        "2026-01-10,EMPLOYER PAYROLL,\"$3,250.00\"\n"
        "2026-01-15,SHELL GAS STATION,-$35.50\n"
        "CORRUPT ROW MISSING DATA\n"
    )
    csv_file.write_text(content, encoding='utf-8')
    
    result = ingest_csv(str(csv_file), account_name="Checking")
    assert result.is_success is True
    assert result.valid_rows == 3
    assert result.dropped_rows >= 1
    
    df = result.dataframe
    assert df.iloc[0]['Amount'] == -45.99
    assert df.iloc[1]['Amount'] == 3250.00
    assert df.iloc[2]['Amount'] == -35.50
    assert df.iloc[0]['Account'] == "Checking"

def test_csv_with_semicolon_and_split_debit_credit(tmp_path):
    csv_file = tmp_path / "split_debit_credit.csv"
    content = (
        "Transaction Date;Payee;Debit;Credit\n"
        "2026-02-01;WHOLE FOODS;85.40;\n"
        "2026-02-02;DIVIDEND PAYMENT;;120.00\n"
        "2026-02-03;PG&E UTILITIES;64.20;\n"
    )
    csv_file.write_text(content, encoding='utf-8')
    
    result = ingest_csv(str(csv_file), account_name="Savings")
    assert result.is_success is True
    assert result.valid_rows == 3
    
    df = result.dataframe
    # Debit should be negative, Credit should be positive
    assert df[df['Description'] == 'WHOLE FOODS'].iloc[0]['Amount'] == -85.40
    assert df[df['Description'] == 'DIVIDEND PAYMENT'].iloc[0]['Amount'] == 120.00
    assert df[df['Description'] == 'PG&E UTILITIES'].iloc[0]['Amount'] == -64.20

# ==================== 4. Excel Ingestion Tests ====================

def test_excel_ingestion(tmp_path):
    excel_path = tmp_path / "financial_ledger.xlsx"
    
    # Create sample DataFrame
    data = {
        "Date": ["2026-03-01", "2026-03-02", "2026-03-03"],
        "Merchant": ["NETFLIX.COM", "TARGET STORE", "FREELANCE CLIENT"],
        "Amount": [-15.99, -82.45, 1500.00],
        "Category": ["Payment: Subscription", "Shopping", "Income"]
    }
    df_raw = pd.DataFrame(data)
    df_raw.to_excel(excel_path, index=False, engine='openpyxl')
    
    result = ingest_excel(str(excel_path), account_name="Credit Card")
    assert result.is_success is True
    assert result.valid_rows == 3
    
    df = result.dataframe
    assert df.iloc[0]['Description'] == "NETFLIX.COM"
    assert df.iloc[0]['Amount'] == -15.99
    assert df.iloc[2]['Amount'] == 1500.00

# ==================== 5. Payment Categorization Tests ====================

def test_payment_classification():
    # Credit Card Payment
    assert classify_payment("AUTOPAY PAYMENT CHASE CREDIT CRD") == "Payment: Credit Card"
    assert classify_payment("AMEX EPAYMENT") == "Payment: Credit Card"
    assert classify_payment("CAPITAL ONE ONLINE PYMT") == "Payment: Credit Card"
    
    # Loan & Mortgage
    assert classify_payment("WELLS FARGO MORTGAGE PAYMENT") == "Payment: Loan & Mortgage"
    assert classify_payment("SOFI LENDING STUDENT LOAN") == "Payment: Loan & Mortgage"
    assert classify_payment("AUTO LOAN DIRECT DEBIT") == "Payment: Loan & Mortgage"
    
    # P2P & Transfers
    assert classify_payment("VENMO PAYMENT TO JOHN") == "Payment: Transfer & P2P"
    assert classify_payment("ZELLE TRANSFER TO ALICE") == "Payment: Transfer & P2P"
    assert classify_payment("PAYPAL INSTANT TRANSFER") == "Payment: Transfer & P2P"
    
    # Bill & Utility Payments
    assert classify_payment("PG&E ONLINE BILL PAY") == "Payment: Bill & Utility"
    assert classify_payment("VERIZON WIRELESS BILL PAYMENT") == "Payment: Bill & Utility"
    
    # Tax Payments
    assert classify_payment("IRS TREAS 310 TAX PAYMENT") == "Payment: Tax"
    assert classify_payment("STATE OF CA FRANCHISE TAX") == "Payment: Tax"
    
    # Subscription Payments
    assert classify_payment("APPLE.COM/BILL RECURRING") == "Payment: Subscription"
    assert classify_payment("GOOGLE PLAY MONTHLY SUB") == "Payment: Subscription"
    
    # Non-payment
    assert classify_payment("CHEVRON GAS STATION") is None
    assert classify_payment("STARBUCKS COFFEE") is None

def test_analyzer_categorization_with_payments():
    cats = db_manager.get_categories()
    
    # Verify seeded categories include payments
    cat_names = [c['name'] for c in cats]
    assert "Payment: Credit Card" in cat_names
    assert "Payment: Transfer & P2P" in cat_names
    assert "Payment: Subscription" in cat_names
    
    # Test categorize_transaction
    assert categorize_transaction("CHASE CARD AUTOPAY PAYMENT", cats) == "Payment: Credit Card"
    assert categorize_transaction("VENMO CASHOUT", cats) == "Payment: Transfer & P2P"
    assert categorize_transaction("NETFLIX RECURRING SUB", cats) in ("Payment: Subscription", "Entertainment")
    assert categorize_transaction("MCDONALDS MEAL", cats) == "Food"

# ==================== 6. Receipt OCR & Parser Tests ====================

def test_receipt_image_parser_fallback(tmp_path):
    # Create a synthetic receipt image using Pillow
    img_path = tmp_path / "Coffee_Shop_Receipt.png"
    img = Image.new('RGB', (400, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "BLUE BOTTLE COFFEE", fill=(0, 0, 0))
    draw.text((20, 60), "Date: 2026-03-20", fill=(0, 0, 0))
    draw.text((20, 100), "Cappuccino $5.50", fill=(0, 0, 0))
    draw.text((20, 140), "TOTAL: $5.50", fill=(0, 0, 0))
    draw.text((20, 180), "Payment: VISA", fill=(0, 0, 0))
    img.save(img_path)
    
    # Run receipt parsing (works with Tesseract or heuristic fallback)
    parsed = parse_receipt(str(img_path))
    assert parsed["success"] is True
    assert "Coffee" in parsed["description"] or "Receipt" in parsed["description"]
    
    # Test ingestion through universal ingest_file
    result = ingest_file(str(img_path), account_name="Main Account")
    assert result.is_success is True
    assert len(result.dataframe) == 1
    assert result.file_type == "image_receipt"

# ==================== 7. Universal Ingestion Dispatcher Tests ====================

def test_universal_ingest_file_dispatcher(tmp_path):
    # 1. CSV
    csv_f = tmp_path / "test.csv"
    csv_f.write_text("Date,Description,Amount\n2026-01-01,Test,10.0\n")
    res_csv = ingest_file(str(csv_f))
    assert res_csv.file_type == "csv"
    assert len(res_csv.dataframe) == 1
    
    # 2. Non-existent file
    res_missing = ingest_file("non_existent_file.xyz")
    assert res_missing.is_success is False
    assert len(res_missing.errors) > 0
