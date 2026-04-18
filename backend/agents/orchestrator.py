"""
Agent Orchestrator — coordinates the multi-agent pipeline.
Order Processor → Inventory Manager → Notification Agent

Uses a module-level singleton so all routes share one instance
instead of each route file instantiating its own copy.
"""

import logging
from typing import Any, Dict

from agents.order_processor import OrderProcessorAgent
from agents.inventory_manager import InventoryManagerAgent
from agents.notification_agent import NotificationAgent

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates all three agents in a logical pipeline."""

    def __init__(self):
        self.order_processor = OrderProcessorAgent()
        self.inventory_manager = InventoryManagerAgent()
        self.notification_agent = NotificationAgent()

    async def process_order_pipeline(self, order_id: str) -> Dict[str, Any]:
        """
        Full pipeline:
        1. Order Processor classifies the order
        2. Inventory Manager deducts stock (skipped if blocked)
        3. Notification Agent evaluates and sends alerts
        """
        actions_taken: list[str] = []

        # Step 1: Classify
        logger.info("Pipeline [%s]: classifying", order_id)
        classification = await self.order_processor.execute({"order_id": order_id})
        actions_taken.append(
            f"Classified: category={classification['category']}, "
            f"priority={classification['priority']}, risk={classification['risk_flag']}"
        )

        # Step 2: Deduct inventory (only if not blocked)
        stock_result = None
        if classification["risk_flag"] != "blocked":
            logger.info("Pipeline [%s]: deducting stock for %s", order_id, classification["product_id"])
            stock_result = await self.inventory_manager.execute({
                "action": "deduct_stock",
                "product_id": classification["product_id"],
                "quantity": classification["quantity"],
            })
            actions_taken.append(
                f"Stock deducted: {classification['product_id']} "
                f"{stock_result['previous_stock']} → {stock_result['new_stock']}"
            )
        else:
            actions_taken.append("Stock deduction SKIPPED — order blocked due to risk.")

        # Step 3: Evaluate notifications
        logger.info("Pipeline [%s]: evaluating notifications", order_id)
        notif_input: Dict[str, Any] = {
            "action": "evaluate_all",
            "order_id": order_id,
            "priority": classification["priority"],
            "risk_flag": classification["risk_flag"],
            "product_name": classification.get("product_name", ""),
            "total_price": classification.get("total_price", 0),
        }
        if stock_result:
            notif_input.update({
                "stock_status": stock_result["stock_status"],
                "product_id": stock_result["product_id"],
                "product_name": stock_result["product_name"],
                "new_stock": stock_result["new_stock"],
                "threshold": stock_result["threshold"],
            })

        notif_result = await self.notification_agent.execute(notif_input)
        if notif_result["count"] > 0:
            actions_taken.append(f"Notifications sent: {notif_result['count']} alert(s)")
        else:
            actions_taken.append("No notifications required.")

        return {
            "order_id": order_id,
            "category": classification["category"],
            "priority": classification["priority"],
            "risk_flag": classification["risk_flag"],
            "risk_score": classification.get("risk_score"),
            "reasoning": classification["reasoning"],
            "actions_taken": actions_taken,
            "stock_impact": stock_result,
            "notifications": notif_result,
            "engine": classification.get("engine"),
            "model": classification.get("model"),
            "latency_ms": classification.get("latency_ms"),
        }

    async def get_restock_suggestions(self) -> Dict:
        return await self.inventory_manager.execute({"action": "restock_suggestions"})


# Module-level singleton — import this instead of creating new instances
orchestrator = AgentOrchestrator()
