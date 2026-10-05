from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Profile, WellnessAnswer

SOURCES = [
    {"title": "American Heart Association: understanding LDL", "url": "https://www.heart.org/en/health-topics/cholesterol/hdl-good-ldl-bad-cholesterol-and-triglycerides/lower-your-ldl"},
    {"title": "American Heart Association: saturated fats", "url": "https://www.heart.org/en/healthy-living/healthy-eating/eat-smart/fats/saturated-fats"},
    {"title": "WHO: physical activity and sedentary behaviour", "url": "https://www.who.int/publications/i/item/9789240015128"},
]

# Curated educational context, never a substitute for a clinician's individual plan.
KNOWLEDGE = """
High LDL often has no symptoms. Cholesterol care depends on LDL, HDL, triglycerides,
age, blood pressure, diabetes, smoking, family history, and prior cardiovascular disease.
A laboratory reference range is not an individualized treatment target. A clinician should
review a newly high result and decide about medications and follow-up blood tests.
Do not promise that food or exercise alone will lower cholesterol enough.
Heart-healthy eating includes vegetables, fruit, beans/pulses, whole grains and appropriate
lean proteins. Replace saturated fat from ghee, butter, full-fat dairy, coconut/palm oil
with suitable unsaturated fats in modest amounts. Do not ban rice/idli/dosa or recommend
extreme dieting, weight loss without context, supplements or "cholesterol cures".
For older adults, gradually adapted activity can help. General WHO population guidance is
150–300 minutes/week moderate activity, strength on at least 2 days/week, and functional
balance/strength activity on at least 3 days/week. These are eventual population goals,
not a prescription to an unknown individual. Start only with comfortable familiar activity
and adapt to pain, falls, mobility, conditions and clinician advice. No unsupported balance
exercises, running, heavy weights or demanding routines in this app.
Regular sleep/wake times, a calm evening and limiting late caffeine may help sleep.
Persistent low mood or poor sleep merits discussion with a clinician or trusted family member.
No diagnosis of depression or other illnesses from check-ins.
"""

PROMPTS = {
    "hello": "வணக்கம் அம்மா. இன்று எப்படி இருக்கீங்க? ஒவ்வொன்றாகப் பார்த்துக்கலாம்.",
    "walk": "மெதுவாக கொஞ்ச நேரம் நடக்கலாம். உடம்பு சௌகரியமாக இருந்தால் மட்டும் நடங்க. வலி இருந்தால் நிறுத்துங்க.",
    "stretch": "கொஞ்ச நேரம் உடம்பை மெதுவாக அசைக்கலாம். வலி வரும் அளவுக்கு செய்ய வேண்டாம்.",
    "mood": "இன்று மனசு எப்படி இருக்கு? நல்லா இருக்கா, சுமாரா இருக்கா, அல்லது கவலையா இருக்கா?",
    "sleep": "இன்று இரவு அமைதியாகத் தூங்கத் தயாராகலாம். நேற்று இரவு எப்படி தூங்கினீங்க?",
    "food": "சாப்பாட்டில் காய்கறியும் பருப்பும் சேர்த்துக்கலாம். நெய், வெண்ணெய் போன்றவற்றைக் குறைவாகப் பயன்படுத்தலாம்.",
    "done": "சரி அம்மா. பதிவு செய்தாச்சு. உங்களுக்கு வசதியாக, மெதுவாகத் தொடரலாம்.",
    "later": "சரி அம்மா. இப்போது வேண்டாம் என்றால் பிறகு பார்த்துக்கலாம்.",
    "report_pending": "அறிக்கையைப் படித்தாச்சு. அதிலுள்ள எண்களை உங்கள் குடும்பத்தினர் சரிபார்த்த பிறகு விளக்கத்தைக் கேட்கலாம்.",
    "emergency": "உடனே உள்ளூர் அவசர மருத்துவ உதவியை அழையுங்க. உதவிக்கு குடும்பத்தினரையும் கூப்பிடுங்க. தனியாக இருக்க வேண்டாம்.",
}


def sample_answer(message: str = "", report: bool = False) -> WellnessAnswer:
    if report:
        text = "இது பயிற்சிக்கான மாதிரி அறிக்கை. கொலஸ்ட்ரால் என்பது இரத்தத்தில் இருக்கும் ஒரு வகைக் கொழுப்பு. அதன் சில அளவுகள் அதிகமாக இருந்தால் இதய நலனை பாதிக்கலாம். உண்மையான அறிக்கையை மருத்துவருடன் பார்த்துப் பேசணும். சாப்பாட்டில் காய்கறியும் பருப்பும் சேர்ப்பது உதவலாம். மருந்து தேவையா என்பதை மருத்துவர்தான் முடிவு செய்யணும்."
        step = "உண்மையான அறிக்கையை மருத்துவருடன் பார்த்துப் பேசலாம்."
    elif "தூங்" in message or "தூக்" in message:
        text = "இது மாதிரி விளக்கம். தினமும் ஒரே நேரத்தில் படுக்க முயற்சி செய்யலாம். மாலையில் டீ, காபியைக் குறைத்துப் பார்க்கலாம். தொடர்ந்து தூக்கம் சரியாக இல்லாவிட்டால் மருத்துவரிடம் பேசலாம்."
        step = "இன்றிரவு படுக்கும் நேரத்தை அமைதியாக வைத்துக்கலாம்."
    elif "கவலை" in message or "மனசு" in message:
        text = "இது மாதிரி விளக்கம். மனசு கவலையா இருந்தால் நம்பிக்கையான குடும்பத்தினருடன் கொஞ்ச நேரம் பேசலாம். அடிக்கடி இப்படி இருந்தால் மருத்துவரிடமும் பேசலாம்."
        step = "உங்களுக்கு நெருக்கமான ஒருவருடன் கொஞ்ச நேரம் பேசலாம்."
    elif any(word in message for word in ["சாப்ப", "உணவு"]) or not message:
        text = "இது மாதிரி விளக்கம். பழக்கமான சாப்பாட்டில் காய்கறியும் பருப்பும் சேர்த்துக்கலாம். நெய், வெண்ணெய் போன்றவற்றைக் குறைவாகப் பயன்படுத்தலாம். உங்களுக்கு உணவுக் கட்டுப்பாடுகள் இருந்தால் குடும்பத்தினர் அல்லது மருத்துவருடன் தேர்வு செய்யலாம்."
        step = "அடுத்த சாப்பாட்டில் உங்களுக்கு ஏற்ற காய்கறியைச் சேர்த்துக்கலாம்."
    else:
        text = "இது மாதிரிக்கான முதல் பார்வை. உண்மையான குரல் உதவியை குடும்பத்தினர் இணைத்த பிறகு இந்தக் கேள்வியைக் கேட்கலாம். இப்போது சாப்பாடு, தூக்கம், மனசு பற்றிய மாதிரி விளக்கங்களைப் பார்க்கலாம்."
        step = "குடும்பத்தினருடன் குரல் உதவியை இணைத்துத் தரச் சொல்லலாம்."
    return WellnessAnswer(simple_tamil=text, english_summary="Prewritten sample walkthrough. It does not analyze a real report or answer this question using AI. Fund the configured API project to validate live analysis and speech.",
                          next_step_tamil=step, clinician_questions=["What follow-up is appropriate for the actual report?"],
                          needs_clinician=True, urgency="clinician" if report else "routine")


def local_now(profile: Profile, now: datetime | None = None) -> datetime:
    return (now or datetime.now().astimezone()).astimezone(ZoneInfo(profile.timezone))


def quiet_time(profile: Profile, clock: str) -> bool:
    start, end = profile.quiet_start, profile.quiet_end
    if start == end:
        return False
    return start <= clock < end if start < end else clock >= start or clock < end


def due_reminders(profile: Profile, now: datetime) -> list[str]:
    local = local_now(profile, now)
    if quiet_time(profile, local.strftime("%H:%M")):
        return []
    due = []
    for reminder in profile.reminders:
        hour, minute = map(int, reminder.time.split(":"))
        scheduled = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if reminder.enabled and timedelta(0) <= local - scheduled < timedelta(minutes=5):
            due.append(reminder.id)
    return due


def today_plan(profile: Profile, checkins: list[dict], now: datetime | None = None) -> dict:
    local = local_now(profile, now)
    day = local.date().isoformat()
    complete = {row["kind"]: row["answer"] for row in reversed(checkins) if row.get("local_date") == day}
    walk_safe = profile.light_activity_ok and profile.mobility == "comfortable"
    stretch_safe = profile.light_activity_ok
    tasks = [
        {"id": "walk", "title": "மெதுவாக நடக்கலாம்", "english": "A little walk", "prompt_key": "walk",
         "detail": f"உங்களுக்கு வசதியாக இருந்தால், {profile.walk_minutes} நிமிடம் மெதுவாக நடங்க. வலி அல்லது தலைசுற்றல் இருந்தால் நிறுத்துங்க." if walk_safe else "உங்களுக்கு ஏற்ற நடையை குடும்பத்தினர் அல்லது மருத்துவரிடம் உறுதி செய்த பிறகு தொடங்கலாம்.",
         "allowed": walk_safe, "answer": complete.get("walk")},
        {"id": "stretch", "title": "கொஞ்சம் அசையலாம்", "english": "Gentle movement", "prompt_key": "stretch",
         "detail": "உட்கார்ந்தபடி தோள்களையும் கைகளையும் மெதுவாக அசைக்கலாம். வலி வந்தால் நிறுத்துங்க." if stretch_safe else "உங்களுக்கு ஏற்ற மெதுவான அசைவுகளை குடும்பத்தினர் அல்லது மருத்துவரிடம் கேட்டுத் தெரிஞ்சுக்கலாம்.",
         "allowed": stretch_safe, "answer": complete.get("stretch")},
        {"id": "mood", "title": "மனசு எப்படி இருக்கு?", "english": "How are you feeling?", "prompt_key": "mood",
         "detail": PROMPTS["mood"], "allowed": True, "answer": complete.get("mood")},
        {"id": "sleep", "title": "நேற்று நல்லா தூங்கினீங்களா?", "english": "How was your sleep?", "prompt_key": "sleep",
         "detail": "தினமும் ஒரே நேரத்தில் படுக்க முயற்சி செய்யலாம். மாலையில் டீ, காபியைக் குறைத்துப் பார்க்கலாம்.", "allowed": True, "answer": complete.get("sleep")},
    ]
    meals = [
        {"title": "காலை", "english": "Breakfast", "text": "இட்லி, காய்கறி சேர்த்த சாம்பார்."},
        {"title": "மதியம்", "english": "Lunch", "text": "சாதத்துடன் காய்கறி, கீரை, பருப்பு சேர்த்துக்கலாம்."},
        {"title": "இரவு", "english": "Dinner", "text": "குறைந்த எண்ணெயில் தோசை, பருப்பு அல்லது காய்கறியுடன்."},
    ]
    if profile.allergies.strip() or profile.conditions.strip():
        meals = [{"title": "உங்களுக்கு ஏற்ற உணவு", "english": "Your food needs", "text": "உங்களின் உணவுக் கட்டுப்பாடுகளுக்கு ஏற்ற உணவை குடும்பத்தினர் அல்லது மருத்துவருடன் தேர்வு செய்யலாம்."}]
    food_tip = PROMPTS["food"] if not profile.allergies.strip() and not profile.conditions.strip() else "உங்களுக்கான உணவுக் கட்டுப்பாடுகளை கவனத்தில் வைத்து, குடும்பத்தினருடன் உணவைத் தேர்வு செய்யலாம்."
    return {"date": day, "name": profile.name, "tasks": tasks, "meals": meals,
            "food_tip": food_tip, "voice_tamil": "வணக்கம் " + profile.name + ". " + tasks[0]["detail"] + " " + PROMPTS["mood"],
            "completed": sum(v not in {"later"} for v in complete.values()),
            "activity_review_needed": not profile.light_activity_ok,
            "sources": SOURCES}


def symptom_emergency(message: str) -> WellnessAnswer | None:
    text = message.casefold()
    # Conservative deterministic branch; the AI may additionally flag urgent descriptions.
    patterns = [r"\b(?:i have|having|my mother has|she has)\s+(?:severe\s+)?chest pain",
                r"\b(?:cannot|can't|unable to) breathe\b", r"\bsudden (?:weakness|face droop|slurred speech)\b",
                r"(?:நெஞ்சு|மார்பு)\s*வலி", r"மூச்சு\s*(?:விட\s*)?முடிய", r"திடீர்.*(?:பேச|பலவீனம்)"]
    if not any(re.search(p, text) for p in patterns):
        return None
    # Don't interpret a simple negated symptom report as a positive emergency symptom.
    if re.search(r"(?:வலி|திணறல்)\s*(?:இல்லை|இல்ல)", text) and not re.search(r"மூச்சு.*முடிய", text):
        return None
    return WellnessAnswer(simple_tamil="நீங்கள் சொன்ன அறிகுறிக்கு உடனடி மருத்துவ உதவி தேவைப்படலாம். " + PROMPTS["emergency"],
                          english_summary="This symptom may need emergency assessment. Contact local emergency services now; don't wait for the app or a caregiver to reply.",
                          next_step_tamil=PROMPTS["emergency"], clinician_questions=[], needs_clinician=True, urgency="urgent")


def clinician_flags(values: list[dict]) -> list[str]:
    flags = []
    for item in values:
        name = item["name"].casefold()
        try:
            value = float(item["value"])
        except ValueError:
            continue
        unit = item["unit"].casefold().replace(" ", "")
        if unit not in {"mg/dl", "mmol/l"}:
            continue
        if "ldl" in name:
            mgdl = value * 38.67 if unit == "mmol/l" else value
            if mgdl >= 190:
                flags.append("An LDL value at or above 190 mg/dL needs prompt clinician review; the app must not recommend lifestyle-only treatment.")
        if "trig" in name:
            mgdl = value * 88.57 if unit == "mmol/l" else value
            if mgdl >= 500:
                flags.append("A triglyceride value at or above 500 mg/dL needs prompt clinician review.")
    return flags
