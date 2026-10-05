import io
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.models import Extraction, LabValue, WellnessAnswer

HEADER = {"X-Nalam-Request": "1"}


class FakeAI:
    client = None
    calls = 0
    last_report = None

    async def extract(self, image):
        self.calls += 1
        return Extraction(report_date="2026-09-01", readable=True, uncertainties=[], values=[
            LabValue(name="LDL cholesterol", value="152", unit="mg/dL", reference_range="<100",
                     report_flag="High", source_text="LDL cholesterol 152 mg/dL <100 High")])

    async def answer(self, message, profile, report, history=None):
        self.calls += 1
        self.last_report = report
        return WellnessAnswer(simple_tamil="அறிக்கையை மருத்துவருடன் பார்த்துப் பேசலாம்.", english_summary="Review the report with her clinician.",
                              next_step_tamil="மருத்துவரிடம் பேசலாம்.", clinician_questions=["What follow-up is appropriate?"],
                              needs_clinician=True, urgency="clinician")

    async def speech(self, text):
        self.calls += 1
        return b"ID3" + b"sample-audio"

    async def transcribe(self, raw, filename, mime):
        self.calls += 1
        return "இன்று என்ன சாப்பிடலாம்?"


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, access_code="test-family-code", caregiver_pin="test-pin-123",
                    session_secret="test-session-secret", scheduler=False, chat_limit=2,
                    public_origin="http://testserver")


@pytest.fixture
def client(settings):
    app = create_app(settings, FakeAI())
    with TestClient(app, headers=HEADER) as client:
        yield client


@pytest.fixture
def family(client):
    assert client.post("/api/auth/login", json={"code":"test-family-code"}).status_code == 200
    return client


@pytest.fixture
def caregiver(family):
    assert family.post("/api/auth/caregiver", json={"code":"test-pin-123"}).status_code == 200
    return family


@pytest.fixture
def ready(caregiver):
    assert caregiver.post("/api/consent", json={"accepted":True}).status_code == 200
    return caregiver


@pytest.fixture
def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (500, 500), "white").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def wav_bytes():
    output=io.BytesIO()
    with wave.open(output,"wb") as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return output.getvalue()
