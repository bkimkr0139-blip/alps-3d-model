import enum
import uuid

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class BaselineStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class Baseline(Base, IdentifiedMixin, ProvenanceMixin):
    """Immutable snapshot of a Variant's requirement/artifact/model versions (§FR-01, §9.2).

    `manifest` is frozen at creation and never rewritten. `status` is the one
    field allowed to change, transitioning ACTIVE -> SUPERSEDED when a newer
    Baseline is created for the same Variant — that is a lifecycle marker, not
    a rewrite of what was frozen.
    """

    __tablename__ = "baselines"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"))
    manifest: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[BaselineStatus] = mapped_column(
        Enum(BaselineStatus, name="baseline_status"), default=BaselineStatus.ACTIVE
    )

    variant: Mapped["Variant"] = relationship(back_populates="baselines")  # noqa: F821
