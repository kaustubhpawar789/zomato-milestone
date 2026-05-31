"""
Restaurant repository — single source of truth for in-memory restaurant records.

Loads from the Phase 1 Parquet cache via ingestion.initialize().
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from src.data.ingestion import KNOWN_CITY_TOKENS, initialize
from src.models.restaurant import BudgetThresholds, IngestionMetadata, Restaurant

logger = logging.getLogger(__name__)

# Substrings that indicate a parsed "city" is actually an address fragment
_CITY_NOISE_MARKERS = (
    " road",
    " main",
    " block",
    " stage",
    " layout",
    " ring road",
    "delivery only",
    " feet ",
    " colony",
    " landmark",
)

_MIN_CITY_RESTAURANT_COUNT = 50


def _is_noise_city_label(city_normalized: str) -> bool:
    if len(city_normalized) > 40:
        return True
    return any(marker in city_normalized for marker in _CITY_NOISE_MARKERS)


def _display_city_name(city_normalized: str, labels: Counter) -> str:
    """Pick the most common display label; normalize well-known cities."""
    display, _ = labels.most_common(1)[0]
    if city_normalized in KNOWN_CITY_TOKENS:
        return city_normalized.title()
    if city_normalized == "bangalore":
        return "Bangalore"
    return display


class RestaurantRepository:
    """In-memory store of preprocessed restaurants and ingestion metadata."""

    def __init__(self) -> None:
        self._restaurants: List[Restaurant] = []
        self._by_id: Dict[str, Restaurant] = {}
        self._metadata: Optional[IngestionMetadata] = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def metadata(self) -> IngestionMetadata:
        if self._metadata is None:
            raise RuntimeError("Repository not loaded. Call load() first.")
        return self._metadata

    def load(self, force_refresh: bool = False) -> IngestionMetadata:
        """
        Load restaurants from cache (or run ingestion on cache miss).

        Returns ingestion metadata for budget thresholds and diagnostics.
        """
        restaurants, metadata = initialize(force_refresh=force_refresh)
        self._restaurants = restaurants
        self._by_id = {r.id: r for r in restaurants}
        self._metadata = metadata
        self._loaded = True
        logger.info(
            "Repository loaded: %s restaurants (cache_hit=%s)",
            len(self._restaurants),
            metadata.cache_hit,
        )
        return metadata

    def ensure_loaded(self, force_refresh: bool = False) -> None:
        if not self._loaded or force_refresh:
            self.load(force_refresh=force_refresh)

    def all(self) -> List[Restaurant]:
        """Return all restaurants for the filter pipeline."""
        self.ensure_loaded()
        return list(self._restaurants)

    def count(self) -> int:
        self.ensure_loaded()
        return len(self._restaurants)

    def get_by_id(self, restaurant_id: str) -> Optional[Restaurant]:
        """Lookup a single restaurant by stable id."""
        self.ensure_loaded()
        return self._by_id.get(restaurant_id)

    def get_many_by_ids(self, restaurant_ids: List[str]) -> List[Restaurant]:
        """Return restaurants for the given ids, preserving order, skipping unknown ids."""
        self.ensure_loaded()
        return [self._by_id[rid] for rid in restaurant_ids if rid in self._by_id]

    def unique_cities(self, min_restaurant_count: int = _MIN_CITY_RESTAURANT_COUNT) -> List[str]:
        """
        Distinct city names for UI dropdowns, sorted alphabetically.

        Groups by city_normalized, keeps cities with enough restaurants or known
        major-city tokens, and drops address-fragment noise from bad parsing.
        """
        self.ensure_loaded()
        label_counts: Dict[str, Counter] = defaultdict(Counter)
        totals: Counter = Counter()

        for restaurant in self._restaurants:
            key = restaurant.city_normalized
            if not key or _is_noise_city_label(key):
                continue
            label_counts[key][restaurant.city] += 1
            totals[key] += 1

        cities: List[str] = []
        for key, labels in label_counts.items():
            if totals[key] < min_restaurant_count and key not in KNOWN_CITY_TOKENS:
                continue
            cities.append(_display_city_name(key, labels))

        return sorted(set(cities), key=str.casefold)

    def unique_locations(self) -> List[str]:
        """Distinct locality names (normalized keys, display labels), sorted."""
        self.ensure_loaded()
        seen: Dict[str, str] = {}
        for restaurant in self._restaurants:
            key = restaurant.location_normalized
            if not key or key in seen:
                continue
            seen[key] = restaurant.location
        return sorted(seen.values(), key=str.casefold)

    def get_budget_thresholds(self, city_normalized: str) -> BudgetThresholds:
        """
        Return per-city budget percentiles, falling back to global thresholds.
        """
        meta = self.metadata
        city_key = city_normalized.strip().casefold()
        if city_key and city_key in meta.budget_thresholds_per_city:
            return meta.budget_thresholds_per_city[city_key]
        return meta.budget_thresholds_global

    def clear(self) -> None:
        """Reset in-memory state (useful for tests)."""
        self._restaurants = []
        self._by_id = {}
        self._metadata = None
        self._loaded = False


_default_repository: Optional[RestaurantRepository] = None


def get_repository() -> RestaurantRepository:
    """Return the process-wide singleton repository instance."""
    global _default_repository
    if _default_repository is None:
        _default_repository = RestaurantRepository()
    return _default_repository


def reset_repository() -> None:
    """Clear the singleton repository (for tests)."""
    global _default_repository
    if _default_repository is not None:
        _default_repository.clear()
    _default_repository = None
