"""SQLite 持久化 — 笔记 CRUD，够用就行"""

import json
import os
import sqlite3
from typing import Dict, List, Optional

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                bvid        TEXT PRIMARY KEY,
                video_title TEXT,
                video_url   TEXT,
                cover_url   TEXT DEFAULT '',
                category    TEXT,
                result_json TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )
        """)


def save_note(result_dict: Dict):
    """保存分析结果。result_dict 是 AnalysisResult.model_dump() 的输出。"""
    bvid = result_dict["bvid"]
    with _conn() as conn:
        conn.execute("""
            INSERT INTO notes (bvid, video_title, video_url, cover_url, category, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(bvid) DO UPDATE SET
                video_title = excluded.video_title,
                video_url   = excluded.video_url,
                cover_url   = excluded.cover_url,
                category    = excluded.category,
                result_json = excluded.result_json,
                updated_at  = datetime('now')
        """, (
            bvid,
            result_dict.get("video_title", ""),
            result_dict.get("video_url", ""),
            result_dict.get("cover_url", ""),
            result_dict.get("category", ""),
            json.dumps(result_dict, ensure_ascii=False),
        ))


def list_notes() -> List[Dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT bvid, video_title, video_url, cover_url, category, created_at, updated_at "
            "FROM notes ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_note(bvid: str) -> Optional[Dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT result_json FROM notes WHERE bvid = ?", (bvid,)
        ).fetchone()
    if not row:
        return None
    return json.loads(row["result_json"])


def delete_note(bvid: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM notes WHERE bvid = ?", (bvid,))
    return cur.rowcount > 0
