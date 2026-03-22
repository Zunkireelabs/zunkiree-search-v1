import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False,
    )
    gateway: Mapped[str] = mapped_column(String(20), nullable=False)  # esewa, khalti
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="NPR")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    gateway_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # pidx (Khalti) / transaction_uuid (eSewa)
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
