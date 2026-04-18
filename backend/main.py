"""
AI E-commerce Automation Agent — FastAPI Application
Multi-agent system for order processing, inventory management, and notifications.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from database.connection import init_db
from routes.orders import router as orders_router
from routes.inventory import router as inventory_router
from routes.alerts import router as alerts_router
from routes.agents import router as agents_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database and seeding data...")
    await init_db()
    logger.info("Application ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="AI E-commerce Automation Agent",
    description="Multi-agent system for intelligent order processing, inventory management, and automated notifications.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders_router, prefix="/api", tags=["Orders"])
app.include_router(inventory_router, prefix="/api", tags=["Inventory"])
app.include_router(alerts_router, prefix="/api", tags=["Alerts"])
app.include_router(agents_router, prefix="/api", tags=["AI Agents"])


@app.get("/api/health")
async def health_check():
    from services.llm_client import llm_client
    return {
        "status": "healthy",
        "service": "ai-ecommerce-agent",
        "ai": llm_client.health(),
    }
