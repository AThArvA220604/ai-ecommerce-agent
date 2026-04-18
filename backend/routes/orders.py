"""
Orders API endpoints.
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from database.connection import get_db
from models.schemas import OrderCreate, OrderResponse, ProcessOrderRequest, ProcessOrderResponse
from agents.orchestrator import orchestrator

router = APIRouter()


@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    status: Optional[str] = Query(None, pattern="^(pending|processing|processed|flagged|cancelled)$"),
    limit: int = Query(50, ge=1, le=500),
):
    async with get_db() as db:
        query = """
            SELECT o.*, p.name as product_name
            FROM orders o LEFT JOIN products p ON o.product_id = p.id
        """
        params: list = []
        if status:
            query += " WHERE o.status = ?"
            params.append(status)
        query += " ORDER BY o.created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT o.*, p.name as product_name FROM orders o LEFT JOIN products p ON o.product_id = p.id WHERE o.id = ?",
            (order_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
        return dict(row)


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(order: OrderCreate):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM products WHERE id = ?", (order.product_id,))
        product = await cursor.fetchone()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {order.product_id} not found")

        product = dict(product)
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        total_price = round(product["price"] * order.quantity, 2)

        await db.execute(
            "INSERT INTO orders (id, product_id, quantity, unit_price, total_price, customer_type) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, order.product_id, order.quantity, product["price"], total_price, order.customer_type.value),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT o.*, p.name as product_name FROM orders o LEFT JOIN products p ON o.product_id = p.id WHERE o.id = ?",
            (order_id,),
        )
        return dict(await cursor.fetchone())


@router.post("/process-order", response_model=ProcessOrderResponse)
async def process_order(request: ProcessOrderRequest):
    # Validate order exists and is processable before invoking the pipeline
    async with get_db() as db:
        cursor = await db.execute("SELECT status FROM orders WHERE id = ?", (request.order_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Order {request.order_id} not found")
        if dict(row)["status"] not in ("pending", "processing"):
            raise HTTPException(status_code=409, detail="Order already processed or flagged")

    result = await orchestrator.process_order_pipeline(request.order_id)
    return result
