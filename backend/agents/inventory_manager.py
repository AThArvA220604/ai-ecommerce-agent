"""
Agent 2: Inventory Manager
Monitors stock levels, deducts on order processing, and generates restock suggestions.
"""

import math
from typing import Any, Dict

from agents.base_agent import BaseAgent, evaluate_stock_status
from database.connection import get_db


class InventoryManagerAgent(BaseAgent):
    def __init__(self):
        super().__init__("inventory_manager")

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        action = input_data.get("action", "check_stock")

        if action == "deduct_stock":
            return await self._deduct_stock(input_data)
        elif action == "restock_suggestions":
            return await self._generate_restock_suggestions()
        elif action == "check_stock":
            return await self._check_product_stock(input_data["product_id"])
        else:
            raise ValueError(f"Unknown inventory action: {action}")

    async def _deduct_stock(self, data: Dict) -> Dict:
        product_id = data["product_id"]
        quantity = data["quantity"]

        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id, name, stock_quantity, reorder_threshold FROM products WHERE id = ?",
                (product_id,),
            )
            product = await cursor.fetchone()
            if not product:
                raise ValueError(f"Product {product_id} not found")

            product = dict(product)
            new_stock = max(0, product["stock_quantity"] - quantity)

            # BUG FIX: Use atomic conditional update to prevent race conditions
            # under concurrent requests. The WHERE clause ensures we only update
            # if stock hasn't changed since we read it.
            result = await db.execute(
                """UPDATE products
                   SET stock_quantity = ?, updated_at = datetime('now')
                   WHERE id = ? AND stock_quantity = ?""",
                (new_stock, product_id, product["stock_quantity"]),
            )
            if result.rowcount == 0:
                raise ValueError(f"Concurrent stock modification detected for {product_id}. Retry.")

            await db.commit()

        stock_status = evaluate_stock_status(new_stock, product["reorder_threshold"])

        result = {
            "product_id": product_id,
            "product_name": product["name"],
            "previous_stock": product["stock_quantity"],
            "deducted": quantity,
            "new_stock": new_stock,
            "threshold": product["reorder_threshold"],
            "stock_status": stock_status,
            "needs_restock": stock_status in ("low", "critical", "out_of_stock"),
        }

        await self.log_action(
            action="deduct_stock",
            input_data={"product_id": product_id, "quantity": quantity},
            output_data=result,
            decision=f"stock_status={stock_status}",
            reasoning=f"Deducted {quantity} units from {product['name']}. Stock {product['stock_quantity']} → {new_stock}. Threshold: {product['reorder_threshold']}.",
        )

        return result

    async def _generate_restock_suggestions(self) -> Dict:
        """Delegates to the restock_service which handles LLM vs rules routing."""
        from services.restock_service import suggest_restocks

        result = await suggest_restocks()

        # Enrich suggestions with product names for display. The service returns
        # product_ids only (LLM doesn't need names to reason), but the UI does.
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id, name, stock_quantity, reorder_threshold FROM products"
            )
            product_info = {row["id"]: dict(row) for row in await cursor.fetchall()}

        enriched = []
        for s in result.batch.suggestions:
            info = product_info.get(s.product_id, {})
            enriched.append({
                "product_id": s.product_id,
                "product_name": info.get("name", "Unknown"),
                "current_stock": info.get("stock_quantity"),
                "threshold": info.get("reorder_threshold"),
                "suggested_quantity": s.suggested_quantity,
                "urgency": s.urgency.value,
                "days_of_stock_remaining": s.days_of_stock_remaining,
                "reasoning": s.reasoning,
            })

        await self.log_action(
            action="restock_suggestions",
            output_data={"count": len(enriched), "engine": result.engine},
            decision=f"Generated {len(enriched)} suggestion(s) via {result.engine}",
            reasoning=result.batch.summary,
        )

        return {
            "suggestions": enriched,
            "total_low_stock": len(enriched),
            "summary": result.batch.summary,
            "engine": result.engine,
            "model": result.model,
            "latency_ms": result.latency_ms,
        }

    async def _check_product_stock(self, product_id: str) -> Dict:
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = await cursor.fetchone()
            if not product:
                raise ValueError(f"Product {product_id} not found")
            product = dict(product)

        product["stock_status"] = evaluate_stock_status(
            product["stock_quantity"], product["reorder_threshold"]
        )
        return product
