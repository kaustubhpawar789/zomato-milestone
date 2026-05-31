"""Domain models for restaurants and ingestion metadata."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip().lower()
    if text in ("", "nan", "none"):
        return None
    return int(value)


@dataclass(frozen=True)
class Restaurant:
    """Canonical restaurant record after ingestion."""

    id: str
    name: str
    location: str
    city: str
    cuisines: str
    rating: float
    approximate_cost: Optional[int]
    address: str
    cost_for_two: str
    location_normalized: str
    city_normalized: str
    cuisines_normalized: str
    listed_area: str
    rest_type: str = ""
    votes: Optional[int] = None
    online_order: str = ""
    book_table: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for LLM prompts and API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "city": self.city,
            "cuisines": self.cuisines,
            "rating": self.rating,
            "approximate_cost": self.approximate_cost,
            "address": self.address,
            "cost_for_two": self.cost_for_two,
            "listed_area": self.listed_area,
            "rest_type": self.rest_type,
            "votes": self.votes,
            "online_order": self.online_order,
            "book_table": self.book_table,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Restaurant":
        return cls(
            id=str(row["id"]),
            name=str(row["name"]),
            location=str(row["location"]),
            city=str(row["city"]),
            cuisines=str(row["cuisines"]),
            rating=float(row["rating"]),
            approximate_cost=_optional_int(row.get("approximate_cost")),
            address=str(row.get("address") or ""),
            cost_for_two=str(row.get("cost_for_two") or ""),
            location_normalized=str(row["location_normalized"]),
            city_normalized=str(row["city_normalized"]),
            cuisines_normalized=str(row["cuisines_normalized"]),
            listed_area=str(row.get("listed_area") or ""),
            rest_type=str(row.get("rest_type") or ""),
            votes=_optional_int(row.get("votes")),
            online_order=str(row.get("online_order") or ""),
            book_table=str(row.get("book_table") or ""),
        )


@dataclass(frozen=True)
class BudgetThresholds:
    """Cost percentile boundaries for budget tiers (low / medium / high)."""

    p33: float
    p66: float
    sample_size: int

    def tier_for_cost(self, cost: Optional[int]) -> Optional[str]:
        if cost is None:
            return None
        if cost <= self.p33:
            return "low"
        if cost <= self.p66:
            return "medium"
        return "high"

    def to_dict(self) -> Dict[str, Any]:
        return {"p33": self.p33, "p66": self.p66, "sample_size": self.sample_size}


@dataclass
class IngestionMetadata:
    """Metadata written alongside the Parquet cache."""

    schema_version: str
    source: str
    row_count: int
    raw_row_count: int
    dropped_incomplete: int
    last_sync_at: str
    cache_path: str
    cache_hit: bool = False
    budget_thresholds_global: BudgetThresholds = field(
        default_factory=lambda: BudgetThresholds(0.0, 0.0, 0)
    )
    budget_thresholds_per_city: Dict[str, BudgetThresholds] = field(default_factory=dict)
    column_mapping: Dict[str, str] = field(default_factory=dict)
    unmapped_columns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "row_count": self.row_count,
            "raw_row_count": self.raw_row_count,
            "dropped_incomplete": self.dropped_incomplete,
            "last_sync_at": self.last_sync_at,
            "cache_path": self.cache_path,
            "cache_hit": self.cache_hit,
            "budget_thresholds": {
                "global": self.budget_thresholds_global.to_dict(),
                "per_city": {
                    city: t.to_dict() for city, t in self.budget_thresholds_per_city.items()
                },
            },
            "column_mapping": self.column_mapping,
            "unmapped_columns": self.unmapped_columns,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IngestionMetadata":
        global_raw = data.get("budget_thresholds", {}).get("global", {})
        per_city_raw = data.get("budget_thresholds", {}).get("per_city", {})
        return cls(
            schema_version=data["schema_version"],
            source=data["source"],
            row_count=data["row_count"],
            raw_row_count=data.get("raw_row_count", data["row_count"]),
            dropped_incomplete=data.get("dropped_incomplete", 0),
            last_sync_at=data["last_sync_at"],
            cache_path=data["cache_path"],
            cache_hit=data.get("cache_hit", False),
            budget_thresholds_global=BudgetThresholds(
                p33=float(global_raw.get("p33", 0)),
                p66=float(global_raw.get("p66", 0)),
                sample_size=int(global_raw.get("sample_size", 0)),
            ),
            budget_thresholds_per_city={
                city: BudgetThresholds(
                    p33=float(v["p33"]),
                    p66=float(v["p66"]),
                    sample_size=int(v["sample_size"]),
                )
                for city, v in per_city_raw.items()
            },
            column_mapping=data.get("column_mapping", {}),
            unmapped_columns=data.get("unmapped_columns", []),
        )
