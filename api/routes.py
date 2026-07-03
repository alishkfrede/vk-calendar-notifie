from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserSettings, Event
from app.schemas import HealthResponse, UserCreate, UserOut, SettingsUpdate, EventOut
from app.services.google_cal import (
    get_authorization_url,
    exchange_code_for_tokens,
    save_tokens,
    sync_events,
)
from app.utils.logger import log
from app.services.vk_client import vk_client
from app.services.scheduler_service import scheduler_service

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.vk_user_id == payload.vk_user_id).first()
    if existing:
        return existing
    user = User(vk_user_id=payload.vk_user_id, timezone=payload.timezone)
    db.add(user)
    db.commit()
    db.refresh(user)
    # Создаём дефолтные настройки
    db.add(UserSettings(user_id=user.id))
    db.commit()
    return user


@router.get("/users/{vk_user_id}", response_model=UserOut)
def get_user(vk_user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ===== OAuth Google =====

@router.get("/auth/google/login")
def google_login(vk_user_id: int = Query(..., description="VK user ID"), db: Session = Depends(get_db)):
    """Начинает OAuth-авторизацию через Google."""
    user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    auth_url = get_authorization_url(user.id)
    return RedirectResponse(url=auth_url)


@router.get("/auth/google/callback")
def google_callback(code: str = Query(...), db: Session = Depends(get_db)):
    """Обрабатывает callback от Google после авторизации."""
    try:
        # Обмениваем code на токены
        tokens = exchange_code_for_tokens(code)
        
        # Получаем информацию о пользователе из Google
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        credentials = Credentials(
            token=tokens.get("token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri"),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            scopes=tokens.get("scopes"),
        )
        
        # Для упрощения используем первого пользователя в БД
        # В реальном приложении нужно получать email из Google и находить пользователя
        user = db.query(User).first()
        if not user:
            raise HTTPException(status_code=404, detail="No users found")
        
        # Сохраняем токены
        save_tokens(user.id, tokens, db)
        
        return {"status": "success", "message": "Google Calendar connected successfully"}
    
    except Exception as e:
        log.error(f"Ошибка при обработке callback: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")


# ===== Синхронизация событий =====

@router.post("/sync/{vk_user_id}")
def sync_calendar(vk_user_id: int, db: Session = Depends(get_db)):
    """Запускает синхронизацию событий из Google Calendar."""
    user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        events = sync_events(user.id, db)
        return {
            "status": "success",
            "synced_events": len(events),
            "message": f"Synced {len(events)} events",
        }
    except Exception as e:
        log.error(f"Ошибка синхронизации: {e}")
        raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")


@router.get("/events/{vk_user_id}", response_model=list[EventOut])
def get_events(vk_user_id: int, db: Session = Depends(get_db)):
    """Получает все события пользователя."""
    user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    events = db.query(Event).filter(Event.user_id == user.id).all()
    return events

# ===== VK Уведомления =====

@router.post("/notify/{vk_user_id}")
def send_notification(
    vk_user_id: int,
    message: str = Query(..., description="Текст сообщения"),
    db: Session = Depends(get_db),
):
    """Отправляет уведомление пользователю ВКонтакте."""
    user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    success = vk_client.send_message(vk_user_id, message, db)
    
    if success:
        return {"status": "success", "message": "Notification sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send notification")


@router.get("/notifications/{vk_user_id}")
def get_notification_history(vk_user_id: int, db: Session = Depends(get_db)):
    """Получает историю уведомлений пользователя."""
    user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    notifications = (
        db.query(NotificationHistory)
        .filter(NotificationHistory.user_id == user.id)
        .order_by(NotificationHistory.sent_at.desc())
        .all()
    )
    
    return [
        {
            "id": n.id,
            "message_text": n.message_text,
            "sent_at": n.sent_at.isoformat(),
            "status": n.status,
            "vk_message_id": n.vk_message_id,
            "error_message": n.error_message,
        }
        for n in notifications
    ]

@router.post("/admin/weekly-summary")
def trigger_weekly_summary():
    """Ручной запуск еженедельной сводки (для тестирования)."""
    scheduler_service.send_weekly_summary()
    return {"status": "success", "message": "Weekly summary triggered"}