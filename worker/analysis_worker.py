import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pika
from PIL import Image
from transformers import pipeline


RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")

TASK_QUEUE = os.getenv("TASK_QUEUE", "image.task.queue")
RESULT_QUEUE = os.getenv("RESULT_QUEUE", "analysis.result.queue")

WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Seoul"))

STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/app/storage")

MODEL_NAME = os.getenv("MODEL_NAME", "Luwayy/disaster_images_model")
ANALYSIS_TYPE = "HF_DISASTER_MODEL"


print(f"[worker:{WORKER_ID}] loading model {MODEL_NAME}")

classifier = pipeline(
    task="image-classification",
    model=MODEL_NAME,
)

print(f"[worker:{WORKER_ID}] model loaded")


def now_iso() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def connect_rabbitmq(retries: int = 60, delay: float = 2.0) -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)

    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials,
        heartbeat=30,
        blocked_connection_timeout=30,
    )

    for attempt in range(1, retries + 1):
        try:
            print(
                f"[worker:{WORKER_ID}] connecting to RabbitMQ "
                f"{RABBITMQ_HOST}:{RABBITMQ_PORT}"
            )
            return pika.BlockingConnection(params)
        except pika.exceptions.AMQPConnectionError:
            print(
                f"[worker:{WORKER_ID}] RabbitMQ not ready "
                f"({attempt}/{retries}), retrying..."
            )
            time.sleep(delay)

    raise RuntimeError("RabbitMQ connection failed")


def resolve_image_path(image_url: str) -> str:
    image_path = Path(image_url)

    if image_path.is_absolute():
        return str(image_path)

    return str(Path(STORAGE_ROOT) / image_path)


def determine_risk_level(model_label: str, confidence: float) -> str:
    if model_label == "Non_Damage":
        return "NORMAL"

    if confidence >= 0.7:
        return "HIGH"

    return "LOW"


def classify_image(image_path: str):
    image = Image.open(image_path).convert("RGB")

    predictions = classifier(image)

    predictions = sorted(
        predictions,
        key=lambda x: x["score"],
        reverse=True,
    )

    top_prediction = predictions[0]

    model_label = top_prediction["label"]
    confidence = float(top_prediction["score"])
    risk_level = determine_risk_level(model_label, confidence)

    top_predictions = [
        {
            "label": pred["label"],
            "score": float(pred["score"]),
        }
        for pred in predictions
    ]

    return model_label, confidence, risk_level, top_predictions


def handle_task(channel, method, properties, body: bytes) -> None:
    try:
        task = json.loads(body.decode("utf-8"))
        started = time.perf_counter()

        print(
            f"[worker:{WORKER_ID}] received task: "
            f"{task.get('taskId')} / {task.get('imageUrl')}"
        )

        image_url = task["imageUrl"]
        image_path = resolve_image_path(image_url)

        model_label, confidence, risk_level, top_predictions = classify_image(image_path)

        processing_ms = int((time.perf_counter() - started) * 1000)

        result = {
            "taskId": task.get("taskId"),
            "reportId": task.get("reportId"),
            "imageUrl": task.get("imageUrl"),
            "location": task.get("location", ""),
            "description": task.get("description", ""),
            "uploadedAt": task.get("uploadedAt"),
            "originalFilename": task.get("originalFilename"),

            "modelLabel": model_label,
            "confidence": confidence,
            "riskLevel": risk_level,
            "topPredictions": top_predictions,

            "processingMs": processing_ms,
            "workerId": WORKER_ID,
            "analyzedAt": now_iso(),
            "analysisType": ANALYSIS_TYPE,
        }

        channel.basic_publish(
            exchange="",
            routing_key=RESULT_QUEUE,
            body=json.dumps(result, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

        channel.basic_ack(delivery_tag=method.delivery_tag)

        print(
            f"[worker:{WORKER_ID}] analyzed "
            f"{result.get('reportId')} as "
            f"{model_label} ({confidence:.3f}) -> {risk_level} "
            f"({processing_ms} ms)"
        )

    except Exception as exc:
        print(f"[worker:{WORKER_ID}] task failed: {exc}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main() -> None:
    connection = connect_rabbitmq()
    channel = connection.channel()

    channel.queue_declare(queue=TASK_QUEUE, durable=True)
    channel.queue_declare(queue=RESULT_QUEUE, durable=True)

    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(
        queue=TASK_QUEUE,
        on_message_callback=handle_task,
    )

    print(f"[worker:{WORKER_ID}] waiting for tasks from {TASK_QUEUE}")
    channel.start_consuming()


if __name__ == "__main__":
    main()
