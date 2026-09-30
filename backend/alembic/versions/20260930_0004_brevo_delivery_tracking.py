"""Track Brevo message IDs and verified delivery events.

Revision ID: 20260930_0004
Revises: 20260929_0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260930_0004"
down_revision: str | None = "20260929_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "risk_drift_deliveries",
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "risk_drift_deliveries",
        sa.Column("provider_event_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_risk_drift_deliveries_provider_message_id",
        "risk_drift_deliveries",
        ["provider_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_risk_drift_deliveries_provider_message_id",
        table_name="risk_drift_deliveries",
    )
    op.drop_column("risk_drift_deliveries", "provider_event_at")
    op.drop_column("risk_drift_deliveries", "provider_message_id")
