from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import secrets
import time
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import OpenAIError
from starlette.middleware.sessions import SessionMiddleware

from .ai import AIService, AIUnavailable, UnsafeImage, prepare_image
from .config import ROOT, Settings
from .models import (ChatRequest, Checkin, Confirmation, ConsentRequest, LoginRequest,
                     Profile, PushSubscription, SpeechRequest)
from .push import PushService, valid_push_endpoint
from .store import DailyLimit, Store
from .wellness import PROMPTS, SOURCES, local_now, sample_answer, symptom_emergency, today_plan


def clean(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in {"id", "created"}}


def report_public(record: dict) -> dict:
    return {k: v for k, v in record.items() if k != "image"}


def audio_format(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"RIFF") and raw[8:12] == b"WAVE":
        return "wav", "audio/wav"
    if raw.startswith(b"OggS"):
        return "ogg", "audio/ogg"
    if raw.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm", "audio/webm"
    if len(raw) > 12 and raw[4:8] == b"ftyp":
        return "mp4", "audio/mp4"
    if raw.startswith(b"ID3") or len(raw) >= 2 and raw[0] == 255 and raw[1] & 224 == 224:
        return "mp3", "audio/mpeg"
    raise HTTPException(415, "Use an MP3, WAV, M4A, Ogg or WebM recording.")


def create_app(settings: Settings | None = None, ai_service: AIService | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir)
    ai = ai_service or AIService(settings)
    push = PushService(settings, store)
    if not store.get("profile", "profile"):
        store.put("profile", Profile(timezone=settings.timezone).model_dump(), "profile")
    attempts: dict[str, list[float]] = defaultdict(list)
    budget_limits = {"chat": settings.chat_limit, "report": settings.report_limit,
                     "speech": settings.speech_limit, "transcribe": settings.transcribe_limit}

    def profile() -> Profile:
        return Profile.model_validate(clean(store.get("profile", "profile") or {}))

    def consume(kind: str) -> None:
        store.consume(local_now(profile()).date().isoformat(), kind, budget_limits[kind])

    def latest_confirmed() -> dict | None:
        reports = [r for r in store.list("report") if r.get("confirmed") and not r.get("synthetic")]
        return max(reports, key=lambda r: (r.get("report_date", ""), r["created"])) if reports else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(push.loop()) if settings.scheduler else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if getattr(ai, "client", None):
            await ai.client.close()
        store.close()

    app = FastAPI(title="Nalam · Tamil wellness", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.ai, app.state.push = store, ai, push
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="nalam_session",
                       max_age=30*86400, same_site="strict", https_only=settings.secure_cookies)

    @app.middleware("http")
    async def security(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("x-nalam-request") != "1":
                return JSONResponse({"detail": "Open this action from the Nalam app."}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in {settings.public_origin, f"{request.url.scheme}://{request.url.netloc}"}:
                return JSONResponse({"detail": "This origin is not allowed."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; worker-src 'self'; manifest-src 'self'"
        if request.url.path.startswith("/api/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    def family(request: Request) -> dict:
        if not request.session.get("authenticated"):
            raise HTTPException(401, "குடும்பத்தினருடன் உள்நுழையுங்கள்.")
        return request.session

    def caregiver(request: Request, session: dict = Depends(family)) -> dict:
        if session.get("caregiver_until", 0) < time.time():
            raise HTTPException(403, "Unlock the caregiver view first.")
        return session

    def consent(_session: dict = Depends(family)) -> None:
        if not (store.get("consent", "consent") or {}).get("accepted"):
            raise HTTPException(403, "Agree to sharing report photos and voice questions with the AI service first.")

    def throttle(request: Request, kind: str) -> str:
        key = f"{request.client.host if request.client else 'local'}:{kind}"
        current = time.time()
        attempts[key] = [t for t in attempts[key] if current - t < 600]
        if len(attempts[key]) >= 5:
            raise HTTPException(429, "Too many attempts. Try again in ten minutes.")
        attempts[key].append(current)
        return key

    @app.exception_handler(AIUnavailable)
    async def ai_missing(request, exc):
        return JSONResponse({"detail": "இப்போது பதில் கிடைக்கவில்லை. கொஞ்ச நேரம் கழித்து முயற்சி செய்யலாம்.",
                             "caregiver_detail": str(exc)}, status_code=503)

    @app.exception_handler(OpenAIError)
    async def ai_failed(request, exc):
        # Don't expose provider responses, uploaded contents, or credentials.
        if getattr(exc, "code", None) in {"insufficient_quota", "credit_balance_exhausted"}:
            return JSONResponse({"detail": "குரல் உதவிக்கான இணைப்பை குடும்பத்தினர் சரிபார்க்க வேண்டும்.",
                                 "caregiver_detail": "The configured OpenAI project has no API credits remaining.",
                                 "code": "api_credit_required"}, status_code=503)
        return JSONResponse({"detail": "இப்போது குரல் உதவி கிடைக்கவில்லை. கொஞ்ச நேரம் கழித்து முயற்சி செய்யலாம்.",
                             "caregiver_detail": "The AI service request failed. Check API billing, model access or connectivity."}, status_code=502)

    @app.exception_handler(DailyLimit)
    async def daily_limit(request, exc):
        return JSONResponse({"detail": "இன்றைக்கான குரல் உதவி வரம்பை அடைந்தாச்சு. நாளை தொடரலாம்.",
                             "caregiver_detail": "The configured daily AI request limit has been reached."}, status_code=429)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/auth")
    async def auth(request: Request):
        return {"authenticated": bool(request.session.get("authenticated")),
                "caregiver": request.session.get("caregiver_until", 0) > time.time()}

    @app.post("/api/auth/login")
    async def login(body: LoginRequest, request: Request):
        attempt_key = throttle(request, "login")
        if not secrets.compare_digest(body.code.encode(), settings.access_code.encode()):
            raise HTTPException(401, "The family access code doesn't match.")
        attempts.pop(attempt_key, None)
        request.session.clear()
        request.session["authenticated"] = True
        return {"ok": True}

    @app.post("/api/auth/caregiver")
    async def unlock(body: LoginRequest, request: Request, _session=Depends(family)):
        attempt_key = throttle(request, "caregiver")
        if not secrets.compare_digest(body.code.encode(), settings.caregiver_pin.encode()):
            raise HTTPException(401, "The caregiver PIN doesn't match.")
        attempts.pop(attempt_key, None)
        request.session["caregiver_until"] = time.time() + 3600
        return {"ok": True}

    @app.post("/api/auth/lock")
    async def lock(request: Request, _session=Depends(family)):
        request.session.pop("caregiver_until", None)
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        request.session.clear()
        return {"ok": True}

    @app.get("/api/state", dependencies=[Depends(family)])
    async def state():
        p = profile()
        reports = store.list("report")
        return {"profile": p.model_dump(), "consent": bool((store.get("consent", "consent") or {}).get("accepted")),
                "ai_connected": bool(settings.api_key), "review_mode": settings.review_mode,
                "prompts": PROMPTS, "today": today_plan(p, store.list("checkin", 300)),
                "reports": [report_public(r) for r in reports], "languages": language_state(),
                "sources": SOURCES}

    @app.post("/api/consent", dependencies=[Depends(caregiver)])
    async def save_consent(body: ConsentRequest):
        store.put("consent", {"accepted": body.accepted, "at": time.time()}, "consent")
        return {"accepted": body.accepted}

    @app.get("/api/profile", dependencies=[Depends(caregiver)])
    async def get_profile():
        return profile().model_dump()

    @app.put("/api/profile", dependencies=[Depends(caregiver)])
    async def save_profile(body: Profile):
        if body.language == "bfq" and not language_state()["bfq"]["ready"]:
            raise HTTPException(409, "Upload and review all core Badaga recordings before enabling that language.")
        store.put("profile", body.model_dump(), "profile")
        return {"ok": True}

    @app.post("/api/checkins", dependencies=[Depends(family)])
    async def checkin(body: Checkin):
        p = profile()
        if body.kind in {"walk", "stretch"} and body.answer == "done" and (not p.light_activity_ok or body.kind == "walk" and p.mobility != "comfortable"):
            raise HTTPException(409, "Please review safe light activity in the caregiver view first.")
        day = local_now(p).date().isoformat()
        store.put("checkin", {**body.model_dump(), "local_date": day}, f"checkin:{day}:{body.kind}")
        return {"ok": True, "reply_tamil": PROMPTS["later"] if body.answer == "later" else PROMPTS["done"],
                "today": today_plan(p, store.list("checkin", 300))}

    @app.get("/api/checkins", dependencies=[Depends(caregiver)])
    async def history():
        rows = store.list("checkin", 120)
        return {"checkins": rows, "low_mood_days": len({r["local_date"] for r in rows[:28] if r["kind"] == "mood" and r["answer"] == "low"})}

    @app.post("/api/reports", dependencies=[Depends(consent)])
    async def upload_report(file: UploadFile = File(...)):
        raw = await file.read(12*1024*1024 + 1)
        try:
            image = await asyncio.to_thread(prepare_image, raw)
        except UnsafeImage as exc:
            raise HTTPException(415, str(exc)) from exc
        consume("report")
        extracted = await ai.extract(image)
        if not extracted.readable or not extracted.values:
            return JSONResponse({"detail": "அறிக்கையில் எண்கள் தெளிவாகத் தெரியவில்லை. அருகில் வைத்து மீண்டும் படம் எடுங்க.",
                                 "uncertainties": extracted.uncertainties}, status_code=422)
        record = {**extracted.model_dump(), "confirmed": False, "explanation": None,
                  "image": base64.b64encode(image).decode(), "synthetic": False}
        rid = store.put("report", record)
        return report_public(store.get(rid, "report"))

    @app.post("/api/demo", dependencies=[Depends(caregiver)])
    async def demo_report():
        if not settings.review_mode:
            raise HTTPException(409, "Enable NALAM_REVIEW_MODE for a fictional walkthrough.")
        image = prepare_image((ROOT / "static/sample-report.png").read_bytes())
        rows = [{"name": name, "value": value, "unit": "mg/dL", "reference_range": ref,
                 "report_flag": "", "source_text": f"{name} {value} mg/dL {ref}"}
                for name, value, ref in [("Total cholesterol", "230", "<200"), ("LDL cholesterol", "152", "<100"),
                                         ("HDL cholesterol", "48", ">40"), ("Triglycerides", "165", "<150")]]
        record = {"report_date": "2026-09-01", "readable": True, "values": rows,
                  "uncertainties": ["Fictional sample. Readings are prewritten, not AI extraction."],
                  "confirmed": False, "explanation": None, "image": base64.b64encode(image).decode(), "synthetic": True}
        rid = store.put("report", record)
        return report_public(store.get(rid, "report"))

    @app.get("/api/reports/{rid}/image", dependencies=[Depends(caregiver)])
    async def report_image(rid: str):
        report = store.get(rid, "report")
        if not report or not report.get("image"):
            raise HTTPException(404, "This photo was removed after confirmation or deletion.")
        return Response(base64.b64decode(report["image"]), media_type="image/jpeg")

    @app.put("/api/reports/{rid}/confirm", dependencies=[Depends(caregiver)])
    async def confirm_report(rid: str, body: Confirmation):
        report = store.get(rid, "report")
        if not report:
            raise HTTPException(404, "Report not found.")
        report.update(body.model_dump())
        report.update(confirmed=True, confirmed_at=time.time(), image=None, explanation=None)
        store.put("report", clean(report), rid)
        return report_public(store.get(rid, "report"))

    @app.post("/api/reports/{rid}/explain", dependencies=[Depends(family)])
    async def explain_report(rid: str):
        report = store.get(rid, "report")
        if not report:
            raise HTTPException(404, "Report not found.")
        if not report.get("confirmed"):
            raise HTTPException(409, "Your caregiver must confirm the numbers and units before an explanation.")
        if report.get("synthetic"):
            return {"answer": sample_answer(report=True).model_dump(), "sources": SOURCES, "sample": True}
        consent({})
        if not report.get("explanation"):
            consume("chat")
            answer = await ai.answer("Explain the confirmed report in simple spoken Tamil. Say what is known, what cannot be concluded, and one practical next step. Suggest clinician follow-up questions; don't make a treatment plan from lab values alone.", profile(), report)
            report["explanation"] = answer.model_dump()
            store.put("report", clean(report), rid)
        return {"answer": report["explanation"], "sources": SOURCES}

    @app.delete("/api/reports/{rid}", dependencies=[Depends(caregiver)])
    async def delete_report(rid: str):
        if not store.get(rid, "report"):
            raise HTTPException(404, "Report not found.")
        store.delete(rid)
        return {"ok": True}

    @app.post("/api/chat", dependencies=[Depends(family)])
    async def chat(body: ChatRequest):
        urgent = symptom_emergency(body.message)
        if urgent:
            return {"answer": urgent.model_dump(), "sources": []}
        if settings.review_mode and not (store.get("consent", "consent") or {}).get("accepted"):
            return {"answer": sample_answer(body.message).model_dump(), "sources": SOURCES, "sample": True}
        consent({})
        consume("chat")
        history = [{"question": r["question"], "reply": r["answer"]["simple_tamil"]} for r in reversed(store.list("chat", 4))]
        answer = await ai.answer(body.message, profile(), latest_confirmed(), history)
        store.put("chat", {"question": body.message, "answer": answer.model_dump()})
        return {"answer": answer.model_dump(), "sources": SOURCES}

    async def spoken(text: str) -> Response:
        digest = hashlib.sha256((settings.tts_model + settings.voice + text).encode()).hexdigest()
        cached = store.get("audio:" + digest, "audio")
        if cached:
            return Response(base64.b64decode(cached["bytes"]), media_type="audio/mpeg")
        consume("speech")
        raw = await ai.speech(text)
        store.put("audio", {"bytes": base64.b64encode(raw).decode()}, "audio:" + digest)
        return Response(raw, media_type="audio/mpeg")

    @app.post("/api/speech", dependencies=[Depends(consent)])
    async def speech(body: SpeechRequest):
        if body.language != "ta":
            raise HTTPException(409, "Free-form Badaga speech is not verified. Use reviewed recordings; report explanations remain in Tamil.")
        return await spoken(body.text)

    @app.get("/api/prompts/{key}/audio", dependencies=[Depends(family)])
    async def prompt_audio(key: str, language: str = "ta"):
        if key not in PROMPTS:
            raise HTTPException(404, "Prompt not found.")
        if language == "bfq":
            clip = store.get("bfq:" + key, "language_clip")
            if not clip:
                raise HTTPException(409, "This Badaga recording has not been reviewed yet.")
            return Response(base64.b64decode(clip["bytes"]), media_type=clip["mime"])
        if language != "ta":
            raise HTTPException(422, "Choose Tamil or reviewed Badaga.")
        consent({})
        return await spoken(PROMPTS[key])

    @app.post("/api/transcribe", dependencies=[Depends(consent)])
    async def transcribe(file: UploadFile = File(...)):
        raw = await file.read(8*1024*1024+1)
        if not raw or len(raw) > 8*1024*1024:
            raise HTTPException(413, "Keep voice messages under 45 seconds and 8 MB.")
        extension, mime = audio_format(raw)
        consume("transcribe")
        text = await ai.transcribe(raw, "question." + extension, mime)
        return {"text": text[:1200], "review_before_send": True}

    def language_state() -> dict:
        present = [key for key in PROMPTS if store.get("bfq:" + key, "language_clip")]
        return {"ta": {"ready": True, "mode": "AI speech; test with a native speaker"},
                "bfq": {"ready": len(present) == len(PROMPTS), "recorded_keys": present,
                        "required_keys": list(PROMPTS), "mode": "Reviewed native-speaker recordings; no free-form medical translation"}}

    @app.get("/api/languages", dependencies=[Depends(caregiver)])
    async def languages():
        return {"languages": language_state(), "prompts": PROMPTS}

    @app.put("/api/languages/bfq/{key}", dependencies=[Depends(caregiver)])
    async def badaga_clip(key: str, reviewed: bool = False, file: UploadFile = File(...)):
        if key not in PROMPTS or not reviewed:
            raise HTTPException(422, "Choose a core phrase and confirm review by a fluent Badaga speaker.")
        raw = await file.read(4*1024*1024+1)
        if not raw or len(raw) > 4*1024*1024:
            raise HTTPException(413, "Keep each recording under 4 MB.")
        _, mime = audio_format(raw)
        store.put("language_clip", {"bytes": base64.b64encode(raw).decode(), "mime": mime, "reviewed": True}, "bfq:" + key)
        return {"ok": True, "languages": language_state()}

    @app.get("/api/push/config", dependencies=[Depends(family)])
    async def push_config():
        return {"public_key": push.public_key, "requires_https_and_home_screen": True}

    @app.post("/api/push/subscribe", dependencies=[Depends(family)])
    async def subscribe(body: PushSubscription):
        try:
            valid = valid_push_endpoint(body.endpoint)
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(422, "Choose a supported secure browser push endpoint.")
        rid = "push:" + hashlib.sha256(body.endpoint.encode()).hexdigest()
        store.put("subscription", {"subscription": body.model_dump(exclude_none=True)}, rid)
        return {"ok": True}

    @app.post("/api/push/unsubscribe", dependencies=[Depends(family)])
    async def unsubscribe(body: PushSubscription):
        store.delete("push:" + hashlib.sha256(body.endpoint.encode()).hexdigest())
        return {"ok": True}

    @app.post("/api/push/test", dependencies=[Depends(caregiver)])
    async def test_push():
        subscriptions = store.list("subscription")
        if not subscriptions:
            raise HTTPException(409, "Enable reminders on the iPhone first.")
        results = await asyncio.gather(*(asyncio.to_thread(push.send, sub) for sub in subscriptions))
        return {"delivered": sum(results), "attempted": len(results)}

    @app.get("/api/export", dependencies=[Depends(caregiver)])
    async def export_data():
        payload = {"profile": profile().model_dump(), "reports": [report_public(r) for r in store.list("report")],
                   "checkins": store.list("checkin", 1000), "conversations": store.list("chat", 1000)}
        return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="nalam-private-export.json"'})

    @app.delete("/api/data", dependencies=[Depends(caregiver)])
    async def delete_all(request: Request):
        store.purge()
        store.put("profile", Profile(timezone=settings.timezone).model_dump(), "profile")
        request.session.pop("caregiver_until", None)
        return {"ok": True}

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "static" / "index.html")

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(ROOT / "static" / "sw.js", media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app
