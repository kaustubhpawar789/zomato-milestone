"""User preference validation (fail closed with field-level errors)."""

from __future__ import annotations

from typing import Dict, Optional

from src.models.preferences import DEFAULT_MIN_RATING, Budget, UserPreferences


class ValidationError(Exception):
    """Raised when user preferences fail validation."""

    def __init__(self, errors: Dict[str, str]) -> None:
        self.errors = dict(errors)
        message = "; ".join(f"{field}: {msg}" for field, msg in self.errors.items())
        super().__init__(message)


def validate_preferences(prefs: UserPreferences) -> None:
    """
    Validate preferences before filtering.

    Raises:
        ValidationError: actionable field-level error messages.
    """
    errors: Dict[str, str] = {}

    if not prefs.location or not prefs.location.strip():
        errors["location"] = "Location is required."

    if not isinstance(prefs.budget, Budget):
        errors["budget"] = "Select a budget: low, medium, or high."

    if prefs.min_rating < 0 or prefs.min_rating > 5:
        errors["min_rating"] = "Rating must be between 0 and 5."

    if prefs.cuisine is not None and len(prefs.cuisine.strip()) > 200:
        errors["cuisine"] = "Cuisine must be 200 characters or fewer."

    total_extra_len = sum(len(t) for t in prefs.additional_preferences)
    if total_extra_len > 500:
        errors["additional_preferences"] = "Additional preferences are too long (max 500 chars total)."

    if errors:
        raise ValidationError(errors)


def normalize_min_rating(value: Optional[float]) -> float:
    """Apply default min_rating when omitted by caller."""
    if value is None:
        return DEFAULT_MIN_RATING
    return float(value)
