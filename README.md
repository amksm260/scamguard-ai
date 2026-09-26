# Kavach AI — an AI safety companion for elderly people

Before you click, pay, or share — check it here.

This is a working MVP: a single web app (FastAPI backend + a plain
HTML/CSS/JS frontend, no build step) that lets someone paste a suspicious
message, upload a screenshot, paste a link, upload a QR code, or paste a
call transcript, and get back one of **LOW RISK / REVIEW / HIGH RISK**
with a plain-language "why" and "what to do" — in English or Hindi.

The whole risk engine is **rule-based and runs 100% locally** — no
external API key, no internet call, no per-request cost. That matters a
lot for a live demo: nothing can time out, rate-limit, or go down on
stage. See `backend/risk_engine.py` for exactly how signals are detected
and scored — every check is a plain, readable regex, so you can walk
judges through the logic line by line.

---

## 1. Project structure

```
kavach-ai/
├── Dockerfile                 # one-command deploy (backend + frontend together)
└── backend/
    ├── main.py                # FastAPI app + all API endpoints
    ├── risk_engine.py          # the core: signals, scoring, LOW/REVIEW/HIGH, explanations
    ├── url_utils.py            # URL structure checks (lookalike domains, shorteners, IP hosts...)
    ├── ocr_utils.py            # screenshot → text (pytesseract)
    ├── qr_utils.py             # QR decode + UPI-payment-link parsing (OpenCV, no libzbar needed)
    ├── i18n.py                 # English/Hindi UI strings
    ├── requirements.txt
    └── static/
        ├── index.html          # the whole UI, one page
        ├── style.css           # design tokens (colors, type, spacing)
        └── app.js               # all frontend logic (fetch calls, rendering, voice, share)
```

## 2. Run it locally (fastest way to try it)

You need Python 3.11+ and Tesseract OCR installed.

```bash
# Debian/Ubuntu (also covers WSL)
sudo apt-get install -y tesseract-ocr

# macOS
brew install tesseract
```

Then:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000** — that's the whole app, frontend included.

## 3. Run it with Docker (recommended for the actual demo machine)

This bakes in Tesseract for you, so there's nothing extra to install:

```bash
docker build -t kavach-ai .
docker run -p 8000:8000 kavach-ai
```

Open **http://localhost:8000**.

## 4. Deploy it for free (so you have a live link for judges)

The easiest path is a Docker-based free host, since it needs zero
configuration beyond "here's a Dockerfile":

**Render.com** (recommended — generous free tier, simple UI)
1. Push this folder to a GitHub repo.
2. On [render.com](https://render.com) → **New +** → **Web Service** →
   connect your repo.
3. Render auto-detects the `Dockerfile`. Leave the build/start commands
   blank (the Dockerfile already defines them).
4. Set **Instance Type** to the free tier, click **Create Web Service**.
5. Wait for the build (~3–5 min the first time) — you'll get a public
   `https://kavach-ai-xxxx.onrender.com` URL.

**Railway.app** is an equally good alternative with the same "connect
repo → auto-detect Dockerfile → deploy" flow.

> Free tiers on both platforms "sleep" after inactivity and take ~30–60
> seconds to wake up on the first request. Open your link 5 minutes
> before you go on stage so it's already warm.

No environment variables are required — the app works out of the box.

## 5. How the risk engine works (for your pitch / Q&A)

```
input (text / OCR / QR / transcript)
        │
        ▼
regex-based signal detection  →  urgency, threat, impersonation,
        │                        OTP/PIN request, payment request,
        │                        reward offer, "click this link",
        │                        sensitive-info request
        ▼
URL structural analysis        →  lookalike domain, IP-address host,
        │                        URL shortener, no HTTPS, excessive
        │                        subdomains
        ▼
weighted score (0–100)  →  < 20 = LOW · 20–44 = REVIEW · ≥ 45 = HIGH
        │
        ▼
plain-language WHY + WHAT-TO-DO, in English or Hindi
```

This is deliberately **not** "send everything to an LLM and hope" — it's
the hybrid approach described in the product doc: deterministic checks
for things that must be reliable (OTP requests, domain mismatches),
kept simple enough to explain and defend to judges.

### Extending it
- Add more scam keywords/phrases → edit the pattern lists at the top of
  `risk_engine.py` (`URGENCY_PATTERNS`, `THREAT_PATTERNS`, etc.)
- Add more known official domains (so more lookalike domains get caught)
  → extend `KNOWN_ORG_DOMAINS` in `risk_engine.py`.
- Add another language → add a new key to `STRINGS` in `i18n.py`, and add
  a `why_XX` / `action_XX` pair per template in `risk_engine.py`.

## 6. What this MVP intentionally does NOT do

Matching the honesty principle in the product doc — this demo does not
claim: direct WhatsApp/SMS interception, telecom-level call monitoring,
direct bank/UPI integration, automatic payment blocking, deepfake
detection, or guaranteed 100% scam detection. It's an advisory tool the
user actively opens and feeds — exactly the realistic MVP scope the
hackathon doc describes.

## 7. Trusted Circle (demo)

"Ask a Trusted Person" uses the device's native share sheet
(`navigator.share`) where available, and falls back to opening a
pre-filled WhatsApp message. Nothing is sent automatically — the user
always takes the final action themselves.
