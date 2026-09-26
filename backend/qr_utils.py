"""
Kavach AI - QR code decoding.

Uses OpenCV's built-in QR detector so there is no extra system dependency
(no libzbar needed) - this keeps deployment simple.
"""

import io
import re
from urllib.parse import urlparse, parse_qs

import numpy as np
import cv2
from PIL import Image


def decode_qr_from_image_bytes(image_bytes: bytes):
    """Returns the decoded string, or None if no QR code was found."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(image)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(bgr)
        return data if data else None
    except Exception:
        return None


def parse_upi_uri(data: str):
    """If the QR content is a UPI payment link (upi://pay?...), pull out the
    fields that matter for risk context. Returns None if it isn't a UPI URI."""
    if not data or not data.lower().startswith("upi://"):
        return None
    parsed = urlparse(data)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    return {
        "payee_vpa": params.get("pa"),
        "payee_name": params.get("pn"),
        "amount": params.get("am"),
        "note": params.get("tn"),
        "raw": data,
    }
