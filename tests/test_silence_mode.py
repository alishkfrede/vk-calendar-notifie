import pytest
from datetime import datetime, timezone, timedelta
from app.services.notification_engine import NotificationEngine
from app.models import User, UserSettings, Event
from app.database import SessionLocal, Base, engine


@pytest.fixture
def db_session():
    """Создаёт тестовую БД."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db_session):
    """Создаёт тестового пользователя."""
    user = User(vk_user_id=999999, timezone="UTC")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_settings(db_session, test_user):
    """Создаёт тестовые настройки."""
    settings = UserSettings(
        user_id=test_user.id,
        silence_start="23:00",
        silence_end="08:00",
        priority_keywords=["срочно", "врач"],
        reminder_intervals=[60, 15, 5],
        grouping_window_minutes=120,
    )
    db_session.add(settings)
    db_session.commit()
    return settings


def test_silence_mode_during_night(db_session, test_user, test_settings):
    """Тест: режим тишины активен ночью."""
    engine = NotificationEngine(db_session, test_user)
    
    # 02:00 — должна быть тишина
    night_time = datetime(2026, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
    assert engine.is_silence_mode_active(night_time) is True


def test_silence_mode_during_day(db_session, test_user, test_settings):
    """Тест: режим тишины не активен днём."""
    engine = NotificationEngine(db_session, test_user)
    
    # 12:00 — тишина не активна
    day_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert engine.is_silence_mode_active(day_time) is False


def test_priority_event_bypasses_silence(db_session, test_user, test_settings):
    """Тест: приоритетное событие обходит режим тишины."""
    engine = NotificationEngine(db_session, test_user)
    
    # Создаём приоритетное событие
    event = Event(
        external_id="test1",
        user_id=test_user.id,
        title="Срочно: врач",
        start_time=datetime(2026, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 3, 0, 0, tzinfo=timezone.utc),
        status="confirmed",
    )
    db_session.add(event)
    db_session.commit()
    
    # Проверяем, что событие приоритетное
    assert engine.is_priority_event(event) is True
    
    # Проверяем, что уведомление должно быть отправлено даже в тишину
    should_send, reason = engine.should_send_notification(event, event.start_time)
    assert should_send is True
    assert "Приоритетное событие" in reason


def test_regular_event_blocked_during_silence(db_session, test_user, test_settings):
    """Тест: обычное событие блокируется в режиме тишины."""
    engine = NotificationEngine(db_session, test_user)
    
    # Создаём обычное событие
    event = Event(
        external_id="test2",
        user_id=test_user.id,
        title="Встреча с коллегой",
        start_time=datetime(2026, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 3, 0, 0, tzinfo=timezone.utc),
        status="confirmed",
    )
    db_session.add(event)
    db_session.commit()
    
    # Проверяем, что событие НЕ приоритетное
    assert engine.is_priority_event(event) is False
    
    # Проверяем, что уведомление НЕ должно быть отправлено в тишину
    should_send, reason = engine.should_send_notification(event, event.start_time)
    assert should_send is False
    assert "Режим тишины" in reason