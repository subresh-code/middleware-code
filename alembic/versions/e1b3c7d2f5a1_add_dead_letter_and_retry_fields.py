"""add_dead_letter_and_retry_fields

Revision ID: e1b3c7d2f5a1
Revises: c57ed2ffe884
Create Date: 2026-05-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1b3c7d2f5a1'
down_revision = 'c57ed2ffe884'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add retry fields to payment_translations
    op.add_column('payment_translations', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('payment_translations', sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True))

    # Create dead_letter table
    op.create_table(
        'dead_letter',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('ase_name', sa.String(100), nullable=False),
        sa.Column('stan', sa.String(6), nullable=True),
        sa.Column('rrn', sa.String(12), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('error_type', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('retried_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['payment_id'], ['payment_translations.id']),
    )
    op.create_index('ix_dead_letter_ase_name', 'dead_letter', ['ase_name'], unique=False)
    op.create_index('ix_dead_letter_payment_id', 'dead_letter', ['payment_id'], unique=False)
    op.create_index('ix_dead_letter_stan', 'dead_letter', ['stan'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_dead_letter_stan', table_name='dead_letter')
    op.drop_index('ix_dead_letter_payment_id', table_name='dead_letter')
    op.drop_index('ix_dead_letter_ase_name', table_name='dead_letter')
    op.drop_table('dead_letter')
    op.drop_column('payment_translations', 'next_retry_at')
    op.drop_column('payment_translations', 'retry_count')
