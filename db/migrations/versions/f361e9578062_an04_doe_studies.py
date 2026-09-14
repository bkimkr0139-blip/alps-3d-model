"""AN-04: doe_studies (response-surface regression + candidate ranking over
process-run/CTQ data)

Revision ID: f361e9578062
Revises: b8f2e4a6c7d1
Create Date: 2026-09-14

NOTE: written by hand, not via `alembic revision --autogenerate` — the
shared dev DB's alembic_version had already moved past this branch's head
(a concurrent worktree applied its own migration directly against the same
Postgres instance). This revision only depends on b8f2e4a6c7d1 (the head
when this branch was cut); merging both branches will need a manual
down_revision fixup (or a merge revision) once both are in the same tree —
see AGENTS.md "AN-04" section.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f361e9578062'
down_revision: Union[str, Sequence[str], None] = 'b8f2e4a6c7d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('doe_studies',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('parameter', sa.String(length=128), nullable=False),
    sa.Column('parameter_unit', sa.String(length=32), nullable=True),
    sa.Column('metric', sa.String(length=32), nullable=False),
    sa.Column('metric_unit', sa.String(length=32), nullable=True),
    sa.Column('target_band', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('observations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('fit', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('candidates', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('constraint_violations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['operation_id'], ['process_operations.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_doe_studies_business_id', 'doe_studies', ['business_id'], unique=True)
    op.create_index(op.f('ix_doe_studies_variant_id'), 'doe_studies', ['variant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_doe_studies_variant_id'), table_name='doe_studies')
    op.drop_index('ix_doe_studies_business_id', table_name='doe_studies')
    op.drop_table('doe_studies')
