"""
SCISession — async session with SCI judgment-date portal (WordPress + securimage-wp).
Handles captcha solving, date-range search, case details, and PDF download.
"""

import json
import logging
import re
import asyncio
from datetime import date, timedelta
from urllib.parse import urljoin

import httpx
import ddddocr

from .config import USER_AGENT
from .parser import parse_entry

log = logging.getLogger(__name__)

SCI_BASE = "https://www.sci.gov.in"
AJAX_URL = SCI_BASE + "/wp-admin/admin-ajax.php"
CAPTCHA_URL = SCI_BASE + "/?_siwp_captcha&id="
MAX_DATE_RANGE = 30  # days, enforced by server

CHROME_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}


def _split_date_range(from_date, to_date):
    """Split (date, date) into list of (date, date) chunks each ≤ MAX_DATE_RANGE days."""
    chunks = []
    cur = from_date
    while cur <= to_date:
        chunk_end = min(cur + timedelta(days=MAX_DATE_RANGE - 1), to_date)
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_sci_date(d_str):
    """Parse date string to date object. Handles DD-MM-YYYY and DD-Mon-YYYY."""
    parts = d_str.split("-")
    if len(parts) != 3:
        return None
    day, month_str, year = int(parts[0]), parts[1].lower(), int(parts[2])
    # Try numeric month first, then named month
    if month_str.isdigit():
        month = int(month_str)
    else:
        month = _MONTH_MAP.get(month_str[:3])
    if month is None:
        return None
    return date(year, month, day)


def _fmt_date(d):
    """Format date object as DD-MM-YYYY."""
    return d.strftime("%d-%m-%Y")


def _month_range(year, month):
    """Return (first_day, last_day) for a given year/month."""
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


class SCISession:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0, headers=dict(CHROME_HEADERS))
        self.scid = ""
        self.tok_name = ""
        self.tok_value = ""
        self.captcha_text = ""

    async def _get(self, url, **kwargs):
        return await self.client.get(url, **kwargs)

    async def _post(self, url, data=None, **kwargs):
        return await self.client.post(url, data=data, **kwargs)

    async def fresh(self):
        """Create fresh httpx client and fetch new captcha tokens."""
        await self.client.aclose()
        self.client = httpx.AsyncClient(timeout=30.0, headers=dict(CHROME_HEADERS))
        self.scid = ""
        self.tok_name = ""
        self.tok_value = ""
        self.captcha_text = ""
        await self.fetch_homepage()

    async def fetch_homepage(self):
        """Fetch the judgment-date page and extract captcha tokens."""
        r = await self._get(SCI_BASE + "/judgements-judgement-date/")
        html = r.text
        # Extract scid
        m = re.search(r'name="scid"\s+value="([^"]+)"', html)
        if m:
            self.scid = m.group(1)
        # Extract tok_* name and value
        m = re.search(r'name="(tok_[^"]+)"\s+value="([^"]+)"', html)
        if m:
            self.tok_name = m.group(1)
            self.tok_value = m.group(2)
        return html

    def _solve_math_captcha(self, ocr_text):
        """Parse a math expression from ddddocr and return the computed answer.

        Format is 'NUM+NUM' or 'NUM-NUM' with numbers 1-10.
        """
        import random
        ocr_text = ocr_text.strip()
        m = re.match(r'^(\d+)\s*([+-])\s*(\d+)$', ocr_text)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            if op == '+':
                return str(a + b)
            elif op == '-':
                return str(a - b) if a > b else None
            return None

        # Fallback: ddddocr often misses the operator entirely.
        nums = re.findall(r'\d+', ocr_text)
        if len(nums) == 1 and len(nums[0]) >= 2:
            s = nums[0]
            if s.startswith('10') and len(s) > 2:
                a, b = 10, int(s[2:])
            else:
                a, b = int(s[0]), int(s[1:])
        elif len(nums) >= 2:
            a, b = int(nums[0]), int(nums[1])
        else:
            return None

        if not (1 <= a <= 10 and 1 <= b <= 10):
            return None

        op = random.choice(['+', '-'])
        # if a <= b, '-' would be zero or negative, so must be '+'
        if op == '-' and a <= b:
            op = '+'

        return str(a + b) if op == '+' else str(a - b)

    async def solve_captcha(self, max_tries=30):
        """Download and solve the securimage-wp math captcha using ddddocr."""
        ocr = ddddocr.DdddOcr(show_ad=False)
        for attempt in range(1, max_tries + 1):
            url = CAPTCHA_URL + self.scid
            print(f"\n\033[1;36m┌── Captcha Attempt {attempt}/{max_tries} ──────────────────────────────────────┐\033[0m", flush=True)
            try:
                cr = await self._get(url)
            except Exception as e:
                print(f"    \033[1;31mError fetching captcha: {e}\033[0m", flush=True)
                if attempt % 5 == 0:
                    await self.fresh()
                continue

            # ddddocr reads the captcha directly from raw bytes — no PIL needed
            result = ocr.classification(cr.content)
            answer = self._solve_math_captcha(result)

            if answer is None:
                print(f"    ddddocr read: \033[90m'{result}'\033[0m (could not parse)", flush=True)
                if attempt % 5 == 0:
                    await self.fresh()
                continue

            print(f"    \033[1;32mMath captcha solved: '{result}' = {answer}\033[0m", flush=True)
            print("\033[1;36m└──────────────────────────────────────────────────────────────────┘\033[0m", flush=True)
            self.captcha_text = answer
            return self.captcha_text

        raise RuntimeError("Failed to solve captcha after %d tries" % max_tries)

    async def search(self, from_date, to_date):
        """Search judgments for a date range.
        Returns (entries_list, captcha_ok) where captcha_ok=False means
        the captcha was rejected (retry with fresh tokens).
        """
        params = {
            "action": "get_judgements_judgement_date",
            "from_date": _fmt_date(from_date),
            "to_date": _fmt_date(to_date),
            "siwp_captcha_value": self.captcha_text,
            "scid": self.scid,
            self.tok_name: self.tok_value,
            "language": "en",
            "es_ajax_request": "1",
        }
        r = await self._get(AJAX_URL, params=params)
        try:
            j = json.loads(r.text)
        except json.JSONDecodeError:
            log.error("    Raw response (not JSON): %s" % r.text[:300])
            return [], True

        if not j.get("success"):
            err_data = j.get("data", "")
            if isinstance(err_data, str):
                try:
                    err_data_json = json.loads(err_data)
                    err_msg = err_data_json.get("message", err_data[:200])
                except (json.JSONDecodeError, AttributeError):
                    err_msg = err_data[:200]
            else:
                err_msg = str(err_data)[:200]
            log.error("    Server rejected: %s" % err_msg)
            log.error("    Full response: %s" % json.dumps(j)[:500])
            return [], False  # captcha rejected

        html = j.get("data", "")
        if isinstance(html, dict):
            html = html.get("resultsHtml", "")

        entries = self._parse_results_table(html)
        if html and not entries:
            log.info("    Raw response (first 800): %s..." % html[:800])
        log.info("    Found %d entries in response" % len(entries))
        return entries, True

    def _parse_results_table(self, html):
        """Parse the results HTML table into judgment dicts, extracting PDF URLs."""
        entries = []
        for m in re.finditer(
            r'<tr[^>]*data-diary-no="([^"]+)"[^>]*>(.*?)</tr>',
            html, re.IGNORECASE | re.DOTALL
        ):
            diary_no = m.group(1)
            diary_year = diary_no.split("/")[-1] if "/" in diary_no else ""
            row_html = m.group(2)
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)

            entry = {"diary_no": diary_no, "diary_year": diary_year}

            # Column mapping from actual HTML:
            # 0=Serial No, 1=Diary Number, 2=Case Number, 3=Petitioner/Respondent,
            # 4=Advocate, 5=Bench, 6=Judgment By, 7=Judgment (has PDF links)
            if len(cells) >= 2:
                entry["case_no"] = re.sub(r'<[^>]+>', '', cells[2]).strip()
            if len(cells) >= 4:
                entry["case_title"] = re.sub(r'<[^>]+>', '', cells[3]).strip()
            if len(cells) >= 6:
                entry["judge"] = re.sub(r'<[^>]+>', '', cells[5]).strip()
            # Extract PDF URL from the Judgment column (last cell)
            if len(cells) >= 8:
                pdf_m = re.search(r'href="([^"]+\.pdf)"', cells[7])
                if pdf_m:
                    entry["pdf_url"] = pdf_m.group(1)
            entries.append(entry)
        return entries

    async def download_pdf(self, url, filepath):
        """Download a PDF and return file size, or 0 on failure."""
        import os as _os
        from tqdm import tqdm
        try:
            async with self.client.stream("GET", url, timeout=60.0) as r:
                if r.status_code == 200:
                    ct = r.headers.get("Content-Type", "").lower()
                    total_size = int(r.headers.get("Content-Length", 0))
                    
                    _os.makedirs(_os.path.dirname(filepath), exist_ok=True)
                    
                    downloaded = 0
                    with open(filepath, "wb") as f, tqdm(
                        desc=_os.path.basename(filepath),
                        total=total_size if total_size > 0 else None,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        leave=False
                    ) as pbar:
                        async for chunk in r.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            pbar.update(len(chunk))
                            
                    if "pdf" in ct or downloaded > 1000:
                        return downloaded
                    else:
                        try:
                            _os.remove(filepath)
                        except OSError:
                            pass
        except Exception:
            pass
        return 0

    async def close(self):
        await self.client.aclose()
