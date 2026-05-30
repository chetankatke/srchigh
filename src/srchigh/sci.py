"""
SCISession — async session with SCI judgment-date portal (WordPress + securimage-wp).
Handles captcha solving, date-range search, case details, and PDF download.
"""

import io
import json
import re
import asyncio
from collections import Counter
from datetime import date, timedelta
from urllib.parse import urljoin

import httpx
from PIL import Image, ImageFilter
import pytesseract

from .config import USER_AGENT
from .parser import parse_entry

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


def _parse_sci_date(d_str):
    """Parse DD-MM-YYYY string to date object."""
    parts = d_str.split("-")
    return date(int(parts[2]), int(parts[1]), int(parts[0]))


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

    def _render_captcha_ascii(self, img, width=60):
        """Render a captcha image as ASCII art for debugging."""
        try:
            resample = Image.Resampling.BILINEAR
        except AttributeError:
            resample = Image.BILINEAR
        w, h = img.size
        aspect = h / w
        height = max(1, int(width * aspect * 0.5))
        img_small = img.resize((width, height), resample)
        ramp = "█▓▒░:  "
        lines = []
        for y in range(height):
            row = []
            for x in range(width):
                v = img_small.getpixel((x, y))
                if isinstance(v, tuple):
                    v = int(0.299 * v[0] + 0.587 * v[1] + 0.114 * v[2])
                idx = max(0, min(int(v * (len(ramp) - 1) / 255.0), len(ramp) - 1))
                row.append(ramp[idx])
            lines.append("    \033[90m│\033[0m" + "".join(row) + "\033[90m│\033[0m")
        border = "    \033[90m┌" + "─" * width + "┐\033[0m"
        bottom = "    \033[90m└" + "─" * width + "┘\033[0m"
        return border + "\n" + "\n".join(lines) + "\n" + bottom

    def _solve_math_captcha(self, ocr_text):
        """Parse a math expression from OCR and return the computed answer, or None.

        Handles formats like '25+17', '25 + 17', '25+17=', and '25+17=?'.
        """
        # Strip trailing garbage (=, ?, spaces, non-alphanumeric)
        clean = ocr_text.strip().rstrip("=? \t")
        # Try to match: digits operator digits
        m = re.match(r'(\d+)\s*([+-])\s*(\d+)', clean)
        if not m:
            return None
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        if op == '+':
            return str(a + b)
        elif op == '-':
            return str(a - b) if a >= b else None
        return None

    async def solve_captcha(self, max_tries=30):
        """Download and solve the securimage-wp **math** captcha.
        
        The SCI site uses Securimage in math mode — the image shows an arithmetic
        expression like '25+17' and the answer is the computed number.
        """
        for attempt in range(1, max_tries + 1):
            url = CAPTCHA_URL + self.scid
            print(f"\n\033[1;36m┌── Captcha Attempt {attempt}/{max_tries} ──────────────────────────────────────┐\033[0m", flush=True)
            try:
                cr = await self._get(url)
                img = Image.open(io.BytesIO(cr.content)).convert("L")
            except Exception as e:
                print(f"    \033[1;31mError fetching captcha: {e}\033[0m", flush=True)
                if attempt % 5 == 0:
                    await self.fresh()
                continue

            # Upscale + denoise
            enhanced = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
            enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))

            # Try multiple OCR configurations to read the math expression
            candidates = {}  # answer -> (source_key, count)
            raw_reads = []  # (source_key, raw_text) for diagnosis
            for src_label, src_img in [("enhanced", enhanced), ("original", img)]:
                for psm in (7, 6, 13, 8):
                    for thresh in range(80, 201, 10):
                        bw = src_img.point(lambda x, t=thresh: 0 if x < t else 255)
                        text = pytesseract.image_to_string(
                            bw,
                            config="--psm %d -c tessedit_char_whitelist="
                                   "0123456789+-=" % psm,
                        ).strip()
                        text = re.sub(r'[^0-9+=]', '', text)
                        if text:
                            raw_reads.append(("%s-psm%d" % (src_label, psm), text))
                        answer = self._solve_math_captcha(text)
                        if answer is not None:
                            key = "%s-psm%d-%d" % (src_label, psm, thresh)
                            candidates[key] = answer

            if not candidates:
                print("    \033[1;31mCould not parse math expression.\033[0m", flush=True)
                # Show first 10 raw OCR outputs for diagnosis
                seen = set()
                shown = 0
                for src, txt in raw_reads:
                    if txt not in seen and shown < 10:
                        print(f"      {src}: \033[90m'{txt}'\033[0m", flush=True)
                        seen.add(txt)
                        shown += 1
                print("    \033[1;31mCould not parse math expression (all OCR attempts failed).\033[0m", flush=True)
                if attempt % 5 == 0:
                    await self.fresh()
                continue

            # Use the most common answer among all successful reads
            answer_counts = Counter(candidates.values())
            best_answer = answer_counts.most_common(1)[0][0]
            best_count = answer_counts.most_common(1)[0][1]

            # Show the raw OCR texts that produced this answer
            raw_examples = set()
            for src, txt in raw_reads:
                ans = self._solve_math_captcha(txt)
                if ans == best_answer:
                    raw_examples.add(txt)
            print(f"    \033[1;32mMath captcha solved: '{best_answer}' ({best_count}/{len(candidates)} reads agree)\033[0m", flush=True)
            for r in sorted(raw_examples)[:3]:
                print(f"      raw OCR: \033[90m'{r}'\033[0m", flush=True)
            print("\033[1;36m└──────────────────────────────────────────────────────────────────┘\033[0m", flush=True)
            self.captcha_text = best_answer
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
        }
        r = await self._get(AJAX_URL, params=params)
        try:
            j = json.loads(r.text)
        except json.JSONDecodeError:
            return [], True

        if not j.get("success"):
            return [], False  # captcha rejected

        html = j.get("data", "")
        if isinstance(html, dict):
            html = html.get("resultsHtml", "")

        entries = self._parse_results_table(html)
        return entries, True

    def _parse_results_table(self, html):
        """Parse the results HTML table into judgment dicts."""
        entries = []
        # Find each table row with data-diary-no and data-diary-year
        for m in re.finditer(
            r'<tr[^>]*data-diary-no="(\d+)"[^>]*data-diary-year="(\d+)"[^>]*>'
            r'(.*?)</tr>',
            html, re.IGNORECASE | re.DOTALL
        ):
            diary_no = m.group(1)
            diary_year = m.group(2)
            row_html = m.group(3)

            # Extract text from table cells (td)
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
            entry = {
                "diary_no": diary_no,
                "diary_year": diary_year,
            }
            if len(cells) >= 1:
                entry["decision_date"] = re.sub(r'<[^>]+>', '', cells[0]).strip()
            if len(cells) >= 2:
                entry["case_no"] = re.sub(r'<[^>]+>', '', cells[1]).strip()
            if len(cells) >= 3:
                entry["judge"] = re.sub(r'<[^>]+>', '', cells[2]).strip()
            if len(cells) >= 4:
                entry["case_title"] = re.sub(r'<[^>]+>', '', cells[3]).strip()
            if len(cells) >= 5:
                entry["free_text"] = re.sub(r'<[^>]+>', '', cells[4]).strip()
            entries.append(entry)
        return entries

    async def get_case_details(self, diary_no, diary_year):
        """Fetch case details HTML which contains the PDF download link."""
        params = {
            "action": "get_case_details",
            "diary_no": diary_no,
            "diary_year": diary_year,
            "es_ajax_request": "1",
            "language": "en",
        }
        r = await self._get(AJAX_URL, params=params)
        try:
            j = json.loads(r.text)
        except json.JSONDecodeError:
            return None
        if not j.get("success"):
            return None
        return j.get("data", "")

    def _extract_pdf_url(self, details_html):
        """Extract PDF download URL from case details HTML."""
        if not details_html:
            return None
        # Look for direct PDF links
        m = re.search(r'href="([^"]+\.pdf[^"]*)"', details_html, re.IGNORECASE)
        if m:
            url = m.group(1)
            if url.startswith("http"):
                return url
            return urljoin(SCI_BASE, url)
        # Look for download links with onclick or data attributes
        m = re.search(r'data-url="([^"]+)"', details_html)
        if m:
            return urljoin(SCI_BASE, m.group(1))
        return None

    async def download_pdf(self, url, filepath):
        """Download a PDF and return file size, or 0 on failure."""
        try:
            r = await self.client.get(url, timeout=60.0)
            if r.status_code == 200:
                ct = r.headers.get("Content-Type", "").lower()
                if "pdf" in ct or len(r.content) > 1000:
                    import os as _os
                    _os.makedirs(_os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "wb") as f:
                        f.write(r.content)
                    return len(r.content)
        except Exception:
            pass
        return 0

    async def close(self):
        await self.client.aclose()
