FROM python:3.12-slim

WORKDIR /app

ARG MODEL_NAME=Luwayy/disaster_images_model

ENV HF_HOME=/app/.cache/huggingface \
    HF_HUB_DISABLE_XET=1 \
    MODEL_NAME=${MODEL_NAME}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir torchvision

# Keep the model download before application code so Docker can reuse this
# expensive layer when only analysis_worker.py changes.
COPY download_model.py .
RUN python download_model.py

COPY analysis_worker.py .

ENV STORAGE_ROOT=/app/storage \
    ANALYZER_MODE=hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

CMD ["python", "-u", "analysis_worker.py"]
