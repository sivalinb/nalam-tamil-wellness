import json
from datetime import datetime, timezone

import pytest

from app.ai import UnsafeImage, prepare_image
from app.models import Profile, Reminder
from app.push import valid_push_endpoint
from app.wellness import clinician_flags, due_reminders, symptom_emergency


def upload(client, image):
    response = client.post("/api/reports", files={"file":("report.png", image, "image/png")})
    assert response.status_code == 200, response.text
    return response.json()


def test_login_and_caregiver_permissions(client, family):
    assert client.get("/api/state").status_code == 200
    assert client.get("/api/profile").status_code == 403
    assert client.post("/api/consent",json={"accepted":True}).status_code == 403
    assert client.post("/api/auth/login",json={"code":"தமிழ்"}).status_code == 401
    assert client.get("/api/health").json()["status"] == "ok"


def test_no_public_health_data(client):
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/export").status_code == 401
    assert client.get("/api/prompts/hello/audio").status_code == 401


def test_csrf_and_cookie_flags(client):
    assert client.post("/api/auth/login",json={"code":"test-family-code"},headers={"Origin":"https://evil.example"}).status_code == 403
    response=client.post("/api/auth/login",json={"code":"test-family-code"})
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert response.headers["cache-control"] == "no-store"
    client.headers.pop("X-Nalam-Request")
    assert client.post("/api/auth/logout").status_code == 403


def test_report_requires_consent(caregiver,image_bytes):
    calls=caregiver.app.state.ai.calls
    assert caregiver.post("/api/reports",files={"file":("report.png",image_bytes,"image/png")}).status_code == 403
    assert caregiver.get("/api/prompts/hello/audio").status_code == 403
    assert caregiver.app.state.ai.calls == calls


def test_photo_confirmation_explanation_and_photo_removal(ready,image_bytes):
    report=upload(ready,image_bytes)
    rid=report["id"]
    assert "image" not in report
    assert ready.post(f"/api/reports/{rid}/explain").status_code == 409
    assert ready.get(f"/api/reports/{rid}/image").status_code == 200
    body={"report_date":report["report_date"],"values":report["values"]}
    assert ready.put(f"/api/reports/{rid}/confirm",json=body).status_code == 200
    assert ready.get(f"/api/reports/{rid}/image").status_code == 404
    answer=ready.post(f"/api/reports/{rid}/explain")
    assert answer.status_code == 200
    assert answer.json()["answer"]["simple_tamil"]
    calls=ready.app.state.ai.calls
    assert ready.post(f"/api/reports/{rid}/explain").status_code == 200
    assert ready.app.state.ai.calls == calls


def test_confirmation_needs_complete_values_and_real_date(ready,image_bytes):
    report=upload(ready,image_bytes)
    values=report["values"];values[0]["unit"]=""
    assert ready.put(f"/api/reports/{report['id']}/confirm",json={"report_date":"2026-09-01","values":values}).status_code == 422
    values[0]["unit"]="mg/dL"
    assert ready.put(f"/api/reports/{report['id']}/confirm",json={"report_date":"2026-15-80","values":values}).status_code == 422


def test_encryption_and_private_exports(ready,image_bytes,settings):
    report=upload(ready,image_bytes)
    raw=(settings.data_dir/"nalam.sqlite3").read_bytes()
    assert b"LDL cholesterol" not in raw
    assert "அம்மா".encode() not in raw
    export=ready.get("/api/export").json()
    assert "image" not in export["reports"][0]
    assert "api_key" not in json.dumps(export)


def test_cost_limits_and_cached_speech(ready):
    for _ in range(2):
        assert ready.post("/api/chat",json={"message":"இன்று என்ன சாப்பிடலாம்?"}).status_code == 200
    assert ready.post("/api/chat",json={"message":"ஒரு கேள்வி"}).status_code == 429
    request={"text":"வணக்கம்","language":"ta"}
    assert ready.post("/api/speech",json=request).status_code == 200
    calls=ready.app.state.ai.calls
    assert ready.post("/api/speech",json=request).status_code == 200
    assert ready.app.state.ai.calls == calls


def test_urgent_symptoms_bypass_ai(ready):
    calls=ready.app.state.ai.calls
    response=ready.post("/api/chat",json={"message":"எனக்கு மார்பு வலி"})
    assert response.json()["answer"]["urgency"] == "urgent"
    assert ready.app.state.ai.calls == calls
    assert symptom_emergency("எனக்கு மார்பு வலி இல்லை") is None


def test_movement_review_and_persisted_checkins(ready):
    assert ready.post("/api/checkins",json={"kind":"walk","answer":"done"}).status_code == 409
    p=ready.get("/api/profile").json();p["light_activity_ok"]=True
    assert ready.put("/api/profile",json=p).status_code == 200
    assert ready.post("/api/checkins",json={"kind":"walk","answer":"done"}).status_code == 200
    assert ready.post("/api/checkins",json={"kind":"mood","answer":"low"}).status_code == 200
    assert len(ready.get("/api/checkins").json()["checkins"]) == 2
    assert ready.post("/api/checkins",json={"kind":"mood","answer":"diagnosed depression"}).status_code == 422
    p["mobility"]="limited"
    assert ready.put("/api/profile",json=p).status_code == 200
    assert ready.post("/api/checkins",json={"kind":"walk","answer":"done"}).status_code == 409


def test_untrusted_uploads_not_sent_to_ai(ready):
    calls=ready.app.state.ai.calls
    assert ready.post("/api/reports",files={"file":("report.png",b"<script>hello</script>","image/png")}).status_code == 415
    assert ready.post("/api/transcribe",files={"file":("voice.mp3",b"<html>wrong</html>","audio/mpeg")}).status_code == 415
    assert ready.app.state.ai.calls == calls
    with pytest.raises(UnsafeImage):prepare_image(b"not an image")


def test_voice_transcription_requires_review(ready,wav_bytes):
    result=ready.post("/api/transcribe",files={"file":("question.wav",wav_bytes,"audio/wav")})
    assert result.status_code == 200
    assert result.json()["review_before_send"] is True
    assert result.json()["text"]


def test_badaga_needs_reviewed_recordings(ready,wav_bytes):
    p=ready.get("/api/profile").json();p["language"]="bfq"
    assert ready.put("/api/profile",json=p).status_code == 409
    assert ready.put("/api/languages/bfq/hello",files={"file":("badaga.wav",wav_bytes,"audio/wav")}).status_code == 422
    assert ready.put("/api/languages/bfq/hello?reviewed=true",files={"file":("badaga.wav",wav_bytes,"audio/wav")}).status_code == 200
    assert ready.get("/api/prompts/hello/audio?language=bfq").status_code == 200
    assert ready.post("/api/speech",json={"text":"anything","language":"bfq"}).status_code == 409


def test_push_endpoint_rejects_ssrf(ready):
    for endpoint in ["http://127.0.0.1:8080", "https://localhost", "https://fcm.googleapis.com.evil.example/x", "https://user:secret@fcm.googleapis.com/x"]:
        assert not valid_push_endpoint(endpoint)
    assert valid_push_endpoint("https://web.push.apple.com/a")
    response=ready.post("/api/push/subscribe",json={"endpoint":"http://127.0.0.1/internal","keys":{"p256dh":"A"*40,"auth":"B"*22}})
    assert response.status_code == 422


def test_quiet_hours_timezone_and_push_dedup(ready):
    p=Profile(timezone="Asia/Kolkata",light_activity_ok=True,reminders=[Reminder(id="walk",time="09:00")])
    when=datetime(2026,10,4,3,31,tzinfo=timezone.utc)
    assert due_reminders(p,when) == ["walk"]
    p.quiet_start="08:30";p.quiet_end="10:00"
    assert due_reminders(p,when) == []
    p.quiet_start="21:30";p.quiet_end="07:30"
    assert due_reminders(p,datetime(2026,10,4,3,40,tzinfo=timezone.utc)) == []
    assert ready.app.state.store.mark_sent("date:walk:device") is True
    assert ready.app.state.store.mark_sent("date:walk:device") is False


def test_clinician_flags_respect_units():
    assert clinician_flags([{"name":"LDL","value":"5.0","unit":"mmol/L"}])
    assert not clinician_flags([{"name":"HDL","value":"200","unit":"mg/dL"}])
    assert not clinician_flags([{"name":"LDL","value":"200","unit":"unknown"}])
    assert clinician_flags([{"name":"Triglycerides","value":"6","unit":"mmol/L"}])


def test_consent_revocation_and_delete(ready,image_bytes):
    upload(ready,image_bytes)
    assert ready.post("/api/consent",json={"accepted":False}).status_code == 200
    assert ready.post("/api/chat",json={"message":"hello"}).status_code == 403
    assert ready.delete("/api/data").status_code == 200
    data=ready.get("/api/state").json()
    assert data["reports"] == []
    assert not data["consent"]


def test_shell_and_privacy_headers(client):
    response=client.get("/")
    assert response.status_code == 200
    assert '<html lang="ta">' in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/sw.js").headers["service-worker-allowed"] == "/"


def test_iphone_heic_and_photo_metadata():
    import io
    from PIL import Image
    image=Image.new("RGB",(200,200),"white")
    exif=Image.Exif();exif[270]="private photo metadata"
    raw=io.BytesIO();image.save(raw,"JPEG",exif=exif)
    normalized=prepare_image(raw.getvalue())
    with Image.open(io.BytesIO(normalized)) as result:
        assert not result.getexif()
    heic=io.BytesIO();image.save(heic,"HEIF")
    with Image.open(io.BytesIO(prepare_image(heic.getvalue()))) as result:
        assert result.format=="JPEG"


@pytest.mark.asyncio
async def test_real_scheduler_deduplicates_without_network(ready,monkeypatch):
    store=ready.app.state.store;push=ready.app.state.push
    store.put("subscription",{"subscription":{"endpoint":"https://web.push.apple.com/test","keys":{}}},"test-device")
    deliveries=[]
    monkeypatch.setattr(push,"send",lambda sub,kind: deliveries.append((sub["id"],kind)) or True)
    p=Profile(timezone="Asia/Kolkata",light_activity_ok=True,reminders=[Reminder(id="walk",time="09:00")])
    when=datetime(2026,10,4,3,31,tzinfo=timezone.utc)
    await push.tick(p,when);await push.tick(p,when)
    assert deliveries==[("test-device","walk")]


def test_sample_mode_is_explicit_and_not_ai(settings):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from conftest import FakeAI
    settings.review_mode=True
    fake=FakeAI()
    with TestClient(create_app(settings,fake),headers={"X-Nalam-Request":"1"}) as client:
        client.post("/api/auth/login",json={"code":settings.access_code})
        client.post("/api/auth/caregiver",json={"code":settings.caregiver_pin})
        state=client.get("/api/state").json()
        assert state["review_mode"] and not state["consent"]
        report=client.post("/api/demo").json()
        assert report["synthetic"] and not report["confirmed"]
        assert client.post(f"/api/reports/{report['id']}/explain").status_code==409
        client.put(f"/api/reports/{report['id']}/confirm",json={"report_date":report["report_date"],"values":report["values"]})
        answer=client.post(f"/api/reports/{report['id']}/explain").json()
        assert answer["sample"] is True
        assert fake.calls==0
        client.post("/api/consent",json={"accepted":True})
        assert client.post("/api/chat",json={"message":"a live question"}).status_code==200
        assert fake.last_report is None
