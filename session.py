"""
ECourtSession — handles all interactions with the eCourts server:
session management, captcha solving, search, and PDF download.

Uses requests.Session with Chrome 120+ TLS fingerprint headers
for stealth. Optionally supports FetcherSession from Scrapling
if installed (better anti-bot evasion).
"""

import io
import json
import re
import time
import urllib.parse

import requests
from PIL import Image
import pytesseract

from config import BASE_URL, USER_AGENT
from parser import parse_entry, parse_results_page


# ── Try to use scrapling's FetcherSession for better stealth ──
try:
    from scrapling.fetchers import FetcherSession as _FetcherSession
    HAS_SCRAPLING = True
except ImportError:
    HAS_SCRAPLING = False


# ── Chrome 120+ realistic headers ──
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


class ECourtSession:
    """Manages one session with the eCourts PDF Search portal.
    
    Uses standard requests.Session by default, or Scrapling's FetcherSession
    if installed for better TLS fingerprinting and anti-bot evasion.
    """

    def __init__(self, use_scrapling=False):
        if use_scrapling and HAS_SCRAPLING:
            self.s = _FetcherSession(impersonate='chrome')
            self._scrapling = True
        else:
            self.s = requests.Session()
            self.s.headers.update(CHROME_HEADERS)
            self._scrapling = False
        self.app_token = ""
        self.captcha_text = ""

    # ── session lifecycle ──

    def fresh(self):
        """Replace the underlying session (new cookies, new token)."""
        if self._scrapling and HAS_SCRAPLING:
            self.s = _FetcherSession(impersonate='chrome')
        else:
            self.s = requests.Session()
            self.s.headers.update(CHROME_HEADERS)
        self.app_token = ""

    def _get(self, path, **kwargs):
        return self.s.get(BASE_URL + path, timeout=30, **kwargs)

    def _post(self, path, data=None, **kwargs):
        return self.s.post(BASE_URL + path, data=data, timeout=30, **kwargs)

    # ── captcha ──

    def solve_captcha(self, search_text="test", search_opt="PHRASE",
                      court_type="2", max_tries=30):
        """Fetch captcha image, OCR it, validate against server.
        Returns (captcha_text, app_token)."""
        for attempt in range(1, max_tries + 1):
            cr = self._get("vendor/securimage/securimage_show.php")
            img = Image.open(io.BytesIO(cr.content)).convert("L")

            guesses = set()
            for thresh in (110, 120, 130, 140, 150, 160, 170):
                bw = img.point(lambda x, t=thresh: 0 if x < t else 255)
                text = pytesseract.image_to_string(
                    bw,
                    config="--psm 8 -c tessedit_char_whitelist="
                           "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                           "abcdefghijklmnopqrstuvwxyz0123456789",
                ).strip()
                text = re.sub(r"[^a-zA-Z0-9]", "", text)
                if 4 <= len(text) <= 6:
                    guesses.add(text)

            if not guesses:
                continue

            for guess in sorted(guesses):
                try:
                    r = self._post("?p=pdf_search/checkCaptcha", data={
                        "captcha": guess,
                        "search_text": search_text,
                        "search_opt": search_opt,
                        "fcourt_type": court_type,
                        "ajax_req": "true",
                        "app_token": self.app_token,
                    })
                    j = json.loads(r.text)
                    if j.get("captcha_status") == "Y":
                        self.app_token = j.get("app_token", "")
                        self.captcha_text = guess
                        return guess, self.app_token
                except (json.JSONDecodeError, Exception):
                    pass

            if attempt % 5 == 0:
                self.fresh()

        raise RuntimeError("Failed to solve captcha after %d tries" % max_tries)

    # ── search ──

    def load_results_page(self, search_term, captcha=None, mode="PHRASE"):
        """GET the search results page (establishes server-side session state)."""
        c = captcha or self.captcha_text
        url = ("?p=pdf_search/home&text=" + urllib.parse.quote(search_term) +
               "&captcha=" + c + "&search_opt=" + mode +
               "&fcourt_type=2&app_token=" + self.app_token)
        r = self._get(url)
        m = re.search(r'app_token=([^"&\s<>]+)', r.text)
        if m:
            self.app_token = m.group(1)
        return r.text

    def get_results(self, search_term, page=0, page_size=25, mode="PHRASE",
                    state_code="", judge_name="", from_date="", to_date="",
                    proximity=""):
        """POST to the DataTable endpoint. Returns (entries_list, total_count)."""
        fields = [
            "state_code", "dist_code", "judge_name", "judge_arr",
            "act_txt", "section_txt", "case_no", "case_year", "pet_res",
            "from_date", "to_date", "disp_nature", "fulltext_case_type",
            "sel_lang", "citation_yr", "citation_vol", "citation_supl",
            "citation_page", "citation_keyword", "neu_cit_year", "neu_no",
            "case_no1", "case_year1", "pet_res1", "fulltext_case_type1",
        ]
        dt = {k: "" for k in fields}
        dt.update({
            "search_txt": "",
            "search_txt1": search_term,
            "search_opt": mode,
            "fcourt_type": "2",
            "state_code": state_code,
            "judge_name": judge_name,
            "from_date": from_date,
            "to_date": to_date,
            "proximity": proximity,
            "iDisplayStart": str(page * page_size),
            "iDisplayLength": str(page_size),
            "sEcho": "1",
            "flag": "",
            "ajax_req": "true",
            "app_token": self.app_token,
        })
        r = self._post("?p=pdf_search/home", data=dt)
        if r.status_code != 200:
            return [], 0
        try:
            j = json.loads(r.text)
        except json.JSONDecodeError:
            return [], 0
        if j.get("app_token"):
            self.app_token = j["app_token"]
        entries, total = parse_results_page(j)
        return entries, total

    # ── PDF download ──

    def get_pdf_url(self, entry):
        """Call openpdfcaptcha → returns temporary PDF download URL."""
        path = entry.get("path", "")
        val = entry.get("val", "0")
        for _ in range(2):
            r = self._post("?p=pdf_search/openpdfcaptcha", data={
                "val": val,
                "lang_flg": "",
                "path": path,
                "citation_year": entry.get("citation_year", ""),
                "fcourt_type": "2",
                "file_type": "",
                "nc_display": "",
                "ajax_req": "true",
                "app_token": self.app_token,
            })
            try:
                j = json.loads(r.text)
            except json.JSONDecodeError:
                continue
            if j.get("app_token"):
                self.app_token = j["app_token"]
            out = j.get("outputfile", "")
            if out:
                if out.startswith("http"):
                    return out
                elif out.startswith("/"):
                    return "https://judgments.ecourts.gov.in" + out
                else:
                    return "https://judgments.ecourts.gov.in/" + out
        return None

    def download_pdf(self, url, filename):
        """Download a PDF from a temp URL. Returns bytes written or 0."""
        try:
            r = self.s.get(url, timeout=60, stream=True)
            if r.status_code == 200:
                ct = r.headers.get("Content-Type", "").lower()
                if "pdf" in ct or len(r.content) > 1000:
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    return len(r.content)
        except Exception:
            pass
        return 0

    def get_pdf_url_for_path(self, pdf_path):
        """Convenience: call openpdfcaptcha with just a path (val=0)."""
        return self.get_pdf_url({
            "path": pdf_path,
            "val": "0",
            "citation_year": "",
        })
