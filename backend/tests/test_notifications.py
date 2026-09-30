from email.message import EmailMessage
from datetime import UTC, datetime, timedelta
from pathlib import Path
import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings, get_settings
from app.database import (
    Database, EmailVerificationRow, NotificationPreferenceRow,
    RiskDriftDeliveryRow, RiskDriftEventRow, UserRow,
)
from app.main import _last_test_email_sent, app, get_database
from app.services.notifications import (
    NotificationRepository, NotificationService,
    email_is_configured,
    email_provider,
    masked_email,
)
from tests.support import CsrfTestClient


def configured_settings() -> Settings:
    return Settings(
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_username="sender@qq.com",
        smtp_password="mail-client-authorization-code",
        smtp_from_email="sender@qq.com",
        smtp_security="ssl",
    )


def configured_brevo_settings() -> Settings:
    return Settings(
        brevo_api_key="xkeysib-test-key",
        brevo_sender_email="sender@qq.com",
    )


def test_brevo_webhook_requires_token_and_updates_matching_delivery(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "brevo-webhook.db"))
    settings = configured_brevo_settings()
    settings.brevo_webhook_token = "test-webhook-token-with-at-least-32-characters"
    settings.background_alerts_enabled = False
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    with database.session() as session:
        user = UserRow(email="owner@example.com", password_hash="hash")
        session.add(user)
        session.flush()
        event = RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="stable",
            current_status="deteriorating", transition_date="2026-09-30",
            severity="warning", title="BTC 衰减", message="复核",
        )
        session.add(event)
        session.flush()
        delivery = RiskDriftDeliveryRow(
            event_id=event.id, user_id=user.id, channel="email", status="sent",
            provider_message_id="tracking-123@brevo.test",
        )
        session.add(delivery)
        session.commit()
        delivery_id = delivery.id
        user_id = user.id
    client = TestClient(app)
    payload = {
        "event": "delivered", "email": "owner@example.com",
        "message-id": "<tracking-123@brevo.test>", "ts_event": 1_780_000_000,
    }
    headers = {"Authorization": f"Bearer {settings.brevo_webhook_token}"}
    try:
        assert client.post("/api/webhooks/brevo", json=payload).status_code == 401
        assert client.post(
            "/api/webhooks/brevo", json=payload, headers={"Authorization": "Bearer wrong"},
        ).status_code == 401
        accepted = client.post("/api/webhooks/brevo", json=payload, headers=headers)
        assert accepted.status_code == 200
        assert accepted.json() == {"status": "updated"}
        assert client.post("/api/webhooks/brevo", json=payload, headers=headers).json() == {"status": "ignored"}
        assert client.post("/api/webhooks/brevo", json={
            **payload, "event": "hard_bounce", "ts_event": 1_779_999_999,
        }, headers=headers).json() == {"status": "ignored"}
        assert client.post("/api/webhooks/brevo", json={
            **payload, "email": "another@example.com", "event": "hard_bounce", "ts_event": 1_780_000_001,
        }, headers=headers).json() == {"status": "ignored"}
        bounced = client.post("/api/webhooks/brevo", json={
            **payload, "event": "hard_bounce", "ts_event": 1_780_000_002,
        }, headers=headers)
        assert bounced.json() == {"status": "updated"}
        with database.session() as session:
            saved = session.get(RiskDriftDeliveryRow, delivery_id)
            assert saved.status == "bounced"
            assert saved.provider_event_at is not None
        history = NotificationRepository(database, user_id).list_drift_deliveries()
        assert history[0].status == "bounced"
        assert history[0].provider_event_at is not None
        assert client.post("/api/webhooks/brevo", json={
            **payload, "message-id": "missing@brevo.test",
        }, headers=headers).json() == {"status": "ignored"}
        assert client.post("/api/webhooks/brevo", json={
            **payload, "event": "opened",
        }, headers=headers).json() == {"status": "ignored"}
        assert client.post("/api/webhooks/brevo", content="[1]", headers=headers).status_code == 400
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)


def test_brevo_webhook_is_closed_without_a_secret(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "brevo-webhook-off.db"))
    settings = configured_brevo_settings()
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        assert TestClient(app).post("/api/webhooks/brevo", json={}).status_code == 503
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)


def test_recognizes_mainland_email_provider() -> None:
    settings = configured_settings()

    assert email_is_configured(settings) is True
    assert email_provider(settings) == "QQ 邮箱"
    assert masked_email(settings.smtp_from_email) == "se***@qq.com"


@pytest.mark.anyio
async def test_brevo_https_api_is_preferred_and_receives_email(tmp_path: Path, monkeypatch) -> None:
    settings = configured_brevo_settings()
    service = NotificationService(Database(str(tmp_path / "brevo.db")), settings)
    captured = {}

    class FakeResponse:
        status_code = 201
        text = ""

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.services.notifications.httpx.post", fake_post)
    await service.send_test_email("recipient@qq.com")

    assert email_is_configured(settings) is True
    assert email_provider(settings) == "Brevo HTTPS API"
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["api-key"] == "xkeysib-test-key"
    assert captured["json"]["sender"]["email"] == "sender@qq.com"
    assert captured["json"]["to"][0]["email"] == "recipient@qq.com"
    assert "邮箱通知测试成功" in captured["json"]["subject"]


@pytest.mark.anyio
async def test_brevo_drift_send_saves_message_id_for_delivery_tracking(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "brevo-tracking.db"))
    service = NotificationService(database, configured_brevo_settings())
    with database.session() as session:
        user = UserRow(email="tracked@example.com", password_hash="hash")
        session.add(user)
        session.flush()
        session.add_all([
            EmailVerificationRow(user_id=user.id, verified_at=datetime.now(UTC)),
            NotificationPreferenceRow(user_id=user.id, drift_email_enabled=True),
        ])
        session.add(RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="stable",
            current_status="deteriorating", transition_date="2026-09-30",
            severity="warning", title="BTC 模型衰减", message="需要复核",
        ))
        session.commit()

    class FakeResponse:
        status_code = 201

        def json(self):
            return {"messageId": "<tracked-message@brevo.test>"}

    monkeypatch.setattr("app.services.notifications.httpx.post", lambda *_args, **_kwargs: FakeResponse())
    from app.services.drift import RiskDriftRepository
    event = RiskDriftRepository(database).recent_events()[0]
    assert (await service.deliver_drift_events([event]))["sent"] == 1
    with database.session() as session:
        delivery = session.scalar(select(RiskDriftDeliveryRow))
        assert delivery.provider_message_id == "tracked-message@brevo.test"
        assert delivery.status == "sent"


@pytest.mark.anyio
async def test_test_email_contains_plain_and_html_parts(tmp_path: Path, monkeypatch) -> None:
    service = NotificationService(Database(str(tmp_path / "notifications.db")), configured_settings())
    captured: list[EmailMessage] = []
    monkeypatch.setattr(service, "_send_message_sync", captured.append)

    await service.send_test_email("recipient@163.com")

    assert len(captured) == 1
    assert captured[0]["To"] == "recipient@163.com"
    assert "邮箱通知测试成功" in str(captured[0]["Subject"])
    assert captured[0].is_multipart()


def test_rejects_unknown_smtp_security(tmp_path: Path) -> None:
    settings = configured_settings()
    settings.smtp_security = "unsafe"
    service = NotificationService(Database(str(tmp_path / "notifications.db")), settings)

    with pytest.raises(RuntimeError, match="SMTP_SECURITY"):
        service._require_configuration()


def test_logged_in_user_can_enable_and_test_email(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "notification-api.db"))
    settings = configured_settings()
    settings.session_secret = "notification-test-secret"
    settings.background_alerts_enabled = False
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    sent_messages = []
    monkeypatch.setattr(
        NotificationService,
        "_send_message_sync",
        lambda self, message: sent_messages.append(message),
    )
    monkeypatch.setattr("app.main.monotonic", lambda: 10.0)
    _last_test_email_sent.clear()
    client = CsrfTestClient(app)
    try:
        registered = client.post(
            "/api/auth/register",
            json={"email": "recipient@163.com", "password": "safe-password-4"},
        )
        assert registered.status_code == 201
        verification_body = sent_messages[0].get_body(preferencelist=("plain",)).get_content()
        match = re.search(r"verify_email_token=([^\s#]+)#account", verification_body)
        assert match is not None
        verified = client.post(
            "/api/auth/email-verification/confirm",
            json={"token": unquote(match.group(1))},
        )
        assert verified.status_code == 200
        enabled = client.put(
            "/api/notifications/settings",
            json={"email_enabled": True, "drift_email_enabled": True},
        )
        sent = client.post("/api/notifications/test-email")
        throttled = client.post("/api/notifications/test-email")

        assert enabled.status_code == 200
        assert enabled.json()["email_provider"] == "QQ 邮箱"
        assert enabled.json()["drift_email_enabled"] is True
        assert sent.status_code == 200
        assert sent.json()["recipient"] == "recipient@163.com"
        assert throttled.status_code == 429
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)
        _last_test_email_sent.clear()


def test_drift_delivery_history_is_private(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "drift-history.db"))
    settings = Settings(session_secret="drift-history-secret", background_alerts_enabled=False)
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_settings] = lambda: settings
    first = CsrfTestClient(app)
    second = CsrfTestClient(app)
    guest = CsrfTestClient(app)
    try:
        first_user = first.post(
            "/api/auth/register",
            json={"email": "first-history@example.com", "password": "safe-password-1"},
        ).json()
        second_user = second.post(
            "/api/auth/register",
            json={"email": "second-history@example.com", "password": "safe-password-2"},
        ).json()
        with database.session() as session:
            first_event = RiskDriftEventRow(
                coin_id="bitcoin", symbol="BTC", previous_status="stable",
                current_status="deteriorating", transition_date="2026-09-29",
                severity="warning", title="BTC 模型衰减", message="需要复核",
            )
            second_event = RiskDriftEventRow(
                coin_id="ethereum", symbol="ETH", previous_status="stable",
                current_status="deteriorating", transition_date="2026-09-29",
                severity="warning", title="ETH 模型衰减", message="需要复核",
            )
            session.add_all([first_event, second_event])
            session.flush()
            session.add_all([
                RiskDriftDeliveryRow(
                    event_id=first_event.id, user_id=first_user["id"],
                    channel="email", status="sent",
                ),
                RiskDriftDeliveryRow(
                    event_id=second_event.id, user_id=second_user["id"],
                    channel="email", status="failed",
                ),
            ])
            session.commit()

        assert guest.get("/api/notifications/drift-deliveries").status_code == 401
        first_response = first.get("/api/notifications/drift-deliveries")
        second_response = second.get("/api/notifications/drift-deliveries")
        assert first_response.status_code == 200
        assert [(item["symbol"], item["status"]) for item in first_response.json()] == [("BTC", "sent")]
        assert [(item["symbol"], item["status"]) for item in second_response.json()] == [("ETH", "failed")]
    finally:
        app.dependency_overrides.pop(get_database, None)
        app.dependency_overrides.pop(get_settings, None)


@pytest.mark.anyio
async def test_drift_email_requires_opt_in_and_suppresses_repeat_for_asset(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "drift-notifications.db"))
    service = NotificationService(database, configured_settings())
    sent: list[EmailMessage] = []
    monkeypatch.setattr(service, "_send_message_sync", sent.append)

    with database.session() as session:
        subscribed = UserRow(email="subscribed@example.com", password_hash="hash")
        unverified = UserRow(email="unverified@example.com", password_hash="hash")
        opted_out = UserRow(email="optedout@example.com", password_hash="hash")
        session.add_all([subscribed, unverified, opted_out])
        session.flush()
        session.add_all([
            EmailVerificationRow(user_id=subscribed.id, verified_at=datetime.now(UTC)),
            EmailVerificationRow(user_id=unverified.id),
            EmailVerificationRow(user_id=opted_out.id, verified_at=datetime.now(UTC)),
            NotificationPreferenceRow(user_id=subscribed.id, drift_email_enabled=True),
            NotificationPreferenceRow(user_id=unverified.id, drift_email_enabled=True),
            NotificationPreferenceRow(user_id=opted_out.id, drift_email_enabled=False),
        ])
        first = RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="stable",
            current_status="deteriorating", transition_date="2026-09-29",
            severity="warning", title="BTC 模型检测到性能衰减", message="需要复核",
        )
        session.add(first)
        session.commit()
        first_id = first.id

    from app.services.drift import RiskDriftRepository
    repository = RiskDriftRepository(database)
    first_event = repository.recent_events()[0]
    assert first_event.id == first_id
    assert await service.deliver_drift_events([first_event]) == {
        "sent": 1, "failed": 0, "suppressed": 0, "deduplicated": 0,
    }
    assert len(sent) == 1
    assert sent[0]["To"] == "subscribed@example.com"
    assert await service.deliver_drift_events([first_event]) == {
        "sent": 0, "failed": 0, "suppressed": 0, "deduplicated": 1,
    }
    assert len(sent) == 1

    with database.session() as session:
        second = RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="mixed",
            current_status="deteriorating", transition_date="2026-09-30",
            severity="warning", title="BTC 模型再次衰减", message="需要复核",
        )
        session.add(second)
        session.commit()
        second_id = second.id

    second_event = next(event for event in repository.recent_events() if event.id == second_id)
    assert await service.deliver_drift_events([second_event]) == {
        "sent": 0, "failed": 0, "suppressed": 1, "deduplicated": 0,
    }
    assert len(sent) == 1
    with database.session() as session:
        deliveries = list(session.scalars(
            select(RiskDriftDeliveryRow).order_by(RiskDriftDeliveryRow.event_id)
        ))
    assert [(row.event_id, row.status) for row in deliveries] == [
        (first_id, "sent"), (second_id, "suppressed"),
    ]


@pytest.mark.anyio
async def test_failed_drift_email_retries_later_only_while_opted_in(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "drift-retry.db"))
    service = NotificationService(database, configured_settings())
    with database.session() as session:
        user = UserRow(email="retry@example.com", password_hash="hash")
        session.add(user)
        session.flush()
        session.add_all([
            EmailVerificationRow(user_id=user.id, verified_at=datetime.now(UTC)),
            NotificationPreferenceRow(user_id=user.id, drift_email_enabled=True),
        ])
        event = RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="stable",
            current_status="deteriorating", transition_date="2026-09-30",
            severity="warning", title="BTC 模型衰减", message="需要复核",
        )
        session.add(event)
        session.commit()
        event_id = event.id
        user_id = user.id

    from app.services.drift import RiskDriftRepository
    event_model = RiskDriftRepository(database).recent_events()[0]

    async def fail_to_send(_recipient, _event):
        raise RuntimeError("provider unavailable")

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(service, "_send_drift_email", fail_to_send)
    monkeypatch.setattr("app.services.notifications.asyncio.sleep", no_wait)
    assert (await service.deliver_drift_events([event_model]))["failed"] == 1
    assert (await service.retry_failed_drift_events())["sent"] == 0

    with database.session() as session:
        delivery = session.scalar(select(RiskDriftDeliveryRow).where(RiskDriftDeliveryRow.event_id == event_id))
        assert delivery is not None
        delivery.attempted_at = datetime.now(UTC) - timedelta(hours=1)
        session.get(NotificationPreferenceRow, user_id).drift_email_enabled = False
        session.commit()
    assert (await service.retry_failed_drift_events())["sent"] == 0

    sent = []

    async def succeed(_recipient, event):
        sent.append(event.id)

    monkeypatch.setattr(service, "_send_drift_email", succeed)
    with database.session() as session:
        session.get(NotificationPreferenceRow, user_id).drift_email_enabled = True
        session.commit()
    assert (await service.retry_failed_drift_events())["sent"] == 1
    assert sent == [event_id]
    assert (await service.retry_failed_drift_events())["sent"] == 0

    with database.session() as session:
        delivery = session.scalar(select(RiskDriftDeliveryRow).where(RiskDriftDeliveryRow.event_id == event_id))
        assert delivery.status == "sent"


@pytest.mark.anyio
async def test_failed_drift_email_does_not_retry_after_a_newer_transition(tmp_path: Path, monkeypatch) -> None:
    database = Database(str(tmp_path / "drift-stale-retry.db"))
    service = NotificationService(database, configured_settings())
    now = datetime.now(UTC)
    with database.session() as session:
        user = UserRow(email="stale@example.com", password_hash="hash")
        session.add(user)
        session.flush()
        session.add_all([
            EmailVerificationRow(user_id=user.id, verified_at=now),
            NotificationPreferenceRow(user_id=user.id, drift_email_enabled=True),
        ])
        warning = RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="stable",
            current_status="deteriorating", transition_date="2026-09-29",
            severity="warning", title="BTC 模型衰减", message="需要复核",
            created_at=now - timedelta(hours=2),
        )
        session.add(warning)
        session.flush()
        session.add(RiskDriftDeliveryRow(
            event_id=warning.id, user_id=user.id, channel="email", status="failed",
            attempted_at=now - timedelta(hours=1),
        ))
        session.add(RiskDriftEventRow(
            coin_id="bitcoin", symbol="BTC", previous_status="deteriorating",
            current_status="stable", transition_date="2026-09-30",
            severity="info", title="BTC 模型恢复", message="已恢复",
            created_at=now - timedelta(minutes=10),
        ))
        session.commit()

    async def unexpected_send(_recipient, _event):
        raise AssertionError("A stale warning must not be sent")

    monkeypatch.setattr(service, "_send_drift_email", unexpected_send)
    assert (await service.retry_failed_drift_events()) == {
        "sent": 0, "failed": 0, "suppressed": 0, "deduplicated": 0,
    }
