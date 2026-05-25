import json
import os
import time

import pika
import redis


RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
RESULT_QUEUE = os.getenv("RESULT_QUEUE", "analysis.result.queue")
RECENT_LIMIT = int(os.getenv("RECENT_LIMIT", "50"))


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
            print(f"[aggregator] RabbitMQ not ready ({attempt}/{retries}), retrying...")
            time.sleep(delay)
    raise RuntimeError("RabbitMQ connection failed")


def connect_redis(retries: int = 60, delay: float = 2.0) -> redis.Redis:
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    for attempt in range(1, retries + 1):
        try:
            client.ping()
            return client
        except redis.RedisError:
            print(f"[aggregator] Redis not ready ({attempt}/{retries}), retrying...")
            time.sleep(delay)
    raise RuntimeError("Redis connection failed")


def save_result(client: redis.Redis, result: dict) -> None:
    report_id = result["reportId"]
    category = result.get("category", "UNKNOWN")
    risk_level = result.get("riskLevel", "LOW")
    processing_ms = int(result.get("processingMs", 0))

    # 같은 reportId가 재전달되어도 통계가 중복 증가하지 않도록 처리 여부를 기록한다.
    is_new = client.setnx(f"processed:{report_id}", "1")
    client.set(f"report:{report_id}", json.dumps(result, ensure_ascii=False))
    client.lrem("recent_reports", 0, report_id)
    client.lpush("recent_reports", report_id)
    client.ltrim("recent_reports", 0, RECENT_LIMIT - 1)

    if is_new:
        client.incr("stats:totalReports")
        client.incr(f"stats:category:{category}")
        client.incr(f"stats:risk:{risk_level}")
        client.incrby("stats:processingMs:sum", processing_ms)


def handle_result(client: redis.Redis):
    def callback(channel: pika.adapters.blocking_connection.BlockingChannel, method, properties, body: bytes) -> None:
        try:
            result = json.loads(body.decode("utf-8"))
            save_result(client, result)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            print(f"[aggregator] saved result for {result['reportId']}")
        except Exception as exc:
            print(f"[aggregator] failed to save result, requeueing: {exc}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    return callback


def main() -> None:
    redis_client = connect_redis()
    connection = connect_rabbitmq()
    channel = connection.channel()
    channel.queue_declare(queue=RESULT_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=RESULT_QUEUE, on_message_callback=handle_result(redis_client))

    print(f"[aggregator] waiting for results from {RESULT_QUEUE}")
    channel.start_consuming()


if __name__ == "__main__":
    main()
