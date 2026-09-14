"""P1: molds, cavities, process operations/runs, lots, defects
(TACT Product–Process Twin vertical slice)

Revision ID: b8f2e4a6c7d1
Revises: c7e21a4f9b05
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8f2e4a6c7d1'
down_revision: Union[str, Sequence[str], None] = 'c7e21a4f9b05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOT_DISPOSITION = postgresql.ENUM('OK', 'QUARANTINE', 'REJECT', name='lot_disposition')
DEFECT_SEVERITY = postgresql.ENUM('MINOR', 'MAJOR', 'CRITICAL', name='defect_severity')
# Table-side copies with create_type=False (see c7e21a4f9b05 for the
# DuplicateObject rationale).
LOT_DISPOSITION_COL = LOT_DISPOSITION.copy()
LOT_DISPOSITION_COL.create_type = False
DEFECT_SEVERITY_COL = DEFECT_SEVERITY.copy()
DEFECT_SEVERITY_COL.create_type = False


def upgrade() -> None:
    LOT_DISPOSITION.create(op.get_bind(), checkfirst=True)
    DEFECT_SEVERITY.create(op.get_bind(), checkfirst=True)

    op.create_table('molds',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('tool_revision', sa.String(length=64), nullable=False),
    sa.Column('process', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_molds_business_id', 'molds', ['business_id'], unique=True)

    op.create_table('cavities',
    sa.Column('mold_id', sa.UUID(), nullable=False),
    sa.Column('cavity_no', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['mold_id'], ['molds.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cavities_business_id', 'cavities', ['business_id'], unique=True)
    op.create_index(op.f('ix_cavities_mold_id'), 'cavities', ['mold_id'], unique=False)

    op.create_table('process_operations',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('seq_no', sa.Integer(), nullable=False),
    sa.Column('equipment', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('window', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_process_operations_business_id', 'process_operations', ['business_id'], unique=True)

    op.create_table('lots',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('mold_id', sa.UUID(), nullable=False),
    sa.Column('cavity_id', sa.UUID(), nullable=False),
    sa.Column('material_lot_id', sa.String(length=255), nullable=True),
    sa.Column('work_order_id', sa.String(length=255), nullable=True),
    sa.Column('produced_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=True),
    sa.Column('disposition', LOT_DISPOSITION_COL, nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['cavity_id'], ['cavities.id'], ),
    sa.ForeignKeyConstraint(['mold_id'], ['molds.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_lots_business_id', 'lots', ['business_id'], unique=True)
    op.create_index(op.f('ix_lots_variant_id'), 'lots', ['variant_id'], unique=False)
    op.create_index(op.f('ix_lots_cavity_id'), 'lots', ['cavity_id'], unique=False)

    op.create_table('process_runs',
    sa.Column('lot_id', sa.UUID(), nullable=False),
    sa.Column('operation_id', sa.UUID(), nullable=False),
    sa.Column('setpoint', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('actual', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('operator', sa.String(length=255), nullable=True),
    sa.Column('out_of_window', sa.Boolean(), nullable=False),
    sa.Column('window_findings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['lot_id'], ['lots.id'], ),
    sa.ForeignKeyConstraint(['operation_id'], ['process_operations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_process_runs_business_id', 'process_runs', ['business_id'], unique=True)
    op.create_index(op.f('ix_process_runs_lot_id'), 'process_runs', ['lot_id'], unique=False)

    op.create_table('defects',
    sa.Column('lot_id', sa.UUID(), nullable=False),
    sa.Column('defect_class', sa.String(length=64), nullable=False),
    sa.Column('severity', DEFECT_SEVERITY_COL, nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit_id', sa.String(length=255), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['lot_id'], ['lots.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_defects_business_id', 'defects', ['business_id'], unique=True)
    op.create_index(op.f('ix_defects_lot_id'), 'defects', ['lot_id'], unique=False)

    # Inspections join the genealogy through the lot (§6.3 Inspection.lot_id).
    op.add_column('test_runs', sa.Column('lot_id', sa.UUID(), nullable=True))
    op.create_foreign_key(None, 'test_runs', 'lots', ['lot_id'], ['id'])
    op.create_index(op.f('ix_test_runs_lot_id'), 'test_runs', ['lot_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_test_runs_lot_id'), table_name='test_runs')
    op.drop_column('test_runs', 'lot_id')
    op.drop_index(op.f('ix_defects_lot_id'), table_name='defects')
    op.drop_index('ix_defects_business_id', table_name='defects')
    op.drop_table('defects')
    op.drop_index(op.f('ix_process_runs_lot_id'), table_name='process_runs')
    op.drop_index('ix_process_runs_business_id', table_name='process_runs')
    op.drop_table('process_runs')
    op.drop_index(op.f('ix_lots_cavity_id'), table_name='lots')
    op.drop_index(op.f('ix_lots_variant_id'), table_name='lots')
    op.drop_index('ix_lots_business_id', table_name='lots')
    op.drop_table('lots')
    op.drop_index('ix_process_operations_business_id', table_name='process_operations')
    op.drop_table('process_operations')
    op.drop_index(op.f('ix_cavities_mold_id'), table_name='cavities')
    op.drop_index('ix_cavities_business_id', table_name='cavities')
    op.drop_table('cavities')
    op.drop_index('ix_molds_business_id', table_name='molds')
    op.drop_table('molds')
    DEFECT_SEVERITY.drop(op.get_bind(), checkfirst=True)
    LOT_DISPOSITION.drop(op.get_bind(), checkfirst=True)
