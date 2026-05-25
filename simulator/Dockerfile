FROM python:3.12-slim

WORKDIR /app

COPY simulator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simulator/upload_simulator.py .
COPY sample_images ./sample_images

ENV SAMPLE_DIR=/app/sample_images

CMD ["python", "-u", "upload_simulator.py"]
