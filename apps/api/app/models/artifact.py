import enum
import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class ArtifactKind(str, enum.Enum):
    STEP = "step"
    GLTF = "gltf"
    NETLIST = "netlist"
    CSV = "csv"
    SIM_LOG = "sim_log"
    OTHER = "other"


class ArtifactVersionStatus(str, enum.Enum):
    PENDING_UPLOAD = "pending_upload"
    PROMOTED = "promoted"


class Artifact(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "artifacts"

    kind: Mapped[ArtifactKind] = mapped_column(Enum(ArtifactKind, name="artifact_kind"))
    name: Mapped[str] = mapped_column(String(255))

    versions: Mapped[list["ArtifactVersion"]] = relationship(back_populates="artifact")


class ArtifactVersion(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "artifact_versions"

    artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artifacts.id"))
    version: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[ArtifactVersionStatus] = mapped_column(
        Enum(ArtifactVersionStatus, name="artifact_version_status"),
        default=ArtifactVersionStatus.PENDING_UPLOAD,
    )
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tool_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_versions.id"), nullable=True
    )
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    artifact: Mapped[Artifact] = relationship(back_populates="versions")
