FROM python:3.12-slim
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
USER appuser
EXPOSE 8000
# Migrations run first (idempotent, advisory-locked); the API refuses to start if they fail.
CMD ["sh","-c","python -m app.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
