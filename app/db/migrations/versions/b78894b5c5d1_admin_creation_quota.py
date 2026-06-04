"""add admin creation quota system

Revision ID: b78894b5c5d1
Revises: 2b231de97dc3
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b78894b5c5d1'
down_revision = '2b231de97dc3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add quota columns to admins table
    with op.batch_alter_table('admins') as batch_op:
        batch_op.add_column(sa.Column(
            'creation_quota_bytes',
            sa.BigInteger(),
            nullable=True,
            comment='NULL = unlimited; positive = byte cap on total allocated user data limits'
        ))
        batch_op.add_column(sa.Column(
            'allocated_quota_bytes',
            sa.BigInteger(),
            nullable=False,
            server_default='0',
            comment='Running sum of data_limit for all owned users with finite limits'
        ))

    # Create admin_quota_logs table
    op.create_table(
        'admin_quota_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('admin_id', sa.Integer(), sa.ForeignKey('admins.id'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.Enum(
            'user_created',
            'user_updated',
            'user_deleted',
            'user_transferred_in',
            'user_transferred_out',
            'quota_adjusted',
            name='adminquotalogtype'
        ), nullable=False),
        sa.Column('old_data_limit', sa.BigInteger(), nullable=True),
        sa.Column('new_data_limit', sa.BigInteger(), nullable=True),
        sa.Column('delta_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table('admin_quota_logs')

    with op.batch_alter_table('admins') as batch_op:
        batch_op.drop_column('allocated_quota_bytes')
        batch_op.drop_column('creation_quota_bytes')

    # Drop enum type (needed for PostgreSQL)
    op.execute("DROP TYPE IF EXISTS adminquotalogtype")
