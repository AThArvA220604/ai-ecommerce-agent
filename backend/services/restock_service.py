"""
Restock suggestion service.

Computes sales velocity from the orders table, pulls supplier lead times
from the products table, and asks the LLM to produce reasoned restock
recommendations. Falls back to a tidied-up version of the rule engine
when the LLM is unavailable.

Velocity is computed inline here rather than in a separate service because
the LLM call is a single batch — there's no benefit to pre-computing and
caching velocities across multiple requests in this system's load profile.
"""

import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from agents.inventory_schemas import (
    RestockBatch,
    RestockResult,
    RestockSuggestion,
    RestockUrgency,
)
from database.connection import get_db
from services.llm_client import LLMUnavailable, llm_client, load_prompt

logger = logging.getLogger(__name__)

VELOCITY_WINDOW_DAYS = 7


# ─── Data gathering ─────────────────────────────────────────────────────────

async def _gather_low_stock_context() -> List[Dict[str, Any]]:
    """
    For every product at or below its reorder threshold, return:
      product info + 7-day sales velocity.

    Velocity is computed from fulfilled orders (status NOT in pending/cancelled/flagged)
    within the window. We count units shipped, divide by window days.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=VELOCITY_WINDOW_DAYS)).isoformat()

    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT
                p.id, p.name, p.stock_quantity, p.reorder_threshold,
                p.supplier, p.supplier_lead_time_days,
                COALESCE(SUM(
                    CASE WHEN o.status = 'processed' AND o.processed_at >= ?
                         THEN o.quantity ELSE 0 END
                ), 0) AS units_sold_window
            FROM products p
            LEFT JOIN orders o ON o.product_id = p.id
            WHERE p.stock_quantity <= p.reorder_threshold
            GROUP BY p.id
            ORDER BY p.stock_quantity ASC
            """,
            (cutoff,),
        )
        rows = await cursor.fetchall()

    products = []
    for row in rows:
        d = dict(row)
        d["velocity_per_day"] = round(d["units_sold_window"] / VELOCITY_WINDOW_DAYS, 2)
        products.append(d)
    return products


# ─── Rule-based fallback ────────────────────────────────────────────────────

def _restock_with_rules(products: List[Dict[str, Any]]) -> RestockBatch:
    """
    Deterministic fallback. Mimics the LLM's reasoning framework but with
    fixed formulas. This is what runs when OpenAI is unavailable.
    """
    suggestions: List[RestockSuggestion] = []
    critical_count = 0

    for p in products:
        stock = p["stock_quantity"]
        threshold = p["reorder_threshold"]
        lead = p["supplier_lead_time_days"]
        velocity = p["velocity_per_day"]

        if velocity <= 0.05:
            # Essentially no sales — skip
            suggestions.append(RestockSuggestion(
                product_id=p["id"],
                suggested_quantity=0,
                urgency=RestockUrgency.LOW,
                days_of_stock_remaining=None,
                reasoning=(
                    f"{p['name']} has negligible sales velocity ({velocity}/day). "
                    f"Stock of {stock} against threshold of {threshold} is a stale trigger; "
                    f"no order needed until velocity picks up."
                ),
            ))
            continue

        days_remaining = stock / velocity if velocity > 0 else 999
        # Cover lead time + 50% safety buffer, rounded to nearest 5
        suggested = max(10, math.ceil((lead * velocity * 1.5) / 5) * 5)

        if days_remaining < lead * 0.5:
            urgency = RestockUrgency.CRITICAL
            critical_count += 1
        elif days_remaining < lead:
            urgency = RestockUrgency.HIGH
        elif days_remaining < lead * 1.5:
            urgency = RestockUrgency.MEDIUM
        else:
            urgency = RestockUrgency.LOW

        suggestions.append(RestockSuggestion(
            product_id=p["id"],
            suggested_quantity=suggested,
            urgency=urgency,
            days_of_stock_remaining=round(days_remaining, 1),
            reasoning=(
                f"{p['name']}: {stock} units on hand, selling {velocity}/day "
                f"gives {days_remaining:.1f} days of stock against {lead}-day lead time. "
                f"Order {suggested} units to cover lead time plus safety buffer."
            ),
        ))

    if critical_count > 0:
        summary = f"{critical_count} product(s) will stock out before shipment arrives — order today."
    elif any(s.urgency == RestockUrgency.HIGH for s in suggestions):
        summary = f"{len(suggestions)} products below threshold; expedite the high-urgency items."
    else:
        summary = f"{len(suggestions)} products at or below threshold; routine reordering cycle."

    return RestockBatch(suggestions=suggestions, summary=summary)


# ─── LLM path ───────────────────────────────────────────────────────────────

def _format_products_for_llm(products: List[Dict[str, Any]]) -> str:
    """Compact product list for the user message."""
    lines = []
    for p in products:
        lines.append(
            f"- {p['id']} {p['name']} | stock={p['stock_quantity']}, "
            f"threshold={p['reorder_threshold']}, velocity={p['velocity_per_day']}/day, "
            f"lead={p['supplier_lead_time_days']}d, supplier={p['supplier']}"
        )
    return "Low-stock products to analyze:\n" + "\n".join(lines)


# ─── Public entry point ─────────────────────────────────────────────────────

async def suggest_restocks() -> RestockResult:
    """
    Main entry. Returns a RestockResult with suggestions for every product
    at or below its reorder threshold.

    Empty input (no low-stock products) short-circuits — no LLM call needed.
    """
    products = await _gather_low_stock_context()

    if not products:
        return RestockResult(
            batch=RestockBatch(
                suggestions=[],
                summary="No products below reorder threshold — inventory healthy.",
            ),
            engine="none",
            model="",
            latency_ms=0,
        )

    # Try LLM
    try:
        system_prompt = load_prompt("restock_planner_v1")
        user_message = _format_products_for_llm(products)

        started = time.perf_counter()
        batch, telemetry = await llm_client.parse(
            system_prompt=system_prompt,
            user_message=user_message,
            schema=RestockBatch,
        )
        logger.info(
            "Restock suggestions generated by LLM for %d products in %dms",
            len(products),
            telemetry["latency_ms"],
        )

        return RestockResult(
            batch=batch,
            engine=telemetry["engine"],
            model=telemetry["model"],
            latency_ms=telemetry["latency_ms"],
        )

    except LLMUnavailable as e:
        logger.info("LLM unavailable for restock (%s), using rule engine", e)
        batch = _restock_with_rules(products)
        return RestockResult(batch=batch, engine="rules_fallback")

    except Exception:
        logger.exception("Unexpected error in LLM restock planning, falling back to rules")
        batch = _restock_with_rules(products)
        return RestockResult(batch=batch, engine="rules_fallback")
