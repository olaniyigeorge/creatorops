"""brief tracking

Revision ID: c1f0a7d3b9e4
Revises: b24993886ef5
Create Date: 2026-10-02 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c1f0a7d3b9e4'
down_revision = 'b24993886ef5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('briefs', sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True))
    # NOT NULL on a table that may hold rows: existing briefs start with zero follow-ups.
    op.add_column('briefs', sa.Column('followup_count', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('briefs', 'followup_count', server_default=None)
    op.add_column('briefs', sa.Column('last_followup_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('briefs', 'last_followup_at')
    op.drop_column('briefs', 'followup_count')
    op.drop_column('briefs', 'submitted_at')
