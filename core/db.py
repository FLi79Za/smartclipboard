import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from core.util import utc_now_iso


@dataclass
class Clip:
    id: int
    content: str
    content_hash: str
    created_at: str
    pinned: int
    clip_type: str
    file_path: Optional[str]
    parent_id: Optional[int]
    version_note: Optional[str]


class ClipDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as con:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS clips (
                  id            INTEGER PRIMARY KEY AUTOINCREMENT,
                  content       TEXT NOT NULL,
                  content_hash  TEXT NOT NULL,
                  created_at    TEXT NOT NULL,
                  pinned        INTEGER NOT NULL DEFAULT 0,
                  clip_type     TEXT NOT NULL DEFAULT 'text',
                  file_path     TEXT,
                  parent_id     INTEGER,
                  version_note  TEXT,
                  FOREIGN KEY(parent_id) REFERENCES clips(id)
                );
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_clips_pinned_created ON clips(pinned, created_at);")
            con.execute("CREATE INDEX IF NOT EXISTS idx_clips_created ON clips(created_at);")
            con.commit()

    def add_text_clip(
        self,
        content: str,
        content_hash: str,
        pinned: int = 0,
        parent_id: Optional[int] = None,
        version_note: Optional[str] = None,
    ) -> int:
        created_at = utc_now_iso()
        with self._conn() as con:
            cur = con.execute(
                """
                INSERT INTO clips (content, content_hash, created_at, pinned, clip_type, file_path, parent_id, version_note)
                VALUES (?, ?, ?, ?, 'text', NULL, ?, ?)
                """,
                (content, content_hash, created_at, pinned, parent_id, version_note),
            )
            con.commit()
            return int(cur.lastrowid)

    def list_clips(self, limit: int = 200) -> List[Clip]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT * FROM clips
                ORDER BY pinned DESC, datetime(created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_clip(r) for r in rows]

    def get_clip(self, clip_id: int) -> Optional[Clip]:
        with self._conn() as con:
            row = con.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return self._row_to_clip(row) if row else None

    def delete_clip(self, clip_id: int) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
            con.commit()

    def set_pinned(self, clip_id: int, pinned: int) -> None:
        with self._conn() as con:
            con.execute("UPDATE clips SET pinned = ? WHERE id = ?", (pinned, clip_id))
            con.commit()

    def _row_to_clip(self, r: sqlite3.Row) -> Clip:
        return Clip(
            id=int(r["id"]),
            content=str(r["content"]),
            content_hash=str(r["content_hash"]),
            created_at=str(r["created_at"]),
            pinned=int(r["pinned"]),
            clip_type=str(r["clip_type"]),
            file_path=r["file_path"],
            parent_id=r["parent_id"],
            version_note=r["version_note"],
        )
