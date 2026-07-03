from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models import Event, UserSettings, User, NotificationHistory
from app.utils.logger import log


class NotificationEngine:
    """Ядро бизнес-логики уведомлений."""
    
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.settings = self._get_user_settings()
    
    def _get_user_settings(self) -> UserSettings:
        """Получает настройки пользователя."""
        settings = self.db.query(UserSettings).filter(
            UserSettings.user_id == self.user.id
        ).first()
        if not settings:
            settings = UserSettings(user_id=self.user.id)
            self.db.add(settings)
            self.db.commit()
        return settings
    
    # ===== 1. Режим ограничения уведомлений (Silence Mode) =====
    
    def is_silence_mode_active(self, check_time: datetime) -> bool:
        """Проверяет, активен ли режим тишины в указанное время."""
        if not self.settings.silence_start or not self.settings.silence_end:
            return False
        
        try:
            # Парсим время тишины (формат "HH:MM")
            silence_start = datetime.strptime(
                self.settings.silence_start, "%H:%M"
            ).time()
            silence_end = datetime.strptime(
                self.settings.silence_end, "%H:%M"
            ).time()
            
            check_time_time = check_time.time()
            
            # Если время окончания < времени начала (например, 23:00-08:00)
            if silence_end < silence_start:
                # Активен, если время >= start ИЛИ < end
                return check_time_time >= silence_start or check_time_time < silence_end
            else:
                # Обычный интервал (например, 13:00-14:00)
                return silence_start <= check_time_time < silence_end
        
        except ValueError as e:
            log.error(f"Ошибка парсинга времени тишины: {e}")
            return False
    
    def is_priority_event(self, event: Event) -> bool:
        """Проверяет, является ли событие приоритетным (исключение из режима тишины)."""
        if not self.settings.priority_keywords:
            return False
        
        keywords = [kw.lower() for kw in self.settings.priority_keywords]
        
        # Проверяем название и описание
        text_to_check = f"{event.title} {event.description or ''}".lower()
        
        return any(keyword in text_to_check for keyword in keywords)
    
    def should_send_notification(
        self, event: Event, notification_time: datetime
    ) -> Tuple[bool, str]:
        """Определяет, нужно ли отправлять уведомление в указанное время."""
        # Проверяем режим тишины
        if self.is_silence_mode_active(notification_time):
            # Если активен, проверяем, приоритетное ли событие
            if self.is_priority_event(event):
                return True, "Приоритетное событие, отправляется в режиме тишины"
            else:
                return False, "Режим тишины активен"
        
        return True, "Отправка разрешена"
    
    # ===== 2. Группировка уведомлений по временным окнам =====
    
    def group_events_by_window(
        self, events: List[Event], window_minutes: Optional[int] = None
    ) -> List[List[Event]]:
        """
        Группирует события по временным окнам.
        Если несколько событий начинаются в пределах интервала,
        они объединяются в одну группу.
        """
        if not events:
            return []
        
        if window_minutes is None:
            window_minutes = self.settings.grouping_window_minutes or 120
        
        # Сортируем события по времени начала
        sorted_events = sorted(events, key=lambda e: e.start_time)
        
        groups = []
        current_group = [sorted_events[0]]
        
        for event in sorted_events[1:]:
            last_event_in_group = current_group[-1]
            time_diff = (event.start_time - last_event_in_group.start_time).total_seconds() / 60
            
            if time_diff <= window_minutes:
                # Событие в пределах окна — добавляем в текущую группу
                current_group.append(event)
            else:
                # Событие вне окна — сохраняем текущую группу и начинаем новую
                groups.append(current_group)
                current_group = [event]
        
        # Добавляем последнюю группу
        groups.append(current_group)
        
        log.info(f"Сгруппировано {len(events)} событий в {len(groups)} групп")
        return groups
    
    def format_grouped_message(self, event_group: List[Event]) -> str:
        """Форматирует сообщение для группы событий."""
        if len(event_group) == 1:
            event = event_group[0]
            return f"🔔 Напоминание: {event.title}\n⏰ {event.start_time.strftime('%H:%M %d.%m.%Y')}\n📍 {event.location or 'Не указано'}"
        
        # Несколько событий в группе
        message = "📅 Сводка ближайших событий:\n\n"
        for event in event_group:
            message += f"• {event.start_time.strftime('%H:%M')} - {event.title}\n"
        
        return message
    
    # ===== 3. Обнаружение конфликтов =====
    
    def detect_conflicts(self, events: List[Event]) -> List[Tuple[Event, Event]]:
        """
        Обнаруживает пересечения временных интервалов событий.
        Возвращает список пар конфликтующих событий.
        """
        conflicts = []
        
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                event1 = events[i]
                event2 = events[j]
                
                if self._events_overlap(event1, event2):
                    conflicts.append((event1, event2))
                    log.warning(f"Обнаружен конфликт: '{event1.title}' и '{event2.title}'")
        
        return conflicts
    
    def _events_overlap(self, event1: Event, event2: Event) -> bool:
        """Проверяет, пересекаются ли временные интервалы двух событий."""
        # События не пересекаются, если одно заканчивается до начала другого
        return not (event1.end_time <= event2.start_time or event2.end_time <= event1.start_time)
    
    def format_conflict_warning(self, event1: Event, event2: Event) -> str:
        """Форматирует предупреждение о конфликте."""
        return (
            f"⚠️ КОНФЛИКТ РАСПИСАНИЯ!\n\n"
            f"Следующие события пересекаются:\n\n"
            f"1️⃣ {event1.title}\n"
            f"   ⏰ {event1.start_time.strftime('%H:%M')} - {event1.end_time.strftime('%H:%M')}\n\n"
            f"2️⃣ {event2.title}\n"
            f"   ⏰ {event2.start_time.strftime('%H:%M')} - {event2.end_time.strftime('%H:%M')}\n\n"
            f"Пожалуйста, проверьте расписание."
        )
    
    # ===== 4. Обработка команд откладывания (Snooze) =====
    
    def parse_snooze_command(self, command: str) -> Optional[timedelta]:
        """
        Парсит команду откладывания и возвращает timedelta.
        
        Поддерживаемые форматы:
        - +10 (минуты)
        - +1ч, +2ч (часы)
        - +30м (минуты)
        - завтра (завтра в это же время)
        - отмена (отменяет уведомление)
        """
        command = command.strip().lower()
        
        # Отмена
        if command in ["отмена", "cancel"]:
            return None
        
        # Завтра
        if command in ["завтра", "tomorrow"]:
            return timedelta(days=1)
        
        # +10 (минуты по умолчанию)
        if command.startswith("+") and command[1:].isdigit():
            minutes = int(command[1:])
            return timedelta(minutes=minutes)
        
        # +1ч, +2ч (часы)
        if command.startswith("+") and command.endswith("ч"):
            try:
                hours = int(command[1:-1])
                return timedelta(hours=hours)
            except ValueError:
                pass
        
        # +30м (минуты)
        if command.startswith("+") and command.endswith("м"):
            try:
                minutes = int(command[1:-1])
                return timedelta(minutes=minutes)
            except ValueError:
                pass
        
        log.warning(f"Не удалось распознать команду: {command}")
        return None
    
    def apply_snooze(
        self, notification: NotificationHistory, command: str
    ) -> Optional[datetime]:
        """
        Применяет команду откладывания к уведомлению.
        Возвращает новое время отправки или None для отмены.
        """
        snooze_delta = self.parse_snooze_command(command)
        
        if snooze_delta is None:
            # Отмена
            notification.status = "cancelled"
            notification.rescheduled_at = None
            self.db.commit()
            log.info(f"Уведомление {notification.id} отменено")
            return None
        
        # Вычисляем новое время отправки
        new_time = notification.sent_at + snooze_delta
        notification.status = "snoozed"
        notification.rescheduled_at = new_time
        self.db.commit()
        
        log.info(f"Уведомление {notification.id} отложено до {new_time}")
        return new_time
    
    # ===== 5. Генерация уведомлений =====
    
    def generate_notifications(
        self, events: List[Event], current_time: datetime
    ) -> List[Dict]:
        """
        Генерирует список уведомлений для отправки.
        
        Возвращает список словарей с полями:
        - type: 'regular', 'grouped', 'conflict'
        - events: список событий
        - message: текст сообщения
        - send_time: время отправки
        """
        notifications = []
        
        # 1. Обнаруживаем конфликты
        conflicts = self.detect_conflicts(events)
        for event1, event2 in conflicts:
            # Предупреждение о конфликте за 1 час до первого события
            conflict_time = min(event1.start_time, event2.start_time) - timedelta(hours=1)
            notifications.append({
                "type": "conflict",
                "events": [event1, event2],
                "message": self.format_conflict_warning(event1, event2),
                "send_time": conflict_time,
            })
        
        # 2. Фильтруем конфликтующие события из обычных уведомлений
        conflict_event_ids = set()
        for e1, e2 in conflicts:
            conflict_event_ids.add(e1.id)
            conflict_event_ids.add(e2.id)
        
        regular_events = [e for e in events if e.id not in conflict_event_ids]
        
        # 3. Группируем оставшиеся события
        event_groups = self.group_events_by_window(regular_events)
        
        for group in event_groups:
            # Проверяем режим тишины для времени отправки
            first_event = group[0]
            reminder_times = self.settings.reminder_intervals or [60, 15, 5]
            
            for minutes_before in reminder_times:
                send_time = first_event.start_time - timedelta(minutes=minutes_before)
                should_send, reason = self.should_send_notification(first_event, send_time)
                
                if should_send:
                    notifications.append({
                        "type": "grouped" if len(group) > 1 else "regular",
                        "events": group,
                        "message": self.format_grouped_message(group),
                        "send_time": send_time,
                    })
        
        log.info(f"Сгенерировано {len(notifications)} уведомлений")
        return notifications


# Функция для создания движка
def create_notification_engine(db: Session, user: User) -> NotificationEngine:
    """Создаёт экземпляр NotificationEngine."""
    return NotificationEngine(db, user)