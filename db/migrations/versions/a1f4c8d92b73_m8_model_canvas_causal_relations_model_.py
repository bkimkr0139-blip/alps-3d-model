"""M8: model canvas — causal relations, model elements/links, model cards

Revision ID: a1f4c8d92b73
Revises: 350c770eb519
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1f4c8d92b73'
down_revision: Union[str, Sequence[str], None] = '350c770eb519'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RELATION_PROVENANCE = postgresql.ENUM(
    'IMPORTED', 'RULE_DERIVED', 'AI_INFERRED', 'HUMAN_APPROVED',
    name='relation_provenance',
)
MODEL_DOMAIN = postgresql.ENUM(
    'MECHANICAL', 'ELECTRICAL', 'CONTROL', 'KANSEI', name='model_domain',
)
TRUST_STATE = postgresql.ENUM(
    'DRAFT', 'VERIFIED', 'VALIDATED_FOR_PURPOSE', 'APPROVED_FOR_REUSE', 'RETIRED',
    name='trust_state',
)
# Table-side copies with create_type=False: op.create_table would otherwise
# re-emit CREATE TYPE for every enum column and die on DuplicateObject
# (the standalone .create(checkfirst=True) calls below already made them).
RELATION_PROVENANCE_COL = RELATION_PROVENANCE.copy()
RELATION_PROVENANCE_COL.create_type = False
MODEL_DOMAIN_COL = MODEL_DOMAIN.copy()
MODEL_DOMAIN_COL.create_type = False
TRUST_STATE_COL = TRUST_STATE.copy()
TRUST_STATE_COL.create_type = False


def upgrade() -> None:
    RELATION_PROVENANCE.create(op.get_bind(), checkfirst=True)
    MODEL_DOMAIN.create(op.get_bind(), checkfirst=True)
    TRUST_STATE.create(op.get_bind(), checkfirst=True)

    op.create_table('causal_relations',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('source_label', sa.String(length=255), nullable=False),
    sa.Column('source_domain', MODEL_DOMAIN_COL, nullable=False),
    sa.Column('target_label', sa.String(length=255), nullable=False),
    sa.Column('target_domain', MODEL_DOMAIN_COL, nullable=False),
    sa.Column('relation_type', sa.String(length=64), nullable=False),
    sa.Column('mechanism', sa.Text(), nullable=True),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('provenance', RELATION_PROVENANCE_COL, nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_causal_relations_business_id', 'causal_relations', ['business_id'], unique=True)
    op.create_index(op.f('ix_causal_relations_variant_id'), 'causal_relations', ['variant_id'], unique=False)

    op.create_table('model_elements',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('domain', MODEL_DOMAIN_COL, nullable=False),
    sa.Column('equation_text', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('unit', sa.String(length=32), nullable=True),
    sa.Column('geometry_component_id', sa.UUID(), nullable=True),
    sa.Column('position', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['geometry_component_id'], ['components.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_model_elements_business_id', 'model_elements', ['business_id'], unique=True)
    op.create_index(op.f('ix_model_elements_variant_id'), 'model_elements', ['variant_id'], unique=False)

    op.create_table('model_links',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('source_element_id', sa.UUID(), nullable=False),
    sa.Column('target_element_id', sa.UUID(), nullable=False),
    sa.Column('signal', sa.String(length=255), nullable=False),
    sa.Column('unit', sa.String(length=32), nullable=True),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['source_element_id'], ['model_elements.id'], ),
    sa.ForeignKeyConstraint(['target_element_id'], ['model_elements.id'], ),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_model_links_business_id', 'model_links', ['business_id'], unique=True)
    op.create_index(op.f('ix_model_links_variant_id'), 'model_links', ['variant_id'], unique=False)

    op.create_table('model_cards',
    sa.Column('variant_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('equation_text', sa.Text(), nullable=True),
    sa.Column('assumptions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('validity_envelope', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('trust_state', TRUST_STATE_COL, nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('business_id', sa.String(length=64), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['variant_id'], ['variants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('variant_id')
    )
    op.create_index('ix_model_cards_business_id', 'model_cards', ['business_id'], unique=True)
    op.create_index(op.f('ix_model_cards_variant_id'), 'model_cards', ['variant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_model_cards_variant_id'), table_name='model_cards')
    op.drop_index('ix_model_cards_business_id', table_name='model_cards')
    op.drop_table('model_cards')
    op.drop_index(op.f('ix_model_links_variant_id'), table_name='model_links')
    op.drop_index('ix_model_links_business_id', table_name='model_links')
    op.drop_table('model_links')
    op.drop_index(op.f('ix_model_elements_variant_id'), table_name='model_elements')
    op.drop_index('ix_model_elements_business_id', table_name='model_elements')
    op.drop_table('model_elements')
    op.drop_index(op.f('ix_causal_relations_variant_id'), table_name='causal_relations')
    op.drop_index('ix_causal_relations_business_id', table_name='causal_relations')
    op.drop_table('causal_relations')
    TRUST_STATE.drop(op.get_bind(), checkfirst=True)
    MODEL_DOMAIN.drop(op.get_bind(), checkfirst=True)
    RELATION_PROVENANCE.drop(op.get_bind(), checkfirst=True)
