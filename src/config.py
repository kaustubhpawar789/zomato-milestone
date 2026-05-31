"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _path_from_env(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    path = Path(raw)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path


PROJECT_ROOT = _PROJECT_ROOT
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
DATA_CACHE_PATH = _path_from_env("DATA_CACHE_PATH", "src/data/cache/restaurants.parquet")
INGESTION_METADATA_PATH = _path_from_env(
    "INGESTION_METADATA_PATH", "src/data/cache/ingestion_metadata.json"
)
TOP_N_RECOMMENDATIONS = int(os.getenv("TOP_N_RECOMMENDATIONS", "5"))
MAX_CANDIDATES_FOR_LLM = int(os.getenv("MAX_CANDIDATES_FOR_LLM", "50"))
MIN_CITY_SAMPLE_SIZE = int(os.getenv("MIN_CITY_SAMPLE_SIZE", "30"))
HF_DATASET_ID = os.getenv("HF_DATASET_ID", "ManikaSaini/zomato-restaurant-recommendation")
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "1.0.0")
