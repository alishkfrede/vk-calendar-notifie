from pydantic import BaseModel, Field
from datetime import datetime

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0"


class UserCreate(BaseModel):
    vk_user_id: int
    timezone: str = "UTC"


class UserOut(BaseModel):
    id: int
    vk_user_id: int
    timezone: str
    is_active: bool

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    reminder_intervals: list[int] | None = Field(default=None, min_length=1)
    silence_start: str | None = None
    silence_end: str | None = None
    priority_keywords: list[str] | None = None
    grouping_window_minutes: int | None = Field(default=None, gt=0)
    weekly_summary_day: str | None = None
    weekly_summary_time: str | None = None

class EventOut(BaseModel):
    id: int
    external_id: str
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
    location: str | None
    status: str
    is_conflict: bool

    model_config = {"from_attributes": True}