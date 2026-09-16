FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads && \
    useradd -r -s /bin/false appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Run Alembic migrations before starting the server (when DATABASE_URL is provided).
# The setup wizard will still run migrations for local/non-Docker installs.
CMD ["sh", "-c", "if [ -n \"$DATABASE_URL\" ]; then alembic upgrade head; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
