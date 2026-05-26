import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pika


RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")

TASK_QUEUE = os.getenv("TASK_QUEUE", "image.task.queue")
RESULT_QUEUE = os.getenv("RESULT_QUEUE", "analysis.result.queue")

WORKER_ID = os.getenv("WORKER_ID", socket.gethostname())
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Seoul"))

# 데모용 분석 지연 시간
MOCK_PROCESSING_DELAY = float(os.getenv("MOCK_PROCESSING_DELAY", "0.3"))


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
            print(f"[worker:{WORKER_ID}] connecting to RabbitMQ {RABBITMQ_HOST}:{RABBITMQ_PORT}")
            return pika.BlockingConnection(params)
        except pika.exceptions.AMQPConnectionError:
            print(f"[worker:{WORKER_ID}] RabbitMQ not ready ({attempt}/{retries}), retrying...")
            time.sleep(delay)

    raise RuntimeError("RabbitMQ connection failed")


def extract_filename(task: dict) -> str:
    """
    imageUrl, fileName, imageId 중 사용 가능한 값에서 파일명을 추출한다.
    현재 중간발표에서는 파일명 기반 Mock 분석을 사용한다.
    """
    image_url = task.get("imageUrl") or task.get("fileName") or task.get("imageId") or ""
    return Path(image_url).name.lower()


def classify_by_filename(task: dict) -> tuple[str, str, float]:
    """
    중간발표용 Mock 분석기.

    실제 AI 모델 대신 파일명 규칙으로 재난 유형을 분류한다.
    예:
    - fire_001.jpg  -> FIRE
    - flood_001.jpg -> FLOOD
    - normal_001.jpg -> NORMAL

    최종 발표 전에는 이 함수만 YOLO 또는 경량 이미지 분류 모델로 교체하면 된다.
    """
    filename = extract_filename(task)

    if "fire" in filename or "flame" in filename or "smoke" in filename:
        return "FIRE", "HIGH", 0.92

    if "flood" in filename or "water" in filename or "rain" in filename:
        return "FLOOD", "HIGH", 0.91

    if "normal" in filename or "safe" in filename:
        return "NORMAL", "LOW", 0.88

    return "UNKNOWN", "LOW", 0.55


def build_result(task: dict, category: str, risk_level: str, confidence: float, processing_ms: int) -> dict:
    return {
        "taskId": task.get("taskId"),
        "reportId": task.get("reportId"),
        "imageId": task.get("imageId"),
        "imageUrl": task.get("imageUrl"),
        "location": task.get("location", ""),
        "description": task.get("description", ""),
        "uploadedAt": task.get("uploadedAt"),
        "category": category,
        "riskLevel": risk_level,
        "confidence": confidence,
        "processingMs": processing_ms,
        "analyzedAt": now_iso(),
        "workerId": WORKER_ID,
        "analysisType": "MOCK_FILENAME_CLASSIFIER",
    }


def handle_task(channel, method, properties, body: bytes) -> None:
    try:
        task = json.loads(body.decode("utf-8"))
        started = time.perf_counter()

        print(f"[worker:{WORKER_ID}] received task: {task.get('taskId')} / {task.get('imageUrl')}")

        # Worker 병렬 처리 효과를 보여주기 위한 데모용 지연
        time.sleep(MOCK_PROCESSING_DELAY)

        category, risk_level, confidence = classify_by_filename(task)
        processing_ms = int((time.perf_counter() - started) * 1000)

        result = build_result(task, category, risk_level, confidence, processing_ms)

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
            f"{result.get('reportId')} as {category}/{risk_level} "
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

    # Worker 하나가 한 번에 하나의 작업만 가져가도록 설정
    # Worker 수를 늘렸을 때 병렬 처리 효과를 보기 좋게 함
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(
        queue=TASK_QUEUE,
        on_message_callback=handle_task,
    )

    print(f"[worker:{WORKER_ID}] waiting for tasks from {TASK_QUEUE}")
    channel.start_consuming()


if __name__ == "__main__":
    main()
