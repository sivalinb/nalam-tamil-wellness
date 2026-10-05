"""Opt-in live integration test. Uses fictional data and consumes small API usage."""
import argparse
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

parser=argparse.ArgumentParser()
parser.add_argument("--audio-output",default="",help="Optional private output file for a generated Tamil voice sample.")
args=parser.parse_args()
settings=Settings.from_env()
with tempfile.TemporaryDirectory(prefix="nalam-smoke-") as directory:
    settings.data_dir=Path(directory);settings.scheduler=False
    with TestClient(create_app(settings),headers={"X-Nalam-Request":"1"}) as client:
        def okay(response):
            if response.status_code!=200:
                raise SystemExit(f"Live test failed: HTTP {response.status_code}; check service access/billing. Private provider responses were not printed.")
            return response
        okay(client.post("/api/auth/login",json={"code":settings.access_code}))
        okay(client.post("/api/auth/caregiver",json={"code":settings.caregiver_pin}))
        okay(client.post("/api/consent",json={"accepted":True}))
        report_path=Path(__file__).resolve().parent.parent/"static/sample-report.png"
        report=okay(client.post("/api/reports",files={"file":("synthetic-report.png",report_path.read_bytes(),"image/png")})).json()
        values={row["name"].casefold():row["value"] for row in report["values"]}
        assert any("ldl" in name and value=="152" for name,value in values.items()),"LDL transcription mismatch"
        assert any("hdl" in name and value=="48" for name,value in values.items()),"HDL transcription mismatch"
        assert all(row["unit"].casefold()=="mg/dl" for row in report["values"]),"Unit transcription mismatch"
        assert client.post(f"/api/reports/{report['id']}/explain").status_code==409
        okay(client.put(f"/api/reports/{report['id']}/confirm",json={"report_date":report["report_date"],"values":report["values"]}))
        explanation=okay(client.post(f"/api/reports/{report['id']}/explain")).json()["answer"]
        assert any('\u0b80'<=c<='\u0bff' for c in explanation["simple_tamil"]),"Expected Tamil explanation"
        utterance="வணக்கம் அம்மா. இன்று எப்படி இருக்கீங்க? சாப்பாட்டில் காய்கறியும் பருப்பும் சேர்த்துக்கலாம். உங்களுக்கு வசதியாக, மெதுவாகத் தொடரலாம்."
        audio=okay(client.post("/api/speech",json={"text":utterance,"language":"ta"})).content
        assert len(audio)>1000,"Expected generated audio"
        if args.audio_output:Path(args.audio_output).write_bytes(audio)
        transcript=okay(client.post("/api/transcribe",files={"file":("sample.mp3",audio,"audio/mpeg")})).json()
        assert transcript["review_before_send"] and any('\u0b80'<=c<='\u0bff' for c in transcript["text"])
        answer=okay(client.post("/api/chat",json={"message":"இந்த அறிக்கையை வைத்து மருந்தை நிறுத்தலாமா?"})).json()["answer"]
        assert answer["needs_clinician"],"Medication question must route to clinician"
        print("PASS: live report photo extraction, confirmation gate, Tamil explanation, generated Tamil audio, Tamil transcription, and clinician routing.")
        print("Synthetic report readings:",[(v["name"],v["value"],v["unit"]) for v in report["values"]])
        print("Tamil voice sample size:",len(audio),"bytes")
