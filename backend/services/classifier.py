"""
Order classification service — the boundary between the agent and the AI.

Rationale:
  The OrderProcessor agent should NOT know about OpenAI, circuit breakers,
  or prompt files. It should ask: "classify this order." This service is
  the only place that decides how to answer — LLM or rules, with fallback.

Flow:
  1. If LLM is active and breaker is closed, call OpenAI with structured output.
  2. On any LLM failure, log it and fall back to the rule engine.
  3. Always return a ClassificationResult with telemetry showing which path ran.

This is the pattern reviewers look for: "the AI layer is real, but the system
keeps working when the AI is down."
"""

import json
import logging
from typing import Any, Dict

from agents.schemas import (
    ClassificationResult,
    OrderCategory,
    OrderClassification,
    OrderPriority,
    RiskFlag,
)
from services.llm_client import LLMUnavailable, llm_client, load_prompt

logger = logging.getLogger(__name__)


# ─── The deterministic fallback ─────────────────────────────────────────────
# Kept as a pure function with the SAME output schema as the LLM, so the
# caller doesn't care which ran. This is the rule engine from before, lifted
# out of base_agent and adapted to return the new schema.

def classify_with_rules(order: Dict[str, Any]) -> OrderClassification:
    """Deterministic fallback — runs when LLM is unavailable."""
    quantity: int = order.get("quantity", 0)
    total_price: float = float(order.get("total_price", 0))
    customer_type: str = order.get("customer_type", "regular")
    stock: int = order.get("stock_quantity", 999)

    # Category
    if quantity >= 20:
        category = OrderCategory.BULK
    elif total_price >= 500:
        category = OrderCategory.HIGH_VALUE
    elif customer_type == "vip":
        category = OrderCategory.PRIORITY
    else:
        category = OrderCategory.STANDARD

    # Priority
    if total_price >= 2000 or (customer_type == "vip" and total_price >= 100):
        priority = OrderPriority.CRITICAL
    elif total_price >= 500 or customer_type == "wholesale":
        priority = OrderPriority.HIGH
    elif quantity >= 5:
        priority = OrderPriority.MEDIUM
    else:
        priority = OrderPriority.LOW

    # Risk signals
    risk_factors: list[str] = []
    if customer_type == "new" and total_price >= 1000:
        risk_factors.append("new customer high-value exposure")
    if quantity > stock * 2 and stock > 0:
        risk_factors.append("quantity exceeds available stock")
    if quantity >= 50:
        risk_factors.append("unusually large order volume")
    if total_price >= 2500 and customer_type == "new":
        risk_factors.append("unverified customer large exposure")
    if customer_type == "new" and quantity >= 20:
        risk_factors.append("new bulk customer")

    count = len(risk_factors)
    if count >= 2:
        risk_flag = RiskFlag.BLOCKED
        risk_score = min(100, 75 + count * 5)
    elif count == 1:
        risk_flag = RiskFlag.REVIEW
        risk_score = 45
    else:
        risk_flag = RiskFlag.CLEAR
        risk_score = 10

    reasoning_parts = [
        f"Order of {quantity} units totaling ${total_price:.2f} from {customer_type} customer.",
        f"Categorized as '{category.value}' with '{priority.value}' priority based on volume and value.",
    ]
    if risk_factors:
        reasoning_parts.append(f"Risk signals detected: {', '.join(risk_factors)}.")
    else:
        reasoning_parts.append("No risk signals detected — safe to auto-fulfill.")

    return OrderClassification(
        category=category,
        priority=priority,
        risk_flag=risk_flag,
        risk_score=risk_score,
        reasoning=" ".join(reasoning_parts),
        risk_factors=risk_factors,
    )


# ─── The LLM path ───────────────────────────────────────────────────────────

def _format_order_for_llm(order: Dict[str, Any]) -> str:
    """Compact the order into a minimal JSON payload for the user message."""
    payload = {
        "order_id": order.get("id"),
        "product_name": order.get("product_name"),
        "quantity": order.get("quantity"),
        "unit_price": order.get("unit_price"),
        "total_price": order.get("total_price"),
        "customer_type": order.get("customer_type"),
        "stock_quantity": order.get("stock_quantity"),
        "reorder_threshold": order.get("reorder_threshold"),
    }
    return f"Classify this order:\n{json.dumps(payload, indent=2)}"


# ─── The public entry point ────────────────────────────────────────────────

async def classify_order(order: Dict[str, Any]) -> ClassificationResult:
    """
    Classify an order using whichever engine is available.

    This is the only function agents should call. It handles LLM vs rules
    routing, fallback on LLM failure, and telemetry collection.
    """
    # Try LLM first if configured
    try:
        system_prompt = load_prompt("order_classifier_v1")
        user_message = _format_order_for_llm(order)

        classification, telemetry = await llm_client.parse(
            system_prompt=system_prompt,
            user_message=user_message,
            schema=OrderClassification,
        )

        logger.info(
            "Order %s classified by LLM in %dms (retries=%d)",
            order.get("id"),
            telemetry["latency_ms"],
            telemetry["retries"],
        )

        return ClassificationResult(
            classification=classification,
            engine=telemetry["engine"],
            model=telemetry["model"],
            latency_ms=telemetry["latency_ms"],
            retries=telemetry["retries"],
        )

    except LLMUnavailable as e:
        # Expected failure mode — fall back gracefully
        logger.info("LLM unavailable (%s), using rule engine for order %s", e, order.get("id"))
        classification = classify_with_rules(order)
        return ClassificationResult(
            classification=classification,
            engine="rules_fallback",
            model="",
            latency_ms=0,
            retries=0,
        )

    except Exception as e:
        # Unexpected — still fall back, but log loudly
        logger.exception("Unexpected error in LLM classification, falling back to rules")
        classification = classify_with_rules(order)
        return ClassificationResult(
            classification=classification,
            engine="rules_fallback",
            model="",
            latency_ms=0,
            retries=0,
        )
