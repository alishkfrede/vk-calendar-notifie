import pytest
from datetime import datetime, timezone, timedelta
from app.services.notification_engine import NotificationEngine
from app.models import User, UserSettings, Event
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
    user = User(vk_user_id=888888, timezone="UTC")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_settings(db_session, test_user):
    settings = UserSettings(
        user_id=test_user.id,
        grouping_window_minutes=120,  # 2 часа
    )
    db_session.add(settings)
    db_session.commit()
    return settings


def test_grouping_close_events(db_session, test_user, test_settings):
    """Тест: события в пределах 2 часов группируются."""
    engine = NotificationEngine(db_session, test_user)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    
    events = [
        Event(
            external_id=f"evt{i}",
            user_id=test_user.id,
            title=f"Событие {i}",
            start_time=base_time + timedelta(minutes=i * 30),  # Каждые 30 минут
            end_time=base_time + timedelta(minutes=i * 30 + 60),
            status="confirmed",
        )
        for i in range(3)
    ]
    
    for event in events:
        db_session.add(event)
    db_session.commit()
    
    groups = engine.group_events_by_window(events, window_minutes=120)
    
    # Все 3 события должны быть в одной группе (разница < 2 часа)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_grouping_separated_events(db_session, test_user, test_settings):
    """Тест: события с разницей > 2 часа не группируются."""
    engine = NotificationEngine(db_session, test_user)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    
    events = [
        Event(
            external_id="evt1",
            user_id=test_user.id,
            title="Событие 1",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),
            status="confirmed",
        ),
        Event(
            external_id="evt2",
            user_id=test_user.id,
            title="Событие 2",
            start_time=base_time + timedelta(hours=5),  # Через 5 часов
            end_time=base_time + timedelta(hours=6),
            status="confirmed",
        ),
    ]
    
    for event in events:
        db_session.add(event)
    db_session.commit()
    
    groups = engine.group_events_by_window(events, window_minutes=120)
    
    # Должно быть 2 отдельные группы
    assert len(groups) == 2
    assert len(groups[0]) == 1
    assert len(groups[1]) == 1


def test_format_grouped_message_single_event(db_session, test_user, test_settings):
    """Тест: форматирование сообщения для одного события."""
    engine = NotificationEngine(db_session, test_user)
    
    event = Event(
        external_id="evt1",
        user_id=test_user.id,
        title="Встреча с клиентом",
        start_time=datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
        location="Офис",
        status="confirmed",
    )
    
    message = engine.format_grouped_message([event])
    
    assert "Встреча с клиентом" in message
    assert "14:00" in message
    assert "Офис" in message


def test_format_grouped_message_multiple_events(db_session, test_user, test_settings):
    """Тест: форматирование сообщения для нескольких событий."""
    engine = NotificationEngine(db_session, test_user)
    
    events = [
        Event(
            external_id=f"evt{i}",
            user_id=test_user.id,
            title=f"Событие {i}",
            start_time=datetime(2026, 1, 1, 10 + i, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 1, 1, 11 + i, 0, 0, tzinfo=timezone.utc),
            status="confirmed",
        )
        for i in range(3)
    ]
    
    message = engine.format_grouped_message(events)
    
    assert "Сводка ближайших событий" in message
    assert "Событие 0" in message
    assert "Событие 1" in message
    assert "Событие 2" in message