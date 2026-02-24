from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class Clip:
    id: int
    content: str
    content_hash: str
    created_at: str
    pinned: int = 0
    tags: str = ""
    parent_id: Optional[int] = None
    version_note: str = ""


class ClipDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _table_columns(self, con: sqlite3.Connection, table: str) -> Dict[str, str]:
        cols: Dict[str, str] = {}
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        for r in rows:
            # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
            cols[str(r[1])] = str(r[2] or "")
        return cols

    def _ensure_columns(self, con: sqlite3.Connection) -> None:
        """
        Lightweight migration: add missing columns to existing DBs.
        """
        cols = self._table_columns(con, "clips")
        # Add columns if missing (SQLite supports ALTER TABLE ADD COLUMN)
        if "pinned" not in cols:
            con.execute("ALTER TABLE clips ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
        if "tags" not in cols:
            con.execute("ALTER TABLE clips ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
        if "parent_id" not in cols:
            con.execute("ALTER TABLE clips ADD COLUMN parent_id INTEGER")
        if "version_note" not in cols:
            con.execute("ALTER TABLE clips ADD COLUMN version_note TEXT NOT NULL DEFAULT ''")

    def _init_db(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    tags TEXT NOT NULL DEFAULT '',
                    parent_id INTEGER,
                    version_note TEXT NOT NULL DEFAULT ''
                )
                """
            )

            # Migrate older DBs that were created before new columns existed
            self._ensure_columns(con)

            # Indexes (safe to run repeatedly)
            con.execute("CREATE INDEX IF NOT EXISTS idx_clips_hash ON clips(content_hash)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_clips_created ON clips(created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_clips_pinned ON clips(pinned)")

    # ---------- CRUD ----------

    def add_text_clip(
        self,
        content: str,
        content_hash: str,
        *,
        parent_id: Optional[int] = None,
        version_note: str = "",
    ) -> Optional[int]:
        content = (content or "").strip()
        if not content:
            return None

        from datetime import datetime

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._conn() as con:
            # Ensure schema exists even if DB file was swapped in
            self._ensure_columns(con)

            row = con.execute("SELECT id FROM clips WHERE content_hash = ?", (content_hash,)).fetchone()
            if row:
                return None

            cur = con.execute(
                """
                INSERT INTO clips (content, content_hash, created_at, pinned, tags, parent_id, version_note)
                VALUES (?, ?, ?, 0, '', ?, ?)
                """,
                (content, content_hash, now, parent_id, version_note or ""),
            )
            return int(cur.lastrowid)

    def list_clips(self, limit: int = 200) -> List[Clip]:
        with self._conn() as con:
            self._ensure_columns(con)
            rows = con.execute(
                """
                SELECT * FROM clips
                ORDER BY pinned DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

        out: List[Clip] = []
        for r in rows:
            keys = set(r.keys())
            out.append(
                Clip(
                    id=int(r["id"]),
                    content=str(r["content"]),
                    content_hash=str(r["content_hash"]),
                    created_at=str(r["created_at"]),
                    pinned=int(r["pinned"]) if "pinned" in keys else 0,
                    tags=str(r["tags"] or "") if "tags" in keys else "",
                    parent_id=r["parent_id"] if "parent_id" in keys else None,
                    version_note=str(r["version_note"] or "") if "version_note" in keys else "",
                )
            )
        return out

    def get_clip(self, clip_id: int) -> Optional[Clip]:
        if not clip_id:
            return None
        with self._conn() as con:
            self._ensure_columns(con)
            r = con.execute("SELECT * FROM clips WHERE id = ?", (int(clip_id),)).fetchone()
        if not r:
            return None
        keys = set(r.keys())
        return Clip(
            id=int(r["id"]),
            content=str(r["content"]),
            content_hash=str(r["content_hash"]),
            created_at=str(r["created_at"]),
            pinned=int(r["pinned"]) if "pinned" in keys else 0,
            tags=str(r["tags"] or "") if "tags" in keys else "",
            parent_id=r["parent_id"] if "parent_id" in keys else None,
            version_note=str(r["version_note"] or "") if "version_note" in keys else "",
        )

    def set_pinned(self, clip_id: int, pinned: int) -> None:
        with self._conn() as con:
            self._ensure_columns(con)
            con.execute("UPDATE clips SET pinned = ? WHERE id = ?", (int(pinned), int(clip_id)))

    def delete_clip(self, clip_id: int) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM clips WHERE id = ?", (int(clip_id),))

    # ---------- Bulk delete ----------

    def delete_clips(self, clip_ids: List[int]) -> int:
        ids = [int(x) for x in (clip_ids or []) if x]
        if not ids:
            return 0

        placeholders = ",".join(["?"] * len(ids))
        with self._conn() as con:
            cur = con.execute(f"DELETE FROM clips WHERE id IN ({placeholders})", ids)
            return int(cur.rowcount or 0)

    def delete_all_clips(self, *, keep_pinned: bool = False) -> int:
        with self._conn() as con:
            self._ensure_columns(con)
            if keep_pinned:
                cur = con.execute("DELETE FROM clips WHERE pinned = 0")
            else:
                cur = con.execute("DELETE FROM clips")
            return int(cur.rowcount or 0)
