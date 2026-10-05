# நலம் · Nalam

A Tamil voice companion for everyday wellness, with a separate caregiver view. Python handles AI calls, private records and reminders; an installable mobile web app provides large Tamil controls, camera upload, audio playback and voice questions.

## What works

- Photograph a printed blood-test report, including iPhone HEIC photos. The server extracts text; a caregiver compares each number, unit and date with the photo before an explanation is available.
- Hear a short explanation in conversational Tamil, with a readable Tamil version, an English caregiver summary and questions to discuss with a clinician.
- Ask a question by voice. Tamil transcription is shown for review and can be played back before sending.
- Get familiar food ideas and gentle walking, movement, mood and sleep check-ins. Activity prompts remain gated until the caregiver has reviewed mobility and restrictions.
- Configure timezone, reminder times and quiet hours. Web Push runs in the Python server and is opt-in on each device.
- Store health content encrypted locally. Export and delete records through caregiver controls.
- Add reviewed Badaga recordings for the ten daily prompts. Free-form Badaga translation/speech is deliberately not enabled without language validation.

This is a working first version for family review, not a clinically validated product. It provides education and supports clinician instructions. It cannot diagnose disease, decide treatment, change medication or reliably assess an emergency. A high cholesterol result needs clinician follow-up even if someone feels well.

## Run locally

Requires Python 3.11 or later. Node is not required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_local.py --key-file ~/api_token --timezone America/Denver
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8787
```

Use an IANA timezone for the person using the app; the command above is just an example. If your key is somewhere else, change `--key-file`. Alternatively copy `.env.example` to `.env`, fill in `OPENAI_API_KEY`, a family code of at least ten characters and a caregiver PIN of at least six characters. Keys stay on the Python server.

Open [the local app](http://127.0.0.1:8787). `scripts/setup_local.py` creates a private `.env` without printing the key or access credentials. Read `NALAM_ACCESS_CODE` there to sign in, and `NALAM_CAREGIVER_PIN` to unlock **குடும்பம் / Caregiver**. Go to **Privacy** to explain the AI processing to her and record her choice, then **Routine** to check her timezone, food restrictions and appropriate activity.

The API key must have usable billing and access to the configured models. A ChatGPT/Codex sign-in token is not an app API key. The default models are `gpt-4.1-mini`, `gpt-4o-mini-tts` and `gpt-4o-mini-transcribe`; all are configurable. API request limits cap this app's daily calls, rather than guaranteeing a specific currency budget. Set a provider budget/alert too if needed.

## First review

1. Open **குடும்பம்**, unlock with the PIN, explain consent in Tamil and save the choice.
2. Check her timezone and restrictions in **Routine**. Leave light activity unapproved if there are unresolved pain, mobility or medical concerns.
3. Return to her view and play **கேட்கலாம்**. Have a native Tamil speaker and the intended listener assess whether the voice is understandable at its normal pace.
4. Use **அறிக்கை** to upload `static/sample-report.png`. It is clearly fictional. Confirm the readings in the caregiver view, then request and play the explanation.
5. On a real iPhone over HTTPS, check microphone permission, transcription review, audio playback, Home Screen installation and notifications.

The app never silently treats sample data as her report. No real family reports or credentials are included in this repository.

If the API project has no credits, set `NALAM_REVIEW_MODE=true` in your private `.env` and restart. The app shows **Sample walkthrough**. Unlock the caregiver view and choose **Load a fictional sample report** to try confirmation and a clearly prewritten Tamil explanation. Food, sleep and mood examples are prewritten too. The demo can use the device's installed Tamil voice at normal speed; it does not silently fall back to English. This does not verify live AI extraction, AI speech, transcription or medical translation. Real uploads and AI processing still require the normal consent flow and a funded API key. Set review mode back to false for ordinary use.

## iPhone and deployment

The localhost preview is for review on the computer running the server. To use the app on her iPhone, run this Python service on a continuously available host with persistent storage and HTTPS. See [deployment notes](docs/deployment.md) and [architecture](docs/architecture.md).

In Safari, add the app to the Home Screen. On iOS 16.4 or later, open the installed app and tap **நினைவூட்டல் வேண்டுமா?** to allow push notifications. Notifications cannot reliably speak custom Tamil instructions while the phone is locked; she taps the notification and plays the prompt. Delivery also depends on connectivity, Focus settings and an awake server. This is not emergency monitoring.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The automated suite checks the report-confirmation gate, authentication, request-origin protection, encrypted storage, consent, quota handling, movement restrictions, voice-upload validation, Badaga review gates and timezone-aware reminder scheduling. It uses a fake AI service and makes no network calls.

To run a small live API check with the clearly synthetic report:

```bash
PYTHONPATH=. python scripts/smoke_live.py
```

This consumes API usage. It verifies integration, not clinical accuracy or your mom's comprehension. `requirements.lock.txt` records the exact environment used for the initial implementation and tests.

## Privacy and limitations

- SQLite payloads use Fernet encryption. The encryption key stays in the private data directory, so this protects data at rest but not a compromised server account.
- Pending report images are encrypted and removed from active records after caregiver confirmation. Input voice recordings are processed in memory and not stored by the app. Saved speech audio is encrypted and pruned after seven days.
- Provider processing is separate from app storage. OpenAI API data is not used for training by default, but abuse-monitoring retention may apply. `store=false` does not guarantee zero provider retention.
- Service-worker caching includes public app files only. Health records, API results and generated audio are never added to that cache. There are no analytics or advertising scripts.
- Caregiver sessions expire after an hour; the family session can last thirty days. This is a single-family application, not a multi-tenant healthcare service.
- Vision and speech can make mistakes. Every report value and unit needs human confirmation; every voice transcript can be replayed before it is sent.
- Tamil is supported by the chosen speech service, but native-listener evaluation is essential. Badaga has a recording workflow, not an unverified AI translation claim.
- Generic food examples yield to known allergies and conditions. Clinician notes are context; the app does not verify who authored them or substitute for medical care.

## Sources

- [American Heart Association: understanding LDL](https://www.heart.org/en/health-topics/cholesterol/hdl-good-ldl-bad-cholesterol-and-triglycerides/lower-your-ldl)
- [American Heart Association: saturated fats](https://www.heart.org/en/healthy-living/healthy-eating/eat-smart/fats/saturated-fats)
- [WHO: physical activity and sedentary behaviour](https://www.who.int/publications/i/item/9789240015128)
- [OpenAI: vision limitations](https://developers.openai.com/api/docs/guides/images-vision)
- [OpenAI: text to speech](https://developers.openai.com/api/docs/guides/text-to-speech)
- [OpenAI: API data controls](https://developers.openai.com/api/docs/guides/your-data)
- [WebKit: Home Screen Web Push on iPhone](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)

See [the review checklist](docs/review-checklist.md) for the remaining real-device and native-speaker validation.
