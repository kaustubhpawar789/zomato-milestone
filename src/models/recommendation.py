"""Recommendation result models returned by the orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.models.restaurant import Restaurant


@dataclass(frozen=True)
class Recommendation:
    """A single ranked recommendation with LLM explanation."""

    restaurant_id: str
    rank: int
    explanation: str
    restaurant: Optional[Restaurant] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "restaurant_id": self.restaurant_id,
            "rank": self.rank,
            "explanation": self.explanation,
        }
        if self.restaurant is not None:
            payload["restaurant"] = self.restaurant.to_dict()
        return payload


@dataclass
class RecommendationResponse:
    """Full response from get_recommendations()."""

    recommendations: List[Recommendation] = field(default_factory=list)
    summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def result_count(self) -> int:
        return len(self.recommendations)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendations": [r.to_dict() for r in self.recommendations],
            "summary": self.summary,
            "metadata": dict(self.metadata),
        }
