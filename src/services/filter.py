"""
Candidate filter service — deterministic narrowing before LLM calls.

Pipeline order: location → cuisine → rating → budget → additional keywords.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from src import config
from src.models.preferences import Budget, UserPreferences
from src.models.restaurant import BudgetThresholds, IngestionMetadata, Restaurant
from src.services.validation import validate_preferences

logger = logging.getLogger(__name__)

# User-facing location aliases (EC-V-021)
LOCATION_ALIASES = {
    "blr": "bangalore",
    "bengaluru": "bangalore",
    "bengalore": "bangalore",
    "banglore": "bangalore",
}


@dataclass
class FilterResult:
    """Output of the candidate filter pipeline."""

    candidates: List[Restaurant] = field(default_factory=list)
    relaxed_constraints: List[str] = field(default_factory=list)
    truncated: bool = False
    hints: List[str] = field(default_factory=list)
    pre_truncate_count: int = 0

    @property
    def is_empty(self) -> bool:
        return len(self.candidates) == 0


def _normalize_location_query(location: str) -> str:
    normalized = " ".join(location.strip().split()).casefold()
    return LOCATION_ALIASES.get(normalized, normalized)


def _match_location(restaurant: Restaurant, location_query: str) -> bool:
    """Match city, locality, listed area, or address (contains, case-insensitive)."""
    if not location_query:
        return False
    listed_norm = " ".join(restaurant.listed_area.split()).casefold() if restaurant.listed_area else ""
    searchable = (
        restaurant.city_normalized,
        restaurant.location_normalized,
        listed_norm,
        restaurant.address.casefold(),
    )
    return any(location_query in text for text in searchable if text)


def _match_cuisine(restaurant: Restaurant, cuisine_query: str) -> bool:
    if not cuisine_query:
        return True
    if cuisine_query in restaurant.cuisines_normalized:
        return True
    tokens = [t.strip() for t in cuisine_query.replace(",", " ").split() if t.strip()]
    return any(token in restaurant.cuisines_normalized for token in tokens)


def _match_rating(restaurant: Restaurant, min_rating: float) -> bool:
    return restaurant.rating >= min_rating


def _match_budget(
    restaurant: Restaurant,
    budget: Budget,
    thresholds: BudgetThresholds,
) -> bool:
    cost = restaurant.approximate_cost
    if cost is None:
        # Include unknown-cost venues in non-budget-specific searches (EC-F-021)
        return True
    tier = thresholds.tier_for_cost(cost)
    if tier is None:
        return True
    return tier == budget.value


def _searchable_text(restaurant: Restaurant) -> str:
    parts = [
        restaurant.name,
        restaurant.cuisines,
        restaurant.rest_type,
        restaurant.location,
        restaurant.address,
        restaurant.listed_area,
        restaurant.online_order,
        restaurant.book_table,
    ]
    return " ".join(p for p in parts if p).casefold()


def _match_additional_preferences(
    restaurant: Restaurant,
    tags: Sequence[str],
) -> bool:
    """OR match: any tag found in restaurant text (EC-F-016)."""
    if not tags:
        return True
    haystack = _searchable_text(restaurant)
    return any(tag in haystack for tag in tags)


def _resolve_budget_thresholds(
    restaurants: Sequence[Restaurant],
    prefs: UserPreferences,
    metadata: IngestionMetadata,
) -> BudgetThresholds:
    """Pick per-city thresholds when location resolves to a dominant city."""
    location_query = _normalize_location_query(prefs.location)
    city_counts: dict[str, int] = {}
    for r in restaurants:
        if _match_location(r, location_query):
            city_counts[r.city_normalized] = city_counts.get(r.city_normalized, 0) + 1
    if city_counts:
        dominant_city = max(city_counts, key=city_counts.get)
        per_city = metadata.budget_thresholds_per_city
        if dominant_city in per_city:
            return per_city[dominant_city]
    return metadata.budget_thresholds_global


def _run_pipeline(
    restaurants: Sequence[Restaurant],
    prefs: UserPreferences,
    *,
    apply_cuisine: bool,
    apply_additional: bool,
    thresholds: BudgetThresholds,
) -> List[Restaurant]:
    location_query = _normalize_location_query(prefs.location)
    cuisine_query = prefs.cuisine_normalized if apply_cuisine else ""
    tags = prefs.additional_preferences_normalized if apply_additional else []

    result: List[Restaurant] = []
    for restaurant in restaurants:
        if not _match_location(restaurant, location_query):
            continue
        if apply_cuisine and cuisine_query and not _match_cuisine(restaurant, cuisine_query):
            continue
        if not _match_rating(restaurant, prefs.min_rating):
            continue
        if not _match_budget(restaurant, prefs.budget, thresholds):
            continue
        if apply_additional and tags and not _match_additional_preferences(restaurant, tags):
            continue
        result.append(restaurant)

    return result


def _sort_candidates(candidates: List[Restaurant], budget: Budget) -> List[Restaurant]:
    """Sort by rating desc; use votes and cost fit as tie-breakers."""

    def cost_fit_score(restaurant: Restaurant) -> float:
        if restaurant.approximate_cost is None:
            return 0.0
        cost = float(restaurant.approximate_cost)
        if budget == Budget.LOW:
            return -cost
        if budget == Budget.HIGH:
            return cost
        return -abs(cost - 500.0)

    return sorted(
        candidates,
        key=lambda r: (r.rating, cost_fit_score(r), r.votes or 0),
        reverse=True,
    )


def _truncate(candidates: List[Restaurant], prefs: UserPreferences, max_candidates: int) -> tuple[List[Restaurant], bool]:
    if len(candidates) <= max_candidates:
        return candidates, False
    sorted_candidates = _sort_candidates(candidates, prefs.budget)
    return sorted_candidates[:max_candidates], True


def _empty_hints(prefs: UserPreferences, relaxed_cuisine: bool) -> List[str]:
    hints = [
        "Try lowering the minimum rating.",
        "Try a different budget tier.",
        "Try a broader location (e.g. Bangalore).",
    ]
    if prefs.cuisine and not relaxed_cuisine:
        hints.insert(0, "Try removing or changing the cuisine filter.")
    elif relaxed_cuisine:
        hints.insert(0, "Cuisine filter was relaxed; still no matches for other criteria.")
    return hints


class CandidateFilterService:
    """Applies the ordered filter pipeline with fallbacks from architecture §3.3."""

    def __init__(
        self,
        metadata: IngestionMetadata,
        max_candidates: Optional[int] = None,
        get_thresholds: Optional[Callable[[Sequence[Restaurant], UserPreferences], BudgetThresholds]] = None,
    ) -> None:
        self._metadata = metadata
        self._max_candidates = max_candidates or config.MAX_CANDIDATES_FOR_LLM
        if get_thresholds is not None:
            self._get_thresholds = get_thresholds
        else:
            self._get_thresholds = lambda restaurants, prefs: _resolve_budget_thresholds(
                restaurants, prefs, metadata
            )

    def _filter_with_options(
        self,
        restaurants: Sequence[Restaurant],
        prefs: UserPreferences,
        *,
        apply_cuisine: bool,
        thresholds: BudgetThresholds,
    ) -> List[Restaurant]:
        """Core pipeline, then optional keyword pass (skipped if it would zero results)."""
        candidates = _run_pipeline(
            restaurants,
            prefs,
            apply_cuisine=apply_cuisine,
            apply_additional=False,
            thresholds=thresholds,
        )
        if not prefs.additional_preferences_normalized or not candidates:
            return candidates

        with_keywords = _run_pipeline(
            restaurants,
            prefs,
            apply_cuisine=apply_cuisine,
            apply_additional=True,
            thresholds=thresholds,
        )
        if with_keywords:
            return with_keywords
        logger.info("Skipping additional_preferences filter (zero matches)")
        return candidates

    def apply(self, restaurants: List[Restaurant], prefs: UserPreferences) -> FilterResult:
        """
        Filter restaurants to a bounded candidate set (≤ max_candidates).

        Validates preferences, runs pipeline, relaxes cuisine once if needed,
        and truncates overflow by rating.
        """
        validate_preferences(prefs)
        thresholds = self._get_thresholds(restaurants, prefs)
        relaxed: List[str] = []

        candidates = self._filter_with_options(
            restaurants,
            prefs,
            apply_cuisine=bool(prefs.cuisine_normalized),
            thresholds=thresholds,
        )

        # EC-F-002: relax cuisine once
        if not candidates and prefs.cuisine_normalized:
            candidates = self._filter_with_options(
                restaurants,
                prefs,
                apply_cuisine=False,
                thresholds=thresholds,
            )
            relaxed.append("cuisine")
            logger.info("Relaxed cuisine constraint; %s candidates", len(candidates))

        pre_truncate_count = len(candidates)
        truncated = False
        if pre_truncate_count > self._max_candidates:
            candidates, truncated = _truncate(candidates, prefs, self._max_candidates)

        hints: List[str] = []
        if not candidates:
            hints = _empty_hints(prefs, relaxed_cuisine="cuisine" in relaxed)

        return FilterResult(
            candidates=candidates,
            relaxed_constraints=relaxed,
            truncated=truncated,
            hints=hints,
            pre_truncate_count=pre_truncate_count,
        )


# Module-level convenience API (implementation plan deliverable name)
_filter_service: Optional[CandidateFilterService] = None


def get_filter_service(metadata: IngestionMetadata) -> CandidateFilterService:
    global _filter_service
    if _filter_service is None or _filter_service._metadata is not metadata:
        _filter_service = CandidateFilterService(metadata)
    return _filter_service


def apply_filter(
    restaurants: List[Restaurant],
    prefs: UserPreferences,
    metadata: IngestionMetadata,
) -> FilterResult:
    """filter_service.apply(restaurants, prefs) entrypoint."""
    return CandidateFilterService(metadata).apply(restaurants, prefs)
