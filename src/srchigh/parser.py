"""
Parse judgment HTML from eCourts DataTable responses using CSS selectors.
Extracts CNR, case title, court, judge, dates, disposal nature, and PDF path.
"""

import re
from parsel import Selector


def parse_entry(html):
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
    court_text = sel.xpath('//span[contains(text(), "Court")]/text()').re_first(r'Court\s*:\s*(.+)')
    if not court_text:
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
    # Primary: targeted XPath sibling queries
    reg_date_val = sel.xpath('//span[contains(text(), "Date of registration")]/following-sibling::font[1]/text()').get()
    decision_date_val = sel.xpath('//span[contains(text(), "Decision Date")]/following-sibling::font[1]/text()').get()
    disposal_nature_val = sel.xpath('//span[contains(text(), "Disposal Nature") or contains(text(), "Disposal")]/following-sibling::font[1]/text()').get()

    if reg_date_val:
        entry["reg_date"] = reg_date_val.strip()
    if decision_date_val:
        entry["decision_date"] = decision_date_val.strip()
    if disposal_nature_val:
        entry["disposal_nature"] = disposal_nature_val.strip()

    # Fallback to list-based zip logic only if primary sibling lookups missed any keys
    if not reg_date_val or not decision_date_val or not disposal_nature_val:
        greens = sel.css('font[color="green"]::text').getall()
        labels = sel.css('span[style*="color:#212F3D"]::text').getall()
        for label, value in zip(labels, greens):
            label_clean = label.strip().lstrip("|").strip()
            value_clean = value.strip()
            if "Date of registration" in label_clean and "reg_date" not in entry:
                entry["reg_date"] = value_clean
            elif "Decision Date" in label_clean and "decision_date" not in entry:
                entry["decision_date"] = value_clean
            elif ("Disposal Nature" in label_clean or "Disposal" in label_clean) and "disposal_nature" not in entry:
                entry["disposal_nature"] = value_clean

    return entry


def parse_results_page(json_response):
    """Extract entries from a DataTable JSON response."""
    reportrow = json_response.get("reportrow") or {}
    aa_data = reportrow.get("aaData") or []
    total = reportrow.get("iTotalRecords", 0) or 0
    entries = []
    for row in aa_data:
        if isinstance(row, list) and len(row) >= 2:
            entries.append(parse_entry(row[1]))
    return entries, total


def get_court_code(court_name):
    """Look up numeric state_code from a court name substring."""
    from .config import COURT_NAMES

    name = court_name.lower().strip()
    for key, code in COURT_NAMES.items():
        if name in key or key in name:
            return str(code)
    return ""
