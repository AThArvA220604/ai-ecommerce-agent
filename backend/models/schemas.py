"""
Pydantic models for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class CustomerType(str, Enum):
    regular = "regular"
    vip = "vip"
    wholesale = "wholesale"
    new = "new"


class OrderStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    flagged = "flagged"
    cancelled = "cancelled"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class RiskFlag(str, Enum):
    clear = "clear"
    review = "review"
    suspicious = "suspicious"
    blocked = "blocked"


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


# --- Orders ---

class OrderCreate(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)
    customer_type: CustomerType = CustomerType.regular


class OrderResponse(BaseModel):
    id: str
    product_id: str
    quantity: int
    unit_price: float
    total_price: float
    customer_type: str
    status: str
    priority: Optional[str] = None
    category: Optional[str] = None
    risk_flag: Optional[str] = None
    risk_score: Optional[int] = None
    ai_reasoning: Optional[str] = None
    ai_engine: Optional[str] = None
    ai_model: Optional[str] = None
    ai_latency_ms: Optional[int] = None
    created_at: str
    processed_at: Optional[str] = None
    product_name: Optional[str] = None


class ProcessOrderRequest(BaseModel):
    order_id: str


class ProcessOrderResponse(BaseModel):
    order_id: str
    category: str
    priority: str
    risk_flag: str
    risk_score: Optional[int] = None
    reasoning: str
    actions_taken: List[str]
    engine: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None


# --- Inventory ---

class ProductResponse(BaseModel):
    id: str
    name: str
    category: str
    price: float
    stock_quantity: int
    reorder_threshold: int
    supplier: Optional[str] = None
    stock_status: str = "normal"
    created_at: str
    updated_at: str


class StockUpdateRequest(BaseModel):
    product_id: str
    quantity_change: int  # positive = restock, negative = deduct
    reason: str = "manual_adjustment"


class RestockSuggestion(BaseModel):
    product_id: str
    product_name: str
    current_stock: int
    threshold: int
    suggested_quantity: int
    urgency: str
    reasoning: str


# --- Alerts ---

class AlertResponse(BaseModel):
    id: int
    alert_type: str
    severity: str
    title: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    acknowledged: bool
    created_at: str


class AlertAcknowledge(BaseModel):
    alert_id: int


# --- Agent Logs ---

class AgentLogResponse(BaseModel):
    id: int
    agent_name: str
    action: str
    input_data: Optional[str] = None
    output_data: Optional[str] = None
    decision: Optional[str] = None
    reasoning: Optional[str] = None
    created_at: str


# --- Dashboard ---

class DashboardStats(BaseModel):
    total_orders: int
    pending_orders: int
    processed_orders: int
    flagged_orders: int
    total_products: int
    low_stock_count: int
    out_of_stock_count: int
    unacknowledged_alerts: int
    total_revenue: float
