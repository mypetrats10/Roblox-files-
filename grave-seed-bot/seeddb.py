"""SQLite storage for the Grave Without a Stone seed catalogue."""
import csv
import io
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

# Order matters: lowest to highest, with instant-complete as its own category.
TIERS = {
    "mediocre": {"label": "Mediocre", "color": 0x8A8F98},
    "good": {"label": "Good", "color": 0x4CAF50},
    "great": {"label": "Great", "color": 0x2196F3},
    "amazing": {"label": "Amazing", "color": 0x9C27B0},
    "perfect": {"label": "Perfect", "color": 0xFFC107},
    "instant": {"label": "Instant Complete", "color": 0xE53935},
}


def normalize_seed(seed: str) -> str:
    """Key used for duplicate checks: trimmed, case-insensitive, inner spaces removed."""
    return "".join(seed.split()).lower()


@dataclass
class Seed:
    id: int
    seed: str
    tier: str
    reason: str
    map: Optional[str]
    building: Optional[str]
    location: Optional[str]
    submitter_id: int
    submitter_name: str
    created_at: int
    message_id: Optional[int]
    message_url: Optional[str]
    images: Optional[str] = None  # newline-separated image URLs from the channel post


class SeedDB:
    def __init__(self, path: str = "seeds.db"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS seeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seed TEXT NOT NULL,
                seed_key TEXT NOT NULL UNIQUE,
                tier TEXT NOT NULL,
                reason TEXT NOT NULL,
                map TEXT,
                building TEXT,
                location TEXT,
                submitter_id INTEGER NOT NULL,
                submitter_name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                message_id INTEGER,
                message_url TEXT,
                images TEXT
            )"""
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(seeds)")}
        if "images" not in cols:  # databases made before image support
            self.conn.execute("ALTER TABLE seeds ADD COLUMN images TEXT")
        self.conn.commit()

    @staticmethod
    def _row(r) -> Optional[Seed]:
        if r is None:
            return None
        d = dict(r)
        d.pop("seed_key", None)
        return Seed(**d)

    def get_setting(self, key: str, default=None):
        r = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_setting(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))
        self.conn.commit()

    def get(self, seed: str) -> Optional[Seed]:
        r = self.conn.execute(
            "SELECT * FROM seeds WHERE seed_key = ?", (normalize_seed(seed),)
        ).fetchone()
        return self._row(r)

    def add(self, seed, tier, reason, submitter_id, submitter_name,
            map=None, building=None, location=None) -> Seed:
        if tier not in TIERS:
            raise ValueError(f"Unknown tier: {tier}")
        if not normalize_seed(seed):
            raise ValueError("Seed can't be empty.")
        if not reason.strip():
            raise ValueError("A reason is required.")
        if tier == "instant" and not all(
            (x or "").strip() for x in (map, building, location)
        ):
            raise ValueError(
                "Instant-complete seeds need the map, the building, and where the flare gun is."
            )
        if self.get(seed):
            raise KeyError("duplicate")
        cur = self.conn.execute(
            """INSERT INTO seeds (seed, seed_key, tier, reason, map, building, location,
                                  submitter_id, submitter_name, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (seed.strip(), normalize_seed(seed), tier, reason.strip(),
             (map or "").strip() or None, (building or "").strip() or None,
             (location or "").strip() or None, submitter_id, submitter_name,
             int(time.time())),
        )
        self.conn.commit()
        return self._row(
            self.conn.execute("SELECT * FROM seeds WHERE id = ?", (cur.lastrowid,)).fetchone()
        )

    def set_message(self, seed_id: int, message_id: int, message_url: str, images=()):
        self.conn.execute(
            "UPDATE seeds SET message_id = ?, message_url = ?, images = ? WHERE id = ?",
            (message_id, message_url, "\n".join(images) or None, seed_id))
        self.conn.commit()

    def remove(self, seed: str) -> Optional[Seed]:
        existing = self.get(seed)
        if existing:
            self.conn.execute("DELETE FROM seeds WHERE id = ?", (existing.id,))
            self.conn.commit()
        return existing

    def list(self, tier: Optional[str] = None, limit: int = 25, offset: int = 0):
        if tier:
            rows = self.conn.execute(
                "SELECT * FROM seeds WHERE tier = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (tier, limit, offset),
            )
        else:
            rows = self.conn.execute(
                "SELECT * FROM seeds ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            )
        return [self._row(r) for r in rows]

    def counts(self) -> dict:
        out = {t: 0 for t in TIERS}
        for r in self.conn.execute("SELECT tier, COUNT(*) c FROM seeds GROUP BY tier"):
            out[r["tier"]] = r["c"]
        return out

    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["seed", "tier", "reason", "map", "building", "flare_gun_location",
                    "images", "post", "submitted_by", "submitted_at_utc"])
        for r in self.conn.execute("SELECT * FROM seeds ORDER BY tier, created_at"):
            w.writerow([r["seed"], TIERS[r["tier"]]["label"], r["reason"], r["map"] or "",
                        r["building"] or "", r["location"] or "", (r["images"] or "").replace("\n", " "),
                        r["message_url"] or "", r["submitter_name"],
                        time.strftime("%Y-%m-%d %H:%M", time.gmtime(r["created_at"]))])
        return buf.getvalue()
