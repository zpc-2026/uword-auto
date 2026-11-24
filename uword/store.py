"""本地状态库：词表、学习进度、答案库、事件日志（SQLite，断点续跑）。"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    word_id   TEXT PRIMARY KEY,
    book_id   TEXT,
    word      TEXT,
    meaning   TEXT,
    learned   INTEGER DEFAULT 0,
    learned_at TEXT
);
CREATE TABLE IF NOT EXISTS bank (
    fp     TEXT PRIMARY KEY,
    qtype  TEXT,
    stem   TEXT,
    answer TEXT,
    hits   INTEGER DEFAULT 0,
    miss   INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS progress (
    k TEXT PRIMARY KEY,
    v TEXT
);
CREATE TABLE IF NOT EXISTS events (
    ts     REAL,
    kind   TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_words_book ON words(book_id, learned);
"""


class Store:
    def __init__(self, path: str = "uword.db"):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # ---------- words ----------
    def upsert_words(self, book_id: str, items: list[dict]) -> int:
        n = 0
        with self.lock:
            for it in items:
                if not it.get("word_id") or not it.get("word"):
                    continue
                self.conn.execute(
                    """INSERT INTO words(word_id, book_id, word, meaning)
                       VALUES(?,?,?,?)
                       ON CONFLICT(word_id) DO UPDATE SET
                         book_id=excluded.book_id,
                         word=excluded.word,
                         meaning=COALESCE(NULLIF(excluded.meaning,''), words.meaning)""",
                    (str(it["word_id"]), str(book_id), it["word"], it.get("meaning") or ""),
                )
                n += 1
            self.conn.commit()
        return n

    def pending_words(self, book_id: str, limit: int = 40, learned: int = 0) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM words WHERE book_id=? AND learned=? ORDER BY rowid LIMIT ?",
                (str(book_id), learned, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_words(self, book_id: str | None = None) -> list[dict]:
        with self.lock:
            if book_id:
                rows = self.conn.execute(
                    "SELECT * FROM words WHERE book_id=?", (str(book_id),)).fetchall()
            else:
                rows = self.conn.execute("SELECT * FROM words").fetchall()
        return [dict(r) for r in rows]

    def mark_learned(self, word_id: str) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE words SET learned=1, learned_at=? WHERE word_id=?",
                (time.strftime("%Y-%m-%d %H:%M:%S"), str(word_id)),
            )
            self.conn.commit()

    def counts(self, book_id: str | None = None):
        with self.lock:
            if book_id:
                row = self.conn.execute(
                    "SELECT COUNT(*) n, SUM(learned) d FROM words WHERE book_id=?",
                    (str(book_id),)).fetchone()
            else:
                row = self.conn.execute("SELECT COUNT(*) n, SUM(learned) d FROM words").fetchone()
        return int(row["n"] or 0), int(row["d"] or 0)

    # ---------- bank ----------
    def bank_get(self, fp: str) -> dict | None:
        with self.lock:
            row = self.conn.execute("SELECT * FROM bank WHERE fp=?", (fp,)).fetchone()
        return dict(row) if row else None

    def bank_put(self, fp: str, qtype: str, stem: str, answer: str, hit: bool = True) -> None:
        with self.lock:
            cur = self.conn.execute("SELECT fp FROM bank WHERE fp=?", (fp,)).fetchone()
            if cur:
                self.conn.execute(
                    "UPDATE bank SET answer=?, hits=hits+?, miss=miss+? WHERE fp=?",
                    (answer, 1 if hit else 0, 0 if hit else 1, fp),
                )
            else:
                self.conn.execute(
                    "INSERT INTO bank(fp, qtype, stem, answer, hits, miss) VALUES(?,?,?,?,?,?)",
                    (fp, qtype, stem, answer, 1 if hit else 0, 0 if hit else 1),
                )
            self.conn.commit()

    def bank_size(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT COUNT(*) n FROM bank").fetchone()["n"])

    # ---------- progress / events ----------
    def set_progress(self, k: str, v: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO progress(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (k, str(v)))
            self.conn.commit()

    def get_progress(self, k: str, default: str | None = None):
        with self.lock:
            row = self.conn.execute("SELECT v FROM progress WHERE k=?", (k,)).fetchone()
        return row["v"] if row else default

    def event(self, kind: str, detail: str) -> None:
        with self.lock:
            self.conn.execute("INSERT INTO events(ts,kind,detail) VALUES(?,?,?)",
                              (time.time(), kind, detail[:2000]))
            self.conn.commit()

    def stats(self) -> dict:
        with self.lock:
            n, d = self.conn.execute("SELECT COUNT(*) n, SUM(learned) d FROM words").fetchone()
            b = self.conn.execute("SELECT COUNT(*) n FROM bank").fetchone()["n"]
            ev = self.conn.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]
        return {"words": int(n or 0), "learned": int(d or 0), "bank": int(b or 0), "events": int(ev or 0)}

    def close(self):
        with self.lock:
            self.conn.close()
