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
            return pika.BlockingConnection(params)
        except pika.exceptions.AMQPConnectionError:
            print(f"[worker:{WORKER_ID}] RabbitMQ not ready ({attempt}/{retries}), retrying...")
            time.sleep(delay)
    raise RuntimeError("RabbitMQ connection failed")


def classify_by_filename(image_url: str) -> tuple[str, str, float]:
    # 중간발표용 Mock 분석기: 실제 AI 대신 파일명 규칙으로 분류한다.
    filename = Path(image_url).name.lower()
    if "fire" in filename:
        return "FIRE", "HIGH", 0.92
    if "flood" in filename:
        return "FLOOD", "HIGH", 0.91
    if "smoke" in filename:
        return "FIRE", "MEDIUM", 0.82
    if "normal" in filename:
        return "NORMAL", "LOW", 0.88
    return "UNKNOWN", "LOW", 0.55


def handle_task(channel: pika.adapters.blocking_connection.BlockingChannel, method, properties, body: bytes) -> None:
    try:
        task = json.loads(body.decode("utf-8"))
        started = time.perf_counter()

        # 분석 시간이 걸리는 상황을 일부러 만든다. Worker 수에 따른 큐 변화를 보여주기 위함이다.
        time.sleep(0.3)
        category, risk_level, confidence = classify_by_filename(task["imageUrl"])
        processing_ms = int((time.perf_counter() - started) * 1000)

        result = {
            "taskId": task["taskId"],
            "reportId": task["reportId"],
            "imageId": task["imageId"],
            "imageUrl": task["imageUrl"],
            "location": task.get("location", ""),
            "description": task.get("description", ""),
            "uploadedAt": task.get("uploadedAt"),
            "category": category,
            "riskLevel": risk_level,
            "confidence": confidence,
            "processingMs": processing_ms,
            "analyzedAt": now_iso(),
            "workerId": WORKER_ID,
        }

        channel.basic_publish(
            exchange="",
            routing_key=RESULT_QUEUE,
            body=json.dumps(result, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)
        print(f"[worker:{WORKER_ID}] analyzed {result['reportId']} as {category}/{risk_level}")
    except Exception as exc:
        print(f"[worker:{WORKER_ID}] task failed, requeueing: {exc}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main() -> None:
    connection = connect_rabbitmq()
    channel = connection.channel()
    channel.queue_declare(queue=TASK_QUEUE, durable=True)
    channel.queue_declare(queue=RESULT_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=TASK_QUEUE, on_message_callback=handle_task)

    print(f"[worker:{WORKER_ID}] waiting for tasks from {TASK_QUEUE}")
    channel.start_consuming()


if __name__ == "__main__":
    main()
