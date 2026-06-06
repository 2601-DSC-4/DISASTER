import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pika
import redis
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware


RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/app/storage/reports"))
TASK_QUEUE = os.getenv("TASK_QUEUE", "image.task.queue")
RESULT_QUEUE = os.getenv("RESULT_QUEUE", "analysis.result.queue")
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Seoul"))

app = FastAPI(title="DISASTER Report API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def safe_filename(filename: str) -> str:
    # Windows/Linux 양쪽에서 문제가 될 수 있는 문자를 간단히 정리한다.
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in filename)


def rabbitmq_connection(retries: int = 30, delay: float = 2.0) -> pika.BlockingConnection:
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
            print(f"[backend] RabbitMQ not ready ({attempt}/{retries}), retrying...")
            time.sleep(delay)
    raise RuntimeError("RabbitMQ connection failed")


def redis_client(retries: int = 30, delay: float = 2.0) -> redis.Redis:
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    for attempt in range(1, retries + 1):
        try:
            client.ping()
            return client
        except redis.RedisError:
            print(f"[backend] Redis not ready ({attempt}/{retries}), retrying...")
            time.sleep(delay)
    raise RuntimeError("Redis connection failed")


def ensure_queues() -> None:
    connection = rabbitmq_connection()
    try:
        channel = connection.channel()
        channel.queue_declare(queue=TASK_QUEUE, durable=True)
        channel.queue_declare(queue=RESULT_QUEUE, durable=True)
    finally:
        connection.close()


@app.on_event("startup")
def startup() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_queues()
    redis_client()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports")
async def create_report(
    image: UploadFile = File(...),
    location: str = Form(...),
    description: str = Form(""),
) -> dict[str, Any]:
    report_id = f"report-{uuid.uuid4().hex[:12]}"
    image_id = f"img-{uuid.uuid4().hex[:12]}"
    original_name = safe_filename(image.filename or "upload.jpg")
    stored_name = f"{image_id}_{original_name}"
    stored_path = STORAGE_DIR / stored_name

    try:
        content = await image.read()
        stored_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"failed to save image: {exc}") from exc

    task = {
        "taskId": f"task-{uuid.uuid4().hex[:12]}",
        "reportId": report_id,
        "imageUrl": f"storage/reports/{stored_name}",
        "uploadedAt": now_iso(),
        "location": location,
        "description": description,
        "originalFilename": original_name,
    }

    try:
        connection = rabbitmq_connection()
        channel = connection.channel()
        channel.queue_declare(queue=TASK_QUEUE, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=TASK_QUEUE,
            body=json.dumps(task, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )
        connection.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"failed to publish task: {exc}") from exc

    return {
        "accepted": True,
        "reportId": report_id,
        "message": "report accepted and queued",
    }


@app.get("/reports/recent")
def recent_reports(limit: int = 20) -> dict[str, Any]:
    client = redis_client()
    report_ids = client.lrange("recent_reports", 0, max(limit - 1, 0))
    reports = []
    for report_id in report_ids:
        raw = client.get(f"report:{report_id}")
        if raw:
            reports.append(json.loads(raw))
    return {"items": reports}


@app.get("/stats/summary")
def stats_summary() -> dict[str, Any]:
    client = redis_client()

    total = int(client.get("stats:totalReports") or 0)
    processing_sum = int(client.get("stats:processingMs:sum") or 0)
    avg_processing = round(processing_sum / total, 2) if total else 0

    return {
        "totalReports": total,
        "categories": {
            "FIRE": int(client.get("stats:category:FIRE") or 0),
            "FLOOD": int(client.get("stats:category:FLOOD") or 0),
            "NORMAL": int(client.get("stats:category:NORMAL") or 0),
            "UNKNOWN": int(client.get("stats:category:UNKNOWN") or 0),
        },
        "risks": {
            "HIGH": int(client.get("stats:risk:HIGH") or 0),
            "MEDIUM": int(client.get("stats:risk:MEDIUM") or 0),
            "LOW": int(client.get("stats:risk:LOW") or 0),
        },
        "averageProcessingMs": avg_processing,
    }

@app.get("/stats/location")
def stats_by_location(limit: int = 5) -> dict[str, Any]:
    client = redis_client()
    
    # 1. 수집된 모든 고유 지역명(Set) 가져오기
    locations = client.smembers("stats:locations")
    
    location_stats = {}
    for loc in locations:
        # 2. 해당 지역의 총 신고 건수
        total = int(client.get(f"stats:location:{loc}:totalReports") or 0)
        
        # 3. 해당 지역의 최근 리포트 데이터 가져오기 (기본 최신 5개)
        report_ids = client.lrange(f"recent_reports:location:{loc}", 0, max(limit - 1, 0))
        recent_items = []
        for r_id in report_ids:
            raw = client.get(f"report:{r_id}")
            if raw:
                recent_items.append(json.loads(raw))
                
        # 4. 지역별 통계 구조 바인딩 (기존 stats/summary 포맷과 통일성 유지)
        location_stats[loc] = {
            "totalReports": total,
            "categories": {
                "FIRE": int(client.get(f"stats:location:{loc}:category:FIRE") or 0),
                "FLOOD": int(client.get(f"stats:location:{loc}:category:FLOOD") or 0),
                "NORMAL": int(client.get(f"stats:location:{loc}:category:NORMAL") or 0),
                "UNKNOWN": int(client.get(f"stats:location:{loc}:category:UNKNOWN") or 0),
            },
            "risks": {
                "HIGH": int(client.get(f"stats:location:{loc}:risk:HIGH") or 0),
                "MEDIUM": int(client.get(f"stats:location:{loc}:risk:MEDIUM") or 0),
                "LOW": int(client.get(f"stats:location:{loc}:risk:LOW") or 0),
            },
            "recentReports": recent_items
        }
        
    return {"locations": location_stats}

@app.get("/queue/status")
def queue_status() -> dict[str, Any]:
    try:
        connection = rabbitmq_connection()
        channel = connection.channel()
        queue = channel.queue_declare(queue=TASK_QUEUE, durable=True, passive=True)
        length = queue.method.message_count
        connection.close()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"failed to read queue status: {exc}") from exc
    return {"queue": TASK_QUEUE, "messages": length}
