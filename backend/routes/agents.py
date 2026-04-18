"""
AI Agents API — batch processing and agent operations.
"""

import logging
from fastapi import APIRouter

from database.connection import get_db
from agents.orchestrator import orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/process-all-orders")
async def process_all_pending_orders():
    """Process every pending order through the full AI pipeline."""
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM orders WHERE status = 'pending' ORDER BY created_at ASC")
        pending = [dict(row)["id"] for row in await cursor.fetchall()]

    if not pending:
        return {"processed": 0, "errors": 0, "results": [], "message": "No pending orders."}

    results = []
    success_count = 0
    error_count = 0

    for order_id in pending:
        try:
            result = await orchestrator.process_order_pipeline(order_id)
            results.append({"order_id": order_id, "status": "success", "result": result})
            success_count += 1
        except Exception as e:
            logger.exception("Failed to process order %s", order_id)
            results.append({"order_id": order_id, "status": "error", "error": str(e)})
            error_count += 1

    return {
        "processed": success_count,
        "errors": error_count,
        "results": results,
    }
