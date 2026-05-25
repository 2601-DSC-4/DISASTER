FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY result_aggregator.py .

CMD ["python", "-u", "result_aggregator.py"]
