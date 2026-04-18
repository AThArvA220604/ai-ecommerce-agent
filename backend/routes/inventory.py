"""
Inventory API endpoints.
"""

from fastapi import APIRouter, HTTPException
from typing import List

from database.connection import get_db
from models.schemas import ProductResponse, StockUpdateRequest
from agents.base_agent import evaluate_stock_status
from agents.orchestrator import orchestrator

router = APIRouter()


def _enrich_stock_status(product_dict: dict) -> dict:
    """Add computed stock_status field using the shared evaluator."""
    product_dict["stock_status"] = evaluate_stock_status(
        product_dict["stock_quantity"], product_dict["reorder_threshold"]
    )
    return product_dict


@router.get("/inventory", response_model=List[ProductResponse])
async def get_inventory():
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM products ORDER BY stock_quantity ASC")
        rows = await cursor.fetchall()
        return [_enrich_stock_status(dict(row)) for row in rows]


@router.get("/inventory/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        return _enrich_stock_status(dict(row))


@router.post("/update-stock")
async def update_stock(request: StockUpdateRequest):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM products WHERE id = ?", (request.product_id,))
        product = await cursor.fetchone()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {request.product_id} not found")

        product = dict(product)
        new_qty = max(0, product["stock_quantity"] + request.quantity_change)

        await db.execute(
            "UPDATE products SET stock_quantity = ?, updated_at = datetime('now') WHERE id = ?",
            (new_qty, request.product_id),
        )
        await db.commit()

        return {
            "product_id": request.product_id,
            "previous_stock": product["stock_quantity"],
            "new_stock": new_qty,
            "change": request.quantity_change,
            "reason": request.reason,
        }


@router.get("/restock-suggestions")
async def get_restock_suggestions():
    return await orchestrator.get_restock_suggestions()
