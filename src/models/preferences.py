"""User preference models for the recommendation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Budget(str, Enum):
    """User budget tier mapped to dataset cost percentiles."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def from_str(cls, value: str) -> "Budget":
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            raise ValueError(
                f"Invalid budget '{value}'. Choose one of: low, medium, high."
            ) from exc


DEFAULT_MIN_RATING = 3.5


@dataclass
class UserPreferences:
    """
    End-user constraints collected before filtering.

    Validation is applied in Phase 3; this model holds the typed contract.
    """

    location: str
    budget: Budget
    cuisine: Optional[str] = None
    min_rating: float = DEFAULT_MIN_RATING
    additional_preferences: List[str] = field(default_factory=list)

    @property
    def location_normalized(self) -> str:
        return " ".join(self.location.strip().split()).casefold()

    @property
    def cuisine_normalized(self) -> str:
        if not self.cuisine:
            return ""
        return " ".join(self.cuisine.strip().split()).casefold()

    @property
    def additional_preferences_normalized(self) -> List[str]:
        return [
            " ".join(tag.strip().split()).casefold()
            for tag in self.additional_preferences
            if tag and tag.strip()
        ]

    def to_dict(self) -> dict:
        return {
            "location": self.location,
            "budget": self.budget.value,
            "cuisine": self.cuisine,
            "min_rating": self.min_rating,
            "additional_preferences": list(self.additional_preferences),
        }
