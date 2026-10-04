"""
LedgerSeLens Data Ingestion Engine
Provides bulletproof, fault-tolerant ingestion for Bank Statements,
Ledgers, and Receipts across PDF, Excel (.xlsx, .xls), CSV (.csv, .tsv),
and Receipt Images (.png, .jpg, .jpeg) with multi-tier parsing fallbacks.
"""

import os
import io
import re
import csv
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
import pandas as pd
from datetime import datetime
from dateutil import parser as date_parser

from core.payment_categorizer import classify_payment, ALL_DEFAULT_CATEGORIES
from core.ocr_engine import parse_receipt, extract_text_from_pdf_pages_ocr, is_tesseract_available

logger = logging.getLogger(__name__)

# Column synonym mappings (normalized to lower case, stripped of punctuation)
SYNONYMS_DATE = {'date', 'trans date', 'transaction date', 'post date', 'posting date', 'value date', 'time', 'day', 'txn date', 'trx date'}
SYNONYMS_DESC = {'description', 'desc', 'payee', 'merchant', 'details', 'particulars', 'narration', 'memo', 'name', 'transaction details', 'item', 'vendor'}
SYNONYMS_AMOUNT = {'amount', 'total', 'net', 'transaction amount', 'sum', 'amt', 'value'}
SYNONYMS_DEBIT = {'debit', 'withdrawal', 'outflow', 'dr', 'expense', 'paid out', 'charge', 'debit amount'}
SYNONYMS_CREDIT = {'credit', 'deposit', 'inflow', 'cr', 'income', 'paid in', 'credit amount'}
SYNONYMS_CATEGORY = {'category', 'cat', 'tag', 'type', 'classification'}
SYNONYMS_NOTES = {'notes', 'note', 'comment', 'memo', 'reference', 'ref', 'check number', 'check no'}
SYNONYMS_ACCOUNT = {'account', 'account name', 'account number', 'acct'}

@dataclass
class IngestionResult:
    dataframe: pd.DataFrame
    total_rows: int = 0
    valid_rows: int = 0
    dropped_rows: int = 0
    file_type: str = "unknown"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    is_success: bool = True

def clean_currency_string(val: Any) -> Optional[float]:
    """
    Sanitizes arbitrary numeric and currency strings into standard float values.
    Handles:
      - '$1,234.56' -> 1234.56
      - '$(12.50)' or '(12.50)' -> -12.50
      - '12.50-' -> -12.50
      - '12.50 DR' -> -12.50
      - '12.50 CR' -> 12.50
      - European '1.234,56' -> 1234.56
    """
    if val is None or pd.isna(val):
        return None
        
    if isinstance(val, (int, float)):
        return float(val)
        
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', 'null', '-', '--'):
        return None

    # Check for credit / debit suffixes
    is_dr = bool(re.search(r'\bdr\b', s, re.I))
    is_cr = bool(re.search(r'\bcr\b', s, re.I))
    
    # Check for accounting parentheses: (123.45) or $(123.45)
    is_paren_negative = ('(' in s and ')' in s)
        
    # Check for trailing negative: 123.45-
    is_trailing_negative = s.endswith('-')
    
    # Check for leading negative: -$123.45 or -123.45
    is_leading_negative = s.startswith('-') or '-$' in s or '-€' in s or '-£' in s

    # Strip symbols, keeping digits, dots, and commas
    cleaned = re.sub(r'[^0-9.,]', '', s)
    if not cleaned:
        return None

    # Handle European decimal style (e.g. 1.234,56 where ',' is decimal and '.' is thousand)
    if ',' in cleaned and '.' in cleaned:
        if cleaned.rfind(',') > cleaned.rfind('.'):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        comma_parts = cleaned.split(',')
        if len(comma_parts) == 2 and len(comma_parts[1]) == 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')

    try:
        amt = float(cleaned)
        if is_paren_negative or is_trailing_negative or is_leading_negative or is_dr:
            amt = -abs(amt)
        elif is_cr:
            amt = abs(amt)
        return amt
    except ValueError:
        return None

def robust_parse_date(val: Any) -> Optional[str]:
    """
    Attempts multiple parsing strategies to convert messy dates into ISO 'YYYY-MM-DD'.
    """
    if val is None or pd.isna(val):
        return None

    if isinstance(val, (datetime, pd.Timestamp)):
        return val.strftime('%Y-%m-%d')

    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', 'null'):
        return None

    # Fast path: common formats
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%Y.%m.%d', '%m/%d/%y', '%d/%m/%y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue

    # Dateutil fuzzy fallback
    try:
        dt = date_parser.parse(s, fuzzy=True)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return None

def normalize_column_name(col_name: str) -> str:
    """Strips punctuation and lowercases column name for fuzzy matching."""
    return re.sub(r'[^a-z0-9 ]', '', str(col_name).lower().strip())

def map_dataframe_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Identifies Date, Description, Amount (or Debit/Credit) columns
    from arbitrary vendor and bank layouts.
    """
    mapping = {}
    col_norm_map = {col: normalize_column_name(col) for col in df.columns}
    
    # Date detection
    for col, norm in col_norm_map.items():
        if norm in SYNONYMS_DATE or any(s in norm for s in ['date', 'time', 'posted']):
            mapping['Date'] = col
            break

    # Description detection
    for col, norm in col_norm_map.items():
        if col in mapping.values():
            continue
        if norm in SYNONYMS_DESC or any(s in norm for s in ['desc', 'payee', 'merchant', 'particulars', 'detail', 'memo']):
            mapping['Description'] = col
            break

    # Amount detection
    for col, norm in col_norm_map.items():
        if col in mapping.values():
            continue
        if norm in SYNONYMS_AMOUNT:
            mapping['Amount'] = col
            break

    # Debit / Credit split detection if single Amount wasn't found
    if 'Amount' not in mapping:
        for col, norm in col_norm_map.items():
            if norm in SYNONYMS_DEBIT or 'debit' in norm or 'withdrawal' in norm:
                mapping['Debit'] = col
                break
        for col, norm in col_norm_map.items():
            if norm in SYNONYMS_CREDIT or 'credit' in norm or 'deposit' in norm:
                mapping['Credit'] = col
                break

    # Optional columns
    for col, norm in col_norm_map.items():
        if col in mapping.values():
            continue
        if norm in SYNONYMS_CATEGORY:
            mapping['Category'] = col
        elif norm in SYNONYMS_NOTES:
            mapping['Notes'] = col
        elif norm in SYNONYMS_ACCOUNT:
            mapping['Account'] = col

    return df, mapping

def find_header_row_csv(lines: List[str], max_rows: int = 30) -> Tuple[int, str]:
    """
    Scans the beginning of a CSV/text file to find the actual table header line,
    skipping bank header metadata, account summaries, or empty lines.
    Returns (header_line_index, detected_delimiter).
    """
    delimiters = [',', ';', '\t', '|']
    best_row = 0
    best_score = -1
    best_delim = ','

    for idx, line in enumerate(lines[:max_rows]):
        line_clean = line.strip().lower()
        if not line_clean:
            continue
            
        for delim in delimiters:
            tokens = [normalize_column_name(t) for t in line_clean.split(delim)]
            score = 0
            has_date = any(t in SYNONYMS_DATE or 'date' in t for t in tokens)
            has_desc = any(t in SYNONYMS_DESC or 'desc' in t or 'payee' in t for t in tokens)
            has_amt = any(t in SYNONYMS_AMOUNT or 'amount' in t or t in SYNONYMS_DEBIT or t in SYNONYMS_CREDIT for t in tokens)
            
            if has_date: score += 3
            if has_desc: score += 3
            if has_amt: score += 3
            
            if score > best_score and score >= 6: # Matches at least 2 key columns
                best_score = score
                best_row = idx
                best_delim = delim

    if best_score < 6:
        # Fallback: Sniff first valid line
        best_row = 0
        best_delim = ','
        for line in lines:
            if line.strip():
                try:
                    dialect = csv.Sniffer().sniff(line)
                    best_delim = dialect.delimiter
                except Exception:
                    pass
                break

    return best_row, best_delim

def ingest_csv(file_path_or_bytes: Union[str, bytes], account_name: str = "Main Account") -> IngestionResult:
    """Robust parser for CSV/TSV statements with encoding & delimiter autodetection."""
    result = IngestionResult(dataframe=pd.DataFrame(), file_type="csv")
    
    # 1. Read raw content with encoding fallbacks
    content = None
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']
    raw_bytes = file_path_or_bytes if isinstance(file_path_or_bytes, bytes) else open(file_path_or_bytes, 'rb').read()
    
    for enc in encodings:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if not content:
        result.errors.append("Failed to decode file with standard encodings (utf-8, latin-1, cp1252).")
        result.is_success = False
        return result

    lines = content.splitlines()
    if not lines:
        result.warnings.append("File is empty.")
        return result

    header_idx, delimiter = find_header_row_csv(lines)
    header_content = "\n".join(lines[header_idx:])

    try:
        df_raw = pd.read_csv(io.StringIO(header_content), sep=delimiter, on_bad_lines='skip', engine='python')
    except Exception as e:
        # Fallback to standard comma separator
        try:
            df_raw = pd.read_csv(io.StringIO(header_content), on_bad_lines='skip')
        except Exception as e2:
            result.errors.append(f"CSV read error: {e2}")
            result.is_success = False
            return result

    return process_raw_dataframe(df_raw, account_name, result)

def ingest_excel(file_path_or_bytes: Union[str, bytes], account_name: str = "Main Account") -> IngestionResult:
    """Robust parser for Excel sheets (.xlsx, .xls, .xlsm)."""
    result = IngestionResult(dataframe=pd.DataFrame(), file_type="excel")
    
    try:
        # Read Excel workbook
        excel_file = pd.ExcelFile(file_path_or_bytes, engine='openpyxl')
        all_dfs = []
        
        for sheet_name in excel_file.sheet_names:
            df_sheet = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            if df_sheet.empty:
                continue
                
            # Scan top 25 rows for genuine header row
            header_row_idx = 0
            found_header = False
            for idx, row in df_sheet.head(25).iterrows():
                row_str_tokens = [normalize_column_name(val) for val in row.dropna()]
                has_date = any(t in SYNONYMS_DATE or 'date' in t for t in row_str_tokens)
                has_desc = any(t in SYNONYMS_DESC or 'desc' in t or 'payee' in t for t in row_str_tokens)
                has_amt = any(t in SYNONYMS_AMOUNT or 'amount' in t or t in SYNONYMS_DEBIT or t in SYNONYMS_CREDIT for t in row_str_tokens)
                if (has_date and has_desc) or (has_date and has_amt):
                    header_row_idx = idx
                    found_header = True
                    break

            if found_header:
                df_clean = pd.read_excel(excel_file, sheet_name=sheet_name, skiprows=header_row_idx)
            else:
                df_clean = pd.read_excel(excel_file, sheet_name=sheet_name)
                
            if not df_clean.empty:
                all_dfs.append(df_clean)

        if not all_dfs:
            result.warnings.append("No readable data sheets found in Excel file.")
            return result

        combined_df = pd.concat(all_dfs, ignore_index=True)
        return process_raw_dataframe(combined_df, account_name, result)
        
    except Exception as e:
        result.errors.append(f"Excel parsing failed: {e}")
        result.is_success = False
        return result

def ingest_pdf(file_path: str, account_name: str = "Main Account") -> IngestionResult:
    """
    Multi-tier parser for PDF bank statements:
      1. pdfplumber structured table extraction
      2. pdfplumber text line regex extraction
      3. OCR rasterization fallback for scanned statements
    """
    result = IngestionResult(dataframe=pd.DataFrame(), file_type="pdf")
    extracted_rows: List[Dict[str, Any]] = []

    try:
        import pdfplumber
        has_digital_text = False

        with pdfplumber.open(file_path) as pdf:
            # Tier 1: Structured Table Extraction
            for page_idx, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        if not table or len(table) < 2:
                            continue
                        
                        has_digital_text = True
                        # Map table headers
                        headers = [str(col).strip() if col else f"col_{c}" for c, col in enumerate(table[0])]
                        for row in table[1:]:
                            if len(row) < 3:
                                continue
                            extracted_rows.append(dict(zip(headers, row)))

                # Tier 2: Text Layout Extraction if tables were sparse
                if not extracted_rows:
                    text = page.extract_text()
                    if text and text.strip():
                        has_digital_text = True
                        for line in text.splitlines():
                            # Pattern: Date Description Amount [Balance]
                            match = re.search(r'(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(.*?)\s+([$-]?\(?\d{1,3}(?:,\d{3})*\.\d{2}\)?-?)', line)
                            if match:
                                d_str, desc_str, amt_str = match.groups()
                                extracted_rows.append({
                                    'Date': d_str,
                                    'Description': desc_str.strip(),
                                    'Amount': amt_str
                                })

        # Tier 3: OCR Fallback if no digital text or tables were found
        if not extracted_rows and not has_digital_text:
            logger.info("PDF has no digital text layer. Engaging OCR rasterization pipeline.")
            result.warnings.append("No digital text found; engaged OCR rasterization engine.")
            ocr_pages = extract_text_from_pdf_pages_ocr(file_path)
            for page_text in ocr_pages:
                for line in page_text.splitlines():
                    match = re.search(r'(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(.*?)\s+([$-]?\(?\d{1,3}(?:,\d{3})*\.\d{2}\)?-?)', line)
                    if match:
                        d_str, desc_str, amt_str = match.groups()
                        extracted_rows.append({
                            'Date': d_str,
                            'Description': desc_str.strip(),
                            'Amount': amt_str
                        })

    except Exception as e:
        result.errors.append(f"PDF parsing error: {e}")
        result.is_success = False
        return result

    if not extracted_rows:
        result.warnings.append("Could not extract any transaction rows from PDF.")
        return result

    df_raw = pd.DataFrame(extracted_rows)
    return process_raw_dataframe(df_raw, account_name, result)

def ingest_image_receipt(file_path: str, account_name: str = "Main Account") -> IngestionResult:
    """Parses a photo or scan of a receipt into a standard transaction row."""
    result = IngestionResult(dataframe=pd.DataFrame(), file_type="image_receipt")
    
    try:
        parsed = parse_receipt(file_path)
        row = {
            'Date': parsed['date'],
            'Description': parsed['description'],
            'Amount': parsed['amount'],
            'Category': parsed['category'],
            'Account': account_name,
            'Notes': parsed.get('notes', ''),
            'Receipt': file_path
        }
        df = pd.DataFrame([row])
        df['Date'] = pd.to_datetime(df['Date'])
        result.dataframe = df
        result.total_rows = 1
        result.valid_rows = 1
        result.is_success = True
        return result
    except Exception as e:
        result.errors.append(f"Image receipt processing failed: {e}")
        result.is_success = False
        return result

def process_raw_dataframe(df_raw: pd.DataFrame, account_name: str, result: IngestionResult) -> IngestionResult:
    """
    Standardizes raw parsed DataFrames into the canonical schema:
    ['Date', 'Description', 'Amount', 'Category', 'Account', 'Notes', 'Receipt']
    """
    result.total_rows = len(df_raw)
    if df_raw.empty:
        result.dataframe = pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Account', 'Notes', 'Receipt'])
        return result

    df, mapping = map_dataframe_columns(df_raw)

    if 'Date' not in mapping or ('Amount' not in mapping and 'Debit' not in mapping):
        result.errors.append(f"Could not map required columns. Detected mapping: {mapping}")
        result.is_success = False
        return result

    rows = []
    dropped_count = 0

    for _, row in df.iterrows():
        # Parse Date
        date_val = robust_parse_date(row.get(mapping.get('Date')))
        if not date_val:
            dropped_count += 1
            continue

        # Parse Description
        desc_col = mapping.get('Description')
        desc_val = str(row.get(desc_col)).strip() if desc_col and pd.notna(row.get(desc_col)) else "Unlabeled Transaction"
        if not desc_val or desc_val.lower() in ('nan', 'none'):
            desc_val = "Unlabeled Transaction"

        # Parse Amount
        amount_val = None
        if 'Amount' in mapping:
            amount_val = clean_currency_string(row.get(mapping['Amount']))
        elif 'Debit' in mapping or 'Credit' in mapping:
            debit_val = clean_currency_string(row.get(mapping.get('Debit')))
            credit_val = clean_currency_string(row.get(mapping.get('Credit')))
            
            if debit_val is not None and debit_val != 0:
                amount_val = -abs(debit_val)
            elif credit_val is not None:
                amount_val = abs(credit_val)

        if amount_val is None:
            dropped_count += 1
            continue

        # Category detection
        category_val = None
        if 'Category' in mapping and pd.notna(row.get(mapping['Category'])):
            cat_candidate = str(row.get(mapping['Category'])).strip()
            if cat_candidate and cat_candidate.lower() not in ('nan', 'none', 'other', 'uncategorized'):
                category_val = cat_candidate

        # Notes and Account
        notes_val = str(row.get(mapping.get('Notes', ''))).strip() if mapping.get('Notes') and pd.notna(row.get(mapping.get('Notes'))) else ""
        if notes_val.lower() in ('nan', 'none'): notes_val = ""

        acct_val = str(row.get(mapping.get('Account', ''))).strip() if mapping.get('Account') and pd.notna(row.get(mapping.get('Account'))) else account_name
        if not acct_val or acct_val.lower() in ('nan', 'none'): acct_val = account_name

        rows.append({
            'Date': date_val,
            'Description': desc_val,
            'Amount': amount_val,
            'Category': category_val, # May be None, will be categorized downstream
            'Account': acct_val,
            'Notes': notes_val,
            'Receipt': ''
        })

    result.dropped_rows = dropped_count
    result.valid_rows = len(rows)

    if not rows:
        result.dataframe = pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Account', 'Notes', 'Receipt'])
        result.warnings.append("All rows in file were header/corrupt or missing valid date/amount.")
        return result

    clean_df = pd.DataFrame(rows)
    clean_df['Date'] = pd.to_datetime(clean_df['Date'])
    result.dataframe = clean_df
    return result

def ingest_file(file_path: str, account_name: str = "Main Account") -> IngestionResult:
    """
    Unified entry point for data ingestion across all supported file types:
    CSV, TSV, XLSX, XLS, PDF, PNG, JPG, JPEG, etc.
    """
    if not os.path.exists(file_path):
        res = IngestionResult(dataframe=pd.DataFrame(), is_success=False)
        res.errors.append(f"File not found: {file_path}")
        return res

    ext = os.path.splitext(file_path)[1].lower()

    if ext in ('.csv', '.tsv', '.txt'):
        return ingest_csv(file_path, account_name)
    elif ext in ('.xlsx', '.xls', '.xlsm'):
        return ingest_excel(file_path, account_name)
    elif ext == '.pdf':
        return ingest_pdf(file_path, account_name)
    elif ext in ('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp'):
        return ingest_image_receipt(file_path, account_name)
    else:
        # Fallback: attempt CSV sniff
        logger.info(f"Unrecognized extension {ext}, attempting CSV parser fallback.")
        return ingest_csv(file_path, account_name)
