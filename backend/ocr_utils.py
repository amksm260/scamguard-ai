"""
Kavach AI - OCR helper.

Extracts text from an uploaded screenshot so the same risk engine that
handles pasted messages can analyse what's in the image.
"""

import io
from PIL import Image
import pytesseract


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("L")  # grayscale improves OCR reliability
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception:
        return ""
