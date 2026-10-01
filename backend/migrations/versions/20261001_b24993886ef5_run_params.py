"""run params

Revision ID: b24993886ef5
Revises: 2a992faee9cd
Create Date: 2026-10-01 12:19:50.964380
"""
from alembic import op
import sqlalchemy as sa


revision = 'b24993886ef5'
down_revision = '2a992faee9cd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOT NULL on a table that may hold rows: existing runs get an empty params object.
    op.add_column('runs', sa.Column('params_json', sa.JSON(), nullable=False, server_default='{}'))
    op.alter_column('runs', 'params_json', server_default=None)


def downgrade() -> None:
    op.drop_column('runs', 'params_json')
