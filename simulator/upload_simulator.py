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
    location = "서울시 동대문구"
    description = f"{MODE} mode upload #{index} from {image_path.name}"

    with image_path.open("rb") as file_obj:
        files = {"image": (image_path.name, file_obj, "image/jpeg")}
        data = {"location": location, "description": description}
        response = requests.post(f"{BACKEND_URL}/reports", files=files, data=data, timeout=10)
        response.raise_for_status()
        print(f"[simulator] uploaded {image_path.name}: {response.json()['reportId']}")


def main() -> None:
    images = sorted(SAMPLE_DIR.glob("*.jpg"))
    if not images:
        raise RuntimeError(f"no sample images found in {SAMPLE_DIR}")

    wait_for_backend()
    print(f"[simulator] mode={MODE}, rate={RATE}/sec, duration={DURATION}s")

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


if __name__ == "__main__":
    main()
