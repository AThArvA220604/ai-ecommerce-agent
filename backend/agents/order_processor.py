"""
Agent 1: Order Processor

Pulls the order from the DB, delegates classification to the classifier
service (which handles LLM-vs-rules routing), then persists the verdict
and telemetry back to the orders table.

This agent is deliberately thin — all the intelligence lives in the
classifier service. The agent's job is orchestration and persistence.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from agents.base_agent import BaseAgent
from database.connection import get_db
from services.classifier import classify_order


class OrderProcessorAgent(BaseAgent):
    def __init__(self):
        super().__init__("order_processor")

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        order_id = input_data["order_id"]

        # 1. Fetch order + product context in a single query
        async with get_db() as db:
            cursor = await db.execute(
                """SELECT o.*, p.stock_quantity, p.name as product_name, p.reorder_threshold
                   FROM orders o JOIN products p ON o.product_id = p.id
                   WHERE o.id = ?""",
                (order_id,),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError(f"Order {order_id} not found")
            order_dict = dict(row)

        # 2. Classify — routes to LLM or rules automatically
        result = await classify_order(order_dict)
        cl = result.classification

        # 3. Persist verdict + telemetry
        now = datetime.now(timezone.utc).isoformat()
        status = "flagged" if cl.risk_flag.value != "clear" else "processed"

        async with get_db() as db:
            await db.execute(
                """UPDATE orders SET
                     category = ?, priority = ?, risk_flag = ?, risk_score = ?,
                     ai_reasoning = ?, ai_engine = ?, ai_model = ?, ai_latency_ms = ?,
                     status = ?, processed_at = ?
                   WHERE id = ?""",
                (
                    cl.category.value,
                    cl.priority.value,
                    cl.risk_flag.value,
                    cl.risk_score,
                    cl.reasoning,
                    result.engine,
                    result.model,
                    result.latency_ms,
                    status,
                    now,
                    order_id,
                ),
            )
            await db.commit()

        # 4. Build response payload
        output = {
            "order_id": order_id,
            "product_id": order_dict["product_id"],
            "product_name": order_dict["product_name"],
            "quantity": order_dict["quantity"],
            "total_price": order_dict["total_price"],
            "stock_quantity": order_dict["stock_quantity"],
            "reorder_threshold": order_dict["reorder_threshold"],
            "category": cl.category.value,
            "priority": cl.priority.value,
            "risk_flag": cl.risk_flag.value,
            "risk_score": cl.risk_score,
            "reasoning": cl.reasoning,
            "risk_factors": cl.risk_factors,
            "engine": result.engine,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "status": status,
        }

        # 5. Audit log — includes the engine so we can distinguish LLM from rule decisions
        await self.log_action(
            action="classify_order",
            input_data={"order_id": order_id},
            output_data=output,
            decision=(
                f"category={cl.category.value}, priority={cl.priority.value}, "
                f"risk={cl.risk_flag.value} (score={cl.risk_score}) via {result.engine}"
            ),
            reasoning=cl.reasoning,
        )

        return output
