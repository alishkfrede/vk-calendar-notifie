from datetime import datetime, timezone
from typing import List, Dict, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from app.config import settings
from app.models import Event, CalendarConnection, User
from app.utils.crypto import encrypt_token, decrypt_token
from app.utils.logger import log


# Scopes для доступа к календарю
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_oauth_flow() -> Flow:
    """Создаёт OAuth flow для авторизации."""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=SCOPES,
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    return flow


def get_authorization_url(user_id: int) -> str:
    """Возвращает URL для авторизации пользователя."""
    flow = get_oauth_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    # В реальном приложении state нужно сохранять для проверки
    log.info(f"Сгенерирован URL авторизации для user_id={user_id}")
    return authorization_url


def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Обменивает authorization code на токены."""
    flow = get_oauth_flow()
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    tokens = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    log.info("Токены успешно получены от Google")
    return tokens


def save_tokens(user_id: int, tokens: Dict[str, Any], db: Session) -> None:
    """Сохраняет зашифрованные токены в БД."""
    # Сериализуем токены в JSON
    import json
    tokens_json = json.dumps(tokens)
    encrypted = encrypt_token(tokens_json)
    
    # Проверяем, есть ли уже подключение
    connection = db.query(CalendarConnection).filter(
        CalendarConnection.user_id == user_id
    ).first()
    
    if connection:
        connection.encrypted_token = encrypted
        connection.status = "active"
    else:
        connection = CalendarConnection(
            user_id=user_id,
            encrypted_token=encrypted,
            status="active",
        )
        db.add(connection)
    
    db.commit()
    log.info(f"Токены сохранены для user_id={user_id}")


def get_credentials(user_id: int, db: Session) -> Credentials:
    """Получает Credentials из БД для пользователя."""
    import json
    
    connection = db.query(CalendarConnection).filter(
        CalendarConnection.user_id == user_id,
        CalendarConnection.status == "active",
    ).first()
    
    if not connection:
        raise ValueError(f"Нет активного подключения к календарю для user_id={user_id}")
    
    tokens_json = decrypt_token(connection.encrypted_token)
    tokens = json.loads(tokens_json)
    
    credentials = Credentials(
        token=tokens.get("token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=tokens.get("token_uri"),
        client_id=tokens.get("client_id"),
        client_secret=tokens.get("client_secret"),
        scopes=tokens.get("scopes"),
    )
    
    return credentials


def sync_events(user_id: int, db: Session) -> List[Event]:
    """Синхронизирует события из Google Calendar."""
    from datetime import timedelta
    
    credentials = get_credentials(user_id, db)
    service = build("calendar", "v3", credentials=credentials)
    
    # Получаем события на ближайшие 30 дней
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=30)).isoformat()
    
    log.info(f"Начало синхронизации событий для user_id={user_id}")
    
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    
    events = events_result.get("items", [])
    log.info(f"Получено {len(events)} событий из Google Calendar")
    
    # Удаляем старые события пользователя
    db.query(Event).filter(Event.user_id == user_id).delete()
    
    # Сохраняем новые события
    saved_events = []
    for event_data in events:
        # Парсим время начала
        start = event_data.get("start", {})
        start_time = start.get("dateTime") or start.get("date")
        
        # Парсим время окончания
        end = event_data.get("end", {})
        end_time = end.get("dateTime") or end.get("date")
        
        # Конвертируем в datetime с timezone
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        
        event = Event(
            external_id=event_data.get("id"),
            user_id=user_id,
            title=event_data.get("summary", "Без названия"),
            description=event_data.get("description"),
            start_time=start_dt,
            end_time=end_dt,
            location=event_data.get("location"),
            status=event_data.get("status", "confirmed"),
        )
        db.add(event)
        saved_events.append(event)
    
    # Обновляем last_synced
    connection = db.query(CalendarConnection).filter(
        CalendarConnection.user_id == user_id
    ).first()
    if connection:
        connection.last_synced = now
    
    db.commit()
    log.info(f"Синхронизация завершена. Сохранено {len(saved_events)} событий")
    
    return saved_events