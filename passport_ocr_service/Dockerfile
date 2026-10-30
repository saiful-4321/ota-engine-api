FROM python:3.11-slim

# Tesseract OCR engine (English model covers the MRZ alphabet A-Z 0-9 <)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng fonts-dejavu-core wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_DEV" = "true" ]; then \
         pip install --no-cache-dir -r requirements-dev.txt \
         && apt-get update && apt-get install -y --no-install-recommends fonts-ocr-b && rm -rf /var/lib/apt/lists/*; \
       fi

COPY . .

# Run as an unprivileged user
RUN useradd --system --uid 10001 --no-create-home ocr && chown -R ocr /app
USER ocr

EXPOSE 7800

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:7800/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 7800 --workers ${WORKERS:-2}"]
