"""add_raw_message_logs

Revision ID: f2c4d8e3g6b2
Revises: e1b3c7d2f5a1
Create Date: 2026-05-04 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f2c4d8e3g6b2'
down_revision = 'e1b3c7d2f5a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create raw_message_logs table
    op.create_table(
        'raw_message_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ase_name', sa.String(100), nullable=False),
        sa.Column('stan', sa.String(6), nullable=True),
        sa.Column('rrn', sa.String(12), nullable=True),
        sa.Column('mti', sa.String(4), nullable=True),
        sa.Column('raw_bytes', sa.Text(), nullable=False),
        sa.Column('parsed_successfully', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_raw_message_logs_ase_name', 'raw_message_logs', ['ase_name'], unique=False)
    op.create_index('ix_raw_message_logs_stan_rrn', 'raw_message_logs', ['stan', 'rrn'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_raw_message_logs_stan_rrn', table_name='raw_message_logs')
    op.drop_index('ix_raw_message_logs_ase_name', table_name='raw_message_logs')
    op.drop_table('raw_message_logs')
