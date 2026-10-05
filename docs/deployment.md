# Running on an iPhone

The local preview listens on 127.0.0.1 and is not reachable from a different phone. A phone deployment needs a reachable HTTPS origin and a Python server that stays awake. The code repository is public; the application and its health records require authentication.

1. Run Python 3.11+ on a trusted host with a persistent private data directory. Install `requirements.txt` and copy `.env.example` into private server configuration.
2. Supply a server-side AI key (or a mounted private key file), a strong family access code, and a separate caregiver PIN. Do not put any credential in build output or browser code.
3. Set `NALAM_DATA_DIR` to persistent storage, `NALAM_PUBLIC_ORIGIN=https://your-real-domain`, `NALAM_SECURE_COOKIES=true`, and the person's correct timezone. Use a real HTTPS/mailto contact for `NALAM_PUSH_CONTACT`.
4. Put an HTTPS reverse proxy in front of `uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8787 --workers 1`. Restrict the Python port to the proxy where possible. Enable proxy-header handling only for a trusted proxy.
5. Keep the private data directory mode 0700 and its key/database files private. Back up encrypted data and keys together. Keep backups out of Git and public storage. Loss of the encryption key makes saved content unrecoverable.
6. Open the HTTPS address on her iPhone, sign in, add it to the Home Screen and open the installed app. Tap the reminder button to request permission. A permission tap is required; the server cannot enable it remotely.
7. Subscribe the actual phone, use the caregiver test-reminder control, and verify delivery while the app is closed and the phone is locked. Check Focus settings. Tap the notification and play the Tamil prompt.

## Container

The included Dockerfile packages the Python service and static app. It does not package `.env`, reports or private storage. Mount persistent storage at `/app/data` and set `NALAM_DATA_DIR=/app/data`. Supply server-side secrets through your platform's private secret mechanism. If using `OPENAI_API_KEY_FILE`, mount the file at the same container path and make it readable to the app's non-root UID 10001.

The image runs one worker. A host restart, autosleep, ephemeral disk or scale-to-zero can interrupt reminder delivery and lose keys/records. Choose hosting that supports an awake Python process and persistent private storage. Do not claim a free ephemeral deployment gives reliable health check-ins.

## Operational limits

- This version handles one family per deployment. It is not designed for shared public registrations or multiple families.
- Request-count limits reduce accidental usage; they are not a dollar billing cap. Provider access, billing and retention remain separate.
- Notification delivery is best effort. Never use this as an emergency alarm, medication management system or unattended medical monitor.
- Provider failures produce a localized retry message. Cached speech helps with repeated prompts but the app does not offer full offline voice or offline report analysis.
- Native-speaker and actual-device review should precede real health use. Start with the supplied synthetic report.
