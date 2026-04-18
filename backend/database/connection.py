"""
Database connection layer.
Uses aiosqlite for local dev; structured for easy PostgreSQL swap via asyncpg.
All schemas mirror PostgreSQL-compatible DDL.
"""

import aiosqlite
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from config import get_settings

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    reorder_threshold INTEGER NOT NULL DEFAULT 10,
    supplier TEXT,
    supplier_lead_time_days INTEGER NOT NULL DEFAULT 7,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    total_price REAL NOT NULL,
    customer_type TEXT NOT NULL DEFAULT 'regular',
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT DEFAULT NULL,
    category TEXT DEFAULT NULL,
    risk_flag TEXT DEFAULT NULL,
    risk_score INTEGER DEFAULT NULL,
    ai_reasoning TEXT DEFAULT NULL,
    ai_engine TEXT DEFAULT NULL,
    ai_model TEXT DEFAULT NULL,
    ai_latency_ms INTEGER DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT DEFAULT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    related_entity_type TEXT,
    related_entity_id TEXT,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    action TEXT NOT NULL,
    input_data TEXT,
    output_data TEXT,
    decision TEXT,
    reasoning TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_id);
CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_agent_logs_agent ON agent_logs(agent_name);
"""

SEED_PRODUCTS = [
    # (id, name, category, price, stock, threshold, supplier, lead_time_days)
    ("PROD-001", "Wireless Bluetooth Headphones", "Electronics", 79.99, 45, 15, "TechSupply Co.", 5),
    ("PROD-002", "Organic Cotton T-Shirt", "Apparel", 29.99, 120, 30, "GreenTextiles Inc.", 14),
    ("PROD-003", "Stainless Steel Water Bottle", "Home & Kitchen", 24.99, 8, 20, "EcoGoods Ltd.", 10),
    ("PROD-004", "Programming Keyboard (Mechanical)", "Electronics", 149.99, 22, 10, "TechSupply Co.", 5),
    ("PROD-005", "Yoga Mat Premium", "Sports", 49.99, 3, 15, "FitLife Corp.", 7),
    ("PROD-006", "Espresso Machine Deluxe", "Home & Kitchen", 299.99, 12, 5, "KitchenPro Ltd.", 21),
    ("PROD-007", "Running Shoes Ultra", "Sports", 129.99, 67, 20, "FitLife Corp.", 7),
    ("PROD-008", "Leather Wallet Slim", "Accessories", 44.99, 0, 25, "CraftGoods Inc.", 14),
    ("PROD-009", "USB-C Hub 7-in-1", "Electronics", 39.99, 55, 15, "TechSupply Co.", 5),
    ("PROD-010", "Scented Candle Set (3-Pack)", "Home & Kitchen", 19.99, 200, 40, "HomeVibes Co.", 10),
]

SEED_ORDERS = [
    ("ORD-1001", "PROD-003", 25, 24.99, 624.75, "wholesale", "pending"),
    ("ORD-1002", "PROD-005", 2, 49.99, 99.98, "regular", "pending"),
    ("ORD-1003", "PROD-008", 50, 44.99, 2249.50, "new", "pending"),
    ("ORD-1004", "PROD-001", 1, 79.99, 79.99, "vip", "pending"),
    ("ORD-1005", "PROD-004", 3, 149.99, 449.97, "regular", "pending"),
    ("ORD-1006", "PROD-006", 10, 299.99, 2999.90, "new", "pending"),
    ("ORD-1007", "PROD-002", 5, 29.99, 149.95, "regular", "pending"),
    ("ORD-1008", "PROD-010", 1, 19.99, 19.99, "vip", "pending"),
]


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async context manager for database connections.
    Guarantees cleanup on both success and exception paths.
    """
    settings = get_settings()
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def _migrate_orders_table(db: aiosqlite.Connection) -> None:
    """
    Add new AI telemetry columns to existing databases.
    SQLite doesn't support IF NOT EXISTS on ADD COLUMN, so we introspect first.
    Safe to run repeatedly.
    """
    cursor = await db.execute("PRAGMA table_info(orders)")
    existing_cols = {row["name"] for row in await cursor.fetchall()}

    new_cols = {
        "risk_score": "INTEGER DEFAULT NULL",
        "ai_engine": "TEXT DEFAULT NULL",
        "ai_model": "TEXT DEFAULT NULL",
        "ai_latency_ms": "INTEGER DEFAULT NULL",
    }
    for col_name, col_def in new_cols.items():
        if col_name not in existing_cols:
            await db.execute(f"ALTER TABLE orders ADD COLUMN {col_name} {col_def}")
            logger.info("Migration: added orders.%s", col_name)


async def _migrate_products_table(db: aiosqlite.Connection) -> None:
    """Add supplier_lead_time_days to existing databases, defaulting to 7."""
    cursor = await db.execute("PRAGMA table_info(products)")
    existing_cols = {row["name"] for row in await cursor.fetchall()}
    if "supplier_lead_time_days" not in existing_cols:
        await db.execute(
            "ALTER TABLE products ADD COLUMN supplier_lead_time_days INTEGER NOT NULL DEFAULT 7"
        )
        logger.info("Migration: added products.supplier_lead_time_days")


async def init_db():
    async with get_db() as db:
        await db.executescript(SCHEMA)
        await _migrate_orders_table(db)
        await _migrate_products_table(db)

        cursor = await db.execute("SELECT COUNT(*) as cnt FROM products")
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            await db.executemany(
                "INSERT INTO products (id, name, category, price, stock_quantity, reorder_threshold, supplier, supplier_lead_time_days) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                SEED_PRODUCTS,
            )
            await db.executemany(
                "INSERT INTO orders (id, product_id, quantity, unit_price, total_price, customer_type, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                SEED_ORDERS,
            )
            await db.commit()
            logger.info("Database seeded with %d products and %d orders.", len(SEED_PRODUCTS), len(SEED_ORDERS))
