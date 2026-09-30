from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailVerificationRow(Base):
    __tablename__ = "email_verifications"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WatchlistRow(Base):
    __tablename__ = "user_watchlist"
    __table_args__ = (UniqueConstraint("user_id", "coin_id", name="uq_watchlist_user_coin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coin_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(16))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertRuleRow(Base):
    __tablename__ = "user_alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coin_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(64))
    operator: Mapped[str] = mapped_column(String(8))
    threshold: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertEventRow(Base):
    __tablename__ = "user_alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("user_alert_rules.id", ondelete="CASCADE"), index=True)
    coin_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(64))
    operator: Mapped[str] = mapped_column(String(8))
    threshold: Mapped[float] = mapped_column(Float)
    observed_value: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(240))
    message: Mapped[str] = mapped_column(Text)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationPreferenceRow(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    drift_email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Kept only for compatibility with databases created before email-only v1.1.
    # These fields are never exposed or used and are always written disabled.
    legacy_telegram_enabled: Mapped[bool] = mapped_column("telegram_enabled", Boolean, default=False)
    legacy_telegram_chat_id: Mapped[str | None] = mapped_column(
        "telegram_chat_id", String(128), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class NotificationDeliveryRow(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("event_id", "channel", name="uq_delivery_event_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("user_alert_events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskDriftSnapshotRow(Base):
    __tablename__ = "risk_drift_snapshots"
    __table_args__ = (
        UniqueConstraint("coin_id", "evaluation_date", name="uq_risk_drift_coin_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coin_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    evaluation_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(32))
    selected_key: Mapped[str] = mapped_column(String(32))
    selected_label: Mapped[str] = mapped_column(String(120))
    horizon_days: Mapped[int] = mapped_column(Integer)
    lift_change: Mapped[float] = mapped_column(Float)
    brier_skill_change: Mapped[float] = mapped_column(Float)
    event_rate_change_percent_points: Mapped[float] = mapped_column(Float)
    latest_lift: Mapped[float] = mapped_column(Float)
    latest_brier_skill_score: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RiskDriftEventRow(Base):
    __tablename__ = "risk_drift_events"
    __table_args__ = (
        UniqueConstraint(
            "coin_id", "previous_status", "current_status", "transition_date",
            name="uq_risk_drift_transition",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coin_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    previous_status: Mapped[str] = mapped_column(String(32))
    current_status: Mapped[str] = mapped_column(String(32))
    transition_date: Mapped[str] = mapped_column(String(10))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(240))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RiskDriftDeliveryRow(Base):
    __tablename__ = "risk_drift_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "user_id", "channel", name="uq_risk_drift_delivery_event_user_channel"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("risk_drift_events.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Database:
    def __init__(self, url_or_path: str, *, initialize_schema: bool = True) -> None:
        url = self._normalize_url(url_or_path)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.url = url
        self.engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)
        if initialize_schema:
            self.create_schema()

    @staticmethod
    def _normalize_url(value: str) -> str:
        if "://" not in value:
            path = Path(value)
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{path.as_posix()}"
        if value.startswith("sqlite:///"):
            path_value = value.removeprefix("sqlite:///")
            path = Path(path_value)
            path.parent.mkdir(parents=True, exist_ok=True)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.session_factory()

    def ping(self) -> None:
        """Raise when the configured database cannot execute a minimal query."""

        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
