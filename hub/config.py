"""Settings read from the environment (.env is loaded by hub.main)."""

import os
from pathlib import Path

BASE_URL = os.environ.get("MODEL_BASE_URL", "https://api.meta.ai/v1")
SPARK_MODEL = os.environ.get("SPARK_MODEL", "muse-spark-1.3")
ASR_URL = os.environ.get("ASR_URL", "wss://api.meta.ai/v1/asr/realtime")
ASR_MODEL = os.environ.get("ASR_MODEL", "muse-voice-transcribe-1.0")
DATA_DIR = Path(os.environ.get("CUEON_DATA", "data"))


def api_key() -> str | None:
    return os.environ.get("MODEL_API_KEY") or None


def fake_mode() -> bool:
    """Run on stand-ins when asked to, or when there is no key to call the real models with."""
    return os.environ.get("CUEON_FAKE") == "1" or api_key() is None
