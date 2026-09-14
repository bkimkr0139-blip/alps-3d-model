"""M9: port contracts, model review findings, UQ analyses

Revision ID: c7e21a4f9b05
Revises: a1f4c8d92b73
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7e21a4f9b05'
down_revision: Union[str, Sequence[str], None] = 'a1f4c8d92b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PORT_DIRECTION = postgresql.ENUM('IN', 'OUT', 'INOUT', name='port_direction')
FINDING_SEVERITY = postgresql.ENUM('ERROR', 'WARNING', 'SUGGESTION', name='finding_severity')
FINDING_STATUS = postgresql.ENUM('OPEN', 'RESOLVED', 'ACCEPTED', name='finding_status')
RELATION_PROVENANCE = postgresql.ENUM(
    'IMPORTED', 'RULE_DERIVED', 'AI_INFERRED', 'HUMAN_APPROVED',
    name='relation_provenance',
)
# Table-side copies with create_type=False: op.create_table would otherwise
# re-emit CREATE TYPE for every enum column and die on DuplicateObject
# (relation_provenance already exists from M8; the others are created by the
# standalone .create(checkfirst=True) calls below).
PORT_DIRECTION_COL = PORT_DIRECTION.copy()
PORT_DIRECTION_COL.create_type = False
FINDING_SEVERITY_COL = FINDING_SEVERITY.copy()
FINDING_SEVERITY_COL.create_type = False
FINDING_STATUS_COL = FINDING_STATUS.copy()
FINDING_STATUS_COL.create_type = False
RELATION_PROVENANCE_COL = RELATION_PROVENANCE.copy()
RELATION_PROVENANCE_COL.create_type = False


def upgrade() -> None:
    PORT_DIRECTION.create(op.get_bind(), checkfirst=True)
    FINDING_SEVERITY.create(op.get_bind(), checkfirst=True)
    FINDING_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table('port_contracts',
    sa.Column('element_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('direction', PORT_DIRECTION_COL, nullable=False),
    sa.Column('quantity', sa.String(length=64), nullable=False),
    sa.Column('unit', sa.String(length=32), nullable=False),
    sa.Column('range_min', sa.Float(), nullable=True),
    sa.Column('range_max', sa.Float(), nullable=True),
    sa.Column('timing_semantics', sa.String(length=64), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['element_id'], ['model_elements.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_port_contracts_business_id', 'port_contracts', ['business_id'], unique=True)
    op.create_index(op.f('ix_port_contracts_element_id'), 'port_contracts', ['element_id'], unique=False)

    op.create_table('model_review_findings',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('run_no', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('severity', FINDING_SEVERITY_COL, nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('status', FINDING_STATUS_COL, nullable=False),
    sa.Column('provenance', RELATION_PROVENANCE_COL, nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_model_review_findings_business_id', 'model_review_findings', ['business_id'], unique=True)
    op.create_index(op.f('ix_model_review_findings_variant_id'), 'model_review_findings', ['variant_id'], unique=False)
    op.create_index(op.f('ix_model_review_findings_run_no'), 'model_review_findings', ['run_no'], unique=False)

    op.create_table('uq_analyses',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('model_type', sa.String(length=64), nullable=False),
    sa.Column('n_samples', sa.Integer(), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('metric_name', sa.String(length=64), nullable=False),
    sa.Column('metric_unit', sa.String(length=32), nullable=False),
    sa.Column('target_band', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_uq_analyses_business_id', 'uq_analyses', ['business_id'], unique=True)
    op.create_index(op.f('ix_uq_analyses_variant_id'), 'uq_analyses', ['variant_id'], unique=False)

    op.add_column('model_links', sa.Column('unit_conversion', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('model_links', 'unit_conversion')
    op.drop_index(op.f('ix_uq_analyses_variant_id'), table_name='uq_analyses')
    op.drop_index('ix_uq_analyses_business_id', table_name='uq_analyses')
    op.drop_table('uq_analyses')
    op.drop_index(op.f('ix_model_review_findings_run_no'), table_name='model_review_findings')
    op.drop_index(op.f('ix_model_review_findings_variant_id'), table_name='model_review_findings')
    op.drop_index('ix_model_review_findings_business_id', table_name='model_review_findings')
    op.drop_table('model_review_findings')
    op.drop_index(op.f('ix_port_contracts_element_id'), table_name='port_contracts')
    op.drop_index('ix_port_contracts_business_id', table_name='port_contracts')
    op.drop_table('port_contracts')
    FINDING_STATUS.drop(op.get_bind(), checkfirst=True)
    FINDING_SEVERITY.drop(op.get_bind(), checkfirst=True)
    PORT_DIRECTION.drop(op.get_bind(), checkfirst=True)
