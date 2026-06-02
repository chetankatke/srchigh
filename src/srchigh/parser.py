"""
Parse judgment HTML from eCourts DataTable responses using CSS selectors.
Extracts CNR, case title, court, judge, dates, disposal nature, and PDF path.
"""

import hashlib
import re
from typing import Tuple
from parsel import Selector


def parse_entry(html: str) -> dict:
    """Parse one judgment HTML cell into a structured dict.

    Uses parsel.Selector for robust CSS-based extraction instead of fragile regexes.
    """
    sel = Selector(text=html)
    entry = {}

    # ── PDF path from open_pdf() onclick attribute ──
    # onclick=javascript:open_pdf('0','','court/cnrorders/...pdf#...')
    onclick = sel.css('button::attr(onclick)').get('')
    m = re.search(r"open_pdf\s*\(\s*'(\d+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'", onclick)
    if m:
        entry["val"] = m.group(1)
        entry["citation_year"] = m.group(2)
        raw_path = m.group(3).replace("\\/", "/")
        entry["path"] = raw_path.split("#")[0]

    # ── Case title from button aria-label ──
    aria = sel.css('button::attr(aria-label)').get('')
    if aria:
        # Strip trailing " pdf" that eCourts appends
        entry["case_title"] = aria.rsplit(" pdf", 1)[0].strip()
    else:
        # Fallback: first font tag
        title = sel.css('font::text').get('')
        if title:
            entry["case_title"] = title.strip()

    # ── Judge ──
    # <strong>Judge : NAME</strong>
    judge_text = sel.css('strong:contains("Judge")::text').get('')
    if judge_text:
        entry["judge"] = judge_text.replace("Judge :", "").strip()

    # ── CNR ──
    # <span> CNR :</span><font color="green"> CNRNUMBER</font>
    cnr = sel.css('font[color="green"]::text').get('')
    if cnr:
        cnr = cnr.strip()
        # CNR is always uppercase alphanumeric
        if re.match(r'^[A-Z0-9]+$', cnr):
            entry["cnr"] = cnr

    # ── Court ──
    # <span style="opacity:...">Court : NAME</span>
    court_text = sel.css('span[style*="opacity"]::text').re_first(r'Court\s*:\s*(.+)')
    if not court_text:
        court_text = sel.css('span[style*="opacity"]::text').get('')
        if court_text and "Court :" in court_text:
            court_text = court_text.split("Court :", 1)[-1].strip()
    if court_text:
        entry["court"] = court_text.strip()

    # ── Citation (SCR format: [2026] 2 S.C.R. 231) ──
    # The citation may appear anywhere in the cell text for SCR entries.
    # Pattern: [YEAR] VOL S.C.R. PAGE  or  (YEAR) VOL S.C.R. PAGE
    all_text = sel.css('*::text').getall()
    full_text = " ".join(t.strip() for t in all_text if t.strip())
    cit_m = re.search(r'[\[\(](\d{4})[\]\)]\s+(\d+)\s+S\.?\s*C\.?\s*R\.?\s+(\d+)', full_text, re.IGNORECASE)
    if cit_m:
        entry["citation"] = "[%s] %s S.C.R. %s" % (cit_m.group(1), cit_m.group(2), cit_m.group(3))

    # ── Date fields ──
    # All <font color="green"> elements in order: CNR, Reg Date, Decision Date, Disposal Nature
    greens = sel.css('font[color="green"]::text').getall()
    # First green font is CNR (already extracted), remaining are dates and disposal
    labels = sel.css('span[style*="color:#212F3D"]::text').getall()
    # labels look like: " CNR :", " | Date of registration :", " | Decision Date :", " | Disposal Nature :"

    for label, value in zip(labels, greens):
        label_clean = label.strip().lstrip("|").strip()
        value_clean = value.strip()
        if "Date of registration" in label_clean:
            entry["reg_date"] = value_clean
        elif "Decision Date" in label_clean:
            entry["decision_date"] = value_clean
        elif "Disposal Nature" in label_clean or "Disposal" in label_clean:
            entry["disposal_nature"] = value_clean

    return entry


def parse_results_page(json_response: dict) -> Tuple[list, int]:
    """Extract entries from a DataTable JSON response."""
    reportrow = json_response.get("reportrow") or {}
    aa_data = reportrow.get("aaData") or []
    total = reportrow.get("iTotalRecords", 0) or 0
    entries = []
    for row in aa_data:
        if isinstance(row, list) and len(row) >= 2:
            entries.append(parse_entry(row[1]))
    return entries, total


def get_court_code(court_name: str) -> str:
    """Look up numeric state_code from a court name substring."""
    from .config import COURT_NAMES

    name = court_name.lower().strip()
    for key, code in COURT_NAMES.items():
        if name in key or key in name:
            return str(code)
    return ""


def make_safe_filename(cnr: str, path: str, source: str = "ecourts") -> str:
    """Return a filesystem-safe filename stem (no extension) for a PDF.

    Logic:
    - If ``cnr`` is present and not the literal "N/A", use it with slashes
      and spaces replaced by underscores.
    - Otherwise, hash the (source, path) pair with SHA-256 (truncated to 16
      hex chars) so the same missing-CNR row always gets the same name and
      different sources/paths get different names (avoids collisions when
      doing bulk dumps that include both eCourts and SCR entries with
      overlapping ``path`` values).
    - Returns ``"unknown"`` if both ``cnr`` and ``path`` are empty.
    """
    if cnr and cnr != "N/A":
        return cnr.replace("/", "_").replace(" ", "_")
    if not path:
        return "unknown"
    h = hashlib.sha256((source + "::" + path).encode("utf-8")).hexdigest()[:16]
    return f"judgment_{h}"
