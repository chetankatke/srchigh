"""Tests for download.py — the batch download orchestrator."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from srchigh import download as dl


class TestDownloadConcurrency:
    """The download_from_db function should actually run downloads in parallel.

    Regression test for the 'fake concurrency' bug — the original code declared
    MAX_CONCURRENT=5 with an asyncio.Semaphore but used a serial `for` loop,
    so parallelism was always 1. Real concurrency requires asyncio.gather.
    """

    @pytest.mark.asyncio
    async def test_multiple_entries_download_in_parallel(self, tmp_path, monkeypatch):
        in_flight = 0
        max_in_flight = 0
        lock = asyncio.Lock()

        async def fake_download_pdf(url, filepath):
            nonlocal in_flight, max_in_flight
            async with lock:
                in_flight += 1
                if in_flight > max_in_flight:
                    max_in_flight = in_flight
            await asyncio.sleep(0.05)
            async with lock:
                in_flight -= 1
            with open(filepath, "wb") as f:
                f.write(b"%PDF-1.4 fake")
            return 2000

        async def fake_get_pdf_url(entry):
            return "http://example.com/" + entry.get("cnr", "") + ".pdf"

        mock_session = MagicMock()
        mock_session.get_pdf_url = fake_get_pdf_url
        mock_session.download_pdf = fake_download_pdf
        mock_session.solve_captcha = AsyncMock(return_value=("aaaa", "tok"))
        mock_session.client = MagicMock()
        mock_session.client.get = AsyncMock(return_value=MagicMock(text=""))
        mock_session.base_url = "http://example.com/"
        mock_session.fcourt_type = "2"
        mock_session.close = AsyncMock()
        mock_session.fresh = AsyncMock()
        mock_session.load_results_page = AsyncMock()
        mock_session.get_results = AsyncMock(return_value=([], 0))

        monkeypatch.setattr(dl, "ECourtSession", lambda **kw: mock_session)

        async def fake_get_undownloaded(search_term, limit=100):
            return [
                {"cnr": f"CNR{i:03d}", "pdf_path": f"p{i}.pdf", "search_term": "t"}
                for i in range(10)
            ]
        monkeypatch.setattr(dl.db, "get_undownloaded", fake_get_undownloaded)
        monkeypatch.setattr(dl.db, "mark_downloaded", AsyncMock())
        monkeypatch.setattr(dl.db, "log_download", AsyncMock())
        monkeypatch.setattr(dl.db, "init_db", AsyncMock())

        out_dir = str(tmp_path / "dl_out")
        stats = await dl.download_from_db(search_term="t", out_dir=out_dir)

        assert max_in_flight > 1, (
            f"Expected parallel downloads (max_in_flight > 1), got {max_in_flight}. "
            "download.py still has the fake-concurrency bug."
        )
        assert stats["downloaded"] == 10


class TestDownloadFiltersExisting:
    """download_from_db should skip PDFs already on disk."""

    @pytest.mark.asyncio
    async def test_skips_existing_pdfs(self, tmp_path, monkeypatch):
        # Pre-create some "existing" PDFs in the output dir
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "CNR000.pdf").write_bytes(b"%PDF-1.4 existing")
        (out_dir / "CNR001.pdf").write_bytes(b"%PDF-1.4 existing")

        async def fake_get_pdf_url(entry):
            return "http://example.com/" + entry.get("cnr", "") + ".pdf"

        # CNR000 and CNR001 were pre-existing — download_pdf should NOT be called
        # for them. CNR002 wasn't, so it WOULD have been called (and is allowed).
        called_for = []

        async def fake_download_pdf(url, filepath):
            called_for.append(filepath)
            with open(filepath, "wb") as f:
                f.write(b"%PDF-1.4 fake")
            return 2000

        mock_session = MagicMock()
        mock_session.get_pdf_url = fake_get_pdf_url
        mock_session.download_pdf = fake_download_pdf
        mock_session.solve_captcha = AsyncMock(return_value=("aaaa", "tok"))
        mock_session.client = MagicMock()
        mock_session.client.get = AsyncMock(return_value=MagicMock(text=""))
        mock_session.base_url = "http://example.com/"
        mock_session.fcourt_type = "2"
        mock_session.close = AsyncMock()
        mock_session.load_results_page = AsyncMock()
        mock_session.get_results = AsyncMock(return_value=([], 0))

        monkeypatch.setattr(dl, "ECourtSession", lambda **kw: mock_session)

        async def fake_get_undownloaded(search_term, limit=100):
            return [
                {"cnr": "CNR000", "pdf_path": "p0.pdf", "search_term": "t"},
                {"cnr": "CNR001", "pdf_path": "p1.pdf", "search_term": "t"},
                {"cnr": "CNR002", "pdf_path": "p2.pdf", "search_term": "t"},
            ]
        monkeypatch.setattr(dl.db, "get_undownloaded", fake_get_undownloaded)
        monkeypatch.setattr(dl.db, "mark_downloaded", AsyncMock())
        monkeypatch.setattr(dl.db, "log_download", AsyncMock())
        monkeypatch.setattr(dl.db, "init_db", AsyncMock())

        stats = await dl.download_from_db(search_term="t", out_dir=str(out_dir))
        # download_from_db pre-filters out CNRs that have existing files in
        # the output dir (see the `already` set check). So download_pdf is
        # only called for the one new file.
        assert len(called_for) == 1
        assert "CNR002.pdf" in called_for[0]
