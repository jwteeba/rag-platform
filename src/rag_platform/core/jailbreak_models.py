"""Download and prepare the local models used by DetectJailbreak."""

from __future__ import annotations

import json
import os
from pathlib import Path

from huggingface_hub import snapshot_download

DETECT_JAILBREAK_REPOSITORY = "zhx123/ftrobertallm"
DETECT_JAILBREAK_MODEL_DIR = (
    Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    / "detect-jailbreak-classifier"
)


def download_models() -> None:
    """Fetch all DetectJailbreak models and normalize its classifier config.

    The classifier repository stores integer values in ``id2label``. Transformers
    5 validates that values are strings, so normalize the local copy and configure
    DetectJailbreak to compare its returned labels as strings.
    """
    from transformers import AutoModel, AutoTokenizer, pipeline

    print("Fetching DetectJailbreak saturation model")
    AutoModel.from_pretrained("GuardrailsAI/prompt-saturation-attack-detector")
    AutoTokenizer.from_pretrained("google-bert/bert-base-cased")

    print("Fetching DetectJailbreak embedding model")
    AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
    AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

    print("Fetching DetectJailbreak classifier")
    model_dir = snapshot_download(
        repo_id=DETECT_JAILBREAK_REPOSITORY,
        local_dir=DETECT_JAILBREAK_MODEL_DIR,
    )
    config_path = Path(model_dir) / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    id2label = config.get("id2label")
    if isinstance(id2label, dict):
        config["id2label"] = {str(label_id): str(label) for label_id, label in id2label.items()}
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    # Load once at build/setup time so an invalid model/config fails immediately.
    pipeline("text-classification", model_dir)
    print("DetectJailbreak models ready")


if __name__ == "__main__":
    download_models()
