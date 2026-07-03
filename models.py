from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    vk_user_id = Column(Integer, unique=True, index=True, nullable=False)
    timezone = Column(String, default="UTC", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    calendar_connections = relationship(
        "CalendarConnection", back_populates="user", cascade="all, delete-orphan"
    )
    settings = relationship(
        "UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship(
        "NotificationHistory", back_populates="user", cascade="all, delete-orphan"
    )


class CalendarConnection(Base):
    __tablename__ = "calendar_connections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    encrypted_token = Column(Text, nullable=False)  # зашифрованный refresh/access token
    last_synced = Column(DateTime, nullable=True)
    status = Column(String, default="active", nullable=False)

    user = relationship("User", back_populates="calendar_connections")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    reminder_intervals = Column(JSON, default=[60, 15, 5])  # минуты
    silence_start = Column(String, nullable=True)           # "23:00"
    silence_end = Column(String, nullable=True)             # "08:00"
    priority_keywords = Column(
        JSON, default=["врач", "срочно", "семья", "дедлайн"]
    )
    grouping_window_minutes = Column(Integer, default=120)  # 2 часа

    weekly_summary_day = Column(String, default="monday")
    weekly_summary_time = Column(String, default="09:00")

    user = relationship("User", back_populates="settings")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    location = Column(String, nullable=True)
    status = Column(String, default="confirmed", nullable=False)  # confirmed/cancelled
    is_conflict = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="events")
    notifications = relationship(
        "NotificationHistory", back_populates="event", cascade="all, delete-orphan"
    )


class NotificationHistory(Base):
    __tablename__ = "notification_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True)

    message_text = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String, default="sent", nullable=False)  # sent/failed/snoozed
    vk_message_id = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    rescheduled_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="notifications")
    event = relationship("Event", back_populates="notifications")


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    context = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)