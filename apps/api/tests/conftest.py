import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.security import CurrentUser, get_current_user

# Own database, never the dev/demo one — running tests must not wipe seeded
# demo data living in settings.postgres_app_db.
test_engine = create_engine(
    f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
    f"@localhost:{settings.postgres_host_port}/{settings.postgres_app_db}_test",
    pool_pre_ping=True,
)

ARCHITECT = CurrentUser(subject="test-architect", username="test.architect", roles=frozenset({"system_architect"}))
APPROVER = CurrentUser(subject="test-approver", username="test.approver", roles=frozenset({"reviewer_approver"}))
MECH_ENGINEER = CurrentUser(
    subject="test-mech", username="test.mech", roles=frozenset({"mechanical_engineer"})
)

# App code calls db.commit() itself (idempotent_write), so tests can't rely on
# an outer transaction + rollback — truncate everything between tests instead.
_TABLES = (
    "audit_events",
    "idempotency_records",
    "defects",
    "process_runs",
    "lots",
    "process_operations",
    "cavities",
    "molds",
    "model_review_findings",
    "uq_analyses",
    "port_contracts",
    "model_cards",
    "model_links",
    "model_elements",
    "causal_relations",
    "gate_decisions",
    "gate_comments",
    "gates",
    "requirement_trace_links",
    "requirements",
    "components",
    "baselines",
    "correlation_records",
    "measurements",
    "test_runs",
    "test_plans",
    "result_metrics",
    "simulation_runs",
    "artifact_versions",
    "artifacts",
    "variants",
    "products",
)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    # drop_all + create_all every run, not just create_all: create_all() only
    # adds missing tables, so a changed column on an existing table would
    # silently test against a stale schema otherwise.
    with test_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with test_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture()
def db_session():
    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = lambda: ARCHITECT
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def as_user(client: TestClient, user: CurrentUser):
    client.app.dependency_overrides[get_current_user] = lambda: user
    return client
