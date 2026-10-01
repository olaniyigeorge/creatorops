"""gate and approvals

Revision ID: 2a992faee9cd
Revises: 8139056c5a53
Create Date: 2026-10-01 11:42:53.325123
"""
from alembic import op
import sqlalchemy as sa


revision = '2a992faee9cd'
down_revision = '8139056c5a53'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notifications',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('link', sa.String(length=512), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_index(op.f('ix_notifications_workspace_id'), 'notifications', ['workspace_id'], unique=False)
    # NOT NULL columns on a table that may already hold rows: add nullable,
    # backfill, then tighten. Legacy rows get their id as a unique step key.
    op.add_column('actions', sa.Column('step_key', sa.String(length=128), nullable=True))
    op.add_column('actions', sa.Column('status', sa.String(length=24), nullable=True))
    op.execute("UPDATE actions SET step_key = CAST(id AS VARCHAR), status = 'executed'")
    op.alter_column('actions', 'step_key', nullable=False)
    op.alter_column('actions', 'status', nullable=False)
    op.add_column('actions', sa.Column('gate_reason', sa.Text(), nullable=True))
    op.add_column('actions', sa.Column('guardrail_feedback', sa.Text(), nullable=True))
    op.add_column('actions', sa.Column('result_json', sa.JSON(), nullable=True))
    op.create_unique_constraint('uq_actions_run_id_step_key', 'actions', ['run_id', 'step_key'])
    op.add_column('approvals', sa.Column('edited_payload_json', sa.JSON(), nullable=True))
    op.add_column('runs', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'started_at')
    op.drop_column('approvals', 'edited_payload_json')
    op.drop_constraint('uq_actions_run_id_step_key', 'actions', type_='unique')
    op.drop_column('actions', 'result_json')
    op.drop_column('actions', 'guardrail_feedback')
    op.drop_column('actions', 'gate_reason')
    op.drop_column('actions', 'status')
    op.drop_column('actions', 'step_key')
    op.drop_index(op.f('ix_notifications_workspace_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
