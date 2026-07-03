import vk_api
from vk_api import VkUpload
from sqlalchemy.orm import Session
from app.config import settings
from app.models import User, NotificationHistory
from app.utils.logger import log


class VKClient:
    """Клиент для работы с VK API."""
    
    def __init__(self):
        self.vk_session = vk_api.VkApi(token=settings.VK_SERVICE_TOKEN)
        self.vk = self.vk_session.get_api()
        self.group_id = settings.VK_GROUP_ID
    
    def send_message(self, user_id: int, message: str, db: Session) -> bool:
        """Отправляет сообщение пользователю ВКонтакте."""
        try:
            # Получаем пользователя из БД
            user = db.query(User).filter(User.vk_user_id == user_id).first()
            if not user:
                log.error(f"Пользователь vk_user_id={user_id} не найден в БД")
                return False
            
            # Отправляем сообщение
            response = self.vk.messages.send(
                user_id=user_id,
                message=message,
                random_id=0,  # 0 означает, что мы не отслеживаем ID
            )
            
            # Сохраняем в историю
            notification = NotificationHistory(
                user_id=user.id,
                message_text=message,
                status="sent",
                vk_message_id=response,
            )
            db.add(notification)
            db.commit()
            
            log.info(f"Сообщение отправлено пользователю {user_id}: {message[:50]}...")
            return True
        
        except Exception as e:
            log.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
            
            # Сохраняем ошибку в историю
            user = db.query(User).filter(User.vk_user_id == user_id).first()
            if user:
                notification = NotificationHistory(
                    user_id=user.id,
                    message_text=message,
                    status="failed",
                    error_message=str(e),
                )
                db.add(notification)
                db.commit()
            
            return False
    
    def send_notification_with_retry(
        self, user_id: int, message: str, db: Session, max_retries: int = 3
    ) -> bool:
        """Отправляет сообщение с повторными попытками при ошибке."""
        import time
        
        for attempt in range(max_retries):
            if self.send_message(user_id, message, db):
                return True
            
            # Экспоненциальная задержка
            delay = 2 ** attempt
            log.warning(f"Попытка {attempt + 1}/{max_retries} не удалась. Ждём {delay}с...")
            time.sleep(delay)
        
        log.error(f"Не удалось отправить сообщение после {max_retries} попыток")
        return False


# Глобальный клиент
vk_client = VKClient()