"""
Agent 3: Notification Agent
Generates alerts for low stock, high-priority orders, and risk flags.
Simulates SMTP email delivery (logs instead of sending in dev mode).
"""

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class NotificationAgent(BaseAgent):
    def __init__(self):
        super().__init__("notification_agent")

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        action = input_data.get("action", "evaluate")
        notifications_sent: List[Dict] = []

        if action == "evaluate_order":
            notifications_sent = await self._evaluate_order(input_data)
        elif action == "evaluate_stock":
            notifications_sent = await self._evaluate_stock(input_data)
        elif action == "evaluate_all":
            if "order_id" in input_data:
                notifications_sent.extend(await self._evaluate_order(input_data))
            if "stock_status" in input_data:
                notifications_sent.extend(await self._evaluate_stock(input_data))
        else:
            self.logger.warning("Unknown notification action: %s", action)

        await self.log_action(
            action="send_notifications",
            input_data=input_data,
            output_data={"notifications": notifications_sent},
            decision=f"Sent {len(notifications_sent)} notification(s)",
            reasoning=f"Evaluated input and triggered {len(notifications_sent)} alerts.",
        )

        return {"notifications_sent": notifications_sent, "count": len(notifications_sent)}

    async def _evaluate_order(self, data: Dict) -> List[Dict]:
        notifications: List[Dict] = []
        priority = data.get("priority", "low")
        risk_flag = data.get("risk_flag", "clear")
        order_id = data.get("order_id", "unknown")
        product_name = data.get("product_name", "Unknown Product")
        total_price = data.get("total_price", 0)

        if priority in ("critical", "high"):
            severity = "critical" if priority == "critical" else "warning"
            title = f"High Priority Order: {order_id}"
            message = (
                f"Order {order_id} for {product_name} (${total_price:.2f}) "
                f"classified as {priority} priority. Requires immediate attention."
            )
            await self.create_alert(
                alert_type="high_priority_order",
                severity=severity,
                title=title,
                message=message,
                entity_type="order",
                entity_id=order_id,
            )
            self._simulate_email(title, message)
            notifications.append({"type": "high_priority_order", "severity": severity, "order_id": order_id})

        if risk_flag != "clear":
            severity = "critical" if risk_flag == "blocked" else "warning"
            title = f"Risk Alert: Order {order_id} flagged as '{risk_flag}'"
            message = (
                f"Order {order_id} for {product_name} has been flagged "
                f"with risk level '{risk_flag}'. Manual review recommended."
            )
            await self.create_alert(
                alert_type="fraud_risk",
                severity=severity,
                title=title,
                message=message,
                entity_type="order",
                entity_id=order_id,
            )
            self._simulate_email(title, message)
            notifications.append({"type": "fraud_risk", "severity": severity, "order_id": order_id})

        return notifications

    async def _evaluate_stock(self, data: Dict) -> List[Dict]:
        notifications: List[Dict] = []
        stock_status = data.get("stock_status", "normal")

        if stock_status not in ("low", "critical", "out_of_stock"):
            return notifications

        product_id = data.get("product_id", "unknown")
        product_name = data.get("product_name", "Unknown Product")
        new_stock = data.get("new_stock", data.get("current_stock", 0))
        threshold = data.get("threshold", 0)

        severity_map = {"out_of_stock": "critical", "critical": "critical", "low": "warning"}
        title_map = {
            "out_of_stock": f"OUT OF STOCK: {product_name}",
            "critical": f"Critical Stock: {product_name}",
            "low": f"Low Stock Warning: {product_name}",
        }
        message_map = {
            "out_of_stock": f"{product_name} ({product_id}) is completely out of stock. Immediate restocking required. Threshold: {threshold} units.",
            "critical": f"{product_name} ({product_id}) has critically low stock at {new_stock} units (threshold: {threshold}). Urgent restock needed.",
            "low": f"{product_name} ({product_id}) stock is low at {new_stock} units (threshold: {threshold}). Consider restocking soon.",
        }

        severity = severity_map[stock_status]
        await self.create_alert(
            alert_type="low_stock",
            severity=severity,
            title=title_map[stock_status],
            message=message_map[stock_status],
            entity_type="product",
            entity_id=product_id,
        )
        self._simulate_email(title_map[stock_status], message_map[stock_status])
        notifications.append({"type": "low_stock", "severity": severity, "product_id": product_id})

        return notifications

    def _simulate_email(self, subject: str, body: str) -> None:
        """Simulate SMTP email delivery. Replace with real SMTP in production."""
        logger.info("[EMAIL] To: ops@ecommerce.ai | Subject: %s", subject)
