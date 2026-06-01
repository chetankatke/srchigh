"""
Database layer — SQLite with aiosqlite for async operations.
Stores judgment records persistently instead of CSV.
"""

import aiosqlite
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.expanduser("~"), ".config", "srchigh", "judgments.db")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS judgments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnr             TEXT,
    case_title      TEXT,
    court           TEXT,
    judge           TEXT,
    reg_date        TEXT,
    decision_date   TEXT,
    disposal_nature TEXT,
    pdf_path        TEXT,
    search_term     TEXT,
    source          TEXT DEFAULT 'ecourts',
    downloaded      INTEGER DEFAULT 0,
    file_size       INTEGER DEFAULT 0,
    created_at      TEXT,
    UNIQUE(cnr, search_term)
)
"""

CREATE_SEARCHES = """
CREATE TABLE IF NOT EXISTS searches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    search_term     TEXT UNIQUE,
    mode            TEXT,
    court           TEXT,
    total_results   INTEGER DEFAULT 0,
    pages_fetched   INTEGER DEFAULT 0,
    created_at      TEXT
)
"""

CREATE_DOWNLOADS_LOG = """
CREATE TABLE IF NOT EXISTS download_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnr             TEXT,
    pdf_path        TEXT,
    search_term     TEXT,
    downloaded_at   TEXT,
    success         INTEGER,
    file_size       INTEGER,
    session_cnr     TEXT
)
"""


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLE)
        await db.executescript(CREATE_SEARCHES)
        await db.executescript(CREATE_DOWNLOADS_LOG)
        # Migration: add source column if missing (existing DBs)
        try:
            await db.execute("ALTER TABLE judgments ADD COLUMN source TEXT DEFAULT 'ecourts'")
        except aiosqlite.OperationalError:
            pass  # column already exists
        try:
            await db.execute("ALTER TABLE searches ADD COLUMN source TEXT DEFAULT 'ecourts'")
        except aiosqlite.OperationalError:
            pass
        await db.commit()


async def insert_judgment(entry, search_term="", downloaded=False, file_size=0, source="ecourts"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO judgments
            (cnr, case_title, court, judge, reg_date, decision_date,
             disposal_nature, pdf_path, search_term, source, downloaded, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.get("cnr"),
            entry.get("case_title"),
            entry.get("court"),
            entry.get("judge"),
            entry.get("reg_date"),
            entry.get("decision_date"),
            entry.get("disposal_nature"),
            entry.get("path"),
            search_term,
            source,
            1 if downloaded else 0,
            file_size,
            datetime.utcnow().isoformat(),
        ))
        await db.commit()


async def insert_judgments_batch(entries, search_term="", source="ecourts"):
    if not entries:
        return
    rows = [
        (
            e.get("cnr"),
            e.get("case_title"),
            e.get("court"),
            e.get("judge"),
            e.get("reg_date"),
            e.get("decision_date"),
            e.get("disposal_nature"),
            e.get("path"),
            search_term,
            source,
            0,
            0,
            datetime.utcnow().isoformat(),
        )
        for e in entries
    ]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany("""
            INSERT OR IGNORE INTO judgments
            (cnr, case_title, court, judge, reg_date, decision_date,
             disposal_nature, pdf_path, search_term, source, downloaded, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        await db.commit()


async def check_existing_cnrs(cnr_list, search_term="", source="ecourts"):
    if not cnr_list:
        return 0
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" * len(cnr_list))
        query = f"SELECT COUNT(*) FROM judgments WHERE search_term = ? AND source = ? AND cnr IN ({placeholders})"
        args = [search_term, source] + cnr_list
        async with db.execute(query, args) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def mark_downloaded(cnr, file_size, search_term=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE judgments SET downloaded = 1, file_size = ?
            WHERE cnr = ? AND search_term = ?
        """, (file_size, cnr, search_term))
        await db.commit()


async def get_undownloaded(search_term="", limit=100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM judgments
            WHERE downloaded = 0 AND search_term = ?
            LIMIT ?
        """, (search_term, limit)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_all_judgments(search_term="", limit=None, offset=0, source=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM judgments WHERE search_term = ?"
        args = [search_term]
        if source:
            sql += " AND source = ?"
            args.append(source)
        if limit:
            sql += " LIMIT ? OFFSET ?"
            args.extend([limit, offset])
        async with db.execute(sql, args) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_judgment_by_cnr(cnr):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM judgments WHERE cnr = ?", (cnr,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_search(search_term, mode, court, total_results=0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO searches (search_term, mode, court, total_results, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(search_term) DO UPDATE SET
                mode = excluded.mode,
                court = excluded.court,
                total_results = COALESCE(excluded.total_results, searches.total_results)
        """, (search_term, mode, court, total_results, datetime.utcnow().isoformat()))
        await db.commit()


async def get_search(search_term):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM searches WHERE search_term = ?", (search_term,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def increment_pages_fetched(search_term):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE searches SET pages_fetched = pages_fetched + 1
            WHERE search_term = ?
        """, (search_term,))
        await db.commit()


async def log_download(cnr, pdf_path, search_term, success, file_size=0, session_cnr=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO download_log
            (cnr, pdf_path, search_term, downloaded_at, success, file_size, session_cnr)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cnr, pdf_path, search_term, datetime.utcnow().isoformat(),
              1 if success else 0, file_size, session_cnr))
        await db.commit()



async def export_to_csv(search_term, out_path, source=None):
    rows = await get_all_judgments(search_term, source=source)
    if not rows:
        return None
    
    if source == "scr":
        # SCR does not have court or reg_date
        headers = ["citation", "case_title", "judge", "decision_date", 
                   "disposal_nature", "pdf_path", "source", "downloaded"]
        for r in rows:
            r["citation"] = r.pop("cnr", "")
    else:
        headers = ["cnr", "case_title", "court", "judge", "reg_date",
                   "decision_date", "disposal_nature", "pdf_path",
                   "source", "downloaded"]
                   
    import csv
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return out_path


async def get_stats(search_term=""):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT downloaded, COUNT(*) as count FROM judgments"
        args = []
        if search_term is not None:
            sql += " WHERE search_term = ?"
            args.append(search_term)
        sql += " GROUP BY downloaded"
        async with db.execute(sql, args) as cur:
            rows = await cur.fetchall()
            total = sum(r["count"] for r in rows)
            downloaded = next((r["count"] for r in rows if r["downloaded"] == 1), 0)
            return {"total": total, "downloaded": downloaded, "pending": total - downloaded}