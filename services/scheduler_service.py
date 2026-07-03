from datetime import datetime, timedelta, timezone
from typing import List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Event, NotificationHistory, UserSettings
from app.services.notification_engine import NotificationEngine
from app.services.vk_client import vk_client
from app.utils.logger import log


class SchedulerService:
    """Сервис для планирования задач."""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.running = False
    
    def start(self):
        """Запускает планировщик."""
        if self.running:
            log.warning("Планировщик уже запущен")
            return
        
        # Задача проверки уведомлений каждую минуту
        self.scheduler.add_job(
            self.check_and_send_notifications,
            IntervalTrigger(minutes=1),
            id="check_notifications",
            name="Проверка и отправка уведомлений",
            replace_existing=True,
        )
        
        # Задача еженедельной сводки (каждый понедельник в 09:00)
        self.scheduler.add_job(
            self.send_weekly_summary,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="weekly_summary",
            name="Еженедельная сводка",
            replace_existing=True,
        )
        
        self.scheduler.start()
        self.running = True
        log.info("Планировщик задач запущен")
    
    def stop(self):
        """Останавливает планировщик."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self.running = False
            log.info("Планировщик остановлен")
    
    def check_and_send_notifications(self):
        """Проверяет и отправляет уведомления для всех пользователей."""
        db = SessionLocal()
        try:
            users = db.query(User).filter(User.is_active == True).all()
            current_time = datetime.now(timezone.utc)
            
            for user in users:
                # 1. Проверяем отложенные уведомления
                self._process_rescheduled_notifications(user, current_time, db)
                
                # 2. Проверяем новые уведомления
                self._process_user_notifications(user, current_time, db)
        
        except Exception as e:
            log.error(f"Ошибка при проверке уведомлений: {e}")
        finally:
            db.close()
    
    def _process_rescheduled_notifications(
        self, user: User, current_time: datetime, db: Session
    ):
        """Отправляет отложенные уведомления, время которых наступило."""
        try:
            # Находим уведомления, которые нужно отправить сейчас
            rescheduled = (
                db.query(NotificationHistory)
                .filter(
                    NotificationHistory.user_id == user.id,
                    NotificationHistory.status == "snoozed",
                    NotificationHistory.rescheduled_at.isnot(None),
                    NotificationHistory.rescheduled_at <= current_time,
                )
                .all()
            )
            
            for notification in rescheduled:
                # Отправляем сообщение
                success = vk_client.send_message(
                    user.vk_user_id,
                    f"🔔 (Отложенное напоминание)\n\n{notification.message_text}",
                    db,
                )
                
                if success:
                    # Обновляем статус
                    notification.status = "sent"
                    notification.rescheduled_at = None
                    db.commit()
                    log.info(
                        f"Отправлено отложенное уведомление для {user.vk_user_id}"
                    )
        
        except Exception as e:
            log.error(f"Ошибка отправки отложенных уведомлений: {e}")
    
    def _process_user_notifications(
        self, user: User, current_time: datetime, db: Session
    ):
        """Обрабатывает уведомления для одного пользователя."""
        try:
            # Получаем события пользователя на ближайшие 24 часа
            time_window = current_time + timedelta(hours=24)
            events = (
                db.query(Event)
                .filter(
                    Event.user_id == user.id,
                    Event.start_time >= current_time,
                    Event.start_time <= time_window,
                    Event.status == "confirmed",
                )
                .all()
            )
            
            if not events:
                return
            
            # Создаём движок уведомлений
            engine = NotificationEngine(db, user)
            
            # Генерируем уведомления
            notifications = engine.generate_notifications(events, current_time)
            
            # Отправляем уведомления, которые должны быть отправлены сейчас
            for notification in notifications:
                send_time = notification["send_time"]
                
                # Проверяем, нужно ли отправлять сейчас (в пределах 1 минуты)
                time_diff = abs((send_time - current_time).total_seconds())
                if time_diff <= 60:  # В пределах 1 минуты
                    # Проверяем, не отправляли ли уже
                    existing = (
                        db.query(NotificationHistory)
                        .filter(
                            NotificationHistory.user_id == user.id,
                            NotificationHistory.message_text == notification["message"],
                            NotificationHistory.sent_at >= current_time - timedelta(minutes=5),
                        )
                        .first()
                    )
                    
                    if not existing:
                        # Отправляем сообщение
                        success = vk_client.send_message(
                            user.vk_user_id,
                            notification["message"],
                            db,
                        )
                        
                        if success:
                            log.info(
                                f"Отправлено уведомление пользователю {user.vk_user_id}: "
                                f"{notification['type']}"
                            )
        
        except Exception as e:
            log.error(f"Ошибка обработки уведомлений для пользователя {user.id}: {e}")
    
    def send_weekly_summary(self):
        """Отправляет еженедельную сводку всем пользователям."""
        db = SessionLocal()
        try:
            users = db.query(User).filter(User.is_active == True).all()
            
            for user in users:
                self._send_user_weekly_summary(user, db)
        
        except Exception as e:
            log.error(f"Ошибка отправки еженедельной сводки: {e}")
        finally:
            db.close()
    
    def _send_user_weekly_summary(self, user: User, db: Session):
        """Отправляет еженедельную сводку одному пользователю."""
        try:
            # Получаем события на следующие 7 дней
            now = datetime.now(timezone.utc)
            week_end = now + timedelta(days=7)
            
            events = (
                db.query(Event)
                .filter(
                    Event.user_id == user.id,
                    Event.start_time >= now,
                    Event.start_time <= week_end,
                    Event.status == "confirmed",
                )
                .order_by(Event.start_time)
                .all()
            )
            
            if not events:
                message = "📅 На следующую неделю событий не запланировано."
            else:
                message = self._format_weekly_summary(events)
            
            # Отправляем сообщение
            success = vk_client.send_message(user.vk_user_id, message, db)
            
            if success:
                log.info(f"Еженедельная сводка отправлена пользователю {user.vk_user_id}")
        
        except Exception as e:
            log.error(f"Ошибка отправки сводки для пользователя {user.id}: {e}")
    
    def _format_weekly_summary(self, events: List[Event]) -> str:
        """Форматирует текст еженедельной сводки."""
        total_events = len(events)
        
        # Группируем по дням
        events_by_day = {}
        for event in events:
            day_key = event.start_time.strftime("%Y-%m-%d")
            if day_key not in events_by_day:
                events_by_day[day_key] = []
            events_by_day[day_key].append(event)
        
        message = f"📊 ЕЖЕНЕДЕЛЬНАЯ СВОДКА\n\n"
        message += f"📅 Всего событий: {total_events}\n\n"
        
        # Выводим по дням
        for day_key in sorted(events_by_day.keys()):
            day_events = events_by_day[day_key]
            date_str = datetime.strptime(day_key, "%Y-%m-%d").strftime("%A, %d %B")
            
            message += f"🗓 {date_str}:\n"
            for event in day_events:
                time_str = event.start_time.strftime("%H:%M")
                message += f"  • {time_str} - {event.title}\n"
            message += "\n"
        
        # Находим свободные окна (упрощённо)
        message += "💡 Свободные окна для работы:\n"
        message += "  • Утро (09:00-12:00) — наименьшая загрузка\n"
        message += "  • Вечер (18:00-21:00) — можно планировать важные задачи\n"
        
        return message


# Глобальный сервис
scheduler_service = SchedulerService()