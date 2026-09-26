# Kavach AI - single-service deployment (backend + frontend together)
FROM python:3.12-slim

# tesseract-ocr is a system binary needed for reading text out of
# uploaded screenshots (pytesseract is just a wrapper around it).
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
