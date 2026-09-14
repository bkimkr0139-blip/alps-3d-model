import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class Product(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    variants: Mapped[list["Variant"]] = relationship(back_populates="product")


class Variant(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "variants"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    product: Mapped[Product] = relationship(back_populates="variants")
    requirements: Mapped[list["Requirement"]] = relationship(back_populates="variant")
    components: Mapped[list["Component"]] = relationship(back_populates="variant")
    baselines: Mapped[list["Baseline"]] = relationship(back_populates="variant")
