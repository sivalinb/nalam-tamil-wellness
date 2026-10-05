from __future__ import annotations

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabValue(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    value: str = Field(max_length=40)
    unit: str = Field(max_length=30)
    reference_range: str = Field(max_length=100)
    report_flag: str = Field(max_length=40)
    source_text: str = Field(max_length=200)


class Extraction(StrictModel):
    report_date: str = Field(max_length=30)
    readable: bool
    values: list[LabValue] = Field(max_length=24)
    uncertainties: list[str] = Field(max_length=10)


class Confirmation(StrictModel):
    report_date: str = Field(max_length=30)
    values: list[LabValue] = Field(min_length=1, max_length=24)

    @field_validator("report_date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if value:
            date.fromisoformat(value)
        return value

    @field_validator("values")
    @classmethod
    def complete_values(cls, values: list[LabValue]) -> list[LabValue]:
        if any(not v.value.strip() or not v.unit.strip() for v in values):
            raise ValueError("Each confirmed result needs a value and unit. Remove unreadable rows.")
        return values


class WellnessAnswer(StrictModel):
    simple_tamil: str = Field(min_length=1, max_length=2400)
    english_summary: str = Field(max_length=1400)
    next_step_tamil: str = Field(max_length=300)
    clinician_questions: list[str] = Field(max_length=4)
    needs_clinician: bool
    urgency: Literal["routine", "clinician", "urgent"]


class Reminder(StrictModel):
    id: Literal["walk", "stretch", "mood", "sleep"]
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    enabled: bool = True


class Profile(StrictModel):
    name: str = Field(default="அம்மா", min_length=1, max_length=50)
    age: int = Field(default=66, ge=18, le=110)
    language: Literal["ta", "bfq"] = "ta"
    timezone: str = "UTC"
    diet: Literal["vegetarian", "mixed"] = "vegetarian"
    mobility: Literal["comfortable", "limited", "needs_help"] = "comfortable"
    light_activity_ok: bool = False
    walk_minutes: int = Field(default=5, ge=1, le=30)
    allergies: str = Field(default="", max_length=300)
    conditions: str = Field(default="", max_length=500)
    clinician_instructions: str = Field(default="", max_length=1500)
    quiet_start: str = Field(default="21:30", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str = Field(default="07:30", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reminders: list[Reminder] = Field(default_factory=lambda: [
        Reminder(id="walk", time="09:00"), Reminder(id="stretch", time="15:00"),
        Reminder(id="mood", time="18:00"), Reminder(id="sleep", time="21:00"),
    ], max_length=4)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Choose a valid IANA timezone.") from exc
        return value

    @model_validator(mode="after")
    def distinct_reminders(self) -> "Profile":
        if len({r.id for r in self.reminders}) != len(self.reminders):
            raise ValueError("Reminder types must be unique.")
        return self


class Checkin(StrictModel):
    kind: Literal["walk", "stretch", "mood", "sleep"]
    answer: str = Field(max_length=60)

    @model_validator(mode="after")
    def supported_answer(self) -> "Checkin":
        allowed = {"walk": {"done", "later"}, "stretch": {"done", "later"},
                   "mood": {"good", "okay", "low"}, "sleep": {"good", "okay", "poor"}}
        if self.answer not in allowed[self.kind]:
            raise ValueError("Choose an available check-in answer.")
        return self


class SpeechRequest(StrictModel):
    text: str = Field(min_length=1, max_length=2400)
    language: Literal["ta", "bfq"] = "ta"


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=1200)


class LoginRequest(StrictModel):
    code: str = Field(min_length=1, max_length=200)


class ConsentRequest(StrictModel):
    accepted: bool


class PushSubscription(StrictModel):
    endpoint: str = Field(max_length=1500)
    keys: dict[str, str]
    expirationTime: int | None = None

    @field_validator("keys")
    @classmethod
    def valid_keys(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != {"p256dh", "auth"} or any(not re_key(v) for v in value.values()):
            raise ValueError("Invalid push keys.")
        return value


def re_key(value: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{16,200}={0,2}", value))
