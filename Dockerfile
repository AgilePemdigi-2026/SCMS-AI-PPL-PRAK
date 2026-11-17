# SCMS-AI: image aplikasi FastAPI
#
# Build mode simulasi (ringan, tanpa model AI):
#   docker build -t scms-ai .
# Build dengan YOLOv8 + sentence-transformers (PyTorch versi CPU):
#   docker build --build-arg WITH_AI=1 -t scms-ai:ai .

FROM python:3.12-slim

ARG WITH_AI=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Jakarta

WORKDIR /app

# Library sistem yang dibutuhkan OpenCV (ultralytics) hanya dipasang bila WITH_AI=1
RUN if [ "$WITH_AI" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
        && rm -rf /var/lib/apt/lists/*; \
    fi

COPY requirements.txt requirements-ai.txt ./
RUN pip install -r requirements.txt \
    && if [ "$WITH_AI" = "1" ]; then \
        pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
        && pip install -r requirements-ai.txt; \
    fi

COPY . .

# Jalankan sebagai user biasa, bukan root
RUN useradd --create-home --uid 1000 scms \
    && mkdir -p app/static/uploads models \
    && chown -R scms:scms /app
USER scms

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/Login', timeout=4)" || exit 1

# Satu worker: tabel dan migrasi kolom dibuat saat aplikasi diimpor (app/main.py),
# jadi beberapa worker sekaligus bisa saling bertabrakan saat start pertama.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
