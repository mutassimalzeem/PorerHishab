FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application and the alembic migration environment.
COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
