import os
import time
from itertools import cycle
from pathlib import Path

import requests


BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
MODE = os.getenv("MODE", "normal").lower()
DEFAULT_RATE = 20 if MODE == "disaster" else 1
RATE = int(os.getenv("RATE", str(DEFAULT_RATE)))
DURATION = int(os.getenv("DURATION", "30"))
SAMPLE_DIR = Path(os.getenv("SAMPLE_DIR", "/app/sample_images"))

# 영상 데모용: 업로드가 끝난 뒤 RabbitMQ 작업 큐가 빌 때까지 기다리며 총 시간을 출력한다.
WAIT_FOR_QUEUE_DRAIN = os.getenv("WAIT_FOR_QUEUE_DRAIN", "true").lower() in {"1", "true", "yes"}
QUEUE_POLL_INTERVAL = float(os.getenv("QUEUE_POLL_INTERVAL", "1"))
QUEUE_DRAIN_TIMEOUT = int(os.getenv("QUEUE_DRAIN_TIMEOUT", "600"))


def wait_for_backend(retries: int = 60, delay: float = 2.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(f"{BACKEND_URL}/health", timeout=3)
            if response.ok:
                return
        except requests.RequestException:
            pass
        print(f"[simulator] backend not ready ({attempt}/{retries}), retrying...")
        time.sleep(delay)
    raise RuntimeError("backend is not reachable")


def upload_image(image_path: Path, index: int) -> None:
    fname = image_path.name.lower()
    if "fire" in fname:
        location = "서울 강남구"
        description = "건물 화재 의심 신고"
    elif "water" in fname:
        location = "부산 해운대구"
        description = "도로 침수 신고"
    elif "land" in fname:
        location = "강원 춘천시"
        description = "산사태 의심 신고"
    else:
        location = "서울 동대문구"
        description = f"일반 상황 제보 #{index} ({image_path.name})"

    with image_path.open("rb") as file_obj:
        files = {"image": (image_path.name, file_obj, "image/jpeg")}
        data = {"location": location, "description": description}
        response = requests.post(f"{BACKEND_URL}/reports", files=files, data=data, timeout=10)
        response.raise_for_status()
        print(f"[simulator] uploaded {image_path.name}: {response.json()['reportId']}")


def get_queue_length() -> int:
    response = requests.get(f"{BACKEND_URL}/queue/status", timeout=5)
    response.raise_for_status()
    return int(response.json().get("messages", 0))


def wait_for_queue_drain(started_at: float) -> None:
    if not WAIT_FOR_QUEUE_DRAIN:
        elapsed = time.perf_counter() - started_at
        print("[simulator] queue empty wait disabled")
        print(f"[simulator] total seconds: {elapsed:.2f}")
        return

    print("[simulator] waiting until image.task.queue becomes empty...")
    deadline = time.time() + QUEUE_DRAIN_TIMEOUT

    while True:
        try:
            queue_length = get_queue_length()
            print(f"Current queue length: {queue_length}")
            if queue_length <= 0:
                elapsed = time.perf_counter() - started_at
                print("[simulator] queue empty")
                print(f"[simulator] total seconds: {elapsed:.2f}")
                return
        except requests.RequestException as exc:
            print(f"[simulator] queue status check failed: {exc}")

        if time.time() >= deadline:
            elapsed = time.perf_counter() - started_at
            print(f"[simulator] queue empty timeout after {QUEUE_DRAIN_TIMEOUT}s")
            print(f"[simulator] total seconds: {elapsed:.2f}")
            return

        time.sleep(QUEUE_POLL_INTERVAL)


def main() -> None:
    images = sorted(SAMPLE_DIR.glob("*.jpg"))
    if not images:
        raise RuntimeError(f"no sample images found in {SAMPLE_DIR}")

    wait_for_backend()
    print(f"[simulator] mode={MODE}, rate={RATE}/sec, duration={DURATION}s")

    started_at = time.perf_counter()
    interval = 1 / max(RATE, 1)
    deadline = time.time() + DURATION
    image_cycle = cycle(images)
    count = 0
    next_tick = time.time()

    while time.time() < deadline:
        image_path = next(image_cycle)
        count += 1
        try:
            upload_image(image_path, count)
        except requests.RequestException as exc:
            print(f"[simulator] upload failed: {exc}")

        next_tick += interval
        sleep_for = next_tick - time.time()
        if sleep_for > 0:
            time.sleep(sleep_for)

    print(f"[simulator] finished, attempted uploads={count}")
    wait_for_queue_drain(started_at)


if __name__ == "__main__":
    main()
