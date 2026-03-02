"""SQLite-backed memory store with WAL mode. Four tiers: working, episodic, semantic, procedural."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiosqlite

from open_sentinel.interfaces import MemoryStore
from open_sentinel.types import Alert, Episode

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    site_id TEXT,
    timestamp TEXT NOT NULL,
    trigger TEXT,
    findings_summary TEXT,
    alerts_generated INTEGER DEFAULT 0,
    outcome TEXT DEFAULT 'pending',
    clinician_feedback TEXT,
    data_snapshot TEXT,
    related_alert_ids TEXT
);

CREATE TABLE IF NOT EXISTS baselines (
    skill_name TEXT NOT NULL,
    site_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (skill_name, site_id, metric)
);

CREATE TABLE IF NOT EXISTS skill_state (
    skill_name TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (skill_name, key)
);

CREATE TABLE IF NOT EXISTS alert_history (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    severity TEXT,
    category TEXT,
    title TEXT,
    description TEXT,
    site_id TEXT,
    evidence TEXT,
    ai_generated INTEGER DEFAULT 0,
    ai_confidence REAL,
    ai_model TEXT,
    ai_reasoning TEXT,
    rule_validated INTEGER DEFAULT 0,
    reflection_iterations INTEGER DEFAULT 0,
    outcome TEXT DEFAULT 'pending',
    clinician_feedback TEXT,
    dedup_key TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    alert_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emission_queue (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    output_name TEXT NOT NULL,
    data TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    next_retry TEXT,
    attempts INTEGER DEFAULT 0
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteMemoryStore(MemoryStore):
    def __init__(self, db_path: str = "sentinel_state.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._working: Dict[str, Any] = {}

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("MemoryStore not initialized. Call initialize() first.")
        return self._db

    # --- Working memory ---

    async def get_working(self, key: str) -> Any:
        return self._working.get(key)

    async def set_working(self, key: str, value: Any) -> None:
        self._working[key] = value

    async def clear_working(self) -> None:
        self._working.clear()

    # --- Episodic memory ---

    async def store_episode(self, episode: Episode) -> None:
        db = self._ensure_db()
        await db.execute(
            """INSERT OR REPLACE INTO episodes
            (id, skill_name, site_id, timestamp, trigger, findings_summary,
             alerts_generated, outcome, clinician_feedback, data_snapshot, related_alert_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                episode.id,
                episode.skill_name,
                episode.site_id,
                episode.timestamp.isoformat(),
                episode.trigger,
                episode.findings_summary,
                episode.alerts_generated,
                episode.outcome,
                episode.clinician_feedback,
                json.dumps(episode.data_snapshot) if episode.data_snapshot else None,
                json.dumps(episode.related_alert_ids) if episode.related_alert_ids else None,
            ),
        )
        await db.commit()

    async def recall_episodes(
        self, skill_name: str, site_id: str, limit: int = 5
    ) -> List[Episode]:
        db = self._ensure_db()
        cursor = await db.execute(
            """SELECT id, skill_name, site_id, timestamp, trigger,
                      findings_summary, alerts_generated, outcome,
                      clinician_feedback, data_snapshot, related_alert_ids
            FROM episodes
            WHERE skill_name = ? AND site_id = ?
            ORDER BY timestamp DESC LIMIT ?""",
            (skill_name, site_id, limit),
        )
        rows = await cursor.fetchall()
        episodes = []
        for row in rows:
            episodes.append(Episode(
                id=row[0],
                skill_name=row[1],
                site_id=row[2],
                timestamp=datetime.fromisoformat(row[3]),
                trigger=row[4] or "",
                findings_summary=row[5] or "",
                alerts_generated=row[6] or 0,
                outcome=row[7] or "pending",
                clinician_feedback=row[8],
                data_snapshot=json.loads(row[9]) if row[9] else None,
                related_alert_ids=json.loads(row[10]) if row[10] else None,
            ))
        return episodes

    async def update_episode_outcome(
        self, alert_id: str, outcome: str, feedback: Optional[str] = None
    ) -> None:
        db = self._ensure_db()
        await db.execute(
            """UPDATE episodes SET outcome = ?, clinician_feedback = ?
            WHERE related_alert_ids LIKE ?""",
            (outcome, feedback, f'%"{alert_id}"%'),
        )
        await db.commit()

    # --- Semantic memory ---

    async def get_baseline(
        self, skill_name: str, site_id: str, metric: str
    ) -> Optional[float]:
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT value FROM baselines WHERE skill_name = ? AND site_id = ? AND metric = ?",
            (skill_name, site_id, metric),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def update_baseline(
        self, skill_name: str, site_id: str, metric: str, value: float
    ) -> None:
        db = self._ensure_db()
        await db.execute(
            """INSERT OR REPLACE INTO baselines (skill_name, site_id, metric, value, updated_at)
            VALUES (?, ?, ?, ?, ?)""",
            (skill_name, site_id, metric, value, _now_iso()),
        )
        await db.commit()

    # --- Procedural memory ---

    async def get_skill_state(self, skill_name: str, key: str) -> Any:
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT value FROM skill_state WHERE skill_name = ? AND key = ?",
            (skill_name, key),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return row[0]

    async def set_skill_state(self, skill_name: str, key: str, value: Any) -> None:
        db = self._ensure_db()
        await db.execute(
            """INSERT OR REPLACE INTO skill_state (skill_name, key, value, updated_at)
            VALUES (?, ?, ?, ?)""",
            (skill_name, key, json.dumps(value), _now_iso()),
        )
        await db.commit()

    # --- Alert history ---

    async def store_alert(self, alert: Alert) -> None:
        db = self._ensure_db()
        await db.execute(
            """INSERT OR REPLACE INTO alert_history
            (id, skill_name, severity, category, title, description, site_id, evidence,
             ai_generated, ai_confidence, ai_model, ai_reasoning,
             rule_validated, reflection_iterations, outcome, clinician_feedback,
             dedup_key, created_at, reviewed_at, alert_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert.id,
                alert.skill_name,
                alert.severity,
                alert.category,
                alert.title,
                alert.description,
                alert.site_id,
                json.dumps(alert.evidence) if alert.evidence else None,
                1 if alert.ai_generated else 0,
                alert.ai_confidence,
                alert.ai_model,
                alert.ai_reasoning,
                1 if alert.rule_validated else 0,
                alert.reflection_iterations,
                alert.outcome,
                alert.clinician_feedback,
                alert.dedup_key,
                alert.created_at.isoformat(),
                alert.reviewed_at.isoformat() if alert.reviewed_at else None,
                alert.model_dump_json(),
            ),
        )
        await db.commit()

    async def get_alert(self, alert_id: str) -> Optional[Alert]:
        db = self._ensure_db()
        cursor = await db.execute(
            "SELECT alert_json FROM alert_history WHERE id = ?",
            (alert_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Alert.model_validate_json(row[0])

    async def recent_alerts(self, skill_name: str, limit: int = 20) -> List[Alert]:
        db = self._ensure_db()
        cursor = await db.execute(
            """SELECT alert_json FROM alert_history
            WHERE skill_name = ?
            ORDER BY created_at DESC LIMIT ?""",
            (skill_name, limit),
        )
        rows = await cursor.fetchall()
        return [Alert.model_validate_json(row[0]) for row in rows]

    async def update_alert_outcome(
        self, alert_id: str, outcome: str, feedback: Optional[str] = None
    ) -> None:
        db = self._ensure_db()
        now = _now_iso()
        # Update indexed columns
        await db.execute(
            """UPDATE alert_history
            SET outcome = ?, clinician_feedback = ?, reviewed_at = ?
            WHERE id = ?""",
            (outcome, feedback, now, alert_id),
        )
        # Update the JSON blob too
        cursor = await db.execute(
            "SELECT alert_json FROM alert_history WHERE id = ?", (alert_id,)
        )
        row = await cursor.fetchone()
        if row:
            alert = Alert.model_validate_json(row[0])
            alert = alert.model_copy(update={
                "outcome": outcome,
                "clinician_feedback": feedback,
                "reviewed_at": datetime.fromisoformat(now),
            })
            await db.execute(
                "UPDATE alert_history SET alert_json = ? WHERE id = ?",
                (alert.model_dump_json(), alert_id),
            )
        await db.commit()

    async def count_recent_alerts(
        self, skill_name: str, severity: Optional[str] = None, window_hours: int = 1
    ) -> int:
        db = self._ensure_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
        if severity:
            cursor = await db.execute(
                """SELECT COUNT(*) FROM alert_history
                WHERE skill_name = ? AND severity = ? AND created_at >= ?""",
                (skill_name, severity, cutoff),
            )
        else:
            cursor = await db.execute(
                """SELECT COUNT(*) FROM alert_history
                WHERE skill_name = ? AND created_at >= ?""",
                (skill_name, cutoff),
            )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # --- Emission queue ---

    async def queue_emission(
        self, alert_id: str, output_name: str, data: str
    ) -> None:
        db = self._ensure_db()
        await db.execute(
            """INSERT INTO emission_queue (id, alert_id, output_name, data, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (str(uuid4()), alert_id, output_name, data, _now_iso()),
        )
        await db.commit()

    async def get_pending_emissions(self, limit: int = 50) -> List[Dict[str, Any]]:
        db = self._ensure_db()
        now = _now_iso()
        cursor = await db.execute(
            """SELECT id, alert_id, output_name, data, attempts
            FROM emission_queue
            WHERE status = 'pending' AND (next_retry IS NULL OR next_retry <= ?)
            ORDER BY created_at ASC LIMIT ?""",
            (now, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "alert_id": row[1],
                "output_name": row[2],
                "data": row[3],
                "attempts": row[4],
            }
            for row in rows
        ]

    async def mark_emission_complete(self, emission_id: str) -> None:
        db = self._ensure_db()
        await db.execute(
            "DELETE FROM emission_queue WHERE id = ?",
            (emission_id,),
        )
        await db.commit()

    async def mark_emission_failed(
        self, emission_id: str, next_retry: datetime
    ) -> None:
        db = self._ensure_db()
        await db.execute(
            """UPDATE emission_queue
            SET attempts = attempts + 1, next_retry = ?
            WHERE id = ?""",
            (next_retry.isoformat(), emission_id),
        )
        await db.commit()
