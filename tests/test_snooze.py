import pytest
from datetime import datetime, timezone, timedelta
from app.services.notification_engine import NotificationEngine
from app.models import User, UserSettings, NotificationHistory
from app.database import SessionLocal, Base, engine


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db_session):
    user = User(vk_user_id=666666, timezone="UTC")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_settings(db_session, test_user):
    settings = UserSettings(user_id=test_user.id)
    db_session.add(settings)
    db_session.commit()
    return settings


def test_parse_snooze_minutes(db_session, test_user, test_settings):
    """Тест: парсинг команды '+10' (минуты)."""
    engine = NotificationEngine(db_session, test_user)
    
    delta = engine.parse_snooze_command("+10")
    
    assert delta == timedelta(minutes=10)


def test_parse_snooze_hours(db_session, test_user, test_settings):
    """Тест: парсинг команды '+2ч' (часы)."""
    engine = NotificationEngine(db_session, test_user)
    
    delta = engine.parse_snooze_command("+2ч")
    
    assert delta == timedelta(hours=2)


def test_parse_snooze_tomorrow(db_session, test_user, test_settings):
    """Тест: парсинг команды 'завтра'."""
    engine = NotificationEngine(db_session, test_user)
    
    delta = engine.parse_snooze_command("завтра")
    
    assert delta == timedelta(days=1)


def test_parse_snooze_cancel(db_session, test_user, test_settings):
    """Тест: парсинг команды 'отмена'."""
    engine = NotificationEngine(db_session, test_user)
    
    delta = engine.parse_snooze_command("отмена")
    
    assert delta is None


def test_apply_snooze(db_session, test_user, test_settings):
    """Тест: применение команды откладывания."""
    engine = NotificationEngine(db_session, test_user)
    
    notification = NotificationHistory(
        user_id=test_user.id,
        message_text="Тестовое уведомление",
        status="sent",
        sent_at=datetime(2026, 1, 1, 10, 0, 0),  # Убрали tzinfo
    )
    db_session.add(notification)
    db_session.commit()
    
    new_time = engine.apply_snooze(notification, "+30")
    
    expected_time = datetime(2026, 1, 1, 10, 30, 0)  # Убрали tzinfo
    assert new_time == expected_time
    assert notification.status == "snoozed"


def test_apply_cancel(db_session, test_user, test_settings):
    """Тест: применение команды отмены."""
    engine = NotificationEngine(db_session, test_user)
    
    notification = NotificationHistory(
        user_id=test_user.id,
        message_text="Тестовое уведомление",
        status="sent",
        sent_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(notification)
    db_session.commit()
    
    new_time = engine.apply_snooze(notification, "отмена")
    
    assert new_time is None
    assert notification.status == "cancelled"