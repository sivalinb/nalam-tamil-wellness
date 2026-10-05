from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from .config import private_file


class DailyLimit(Exception):
    pass


class Store:
    """Single-family storage; every content payload is encrypted at rest."""
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        self.cipher = Fernet(private_file(directory / "encryption.key", Fernet.generate_key()))
        self.lock = threading.RLock()
        dbpath = directory / "nalam.sqlite3"
        self.db = sqlite3.connect(dbpath, check_same_thread=False)
        dbpath.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, created REAL NOT NULL, payload BLOB NOT NULL);
        CREATE INDEX IF NOT EXISTS records_kind ON records(kind, created);
        CREATE TABLE IF NOT EXISTS usage (day TEXT NOT NULL, kind TEXT NOT NULL, count INTEGER NOT NULL,
            PRIMARY KEY(day,kind));
        CREATE TABLE IF NOT EXISTS sent (key TEXT PRIMARY KEY, created REAL NOT NULL);
        """)
        self.db.commit()

    def put(self, kind: str, payload: dict, record_id: str | None = None) -> str:
        rid = record_id or str(uuid.uuid4())
        encrypted = self.cipher.encrypt(json.dumps(payload, ensure_ascii=False).encode())
        with self.lock, self.db:
            self.db.execute("INSERT INTO records(id,kind,created,payload) VALUES(?,?,?,?) "
                            "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                            (rid, kind, time.time(), encrypted))
        return rid

    def get(self, rid: str, kind: str | None = None) -> dict | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
        if row is None or kind is not None and row["kind"] != kind:
            return None
        return {"id": row["id"], "created": row["created"], **json.loads(self.cipher.decrypt(row["payload"]))}

    def list(self, kind: str, limit: int = 100) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created DESC LIMIT ?",
                                   (kind, limit)).fetchall()
        return [{"id": row["id"], "created": row["created"], **json.loads(self.cipher.decrypt(row["payload"]))}
                for row in rows]

    def delete(self, rid: str) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM records WHERE id=?", (rid,))

    def consume(self, day: str, kind: str, limit: int) -> None:
        with self.lock, self.db:
            row = self.db.execute("SELECT count FROM usage WHERE day=? AND kind=?", (day, kind)).fetchone()
            if row and row[0] >= limit:
                raise DailyLimit(kind)
            self.db.execute("INSERT INTO usage(day,kind,count) VALUES(?,?,1) "
                            "ON CONFLICT(day,kind) DO UPDATE SET count=count+1", (day, kind))

    def mark_sent(self, key: str) -> bool:
        with self.lock, self.db:
            cursor = self.db.execute("INSERT OR IGNORE INTO sent(key,created) VALUES(?,?)", (key, time.time()))
        return bool(cursor.rowcount)

    def unmark_sent(self, key: str) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM sent WHERE key=?", (key,))

    def purge(self) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM records")
            self.db.execute("DELETE FROM sent")

    def prune(self) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM records WHERE kind='audio' AND created<?", (time.time() - 7*86400,))
            self.db.execute("DELETE FROM sent WHERE created<?", (time.time() - 30*86400,))

    def close(self) -> None:
        self.db.close()
