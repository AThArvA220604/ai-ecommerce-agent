"""
Structured output schemas for LLM-driven agents.

These Pydantic models double as:
  1. The contract the LLM must satisfy (enforced by OpenAI structured outputs)
  2. Input validation when falling back to the rule engine
  3. The shape the rest of the pipeline consumes

Keep these SMALL and FLAT. Structured outputs work best with simple schemas.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


# ─── Enums used by the order classifier ─────────────────────────────────────
# Using str Enums gives us JSON-Schema enum constraints for free —
# the LLM literally cannot return an invalid value.

class OrderCategory(str, Enum):
    BULK = "bulk"
    HIGH_VALUE = "high-value"
    PRIORITY = "priority"
    STANDARD = "standard"


class OrderPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskFlag(str, Enum):
    CLEAR = "clear"
    REVIEW = "review"
    BLOCKED = "blocked"


# ─── The classification output ──────────────────────────────────────────────

class OrderClassification(BaseModel):
    """
    What the Order Processor agent produces for every order.
    The LLM must fill all fields; OpenAI's structured outputs enforce this.
    """

    category: OrderCategory = Field(
        description="Segment this order falls into based on size, value, and customer."
    )
    priority: OrderPriority = Field(
        description="How urgently ops should handle this. Critical = drop-everything."
    )
    risk_flag: RiskFlag = Field(
        description="Fraud/abuse assessment. 'blocked' = do not fulfill without human approval."
    )
    risk_score: int = Field(
        ge=0,
        le=100,
        description="Numeric risk from 0 (safe) to 100 (definitely fraud). Use the full range.",
    )
    reasoning: str = Field(
        min_length=20,
        max_length=500,
        description="Two to four sentences explaining the decision. Cite specific data points.",
    )
    risk_factors: List[str] = Field(
        default_factory=list,
        description="Short phrases naming each risk signal detected. Empty list if clear.",
    )


# ─── Telemetry for observability ────────────────────────────────────────────

class ClassificationResult(BaseModel):
    """
    Wraps the classification with metadata about HOW it was produced.
    This is what gets logged and returned to the API — not just the verdict,
    but the audit trail (which engine, which model, how long it took).
    """

    classification: OrderClassification
    engine: str  # "llm" | "rules" | "rules_fallback"
    model: str = ""  # populated only when engine == "llm"
    latency_ms: int = 0
    retries: int = 0
