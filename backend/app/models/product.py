import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # Rich details: fabric, fit, construction, care
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    images: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of URLs
    url: Mapped[str | None] = mapped_column(Text, nullable=True)  # Product page URL
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sizes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    colors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    vector_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA256 of URL
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="products")


from app.models.customer import Customer
