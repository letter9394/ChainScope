"""Add opt-in risk-drift email delivery audit records.

Revision ID: 20260929_0003
Revises: 20260929_0002
Create Date: 2026-09-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260929_0003"
down_revision: str | None = "20260929_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    preference_columns = {
        column["name"] for column in inspector.get_columns("notification_preferences")
    }
    if "drift_email_enabled" not in preference_columns:
        op.add_column(
            "notification_preferences",
            sa.Column(
                "drift_email_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    op.create_table(
        "risk_drift_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["risk_drift_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "user_id", "channel",
            name="uq_risk_drift_delivery_event_user_channel",
        ),
    )
    op.create_index(
        "ix_risk_drift_deliveries_event_id", "risk_drift_deliveries", ["event_id"]
    )
    op.create_index(
        "ix_risk_drift_deliveries_user_id", "risk_drift_deliveries", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_risk_drift_deliveries_user_id", table_name="risk_drift_deliveries")
    op.drop_index("ix_risk_drift_deliveries_event_id", table_name="risk_drift_deliveries")
    op.drop_table("risk_drift_deliveries")
    op.drop_column("notification_preferences", "drift_email_enabled")
