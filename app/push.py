from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush

from .config import Settings, private_file
from .models import Profile
from .store import Store
from .wellness import due_reminders, local_now

log = logging.getLogger("nalam.push")


def valid_push_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and not parsed.username and not parsed.password and parsed.port in {None, 443} and (
        host == "fcm.googleapis.com" or host == "updates.push.services.mozilla.com"
        or host.endswith(".push.apple.com") or host.endswith(".notify.windows.com")
    )


class PushService:
    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self.key_path = settings.data_dir / "vapid.key"
        generated = ec.generate_private_key(ec.SECP256R1())
        pem = private_file(self.key_path, generated.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        key = serialization.load_pem_private_key(pem, password=None)
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.public_key = base64.urlsafe_b64encode(public).rstrip(b"=").decode()

    def send(self, subscription: dict, kind: str = "test") -> bool:
        try:
            webpush(subscription_info=subscription["subscription"],
                    data=json.dumps({"title": "நலம்", "body": "ஒரு சிறிய நினைவூட்டல். திறந்து கேட்கலாம்.",
                                     "url": "/?reminder=" + kind, "tag": "nalam-" + kind}, ensure_ascii=False),
                    vapid_private_key=str(self.key_path), vapid_claims={"sub": self.settings.push_contact},
                    timeout=10, ttl=300)
            return True
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in {404, 410}:
                self.store.delete(subscription["id"])
            log.warning("Push delivery failed (status %s).", status or "unavailable")
            return False
        except Exception:
            log.warning("Push service is unavailable.")
            return False

    async def tick(self, profile: Profile, now: datetime | None = None) -> None:
        now = now or datetime.now().astimezone()
        day = local_now(profile, now).date().isoformat()
        for kind in due_reminders(profile, now):
            if kind in {"walk", "stretch"} and (not profile.light_activity_ok or kind == "walk" and profile.mobility != "comfortable"):
                continue
            for sub in self.store.list("subscription"):
                key = f"{day}:{kind}:{sub['id']}"
                if self.store.mark_sent(key):
                    if not await asyncio.to_thread(self.send, sub, kind):
                        self.store.unmark_sent(key)

    async def loop(self) -> None:
        while True:
            try:
                profile_data = self.store.get("profile", "profile") or {}
                clean = {k: v for k, v in profile_data.items() if k not in {"id", "created"}}
                await self.tick(Profile.model_validate(clean))
                self.store.prune()
            except Exception:
                log.warning("Reminder check could not complete.")
            await asyncio.sleep(60)
