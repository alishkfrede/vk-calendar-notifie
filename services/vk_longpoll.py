import threading
import time
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from sqlalchemy.orm import Session
from app.config import settings
from app.database import SessionLocal
from app.models import User, NotificationHistory
from app.services.notification_engine import NotificationEngine
from app.utils.logger import log


class VKLongPollService:
    """Сервис для обработки входящих сообщений через LongPoll."""
    
    def __init__(self):
        self.vk_session = vk_api.VkApi(token=settings.VK_SERVICE_TOKEN)
        self.longpoll = VkLongPoll(self.vk_session)
        self.vk = self.vk_session.get_api()
        self.running = False
        self.thread = None
    
    def start(self):
        """Запускает LongPoll в отдельном потоке."""
        if self.running:
            log.warning("LongPoll уже запущен")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()
        log.info("VK LongPoll запущен")
    
    def stop(self):
        """Останавливает LongPoll."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        log.info("VK LongPoll остановлен")
    
    def _listen(self):
        """Слушает входящие сообщения."""
        while self.running:
            try:
                for event in self.longpoll.listen():
                    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
                        self._handle_message(event.user_id, event.text)
            except Exception as e:
                log.error(f"Ошибка в LongPoll: {e}")
                time.sleep(5)
    
    def _handle_message(self, vk_user_id: int, text: str):
        """Обрабатывает входящее сообщение."""
        log.info(f"Получено сообщение от {vk_user_id}: {text}")
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.vk_user_id == vk_user_id).first()
            if not user:
                log.warning(f"Пользователь {vk_user_id} не найден в БД")
                return
            
            # Проверяем, является ли это командой
            command_type = self._detect_command_type(text)
            
            if command_type == "snooze":
                self._process_snooze_command(user, text, db)
            elif command_type == "help":
                self._send_help_message(vk_user_id)
            elif command_type == "status":
                self._send_status_message(user, vk_user_id, db)
            else:
                log.info(f"Сообщение от {vk_user_id} не является командой")
        
        finally:
            db.close()
    
    def _detect_command_type(self, text: str) -> str:
        """Определяет тип команды."""
        text_lower = text.strip().lower()
        
        # Команды откладывания
        if (
            text_lower.startswith("+") or
            text_lower in ["завтра", "tomorrow", "отмена", "cancel"]
        ):
            return "snooze"
        
        # Справка
        if text_lower in ["помощь", "help", "/help", "?"]:
            return "help"
        
        # Статус уведомлений
        if text_lower in ["статус", "status", "/status"]:
            return "status"
        
        return "unknown"
    
    def _process_snooze_command(self, user: User, command: str, db: Session):
        """Обрабатывает команду откладывания уведомления."""
        try:
            engine = NotificationEngine(db, user)
            
            # Находим последнее отправленное уведомление (не отложенное и не отменённое)
            last_notification = (
                db.query(NotificationHistory)
                .filter(
                    NotificationHistory.user_id == user.id,
                    NotificationHistory.status.in_(["sent", "snoozed"]),
                )
                .order_by(NotificationHistory.sent_at.desc())
                .first()
            )
            
            if not last_notification:
                self._send_vk_message(
                    user.vk_user_id,
                    "❌ Нет активных уведомлений для откладывания.",
                )
                return
            
            # Применяем команду
            new_time = engine.apply_snooze(last_notification, command)
            
            if new_time is None:
                # Отмена
                self._send_vk_message(
                    user.vk_user_id,
                    f"✅ Уведомление '{last_notification.message_text[:50]}...' отменено.",
                )
            else:
                # Откладывание
                time_str = new_time.strftime("%H:%M %d.%m.%Y")
                self._send_vk_message(
                    user.vk_user_id,
                    f"✅ Уведомление отложено до {time_str}.\n"
                    f"Команда: {command}",
                )
            
            log.info(f"Команда snooze обработана для {user.vk_user_id}: {command}")
        
        except Exception as e:
            log.error(f"Ошибка обработки команды snooze: {e}")
            self._send_vk_message(
                user.vk_user_id,
                f"❌ Ошибка при обработке команды: {str(e)}",
            )
    
    def _send_help_message(self, vk_user_id: int):
        """Отправляет справку по командам."""
        help_text = (
            "📖 Доступные команды:\n\n"
            "⏰ Откладывание уведомлений:\n"
            "  • +10 — отложить на 10 минут\n"
            "  • +30 — отложить на 30 минут\n"
            "  • +1ч — отложить на 1 час\n"
            "  • +2ч — отложить на 2 часа\n"
            "  • завтра — отложить на завтра\n"
            "  • отмена — отменить уведомление\n\n"
            "ℹ️ Другое:\n"
            "  • статус — показать активные уведомления\n"
            "  • помощь — показать эту справку"
        )
        self._send_vk_message(vk_user_id, help_text)
    
    def _send_status_message(self, user: User, vk_user_id: int, db: Session):
        """Отправляет статус активных уведомлений."""
        snoozed = (
            db.query(NotificationHistory)
            .filter(
                NotificationHistory.user_id == user.id,
                NotificationHistory.status == "snoozed",
                NotificationHistory.rescheduled_at.isnot(None),
            )
            .all()
        )
        
        if not snoozed:
            self._send_vk_message(vk_user_id, "📭 Нет отложенных уведомлений.")
            return
        
        message = f"📋 Отложенные уведомления ({len(snoozed)}):\n\n"
        for n in snoozed:
            time_str = n.rescheduled_at.strftime("%H:%M %d.%m.%Y")
            message += f"• [{time_str}] {n.message_text[:60]}...\n"
        
        self._send_vk_message(vk_user_id, message)
    
    def _send_vk_message(self, vk_user_id: int, message: str):
        """Отправляет сообщение через VK API."""
        try:
            self.vk.messages.send(
                user_id=vk_user_id,
                message=message,
                random_id=0,
            )
        except Exception as e:
            log.error(f"Ошибка отправки сообщения {vk_user_id}: {e}")


# Глобальный сервис
longpoll_service = VKLongPollService()