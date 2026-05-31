"""
Data ingestion: load Zomato dataset from Hugging Face, normalize, cache as Parquet.

Schema mapping (HF column -> internal field):
  name -> name
  location -> location (locality)
  address -> address (+ city extraction)
  listed_in(city) -> listed_area
  cuisines -> cuisines
  rate -> rating
  approx_cost(for two people) -> approximate_cost, cost_for_two
  votes -> votes
  rest_type -> rest_type
  online_order, book_table -> preserved as-is
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from datasets import load_dataset

from src import config
from src.models.restaurant import BudgetThresholds, IngestionMetadata, Restaurant

logger = logging.getLogger(__name__)

# Hugging Face column -> internal canonical field
COLUMN_MAPPING: Dict[str, str] = {
    "name": "name",
    "location": "location",
    "address": "address",
    "listed_in(city)": "listed_area",
    "cuisines": "cuisines",
    "rate": "rating",
    "approx_cost(for two people)": "cost_for_two",
    "votes": "votes",
    "rest_type": "rest_type",
    "online_order": "online_order",
    "book_table": "book_table",
}

# Columns present in HF dataset but not mapped to core Restaurant fields
UNMAPPED_COLUMNS = [
    "url",
    "dish_liked",
    "reviews_list",
    "menu_item",
    "listed_in(type)",
    "phone",
]

CITY_ALIASES: Dict[str, str] = {
    "bengaluru": "bangalore",
    "banglore": "bangalore",
    "bengalore": "bangalore",
    "blr": "bangalore",
}

KNOWN_CITY_TOKENS = {
    "bangalore",
    "bengaluru",
    "delhi",
    "mumbai",
    "chennai",
    "hyderabad",
    "kolkata",
    "pune",
    "gurgaon",
    "noida",
    "india",
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).casefold()


def _extract_city_from_address(address: str) -> str:
    """Heuristic: use last comma-separated segment; normalize known aliases."""
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if not parts:
        return ""
    candidate = parts[-1]
    normalized = _normalize_text(candidate)
    if normalized in CITY_ALIASES:
        return CITY_ALIASES[normalized]
    # If last segment is not a major city, scan address parts right-to-left
    for part in reversed(parts):
        token = _normalize_text(part)
        if token in CITY_ALIASES:
            return CITY_ALIASES[token]
        if token in KNOWN_CITY_TOKENS:
            return CITY_ALIASES.get(token, token)
    return CITY_ALIASES.get(normalized, normalized)


def parse_rating(raw: Any) -> Optional[float]:
    """Parse values like '4.1/5', drop '-', 'NEW', empty."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in ("-", "NEW"):
        return None
    match = re.match(r"^([\d.]+)", text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if value < 0 or value > 5:
        return max(0.0, min(5.0, value))
    return value


def parse_cost(raw: Any) -> Optional[int]:
    """Extract integer cost from strings like '800' or '₹1,200 for two'."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _make_restaurant_id(name: str, city: str, location: str, row_index: int) -> str:
    payload = f"{name}|{city}|{location}|{row_index}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _compute_percentiles(costs: pd.Series) -> BudgetThresholds:
    valid = costs.dropna()
    if valid.empty:
        return BudgetThresholds(p33=0.0, p66=0.0, sample_size=0)
    return BudgetThresholds(
        p33=float(valid.quantile(0.33)),
        p66=float(valid.quantile(0.66)),
        sample_size=int(len(valid)),
    )


def compute_budget_thresholds(df: pd.DataFrame) -> Tuple[BudgetThresholds, Dict[str, BudgetThresholds]]:
    """Global and per-city percentile thresholds for budget tiers."""
    global_thresholds = _compute_percentiles(df["approximate_cost"])
    per_city: Dict[str, BudgetThresholds] = {}
    min_samples = config.MIN_CITY_SAMPLE_SIZE

    for city, group in df.groupby("city_normalized"):
        if not city:
            continue
        costs = group["approximate_cost"]
        if len(costs.dropna()) >= min_samples:
            per_city[str(city)] = _compute_percentiles(costs)
        else:
            per_city[str(city)] = global_thresholds

    return global_thresholds, per_city


def _transform_raw_dataframe(raw_df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Map HF columns to canonical schema and drop incomplete rows."""
    records: List[Dict[str, Any]] = []
    dropped = 0

    for row_index, row in raw_df.iterrows():
        name = str(row.get("name") or "").strip()
        location = str(row.get("location") or "").strip()
        address = str(row.get("address") or "").strip()
        rating = parse_rating(row.get("rate"))

        if not name or not location or rating is None:
            dropped += 1
            continue

        city = _extract_city_from_address(address)
        if not city:
            city = _normalize_text(row.get("listed_in(city)"))

        cost_raw = row.get("approx_cost(for two people)")
        approximate_cost = parse_cost(cost_raw)
        cuisines = str(row.get("cuisines") or "").strip()

        restaurant_id = _make_restaurant_id(name, city, location, int(row_index))

        records.append(
            {
                "id": restaurant_id,
                "name": name,
                "location": location,
                "city": city,
                "cuisines": cuisines,
                "rating": rating,
                "approximate_cost": approximate_cost,
                "address": address,
                "cost_for_two": str(cost_raw or "").strip(),
                "location_normalized": _normalize_text(location),
                "city_normalized": _normalize_text(city),
                "cuisines_normalized": _normalize_text(cuisines),
                "listed_area": str(row.get("listed_in(city)") or "").strip(),
                "rest_type": str(row.get("rest_type") or "").strip(),
                "votes": int(row["votes"]) if pd.notna(row.get("votes")) else None,
                "online_order": str(row.get("online_order") or "").strip(),
                "book_table": str(row.get("book_table") or "").strip(),
            }
        )

    logger.info("Transformation complete: kept=%s dropped=%s", len(records), dropped)
    return pd.DataFrame(records), dropped


def _load_hf_dataset() -> pd.DataFrame:
    logger.info("Loading dataset from Hugging Face: %s", config.HF_DATASET_ID)
    dataset = load_dataset(config.HF_DATASET_ID, split="train")
    logger.info("HF dataset loaded: %s rows, columns=%s", len(dataset), dataset.column_names)
    return dataset.to_pandas()


def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp_path, index=False)
    tmp_path.replace(path)


def _atomic_write_json(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp_path.replace(path)


def run_ingestion(force_refresh: bool = False) -> Tuple[pd.DataFrame, IngestionMetadata]:
    """
    Download (if needed), transform, compute budget thresholds, and write cache.
    """
    cache_path = config.DATA_CACHE_PATH
    metadata_path = config.INGESTION_METADATA_PATH

    if not force_refresh and cache_path.exists() and metadata_path.exists():
        return load_from_cache()

    raw_df = _load_hf_dataset()
    raw_row_count = len(raw_df)

    processed_df, dropped = _transform_raw_dataframe(raw_df)
    if processed_df.empty:
        raise RuntimeError(
            "No usable restaurant records after preprocessing. Check dataset and mapping."
        )

    global_thresholds, per_city_thresholds = compute_budget_thresholds(processed_df)
    sync_time = datetime.now(timezone.utc).isoformat()

    metadata = IngestionMetadata(
        schema_version=config.SCHEMA_VERSION,
        source=config.HF_DATASET_ID,
        row_count=len(processed_df),
        raw_row_count=raw_row_count,
        dropped_incomplete=dropped,
        last_sync_at=sync_time,
        cache_path=str(cache_path),
        cache_hit=False,
        budget_thresholds_global=global_thresholds,
        budget_thresholds_per_city=per_city_thresholds,
        column_mapping=COLUMN_MAPPING,
        unmapped_columns=UNMAPPED_COLUMNS,
    )

    _atomic_write_parquet(processed_df, cache_path)
    _atomic_write_json(metadata.to_dict(), metadata_path)

    logger.info(
        "Ingestion complete: rows=%s dropped=%s cache=%s global_p33=%.0f global_p66=%.0f",
        metadata.row_count,
        dropped,
        cache_path,
        global_thresholds.p33,
        global_thresholds.p66,
    )
    return processed_df, metadata


def load_from_cache() -> Tuple[pd.DataFrame, IngestionMetadata]:
    """Load processed restaurants and metadata from local cache."""
    cache_path = config.DATA_CACHE_PATH
    metadata_path = config.INGESTION_METADATA_PATH

    if not cache_path.exists():
        raise FileNotFoundError(f"Cache not found at {cache_path}. Run ingestion first.")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata not found at {metadata_path}. Run ingestion first.")

    if metadata_path.stat().st_size == 0:
        raise ValueError(f"Corrupt metadata file (empty): {metadata_path}")

    try:
        df = pd.read_parquet(cache_path)
    except Exception as exc:
        raise ValueError(f"Corrupt or unreadable cache at {cache_path}: {exc}") from exc

    with metadata_path.open(encoding="utf-8") as f:
        metadata_dict = json.load(f)

    metadata = IngestionMetadata.from_dict(metadata_dict)
    metadata.cache_hit = True
    metadata.cache_path = str(cache_path)

    logger.info(
        "Cache hit: loaded %s restaurants (schema=%s, synced=%s)",
        len(df),
        metadata.schema_version,
        metadata.last_sync_at,
    )
    return df, metadata


def initialize(force_refresh: bool = False) -> Tuple[List[Restaurant], IngestionMetadata]:
    """
    Cache-first entrypoint for app startup.

    Returns in-memory Restaurant list and ingestion metadata.
    """
    cache_path = config.DATA_CACHE_PATH
    metadata_path = config.INGESTION_METADATA_PATH

    if (
        not force_refresh
        and cache_path.exists()
        and metadata_path.exists()
        and metadata_path.stat().st_size > 0
    ):
        try:
            df, metadata = load_from_cache()
            if metadata.schema_version != config.SCHEMA_VERSION:
                logger.warning(
                    "Schema version mismatch (cache=%s, expected=%s). Re-ingesting.",
                    metadata.schema_version,
                    config.SCHEMA_VERSION,
                )
                df, metadata = run_ingestion(force_refresh=True)
        except (ValueError, FileNotFoundError) as exc:
            logger.warning("Cache load failed (%s). Re-ingesting.", exc)
            df, metadata = run_ingestion(force_refresh=True)
    else:
        df, metadata = run_ingestion(force_refresh=force_refresh)

    restaurants = [Restaurant.from_row(row) for row in df.to_dict(orient="records")]
    return restaurants, metadata


def main() -> None:
    """CLI entrypoint: python -m src.data.ingestion [--force]"""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Ingest Zomato dataset and build local cache.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and rebuild cache even if Parquet exists.",
    )
    args = parser.parse_args()

    restaurants, metadata = initialize(force_refresh=args.force)
    print(f"Ingestion OK: {len(restaurants)} restaurants")
    print(f"  Raw rows:     {metadata.raw_row_count}")
    print(f"  Dropped:      {metadata.dropped_incomplete}")
    print(f"  Cache:        {metadata.cache_path}")
    print(f"  Cache hit:    {metadata.cache_hit}")
    print(f"  Synced at:    {metadata.last_sync_at}")
    print(
        f"  Budget (global): low≤{metadata.budget_thresholds_global.p33:.0f}, "
        f"medium≤{metadata.budget_thresholds_global.p66:.0f}, "
        f"high>{metadata.budget_thresholds_global.p66:.0f}"
    )
    print(f"  Per-city maps: {len(metadata.budget_thresholds_per_city)} cities")


if __name__ == "__main__":
    main()
