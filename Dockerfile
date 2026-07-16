# Niat — container image for Google Cloud Run (or any Docker host).
# The core server uses only the Python standard library, so the image is small.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects PORT; the server must listen on all interfaces there.
ENV HOST=0.0.0.0

CMD ["python", "server.py"]
