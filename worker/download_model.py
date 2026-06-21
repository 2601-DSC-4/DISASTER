import os

from transformers import AutoConfig, AutoImageProcessor, AutoModelForImageClassification


MODEL_NAME = os.getenv("MODEL_NAME", "Luwayy/disaster_images_model")


def model_is_cached() -> bool:
    try:
        AutoConfig.from_pretrained(MODEL_NAME, local_files_only=True)
        AutoImageProcessor.from_pretrained(MODEL_NAME, local_files_only=True)
        AutoModelForImageClassification.from_pretrained(MODEL_NAME, local_files_only=True)
        return True
    except Exception as exc:
        print(f"[model-download] cache miss for {MODEL_NAME}: {exc}")
        return False


def main() -> None:
    if model_is_cached():
        print(f"[model-download] using cached model {MODEL_NAME}")
        return

    print(f"[model-download] downloading {MODEL_NAME}")
    AutoConfig.from_pretrained(MODEL_NAME)
    AutoImageProcessor.from_pretrained(MODEL_NAME)
    AutoModelForImageClassification.from_pretrained(MODEL_NAME)
    print(f"[model-download] downloaded {MODEL_NAME}")


if __name__ == "__main__":
    main()
