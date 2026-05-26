"""
Integration tests for session.py — require network access to eCourts server.
Marked with @pytest.mark.network — skipped unless --network is passed.

Run:  python3 -m pytest tests/test_session.py -v --network
"""

import os
import pytest

pytestmark = pytest.mark.network


class TestSessionInit:
    """Verify a session can be established with the eCourts server."""

    @pytest.mark.asyncio
    async def test_homepage_loads(self):
        from srchigh.session import ECourtSession
        ec = ECourtSession()
        r = await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        assert r.status_code == 200
        assert "judgments" in r.text.lower()
        await ec.close()

    @pytest.mark.asyncio
    async def test_homepage_sets_cookie(self):
        from srchigh.session import ECourtSession
        ec = ECourtSession()
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        assert len(ec.client.cookies) > 0
        await ec.close()


class TestCaptchaSolving:
    """Captcha solving with OCR — may fail if OCR can't read the image."""

    @pytest.mark.asyncio
    async def test_solve_captcha_returns_token(self):
        from srchigh.session import ECourtSession
        ec = ECourtSession()
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            text, token = await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha via OCR")
        assert len(text) >= 4
        assert len(token) > 0
        await ec.close()

    @pytest.mark.asyncio
    async def test_captcha_validation_endpoint(self):
        """Hit checkCaptcha with a random guess — expect failure, not crash."""
        from srchigh.session import ECourtSession
        import json
        ec = ECourtSession()
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        r = await ec.client.post(
            "https://judgments.ecourts.gov.in/pdfsearch/?p=pdf_search/checkCaptcha",
            data={
                "captcha": "AAAA",
                "search_text": "test",
                "search_opt": "PHRASE",
                "fcourt_type": "2",
                "ajax_req": "true",
                "app_token": "",
            },
        )
        assert r.status_code == 200
        j = json.loads(r.text)
        assert "captcha_status" in j
        assert j["captcha_status"] == "N"
        await ec.close()


class TestSearch:
    """Full search flow — requires solved captcha."""

    @pytest.fixture(scope="class")
    def ec(self):
        from srchigh.session import ECourtSession
        ec = ECourtSession()
        return ec

    @pytest.mark.asyncio
    async def test_results_page_loads(self, ec):
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha for search test")
        await ec.load_results_page("test")
        assert len(ec.app_token) > 0
        await ec.close()

    @pytest.mark.asyncio
    async def test_get_results_returns_entries(self, ec):
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha for search test")
        await ec.load_results_page("test")
        for _ in range(3):
            await ec.get_results("test", page=0, page_size=5)
        entries, total = await ec.get_results("test", page=0, page_size=5)
        assert len(entries) > 0
        assert total > 0
        await ec.close()

    @pytest.mark.asyncio
    async def test_get_results_parsed_entries_have_cnr(self, ec):
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha")
        await ec.load_results_page("test")
        for _ in range(3):
            await ec.get_results("test", page=0, page_size=5)
        entries, _ = await ec.get_results("test", page=0, page_size=5)
        for e in entries[:3]:
            assert e.get("cnr", "") != ""
        await ec.close()

    @pytest.mark.asyncio
    async def test_get_results_count_matches_page_size(self, ec):
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha")
        await ec.load_results_page("test")
        for _ in range(3):
            await ec.get_results("test", page=0, page_size=3)
        entries, _ = await ec.get_results("test", page=0, page_size=3)
        assert len(entries) == 3
        await ec.close()

    @pytest.mark.asyncio
    async def test_pagination_returns_different_results(self, ec):
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha")
        await ec.load_results_page("test")
        for _ in range(3):
            await ec.get_results("test", page=0, page_size=5)
        page0, _ = await ec.get_results("test", page=0, page_size=5)
        page1, _ = await ec.get_results("test", page=1, page_size=5)
        cnrs0 = [e.get("cnr", "") for e in page0]
        cnrs1 = [e.get("cnr", "") for e in page1]
        assert cnrs0 != cnrs1
        await ec.close()


class TestPdfDownload:
    """PDF download — requires solved captcha and search results."""

    @pytest.fixture(scope="class")
    def ec(self):
        from srchigh.session import ECourtSession
        ec = ECourtSession()
        return ec

    @pytest.mark.asyncio
    async def test_get_pdf_url_returns_url(self, ec):
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha")
        await ec.load_results_page("test")
        for _ in range(4):
            await ec.get_results("test", page=0, page_size=5)
        entries, _ = await ec.get_results("test", page=0, page_size=5)
        if not entries:
            pytest.skip("No results to test PDF download")
        url = await ec.get_pdf_url(entries[0])
        assert url is not None
        assert url.startswith("https://judgments.ecourts.gov.in")
        await ec.close()

    @pytest.mark.asyncio
    async def test_download_pdf_returns_bytes(self, ec):
        import tempfile
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha")
        await ec.load_results_page("test")
        for _ in range(4):
            await ec.get_results("test", page=0, page_size=5)
        entries, _ = await ec.get_results("test", page=0, page_size=5)
        if not entries:
            pytest.skip("No results to test PDF download")
        url = await ec.get_pdf_url(entries[0])
        if not url:
            pytest.skip("Could not get PDF URL")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            size = await ec.download_pdf(url, tmp.name)
            assert size > 1000
            with open(tmp.name, "rb") as f:
                header = f.read(5)
            assert header == b"%PDF-"
            os.unlink(tmp.name)
        await ec.close()

    @pytest.mark.asyncio
    async def test_get_pdf_url_for_path_works(self, ec):
        await ec.client.get("https://judgments.ecourts.gov.in/pdfsearch/")
        try:
            await ec.solve_captcha(search_text="test", max_tries=10)
        except RuntimeError:
            pytest.skip("Could not solve captcha")
        await ec.load_results_page("test")
        for _ in range(4):
            await ec.get_results("test", page=0, page_size=5)
        entries, _ = await ec.get_results("test", page=0, page_size=5)
        if not entries or not entries[0].get("path"):
            pytest.skip("No path to test")
        url = await ec.get_pdf_url_for_path(entries[0]["path"])
        assert url is not None
        assert "judgments.ecourts.gov.in" in url
        await ec.close()