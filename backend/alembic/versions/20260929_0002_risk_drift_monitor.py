"""Persist risk-model drift snapshots and transition events.

Revision ID: 20260929_0002
Revises: 20260928_0001
Create Date: 2026-09-29
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260929_0002"
down_revision: str | None = "20260928_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_drift_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coin_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("evaluation_date", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("selected_key", sa.String(length=32), nullable=False),
        sa.Column("selected_label", sa.String(length=120), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("lift_change", sa.Float(), nullable=False),
        sa.Column("brier_skill_change", sa.Float(), nullable=False),
        sa.Column("event_rate_change_percent_points", sa.Float(), nullable=False),
        sa.Column("latest_lift", sa.Float(), nullable=False),
        sa.Column("latest_brier_skill_score", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coin_id", "evaluation_date", name="uq_risk_drift_coin_date"),
    )
    op.create_index("ix_risk_drift_snapshots_coin_id", "risk_drift_snapshots", ["coin_id"])
    op.create_index("ix_risk_drift_snapshots_observed_at", "risk_drift_snapshots", ["observed_at"])

    op.create_table(
        "risk_drift_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coin_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("current_status", sa.String(length=32), nullable=False),
        sa.Column("transition_date", sa.String(length=10), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "coin_id", "previous_status", "current_status", "transition_date",
            name="uq_risk_drift_transition",
        ),
    )
    op.create_index("ix_risk_drift_events_coin_id", "risk_drift_events", ["coin_id"])
    op.create_index("ix_risk_drift_events_created_at", "risk_drift_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_risk_drift_events_created_at", table_name="risk_drift_events")
    op.drop_index("ix_risk_drift_events_coin_id", table_name="risk_drift_events")
    op.drop_table("risk_drift_events")
    op.drop_index("ix_risk_drift_snapshots_observed_at", table_name="risk_drift_snapshots")
    op.drop_index("ix_risk_drift_snapshots_coin_id", table_name="risk_drift_snapshots")
    op.drop_table("risk_drift_snapshots")
