"""
ECourtSession — async HTTP session with eCourts / SCR server using httpx.
Handles captcha solving, search, and PDF URL retrieval.

Chrome 120+ TLS fingerprint headers for stealth.
"""

import io
import json
import re
import asyncio
from urllib.parse import urlparse

import httpx
from PIL import Image
import pytesseract

from .config import USER_AGENT
from .parser import parse_entry, parse_results_page


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
    def __init__(self, base_url=None, fcourt_type="2"):
        self.base_url = base_url or "https://judgments.ecourts.gov.in/pdfsearch/"
        self.fcourt_type = fcourt_type
        self.client = httpx.AsyncClient(timeout=30.0, headers=dict(CHROME_HEADERS))
        self.app_token = ""
        self.captcha_text = ""

    async def fresh(self):
        await self.client.aclose()
        self.client = httpx.AsyncClient(timeout=30.0, headers=dict(CHROME_HEADERS))
        self.app_token = ""

    async def _get(self, path, **kwargs):
        return await self.client.get(self.base_url + path, **kwargs)

    async def _post(self, path, data=None, **kwargs):
        return await self.client.post(self.base_url + path, data=data, **kwargs)

    def _render_image_to_ascii(self, img, width=60):
        resample = Image.Resampling.BILINEAR

        w_original, h_original = img.size
        aspect_ratio = h_original / w_original
        height = int(width * aspect_ratio * 0.5)
        if height < 1:
            height = 1

        img_resized = img.resize((width, height), resample)

        ramp = "█▓▒░:  "
        lines = []
        for y in range(height):
            row = []
            for x in range(width):
                val = img_resized.getpixel((x, y))
                if isinstance(val, tuple):
                    val = int(0.299 * val[0] + 0.587 * val[1] + 0.114 * val[2])
                idx = int(val * (len(ramp) - 1) / 255.0)
                idx = max(0, min(idx, len(ramp) - 1))
                row.append(ramp[idx])
            lines.append("    \033[90m│\033[0m" + "".join(row) + "\033[90m│\033[0m")

        border = "    \033[90m┌" + "─" * width + "┐\033[0m"
        bottom_border = "    \033[90m└" + "─" * width + "┘\033[0m"
        return border + "\n" + "\n".join(lines) + "\n" + bottom_border

    async def solve_captcha(self, search_text="test", search_opt="PHRASE",
                            court_type=None, max_tries=30):
        for attempt in range(1, max_tries + 1):
            print(f"\n\033[1;36m┌── Captcha Attempt {attempt}/{max_tries} ──────────────────────────────────────┐\033[0m", flush=True)
            try:
                cr = await self._get("vendor/securimage/securimage_show.php")
                img = Image.open(io.BytesIO(cr.content)).convert("L")
                print("    \033[1;33mDownloaded Captcha Image:\033[0m", flush=True)
                print(self._render_image_to_ascii(img), flush=True)
            except Exception as e:
                print(f"    \033[1;31mError fetching/parsing captcha image: {e}\033[0m", flush=True)
                print("\033[1;36m└──────────────────────────────────────────────────────────────────┘\033[0m", flush=True)
                continue

            guesses_by_thresh = {}
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
                    guesses_by_thresh[thresh] = text
                else:
                    guesses_by_thresh[thresh] = f"{text} (ignored, len={len(text)})"

            print("    \033[1;34mStep 1: Preprocessing & OCR Thresholds:\033[0m", flush=True)
            for thresh in sorted(guesses_by_thresh.keys()):
                val = guesses_by_thresh[thresh]
                if val in guesses:
                    print(f"      Threshold {thresh:03d} -> \033[1;32m'{val}'\033[0m (valid length)", flush=True)
                else:
                    print(f"      Threshold {thresh:03d} -> \033[90m'{val}'\033[0m", flush=True)

            if not guesses:
                print("    \033[1;31mNo valid OCR guesses found for this attempt.\033[0m", flush=True)
                print("\033[1;36m└──────────────────────────────────────────────────────────────────┘\033[0m", flush=True)
                continue

            print("    \033[1;34mStep 2: Validating guesses against server:\033[0m", flush=True)
            for guess in sorted(guesses):
                try:
                    print(f"      Testing guess \033[1;35m'{guess}'\033[0m ... ", end="", flush=True)
                    r = await self._post("?p=pdf_search/checkCaptcha", data={
                        "captcha": guess,
                        "search_text": search_text,
                        "search_opt": search_opt,
                        "fcourt_type": court_type or self.fcourt_type,
                        "ajax_req": "true",
                        "app_token": self.app_token,
                    })
                    j = json.loads(r.text)
                    if j.get("captcha_status") == "Y":
                        print("\033[1;32m✓ ACCEPTED!\033[0m", flush=True)
                        self.app_token = j.get("app_token", "")
                        self.captcha_text = guess
                        print(f"\033[1;32m    ★ Successfully solved: '{guess}'\033[0m", flush=True)
                        print("\033[1;36m└──────────────────────────────────────────────────────────────────┘\033[0m", flush=True)
                        return guess, self.app_token
                    else:
                        print("\033[1;31m✗ Rejected\033[0m", flush=True)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"\033[1;31mError ({e})\033[0m", flush=True)

            print("\033[1;36m└──────────────────────────────────────────────────────────────────┘\033[0m", flush=True)
            if attempt % 5 == 0:
                await self.fresh()

        raise RuntimeError("Failed to solve captcha after %d tries" % max_tries)

    async def load_results_page(self, search_term, captcha=None, mode="PHRASE"):
        c = captcha or self.captcha_text
        import urllib.parse
        url = ("?p=pdf_search/home&text=" + urllib.parse.quote(search_term) +
               "&captcha=" + c + "&search_opt=" + mode +
               "&fcourt_type=%s&app_token=" % self.fcourt_type + self.app_token)
        r = await self._get(url)
        m = re.search(r'app_token=([^"&\s<>]+)', r.text)
        if m:
            self.app_token = m.group(1)
        return r.text

    async def get_results(self, search_term, page=0, page_size=25, mode="PHRASE",
                          state_code="", judge_name="", from_date="", to_date="",
                          proximity="", **extra_params):
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
            "fcourt_type": self.fcourt_type,
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
        dt.update(extra_params)
        r = await self._post("?p=pdf_search/home", data=dt)
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

    async def get_pdf_url(self, entry):
        path = entry.get("path", "")
        val = entry.get("val", "0")
        for _ in range(2):
            r = await self._post("?p=pdf_search/openpdfcaptcha", data={
                "val": val,
                "lang_flg": "",
                "path": path,
                "citation_year": entry.get("citation_year", ""),
                "fcourt_type": self.fcourt_type,
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
                else:
                    # Extract origin from self.base_url (e.g. "https://scr.sci.gov.in")
                    # so relative paths resolve to the right domain per source
                    parsed = urlparse(self.base_url)
                    origin = "%s://%s" % (parsed.scheme, parsed.netloc)
                    if out.startswith("/"):
                        return origin + out
                    else:
                        return origin + "/" + out
        return None

    async def download_pdf(self, url, filename):
        try:
            r = await self.client.get(url, timeout=60.0)
            if r.status_code == 200:
                ct = r.headers.get("Content-Type", "").lower()
                if "pdf" in ct or len(r.content) > 1000:
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    return len(r.content)
        except Exception:
            pass
        return 0

    async def get_pdf_url_for_path(self, pdf_path):
        return await self.get_pdf_url({
            "path": pdf_path,
            "val": "0",
            "citation_year": "",
        })

    async def close(self):
        await self.client.aclose()