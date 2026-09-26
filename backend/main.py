"""
Kavach AI - FastAPI backend.

Endpoints (all return the same shape - see `result_payload`):
  POST /api/analyze/text        {"text": "..."}
  POST /api/analyze/url         {"url": "...", "context": "optional message text"}
  POST /api/analyze/call        {"transcript": "..."}
  POST /api/analyze/screenshot  multipart file upload (image)
  POST /api/analyze/qr          multipart file upload (image)
  GET  /api/i18n/{lang}         UI string dictionary ("en" | "hi")

Everything runs locally and deterministically (rule-based risk engine) -
no external API key is required for the core product to work end-to-end,
which matters for a reliable live demo.
"""

from pathlib import Path

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import risk_engine
import url_utils
import ocr_utils
import qr_utils
from i18n import STRINGS

app = FastAPI(title="Kavach AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class TextIn(BaseModel):
    text: str


class UrlIn(BaseModel):
    url: str
    context: str = ""


class CallIn(BaseModel):
    transcript: str


# ---------------------------------------------------------------------------
# Response shaping
# ---------------------------------------------------------------------------

def result_payload(result: risk_engine.AnalysisResult, extra: dict | None = None) -> dict:
    payload = {
        "risk_level": result.risk_level,
        "score": result.score,
        "signals": [
            {"id": s.id, "why_en": s.why_en, "why_hi": s.why_hi} for s in result.signals
        ],
        "action_en": result.action_en,
        "action_hi": result.action_hi,
    }
    if extra:
        payload.update(extra)
    if result.extra:
        payload.update(result.extra)
    return payload


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/analyze/text")
def analyze_text(body: TextIn):
    text_result = risk_engine.analyze_text(body.text, source_type="message")

    found_url = url_utils.find_first_url(body.text)
    if found_url:
        url_result = risk_engine.analyze_url(found_url)
        combined = risk_engine.combine(text_result, url_result)
        combined.extra = url_result.extra
        return result_payload(combined, {"analysed_text": body.text, "url": found_url})

    return result_payload(text_result, {"analysed_text": body.text})


@app.post("/api/analyze/call")
def analyze_call(body: CallIn):
    result = risk_engine.analyze_text(body.transcript, source_type="call")
    return result_payload(result, {"analysed_text": body.transcript})


@app.post("/api/analyze/url")
def analyze_url(body: UrlIn):
    url_result = risk_engine.analyze_url(body.url)
    if body.context.strip():
        text_result = risk_engine.analyze_text(body.context, source_type="message")
        combined = risk_engine.combine(url_result, text_result)
        combined.extra = url_result.extra
        return result_payload(combined, {"analysed_text": body.context, "url": body.url})
    return result_payload(url_result, {"url": body.url})


@app.post("/api/analyze/screenshot")
async def analyze_screenshot(file: UploadFile = File(...)):
    image_bytes = await file.read()
    extracted_text = ocr_utils.extract_text_from_image_bytes(image_bytes)

    text_result = risk_engine.analyze_text(extracted_text, source_type="message")

    found_url = url_utils.find_first_url(extracted_text)
    if found_url:
        url_result = risk_engine.analyze_url(found_url)
        combined = risk_engine.combine(text_result, url_result)
        return result_payload(combined, {"analysed_text": extracted_text, "url": found_url})

    return result_payload(text_result, {"analysed_text": extracted_text})


@app.post("/api/analyze/qr")
async def analyze_qr(file: UploadFile = File(...)):
    image_bytes = await file.read()
    data = qr_utils.decode_qr_from_image_bytes(image_bytes)

    if not data:
        return {"no_qr_found": True}

    upi = qr_utils.parse_upi_uri(data)
    if upi:
        # A UPI payment QR is itself a payment action - treat that as a
        # payment signal, then also run it through URL/text analysis in
        # case the payee name embeds an org name that doesn't match.
        base_result = risk_engine.analyze_text("scan this qr code enter your upi pin",
                                                 source_type="message")
        return result_payload(base_result, {"qr_data": data, "upi": upi})

    # Not a UPI link - could be a plain URL or arbitrary text.
    if data.lower().startswith("http"):
        url_result = risk_engine.analyze_url(data)
        return result_payload(url_result, {"qr_data": data, "url": data})

    text_result = risk_engine.analyze_text(data, source_type="message")
    return result_payload(text_result, {"qr_data": data})


@app.get("/api/i18n/{lang}")
def get_i18n(lang: str):
    return STRINGS.get(lang, STRINGS["en"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve the frontend (single-page app) - keeps deployment to one service.
# ---------------------------------------------------------------------------

app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
