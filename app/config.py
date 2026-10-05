from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def private_file(path: Path, content: bytes) -> bytes:
    """Create private durable secrets once; never replace an existing key."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
    except FileExistsError:
        pass
    return path.read_bytes()


@dataclass
class Settings:
    data_dir: Path
    access_code: str
    caregiver_pin: str
    session_secret: str
    api_key: str = ""
    text_model: str = "gpt-4.1-mini"
    tts_model: str = "gpt-4o-mini-tts"
    stt_model: str = "gpt-4o-mini-transcribe"
    voice: str = "coral"
    timezone: str = "UTC"
    secure_cookies: bool = False
    public_origin: str = "http://127.0.0.1:8787"
    push_contact: str = "https://example.com/nalam"
    chat_limit: int = 30
    report_limit: int = 8
    speech_limit: int = 80
    transcribe_limit: int = 30
    scheduler: bool = True
    review_mode: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("NALAM_DATA_DIR", str(ROOT / "data"))).expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        key_path = os.getenv("OPENAI_API_KEY_FILE", "").strip()
        if not api_key and key_path:
            api_key = Path(key_path).expanduser().read_text().strip()
        access = os.getenv("NALAM_ACCESS_CODE", "").strip()
        pin = os.getenv("NALAM_CAREGIVER_PIN", "").strip()
        if not access or not pin:
            raise RuntimeError("Set NALAM_ACCESS_CODE and NALAM_CAREGIVER_PIN in your private .env first. See README.")
        if len(access) < 10 or len(pin) < 6:
            raise RuntimeError("Use a family access code of at least 10 characters and a caregiver PIN of at least 6 characters.")
        return cls(
            data_dir=data_dir, access_code=access, caregiver_pin=pin,
            session_secret=private_file(data_dir / "session.key", secrets.token_bytes(48)).hex(),
            api_key=api_key, text_model=os.getenv("NALAM_TEXT_MODEL", "gpt-4.1-mini"),
            tts_model=os.getenv("NALAM_TTS_MODEL", "gpt-4o-mini-tts"),
            stt_model=os.getenv("NALAM_STT_MODEL", "gpt-4o-mini-transcribe"),
            voice=os.getenv("NALAM_VOICE", "coral"), timezone=os.getenv("NALAM_TIMEZONE", "UTC"),
            secure_cookies=os.getenv("NALAM_SECURE_COOKIES", "false").lower() == "true",
            public_origin=os.getenv("NALAM_PUBLIC_ORIGIN", "http://127.0.0.1:8787").rstrip("/"),
            push_contact=os.getenv("NALAM_PUSH_CONTACT", "https://example.com/nalam"),
            chat_limit=int(os.getenv("NALAM_DAILY_CHAT_LIMIT", "30")),
            report_limit=int(os.getenv("NALAM_DAILY_REPORT_LIMIT", "8")),
            speech_limit=int(os.getenv("NALAM_DAILY_SPEECH_LIMIT", "80")),
            transcribe_limit=int(os.getenv("NALAM_DAILY_TRANSCRIBE_LIMIT", "30")),
            review_mode=os.getenv("NALAM_REVIEW_MODE", "false").lower() == "true",
        )
