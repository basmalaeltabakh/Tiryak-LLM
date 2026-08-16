import easyocr
from pathlib import Path
from typing import List, Dict
import fitz  # PyMuPDF

# Initialize once (loading the model is expensive, so we do it at module level)
_reader = None


def get_ocr_reader():
    """
    Lazy-loads the EasyOCR reader (Arabic + English).
    Loading this model takes a few seconds, so we only do it once
    and reuse it across calls.
    """
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["ar", "en"], gpu=False)
    return _reader


def ocr_image(image_path: str) -> str:
    """
    Runs OCR on a single image file and returns extracted text.
    """
    reader = get_ocr_reader()
    results = reader.readtext(image_path, detail=0, paragraph=True)
    return "\n".join(results)


def ocr_scanned_pdf(file_path: str) -> List[Dict]:
    """
    Converts each PDF page to an image, then runs OCR on it.
    Used when parse_pdf() detects the PDF has little to no
    extractable text (i.e., it's scanned).
    """
    doc = fitz.open(file_path)
    reader = get_ocr_reader()
    pages_content = []

    for page_num, page in enumerate(doc, start=1):
        # Render page to an image (higher zoom = better OCR accuracy)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        image_bytes = pix.tobytes("png")

        # EasyOCR can read directly from bytes
        results = reader.readtext(image_bytes, detail=0, paragraph=True)
        text = "\n".join(results)

        pages_content.append({
            "page_number": page_num,
            "text": text.strip()
        })

    doc.close()
    return pages_content