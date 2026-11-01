"""
LedgerSeLens Optical Character Recognition (OCR) Engine
Extracts transaction details from receipt images (PNG, JPG, TIFF, etc.)
and scanned PDF statements, with robust Tesseract path auto-detection
and heuristic fallback parsing.
"""

import os
import re
import json
import shutil
import tempfile
import subprocess
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import numpy as np
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

    # Attempt Tesseract OCR if available
    if is_tesseract_available():
        try:
            import pytesseract
            processed = preprocess_image_for_ocr(img)
            text = pytesseract.image_to_string(processed)
            if text and text.strip():
                return text.strip(), "tesseract"
        except Exception as e:
            logger.warning(f"Tesseract execution error: {e}. Falling back to Windows/heuristic extractor.")

    # Attempt native Windows Media OCR on Windows hosts
    if os.name == 'nt':
        try:
            batch_res = _run_windows_media_ocr_batch([img], clean_masks=False)
            if batch_res and batch_res[0].get("text", "").strip():
                return batch_res[0]["text"].strip(), "windows_ocr"
        except Exception as e:
            logger.debug(f"Windows Media OCR skipped: {e}")

    # Heuristic / Metadata Fallback when OCR binary is missing or fails
    fallback_text = _extract_image_heuristic_text(img, image_input if isinstance(image_input, str) else "")
    return fallback_text, "heuristic_fallback"


def _clean_asterisk_masks(gray_arr: np.ndarray) -> np.ndarray:
    """
    Removes horizontal chains of 4+ consecutive identical asterisk glyphs ('****')
    from rendered statement images so OCR word tokenizers do not discard masked
    UPI/card tokens (e.g., 'UPI-SURAJ-*********BZZ6@PTY' -> 'UPI-SURAJ- BZZ6@PTY').
    """
    try:
        from scipy import ndimage
        binary = gray_arr < 180
        labeled, _ = ndimage.label(binary)
        objs = ndimage.find_objects(labeled)

        candidates = []
        for sl in objs:
            if sl is None:
                continue
            ys, xs = sl
            h = ys.stop - ys.start
            w = xs.stop - xs.start
            if 10 <= w <= 15 and 11 <= h <= 15:
                candidates.append((ys.start, ys.stop, xs.start, xs.stop))

        if len(candidates) < 4:
            return gray_arr

        # Group candidates by line (y0 within 3px), then sort each line by x0
        candidates.sort(key=lambda c: c[0])
        line_groups: List[List[Tuple[int, int, int, int]]] = []
        for c in candidates:
            if not line_groups or abs(c[0] - line_groups[-1][-1][0]) > 3:
                line_groups.append([c])
            else:
                line_groups[-1].append(c)

        to_erase = []
        for grp in line_groups:
            grp.sort(key=lambda c: c[2])
            chain = [grp[0]]
            for cur in grp[1:]:
                prev = chain[-1]
                if 1 <= (cur[2] - prev[3]) <= 8 and abs(cur[1] - prev[1]) <= 3:
                    chain.append(cur)
                else:
                    if len(chain) >= 4:
                        to_erase.extend(chain)
                    chain = [cur]
            if len(chain) >= 4:
                to_erase.extend(chain)

        if not to_erase:
            return gray_arr

        out = gray_arr.copy()
        for y0, y1, x0, x1 in to_erase:
            out[max(0, y0 - 1):min(out.shape[0], y1 + 1), max(0, x0 - 1):min(out.shape[1], x1 + 1)] = 255
        return out
    except Exception:
        return gray_arr


_WIN_OCR_PS_SCRIPT = r"""
param([string[]]$ImagePaths, [string]$OutFile)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

$ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $ocrEngine) {
    $lang = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages[0]
    $ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
}

$allPages = @()
foreach ($path in $ImagePaths) {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($ocrEngine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    
    $words = @()
    $lineStrings = @()
    foreach ($line in $result.Lines) {
        $lineStrings += $line.Text
        foreach ($w in $line.Words) {
            $r = $w.BoundingRect
            $words += @{
                t = $w.Text
                x = [math]::Round($r.X, 1)
                y = [math]::Round($r.Y, 1)
                w = [math]::Round($r.Width, 1)
                h = [math]::Round($r.Height, 1)
            }
        }
    }
    $allPages += ,@{
        text = ($lineStrings -join "`n")
        words = $words
    }
    $stream.Dispose()
}
$jsonStr = ConvertTo-Json -InputObject @($allPages) -Depth 5 -Compress
[System.IO.File]::WriteAllText($OutFile, $jsonStr, [System.Text.Encoding]::UTF8)
"""


def _run_windows_media_ocr_batch(images: List[Image.Image], clean_masks: bool = True) -> List[Dict[str, Any]]:
    """
    Executes Windows built-in WinRT Optical Character Recognition in batch
    across a list of PIL Images, returning text and word bounding boxes per page.
    """
    if os.name != 'nt' or not images:
        return []

    tmpdir = tempfile.mkdtemp(prefix="ledgerselens_ocr_")
    try:
        img_paths = []
        for idx, img in enumerate(images):
            gray = img.convert("L")
            if clean_masks:
                arr = _clean_asterisk_masks(np.array(gray))
                gray = Image.fromarray(arr)
            elif gray.width < 1000:
                gray = gray.resize((gray.width * 3, gray.height * 3), Image.Resampling.BICUBIC)
            p = os.path.join(tmpdir, f"page_{idx}.png")
            gray.save(p)
            img_paths.append(p)

        ps_file = os.path.join(tmpdir, "run_ocr.ps1")
        out_json = os.path.join(tmpdir, "ocr_out.json")
        with open(ps_file, "w", encoding="utf-8") as f:
            f.write(_WIN_OCR_PS_SCRIPT)

        paths_arg = ",".join(f"'{p}'" for p in img_paths)
        proc = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command", f"& '{ps_file}' -ImagePaths @({paths_arg}) -OutFile '{out_json}'"
            ],
            capture_output=True, text=True, encoding="utf-8", timeout=60
        )
        if proc.returncode != 0 or not os.path.exists(out_json):
            return []

        with open(out_json, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.debug(f"Windows batch OCR error: {e}")
        return []
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def extract_structured_table_from_pdf_ocr(pdf_path: str, max_pages: int = 20) -> List[Dict[str, Any]]:
    """
    Renders vector-outlined or scanned PDF bank statements at 300 DPI, detects
    table grid lines (horizontal & vertical rules) using pixel projections, and
    reconstructs multi-page structured table rows using OCR word bounding boxes.
    """
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_path)
        num_pages = min(len(pdf), max_pages)
        pil_images = [pdf[i].render(scale=300 / 72.0).to_pil() for i in range(num_pages)]
    except Exception as e:
        logger.debug(f"PDF rendering for structured OCR failed: {e}")
        return []

    ocr_pages = _run_windows_media_ocr_batch(pil_images, clean_masks=True)
    if not ocr_pages or len(ocr_pages) != len(pil_images):
        return []

    extracted_rows: List[Dict[str, Any]] = []
    active_headers: Optional[List[str]] = None

    for page_idx, (pil_img, page_ocr) in enumerate(zip(pil_images, ocr_pages)):
        words = page_ocr.get("words", [])
        if not words:
            continue

        arr = np.array(pil_img.convert("L"))
        height, width = arr.shape

        # Detect horizontal table grid lines across the page width
        x_start, x_end = int(width * 0.015), int(width * 0.96)
        row_dark = (arr[:, x_start:x_end] < 150).mean(axis=1)
        h_candidates = np.where(row_dark > 0.65)[0]

        h_lines: List[int] = []
        for y in h_candidates:
            if not h_lines or y - h_lines[-1] > 8:
                h_lines.append(int(y))

        # Filter to the main transaction table (skipping upper address box if present)
        # Group consecutive h_lines where spacing is < 250px (table rows)
        best_group: List[int] = []
        cur_group: List[int] = []
        for y in h_lines:
            if not cur_group or (y - cur_group[-1] <= 260):
                cur_group.append(y)
            else:
                if len(cur_group) >= len(best_group):
                    best_group = cur_group
                cur_group = [y]
        if len(cur_group) >= len(best_group):
            best_group = cur_group

        h_lines = best_group
        if len(h_lines) < 2:
            continue

        y0, y1 = h_lines[0], h_lines[-1]
        if y1 - y0 < 30:
            continue

        # Detect vertical column grid lines within the table's vertical span
        col_dark = (arr[y0:y1, :] < 150).mean(axis=0)
        v_candidates = np.where(col_dark > 0.65)[0]
        v_lines: List[int] = []
        for x in v_candidates:
            if not v_lines or x - v_lines[-1] > 15:
                v_lines.append(int(x))

        if len(v_lines) < 3:
            continue

        for r_idx in range(len(h_lines) - 1):
            ry0, ry1 = h_lines[r_idx], h_lines[r_idx + 1]
            if ry1 - ry0 < 18:
                continue

            row_words = [
                w for w in words
                if ry0 - 5 <= (w["y"] + w["h"] / 2.0) <= ry1 + 5
            ]
            if not row_words:
                continue

            cells: List[str] = []
            for c_idx in range(len(v_lines) - 1):
                cx0, cx1 = v_lines[c_idx], v_lines[c_idx + 1]
                c_words = [
                    w for w in row_words
                    if cx0 - 6 <= (w["x"] + w["w"] / 2.0) <= cx1 + 6
                ]
                c_words.sort(key=lambda w: (round(w["y"] / 18.0), w["x"]))
                cell_text = " ".join(str(w["t"]) for w in c_words).strip()
                cells.append(cell_text)

            if not any(cells):
                continue

            # Check if this row is a table header row
            first_cell_norm = re.sub(r'[^a-z]', '', cells[0].lower())
            second_cell_norm = re.sub(r'[^a-z]', '', cells[1].lower()) if len(cells) > 1 else ""
            if first_cell_norm in ('date', 'txndate', 'transdate', 'postdate') or second_cell_norm in ('narration', 'description', 'particulars', 'details'):
                active_headers = [c if c else f"col_{i}" for i, c in enumerate(cells)]
                continue

            if active_headers is None:
                # Default standard 5-column bank statement layout if header wasn't on page 1
                if len(cells) == 5:
                    active_headers = ['Date', 'Narration', 'Chq. / Ref No.', 'Value Date', 'Withdrawal Amount']
                elif len(cells) >= 3:
                    active_headers = ['Date', 'Description', 'Amount'] + [f"col_{i}" for i in range(3, len(cells))]
                else:
                    active_headers = [f"col_{i}" for i in range(len(cells))]

            # Align headers count with cells count
            row_dict = {}
            for c_idx, val in enumerate(cells):
                col_name = active_headers[c_idx] if c_idx < len(active_headers) else f"col_{c_idx}"
                row_dict[col_name] = val
            extracted_rows.append(row_dict)

    return extracted_rows

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
