"""
LedgerSeLens Optical Character Recognition (OCR) Engine
Extracts transaction details from receipt images (PNG, JPG, TIFF, etc.)
and scanned PDF statements, with robust Tesseract path auto-detection
and heuristic fallback parsing.
"""

import os
import re
import shutil
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# Known standard Tesseract locations on Windows and Linux
CANDIDATE_TESSERACT_PATHS = [
    os.environ.get("TESSERACT_CMD", ""),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    "/opt/homebrew/bin/tesseract",
]

_TESSERACT_INITIALIZED = False
_TESSERACT_AVAILABLE = False

def init_tesseract() -> bool:
    """Auto-detects and binds the Tesseract OCR executable."""
    global _TESSERACT_INITIALIZED, _TESSERACT_AVAILABLE
    if _TESSERACT_INITIALIZED:
        return _TESSERACT_AVAILABLE

    try:
        import pytesseract
        
        # 1. Check if 'tesseract' is already in PATH
        which_path = shutil.which("tesseract")
        if which_path and os.path.exists(which_path):
            pytesseract.pytesseract.tesseract_cmd = which_path
            _TESSERACT_AVAILABLE = True
            _TESSERACT_INITIALIZED = True
            logger.info(f"Tesseract OCR found in PATH: {which_path}")
            return True

        # 2. Check candidate directories
        for candidate in CANDIDATE_TESSERACT_PATHS:
            if candidate and os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                _TESSERACT_AVAILABLE = True
                _TESSERACT_INITIALIZED = True
                logger.info(f"Tesseract OCR found at candidate location: {candidate}")
                return True

        # 3. Test execution
        try:
            pytesseract.get_tesseract_version()
            _TESSERACT_AVAILABLE = True
        except Exception:
            _TESSERACT_AVAILABLE = False
            
    except ImportError:
        logger.warning("pytesseract is not installed.")
        _TESSERACT_AVAILABLE = False

    _TESSERACT_INITIALIZED = True
    if not _TESSERACT_AVAILABLE:
        logger.info("Tesseract binary not found on host. Gracefully using heuristic OCR fallback.")
    return _TESSERACT_AVAILABLE

def is_tesseract_available() -> bool:
    return init_tesseract()

def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """Preprocesses an image to increase OCR character recognition accuracy."""
    try:
        # Convert to Grayscale
        gray = image.convert('L')
        # Increase contrast
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.8)
        # Apply slight sharpening
        sharpened = enhanced.filter(ImageFilter.SHARPEN)
        return sharpened
    except Exception as e:
        logger.debug(f"Image preprocessing skipped: {e}")
        return image

def extract_text_from_image(image_input) -> Tuple[str, str]:
    """
    Extracts text from an image (file path or PIL Image).
    Returns (extracted_text, engine_used).
    """
    img = None
    if isinstance(image_input, str):
        if not os.path.exists(image_input):
            raise FileNotFoundError(f"Image file not found: {image_input}")
        img = Image.open(image_input)
    elif isinstance(image_input, Image.Image):
        img = image_input
    elif hasattr(image_input, 'read'): # File-like object
        img = Image.open(image_input)
    else:
        raise ValueError("Unsupported image input type for OCR.")

    # Attempt Tesseract OCR if available
    if is_tesseract_available():
        try:
            import pytesseract
            processed = preprocess_image_for_ocr(img)
            text = pytesseract.image_to_string(processed)
            if text and text.strip():
                return text.strip(), "tesseract"
        except Exception as e:
            logger.warning(f"Tesseract execution error: {e}. Falling back to heuristic extractor.")

    # Heuristic / Metadata Fallback when OCR binary is missing or fails
    fallback_text = _extract_image_heuristic_text(img, image_input if isinstance(image_input, str) else "")
    return fallback_text, "heuristic_fallback"

def _extract_image_heuristic_text(image: Image.Image, file_path: str = "") -> str:
    """
    Fallback extractor when Tesseract binary is absent.
    Inspects image metadata and filename to generate clean placeholder receipt lines.
    """
    filename = os.path.basename(file_path) if file_path else "Receipt"
    clean_name = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').title()
    
    # Try reading EXIF date
    date_str = datetime.now().strftime('%Y-%m-%d')
    try:
        exif = image._getexif() if hasattr(image, '_getexif') and image._getexif() else {}
        if exif and 306 in exif: # DateTime tag
            raw_date = exif[306]
            parts = raw_date.split(' ')[0].replace(':', '-')
            date_str = parts
    except Exception:
        pass

    return f"{clean_name}\nDate: {date_str}\nTOTAL: $0.00\n[OCR binary unavailable - image registered]"

def extract_text_from_pdf_pages_ocr(pdf_path: str, max_pages: int = 10) -> List[str]:
    """
    Renders PDF pages into images using pypdfium2 (or pdfplumber)
    and executes OCR on each scanned page.
    """
    page_texts = []
    
    # Try pypdfium2 first (high speed, excellent rendering)
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_path)
        num_pages = min(len(pdf), max_pages)
        for i in range(num_pages):
            page = pdf[i]
            # Render at 300 DPI for high OCR accuracy
            pil_image = page.render(scale=300/72).to_pil()
            text, _ = extract_text_from_image(pil_image)
            page_texts.append(text)
        return page_texts
    except Exception as e:
        logger.debug(f"pypdfium2 rendering failed: {e}. Trying pdfplumber fallback.")

    # Fallback to pdfplumber image conversion
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                try:
                    pil_image = page.to_image(resolution=300).original
                    text, _ = extract_text_from_image(pil_image)
                    page_texts.append(text)
                except Exception:
                    page_texts.append("")
        return page_texts
    except Exception as e:
        logger.error(f"PDF OCR rendering failed completely: {e}")
        return []

# Regex patterns for receipt parsing
DATE_PATTERNS = [
    re.compile(r'\b(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\b'), # YYYY-MM-DD
    re.compile(r'\b(\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})\b'), # MM-DD-YYYY or DD-MM-YYYY
    re.compile(r'\b(\d{1,2}[-/.]\d{1,2}[-/.]\d{2})\b'),   # MM/DD/YY
    re.compile(r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2})\b', re.I),
    re.compile(r'\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})\b', re.I)
]

AMOUNT_PATTERNS = [
    re.compile(r'(?:total|amount\s*due|grand\s*total|balance\s*due|final\s*total)[\s:]*[$€£]?\s*([0-9]{1,4}(?:,[0-9]{3})*\.[0-9]{2})\b', re.I),
    re.compile(r'(?:subtotal|sub-total)[\s:]*[$€£]?\s*([0-9]{1,4}(?:,[0-9]{3})*\.[0-9]{2})\b', re.I),
    re.compile(r'[$€£]\s*([0-9]{1,4}(?:,[0-9]{3})*\.[0-9]{2})\b'),
]

PAYMENT_METHOD_PATTERNS = [
    (re.compile(r'\b(visa|mastercard|amex|american\s*express|discover)\b', re.I), 'Credit Card'),
    (re.compile(r'\b(apple\s*pay|google\s*pay|samsung\s*pay)\b', re.I), 'Mobile Payment'),
    (re.compile(r'\b(cash|tendered)\b', re.I), 'Cash'),
    (re.compile(r'\b(debit|interac)\b', re.I), 'Debit Card')
]

def parse_receipt(file_path_or_image) -> Dict[str, Any]:
    """
    Parses a receipt image via OCR and extracts structured transaction fields:
    Date, Merchant (Description), Amount, Payment Method, and Category.
    """
    raw_text, engine = extract_text_from_image(file_path_or_image)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    # 1. Extract Merchant (first non-empty line with letters, avoiding phone/website/noise)
    merchant = "Receipt Purchase"
    for line in lines[:5]:
        if len(line) >= 3 and re.search(r'[A-Za-z]', line) and not re.search(r'^(tel|phone|www|http|tax|invoice|date|order|receipt)', line, re.I):
            merchant = line.title()
            break

    # If the merchant name came from the filename
    if merchant == "Receipt Purchase" and isinstance(file_path_or_image, str):
        base = os.path.splitext(os.path.basename(file_path_or_image))[0]
        merchant = base.replace('_', ' ').replace('-', ' ').title()

    # 2. Extract Date
    parsed_date = datetime.now().strftime('%Y-%m-%d')
    for line in lines:
        matched = False
        for pat in DATE_PATTERNS:
            m = pat.search(line)
            if m:
                raw_d = m.group(1)
                try:
                    # Attempt common formats
                    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y', '%m/%d/%y', '%B %d, %Y', '%b %d, %Y', '%d %b %Y'):
                        try:
                            dt = datetime.strptime(raw_d, fmt)
                            parsed_date = dt.strftime('%Y-%m-%d')
                            matched = True
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            if matched:
                break
        if matched:
            break

    # 3. Extract Amount
    total_amount = 0.0
    amounts_found = []
    
    # First search for explicit TOTAL
    for line in lines:
        for pat in AMOUNT_PATTERNS:
            matches = pat.findall(line)
            for match in matches:
                try:
                    clean_amt = float(match.replace(',', ''))
                    amounts_found.append(clean_amt)
                except ValueError:
                    continue

    if amounts_found:
        # Receipt Total is typically the largest monetary figure
        total_amount = max(amounts_found)

    # 4. Extract Payment Method
    payment_method = "Unknown"
    for line in lines:
        for pat, method in PAYMENT_METHOD_PATTERNS:
            if pat.search(line):
                payment_method = method
                break
        if payment_method != "Unknown":
            break

    # 5. Categorize
    from core.payment_categorizer import classify_payment
    detected_cat = classify_payment(merchant, -total_amount)
    if not detected_cat:
        # Heuristic merchant check
        lower_m = merchant.lower()
        if any(w in lower_m for w in ['restaurant', 'cafe', 'coffee', 'starbucks', 'burger', 'pizza', 'diner', 'grill', 'bistro', 'bakery', 'taco', 'sushi']):
            detected_cat = 'Food'
        elif any(w in lower_m for w in ['market', 'supermarket', 'grocery', 'trader', 'costco', 'walmart', 'target']):
            detected_cat = 'Food'
        elif any(w in lower_m for w in ['gas', 'fuel', 'chevron', 'shell', 'exxon', 'oil', 'parking']):
            detected_cat = 'Transport'
        elif any(w in lower_m for w in ['pharmacy', 'cvs', 'walgreens', 'health', 'clinic']):
            detected_cat = 'Healthcare'
        else:
            detected_cat = 'Shopping'

    file_path_str = file_path_or_image if isinstance(file_path_or_image, str) else ""

    return {
        "success": True,
        "date": parsed_date,
        "description": merchant,
        "amount": -round(total_amount, 2), # Stored as negative expense
        "category": detected_cat,
        "receipt_path": file_path_str,
        "notes": f"Payment: {payment_method} | Engine: {engine}",
        "raw_text": raw_text,
        "engine": engine
    }
