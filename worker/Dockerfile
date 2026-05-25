FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY analysis_worker.py .

ENV STORAGE_ROOT=/app/storage

CMD ["python", "-u", "analysis_worker.py"]
