"""
Base Agent — shared infrastructure for all automation agents.

Provides:
  - Logging of agent actions to the agent_logs table
  - Alert creation into the alerts table
  - The shared stock-status evaluator used across agents AND routes

Classification logic has moved to services/classifier.py, which is the
boundary between agents and the AI layer.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from database.connection import get_db

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all automation agents."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"agent.{name}")

    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def log_action(
        self,
        action: str,
        input_data: Any = None,
        output_data: Any = None,
        decision: str = "",
        reasoning: str = "",
    ) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO agent_logs (agent_name, action, input_data, output_data, decision, reasoning) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.name,
                    action,
                    json.dumps(input_data, default=str) if input_data else None,
                    json.dumps(output_data, default=str) if output_data else None,
                    decision,
                    reasoning,
                ),
            )
            await db.commit()
        self.logger.info("[%s] decision=%s", action, decision)

    async def create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO alerts (alert_type, severity, title, message, related_entity_type, related_entity_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (alert_type, severity, title, message, entity_type, entity_id),
            )
            await db.commit()
        self.logger.info("Alert created: [%s] %s", severity, title)


def evaluate_stock_status(stock: int, threshold: int) -> str:
    """Shared stock-level evaluator — used by agents AND routes. Single source of truth."""
    if stock == 0:
        return "out_of_stock"
    if stock <= threshold * 0.3:
        return "critical"
    if stock <= threshold:
        return "low"
    return "normal"
