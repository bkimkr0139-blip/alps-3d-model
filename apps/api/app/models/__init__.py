"""Import every mapped model so SQLAlchemy's mapper registry can resolve
string-based relationship() references before any query runs."""

from app.models.artifact import Artifact, ArtifactVersion  # noqa: F401
from app.models.audit import AuditEvent  # noqa: F401
from app.models.baseline import Baseline  # noqa: F401
from app.models.component import Component  # noqa: F401
from app.models.gate import Gate, GateComment, GateDecision  # noqa: F401
from app.models.idempotency import IdempotencyRecord  # noqa: F401
from app.models.model_canvas import (  # noqa: F401
    CausalRelation,
    ModelCard,
    ModelElement,
    ModelLink,
    ModelReviewFinding,
    PortContract,
    UQAnalysis,
)
from app.models.process_twin import (  # noqa: F401
    Cavity,
    Defect,
    Lot,
    Mold,
    ProcessOperation,
    ProcessRun,
)
from app.models.product import Product, Variant  # noqa: F401
from app.models.requirement import Requirement, RequirementTraceLink  # noqa: F401
from app.models.simulation import ResultMetric, SimulationRun  # noqa: F401
from app.models.test import CorrelationRecord, Measurement, TestPlan, TestRun  # noqa: F401
