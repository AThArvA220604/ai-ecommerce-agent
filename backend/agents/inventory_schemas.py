"""
Schemas for the AI-driven inventory suggestions.

The LLM reasons about restock quantity given:
  - current stock level
  - reorder threshold
  - 7-day sales velocity (units per day)
  - supplier lead time (days)
  - recent stockout history
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RestockUrgency(str, Enum):
    CRITICAL = "critical"   # order today, expedite shipping
    HIGH = "high"           # order within 1-2 days
    MEDIUM = "medium"       # order this week
    LOW = "low"             # monitor, no immediate action


class RestockSuggestion(BaseModel):
    """One restock recommendation from the Inventory agent."""

    product_id: str = Field(description="The product SKU this recommendation is for.")
    suggested_quantity: int = Field(
        ge=0,
        description="Units to order. Zero means no order needed despite low stock.",
    )
    urgency: RestockUrgency = Field(description="How soon ops should act on this.")
    days_of_stock_remaining: Optional[float] = Field(
        default=None,
        description="Estimated days until stockout at current velocity. Null if unknown.",
    )
    reasoning: str = Field(
        min_length=20,
        max_length=400,
        description="Two-to-three sentence rationale citing velocity, lead time, and stock.",
    )


class RestockBatch(BaseModel):
    """
    What the LLM returns when analyzing multiple low-stock products at once.

    Batching is deliberate: sending all low-stock products in one LLM call
    is cheaper and lets the model reason across products (e.g., 'all these
    are from the same supplier, consolidate the order').
    """

    suggestions: List[RestockSuggestion] = Field(
        description="One entry per low-stock product. Order of suggestions is not significant."
    )
    summary: str = Field(
        min_length=10,
        max_length=300,
        description="One-sentence overview of the restock situation across all products.",
    )


class RestockResult(BaseModel):
    """Telemetry wrapper, same pattern as ClassificationResult."""

    batch: RestockBatch
    engine: str
    model: str = ""
    latency_ms: int = 0
