FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer is cached until requirements change.
COPY v1/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source (secrets stay out via .dockerignore).
COPY v1/ .

EXPOSE 8000

# Respect $PORT injected by the platform (Render sets it); fall back to 8000.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}