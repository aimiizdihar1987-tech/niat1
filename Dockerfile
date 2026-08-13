# Niat production image for Cloud Run (also works with ordinary Docker).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    NIAT_CONTAINER=1 \
    NIAT_STORAGE=supabase \
    NIAT_OUTPUT_DIR=/tmp/niat-output

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt \
    && groupadd --system niat \
    && useradd --system --gid niat --home-dir /app --no-create-home niat \
    && mkdir -p /tmp/niat-output \
    && chown -R niat:niat /app /tmp/niat-output

# Copy only runtime files. Secrets, local databases, pupil files, generated
# outputs and unrelated prototypes never become image layers.
COPY --chown=niat:niat server.py auth.py bank_soalan.py lessons.py ./
COPY --chown=niat:niat supabase_client.py guardrail.py wordlist.py ./
COPY --chown=niat:niat peringatan.py prestasi_murid.py remind_cron.py niat_google.py ./
COPY --chown=niat:niat export_docx.py export_pptx.py ./
COPY --chown=niat:niat dskp_english_f1.json dskp_english_f2.json dskp_english_f3.json ./
COPY --chown=niat:niat dskp_english_f4.json dskp_english_f5.json ./
COPY --chown=niat:niat prompts/ ./prompts/
COPY --chown=niat:niat web/ ./web/
COPY --chown=niat:niat data/cefr_b1_wordlist.json ./data/cefr_b1_wordlist.json

USER niat
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/api/health', timeout=3)" || exit 1

CMD ["python", "-u", "server.py"]
