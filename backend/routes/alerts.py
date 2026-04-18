"""
Alerts, Agent Logs, and Dashboard API endpoints.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from database.connection import get_db
from models.schemas import AlertResponse, AlertAcknowledge, AgentLogResponse, DashboardStats

router = APIRouter()


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    acknowledged: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=500),
):
    async with get_db() as db:
        query = "SELECT * FROM alerts"
        params: list = []
        if acknowledged is not None:
            query += " WHERE acknowledged = ?"
            params.append(1 if acknowledged else 0)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.post("/alerts/acknowledge")
async def acknowledge_alert(request: AlertAcknowledge):
    async with get_db() as db:
        # Verify alert exists before updating
        cursor = await db.execute("SELECT id FROM alerts WHERE id = ?", (request.alert_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Alert {request.alert_id} not found")

        await db.execute(
            "UPDATE alerts SET acknowledged = 1 WHERE id = ? AND acknowledged = 0",
            (request.alert_id,),
        )
        await db.commit()
        return {"status": "acknowledged", "alert_id": request.alert_id}


@router.get("/agent-logs", response_model=List[AgentLogResponse])
async def get_agent_logs(
    agent_name: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    async with get_db() as db:
        query = "SELECT * FROM agent_logs"
        params: list = []
        if agent_name:
            query += " WHERE agent_name = ?"
            params.append(agent_name)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    """
    PERF FIX: Original made 8 sequential queries each opening a separate connection.
    Consolidated into a single connection with one compound query.
    """
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT
                (SELECT COUNT(*) FROM orders) as total_orders,
                (SELECT COUNT(*) FROM orders WHERE status = 'pending') as pending_orders,
                (SELECT COUNT(*) FROM orders WHERE status = 'processed') as processed_orders,
                (SELECT COUNT(*) FROM orders WHERE status = 'flagged') as flagged_orders,
                (SELECT COUNT(*) FROM products) as total_products,
                (SELECT COUNT(*) FROM products WHERE stock_quantity <= reorder_threshold AND stock_quantity > 0) as low_stock_count,
                (SELECT COUNT(*) FROM products WHERE stock_quantity = 0) as out_of_stock_count,
                (SELECT COUNT(*) FROM alerts WHERE acknowledged = 0) as unacknowledged_alerts,
                (SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status != 'cancelled') as total_revenue
        """)
        row = await cursor.fetchone()
        return dict(row)
