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
    user = User(vk_user_id=777777, timezone="UTC")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_settings(db_session, test_user):
    settings = UserSettings(user_id=test_user.id)
    db_session.add(settings)
    db_session.commit()
    return settings


def test_detect_overlapping_events(db_session, test_user, test_settings):
    """Тест: обнаружение пересекающихся событий."""
    engine = NotificationEngine(db_session, test_user)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    
    events = [
        Event(
            external_id="evt1",
            user_id=test_user.id,
            title="Встреча 1",
            start_time=base_time,
            end_time=base_time + timedelta(hours=2),  # 10:00-12:00
            status="confirmed",
        ),
        Event(
            external_id="evt2",
            user_id=test_user.id,
            title="Встреча 2",
            start_time=base_time + timedelta(hours=1),  # 11:00-13:00 (пересекается)
            end_time=base_time + timedelta(hours=3),
            status="confirmed",
        ),
    ]
    
    for event in events:
        db_session.add(event)
    db_session.commit()
    
    conflicts = engine.detect_conflicts(events)
    
    assert len(conflicts) == 1
    assert conflicts[0][0].title == "Встреча 1"
    assert conflicts[0][1].title == "Встреча 2"


def test_detect_non_overlapping_events(db_session, test_user, test_settings):
    """Тест: не пересекающиеся события не конфликтуют."""
    engine = NotificationEngine(db_session, test_user)
    
    base_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    
    events = [
        Event(
            external_id="evt1",
            user_id=test_user.id,
            title="Встреча 1",
            start_time=base_time,
            end_time=base_time + timedelta(hours=1),  # 10:00-11:00
            status="confirmed",
        ),
        Event(
            external_id="evt2",
            user_id=test_user.id,
            title="Встреча 2",
            start_time=base_time + timedelta(hours=2),  # 12:00-13:00 (не пересекается)
            end_time=base_time + timedelta(hours=3),
            status="confirmed",
        ),
    ]
    
    for event in events:
        db_session.add(event)
    db_session.commit()
    
    conflicts = engine.detect_conflicts(events)
    
    assert len(conflicts) == 0


def test_format_conflict_warning(db_session, test_user, test_settings):
    """Тест: форматирование предупреждения о конфликте."""
    engine = NotificationEngine(db_session, test_user)
    
    event1 = Event(
        external_id="evt1",
        user_id=test_user.id,
        title="Встреча с клиентом",
        start_time=datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        status="confirmed",
    )
    
    event2 = Event(
        external_id="evt2",
        user_id=test_user.id,
        title="Звонок руководителю",
        start_time=datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, 11, 30, 0, tzinfo=timezone.utc),
        status="confirmed",
    )
    
    message = engine.format_conflict_warning(event1, event2)
    
    assert "КОНФЛИКТ РАСПИСАНИЯ" in message
    assert "Встреча с клиентом" in message
    assert "Звонок руководителю" in message