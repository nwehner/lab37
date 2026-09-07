from __future__ import annotations

from enum import Enum


class IngestionSource(str, Enum):
    WEBHOOK = "webhook"
    POLLING_API = "polling_api"
    CSV_UPLOAD = "csv_upload"


class OrderStatus(str, Enum):
    RECEIVED = "received"
    IN_PREP = "in_prep"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ItemStatus(str, Enum):
    ORDERED = "ordered"
    PROCESSING = "processing"
    WITH_COURIER = "with_courier"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class OrderEventType(str, Enum):
    ORDER_RECEIVED = "order_received"
    ORDER_UPDATED = "order_updated"
    ITEM_STATUS_CHANGED = "item_status_changed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_DISPATCHED = "order_dispatched"
    INGESTION_WARNING = "ingestion_warning"


class IngestionRunOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
