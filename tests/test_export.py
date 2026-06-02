"""Unit tests for db.py — async DB operations."""

import os
import sys
import asyncio
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from srchigh import db


@pytest.fixture
def sample_entries():
    return [
        {
            "cnr": "HCBM0000001",
            "case_title": "Case A vs State",
            "court": "Bombay High Court",
            "judge": "JUSTICE X",
            "reg_date": "01-01-2024",
            "decision_date": "15-06-2024",
            "disposal_nature": "DISMISSED",
            "path": "court/orders/HCBM0000001.pdf",
        },
        {
            "cnr": "DLHC0000002",
            "case_title": "Case B vs Union",
            "court": "Delhi High Court",
            "judge": "JUSTICE Y",
            "reg_date": "05-03-2024",
            "decision_date": "20-08-2024",
            "disposal_nature": "ALLOWED",
            "path": "court/orders/DLHC0000002.pdf",
        },
    ]


class TestDbInit:
    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            async with db.aiosqlite.connect(db.DB_PATH) as conn:
                async with conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ) as cur:
                    tables = [r[0] for r in await cur.fetchall()]
            assert "judgments" in tables
            assert "searches" in tables
            assert "download_log" in tables
        finally:
            db.DB_PATH = old_path


class TestInsertJudgments:
    @pytest.mark.asyncio
    async def test_insert_single_judgment(self, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            entry = {
                "cnr": "TEST001",
                "case_title": "Test Case",
                "court": "Bombay HC",
                "judge": "JUSTICE Z",
                "reg_date": "01-01-2024",
                "decision_date": "15-06-2024",
                "disposal_nature": "DISMISSED",
                "path": "orders/test.pdf",
            }
            await db.insert_judgment(entry, "test_search")
            rows = await db.get_all_judgments("test_search")
            assert len(rows) == 1
            assert rows[0]["cnr"] == "TEST001"
        finally:
            db.DB_PATH = old_path

    @pytest.mark.asyncio
    async def test_insert_batch(self, sample_entries, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.insert_judgments_batch(sample_entries, "batch_test")
            rows = await db.get_all_judgments("batch_test")
            assert len(rows) == 2
        finally:
            db.DB_PATH = old_path

    @pytest.mark.asyncio
    async def test_duplicate_cnr_skipped(self, sample_entries, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.insert_judgments_batch(sample_entries, "dup_test")
            await db.insert_judgments_batch([sample_entries[0]], "dup_test")
            rows = await db.get_all_judgments("dup_test")
            assert len(rows) == 2
        finally:
            db.DB_PATH = old_path


class TestMarkDownloaded:
    @pytest.mark.asyncio
    async def test_mark_downloaded(self, sample_entries, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.insert_judgments_batch(sample_entries, "dl_test")
            await db.mark_downloaded("HCBM0000001", 12345, "dl_test")
            stats = await db.get_stats("dl_test")
            assert stats["downloaded"] == 1
            assert stats["pending"] == 1
        finally:
            db.DB_PATH = old_path


class TestGetUndownloaded:
    @pytest.mark.asyncio
    async def test_get_undownloaded(self, sample_entries, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.insert_judgments_batch(sample_entries, "pending_test")
            await db.mark_downloaded("HCBM0000001", 100, "pending_test")
            undl = await db.get_undownloaded("pending_test")
            assert len(undl) == 1
            assert undl[0]["cnr"] == "DLHC0000002"
        finally:
            db.DB_PATH = old_path


class TestExportToCsv:
    @pytest.mark.asyncio
    async def test_export_to_csv(self, sample_entries, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.insert_judgments_batch(sample_entries, "csv_test")
            out_path = str(tmp_path / "results.csv")
            result = await db.export_to_csv("csv_test", out_path)
            assert result == out_path
            with open(out_path) as f:
                content = f.read()
            assert "HCBM0000001" in content
            assert "DLHC0000002" in content
        finally:
            db.DB_PATH = old_path

    @pytest.mark.asyncio
    async def test_export_empty(self, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            out_path = str(tmp_path / "empty.csv")
            result = await db.export_to_csv("nonexistent", out_path)
            assert result is None
        finally:
            db.DB_PATH = old_path




class TestStats:
    @pytest.mark.asyncio
    async def test_stats_all_zeros(self, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            stats = await db.get_stats("nonexistent")
            assert stats["total"] == 0
            assert stats["downloaded"] == 0
            assert stats["pending"] == 0
        finally:
            db.DB_PATH = old_path

    @pytest.mark.asyncio
    async def test_stats_mixed(self, sample_entries, tmp_path):
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.insert_judgments_batch(sample_entries, "stats_test")
            await db.mark_downloaded("HCBM0000001", 100, "stats_test")
            stats = await db.get_stats("stats_test")
            assert stats["total"] == 2
            assert stats["downloaded"] == 1
            assert stats["pending"] == 1
        finally:
            db.DB_PATH = old_path


class TestTimestampIsTimezoneAware:
    """Regression tests for the datetime.utcnow() deprecation fix.

    Inserted rows, upserted searches, and download_log entries must all
    store timezone-aware ISO 8601 timestamps.
    """

    @pytest.mark.asyncio
    async def test_insert_judgment_writes_iso_with_utc_suffix(self, tmp_path):
        from datetime import datetime
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.insert_judgment(
                {"cnr": "TS001", "case_title": "X", "path": "p.pdf"},
                "ts_test",
            )
            rows = await db.get_all_judgments("ts_test")
            created_at = rows[0]["created_at"]
            # Should be parseable as ISO with timezone (Z or +00:00)
            parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            assert parsed.tzinfo is not None, f"Expected tz-aware, got {created_at!r}"
            assert 2020 < parsed.year < 2100
        finally:
            db.DB_PATH = old_path

    @pytest.mark.asyncio
    async def test_upsert_search_writes_iso_with_utc_suffix(self, tmp_path):
        from datetime import datetime
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.upsert_search("term1", "PHRASE", "bombay", 100)
            row = await db.get_search("term1")
            parsed = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            assert parsed.tzinfo is not None, f"Expected tz-aware, got {row['created_at']!r}"
        finally:
            db.DB_PATH = old_path

    @pytest.mark.asyncio
    async def test_log_download_writes_iso_with_utc_suffix(self, tmp_path):
        from datetime import datetime
        old_path = db.DB_PATH
        db.DB_PATH = str(tmp_path / "test.db")
        try:
            await db.init_db()
            await db.log_download("CNR1", "p.pdf", "term1", True, 1024)
            async with db.aiosqlite.connect(db.DB_PATH) as conn:
                async with conn.execute("SELECT downloaded_at FROM download_log") as cur:
                    row = await cur.fetchone()
            parsed = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
            assert parsed.tzinfo is not None, f"Expected tz-aware, got {row[0]!r}"
        finally:
            db.DB_PATH = old_path