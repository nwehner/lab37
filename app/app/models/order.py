import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from app.models.enums import IngestionSource, ItemStatus, MealType, OrderEventType, OrderStatus

# No `from __future__ import annotations` here: SQLModel's relationship handling reads
# real annotation objects (not PEP 563 strings) off the class to decide whether to
# auto-wrap them in `Mapped[...]`; postponed evaluation breaks that. Forward references
# to classes defined later in this file are quoted manually instead.


class Order(SQLModel, table=True):
    __tablename__ = "order"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_order_source_external_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source: IngestionSource = Field(index=True)
    external_id: str | None = Field(default=None, index=True)
    status: OrderStatus = Field(default=OrderStatus.RECEIVED, index=True)
    delivery_platform: str | None = None
    restaurant: str | None = Field(default=None, index=True)
    customer_first_name: str | None = None
    customer_last_name: str | None = None
    notes: str | None = None
    total: float | None = None
    meal: MealType | None = Field(default=None, index=True)
    for_tomorrow: bool | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    items: list["OrderItem"] = Relationship(back_populates="order")
    events: list["OrderEvent"] = Relationship(back_populates="order")


class OrderItem(SQLModel, table=True):
    __tablename__ = "order_item"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_id: uuid.UUID = Field(foreign_key="order.id", index=True)
    external_item_id: str | None = Field(default=None, index=True)
    name: str
    category: str | None = None
    price: float | None = None
    status: ItemStatus | None = None

    order: Order = Relationship(back_populates="items")


class OrderEvent(SQLModel, table=True):
    __tablename__ = "order_event"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_id: uuid.UUID = Field(foreign_key="order.id", index=True)
    event_type: OrderEventType
    source: IngestionSource
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)

    order: Order = Relationship(back_populates="events")
