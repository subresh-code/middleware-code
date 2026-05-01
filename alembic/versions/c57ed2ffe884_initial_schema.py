"""initial_schema

Revision ID: c57ed2ffe884
Revises: 
Create Date: 2026-04-30 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c57ed2ffe884'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ase_registry table
    op.create_table(
        'ase_registry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ase_name', sa.String(100), nullable=False),
        sa.Column('api_key_hash', sa.String(255), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, default=True),
        sa.Column('max_connections', sa.Integer(), nullable=True, default=50),
        sa.Column('frame_length_type', sa.Integer(), nullable=True, default=2),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ase_name'),
    )
    op.create_index('ix_ase_registry_ase_name', 'ase_registry', ['ase_name'], unique=True)
    op.create_index('ix_ase_registry_id', 'ase_registry', ['id'], unique=False)

    # Create payment_translations table
    op.create_table(
        'payment_translations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ase_name', sa.String(100), nullable=False),
        sa.Column('raw_message', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('RECEIVED', 'TRANSLATING', 'TRANSLATED', 'ILP_PREPARED', 'ILP_FULFILLED', 'ILP_REJECTED', 'NOTIFIED', 'SETTLED', 'FAILED', name='paymentstatus'), nullable=False),
        sa.Column('amount_value', sa.Numeric(20, 2), nullable=True),
        sa.Column('amount_ilp_uint64', sa.BigInteger(), nullable=True),
        sa.Column('currency', sa.String(3), nullable=True),
        sa.Column('stan', sa.String(6), nullable=True),
        sa.Column('rrn', sa.String(12), nullable=True),
        sa.Column('mti', sa.String(4), nullable=True),
        sa.Column('processing_code', sa.String(6), nullable=True),
        sa.Column('terminal_id', sa.String(16), nullable=True),
        sa.Column('wallet_address', sa.String(255), nullable=True),
        sa.Column('rafiki_payment_id', sa.String(255), nullable=True),
        sa.Column('response_code', sa.String(2), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_payment_translations_ase_name', 'payment_translations', ['ase_name'], unique=False)
    op.create_index('ix_payment_translations_id', 'payment_translations', ['id'], unique=False)
    op.create_index('ix_payment_translations_rrn', 'payment_translations', ['rrn'], unique=False)
    op.create_index('ix_payment_translations_stan', 'payment_translations', ['stan'], unique=False)
    op.create_index('ix_payment_translations_status', 'payment_translations', ['status'], unique=False)

    # Create account_wallet_mapping table
    op.create_table(
        'account_wallet_mapping',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ase_name', sa.String(100), nullable=False),
        sa.Column('account_number', sa.String(100), nullable=False),
        sa.Column('wallet_address', sa.String(255), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, default=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_account_wallet_mapping_account_number', 'account_wallet_mapping', ['account_number'], unique=False)
    op.create_index('ix_account_wallet_mapping_ase_name', 'account_wallet_mapping', ['ase_name'], unique=False)
    op.create_index('ix_account_wallet_mapping_id', 'account_wallet_mapping', ['id'], unique=False)

    # Create settlement_batches table
    op.create_table(
        'settlement_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ase_name', sa.String(100), nullable=False),
        sa.Column('batch_date', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('total_amount', sa.Numeric(20, 2), nullable=False),
        sa.Column('payment_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'SUBMITTED', 'FAILED', name='batchstatus'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_settlement_batches_ase_name', 'settlement_batches', ['ase_name'], unique=False)
    op.create_index('ix_settlement_batches_id', 'settlement_batches', ['id'], unique=False)

    # Create audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('from_status', sa.Enum('RECEIVED', 'TRANSLATING', 'TRANSLATED', 'ILP_PREPARED', 'ILP_FULFILLED', 'ILP_REJECTED', 'NOTIFIED', 'SETTLED', 'FAILED', name='paymentstatus'), nullable=True),
        sa.Column('to_status', sa.Enum('RECEIVED', 'TRANSLATING', 'TRANSLATED', 'ILP_PREPARED', 'ILP_FULFILLED', 'ILP_REJECTED', 'NOTIFIED', 'SETTLED', 'FAILED', name='paymentstatus'), nullable=False),
        sa.Column('triggered_by', sa.Enum('ASE_INBOUND', 'TRANSLATION_JOB', 'RAFIKI_WEBHOOK', 'SETTLEMENT_JOB', 'SYSTEM', name='triggeredby'), nullable=False),
        sa.Column('meta_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['payment_id'], ['payment_translations.id']),
    )
    op.create_index('ix_audit_log_payment_id', 'audit_log', ['payment_id'], unique=False)
    op.create_index('ix_audit_log_id', 'audit_log', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('settlement_batches')
    op.drop_table('account_wallet_mapping')
    op.drop_table('payment_translations')
    op.drop_table('ase_registry')
