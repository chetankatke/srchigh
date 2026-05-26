#!/usr/bin/env python3
"""
eCourts India — High Court Judgments Scraper
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Search, export metadata, and download judgments from all Indian High Courts.

Usage:
  python3 main.py <search_term> [count] [options]

Examples:
  python3 main.py "divorce" 5
  python3 main.py "divorce" 5 --court bombay
  python3 main.py "divorce" --court bombay --all --csv --no-download
  python3 main.py --from-csv ~/myJud/divorce
"""

import sys
import os
import re
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

from .config import (
    COURT_NAMES, MODE_LABELS, DOWNLOADS_PER_SESSION,
    ALL_PAGE_SIZE, DEFAULT_PAGE_SIZE, MAX_PAGES_ALL, BASE_URL,
    is_first_run, first_run_setup, apply_config_to_params,
    mark_first_run_done,
)
from .session import ECourtSession
from .export import write_results_csv
from .download import download_from_csv


# ── argument parsing ──

def parse_args():
    args = sys.argv[1:]
    p = {
        "search": "", "count": 5, "mode": "PHRASE", "proximity": "",
        "page": 0, "pages": None, "state": "", "judge": "",
        "from_date": "", "to_date": "", "out": "",
        "court": "", "all": False, "csv": False, "no_dl": False,
        "from_csv": "",
    }
    pos = 0
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--page" and i + 1 < len(args):
            p["page"] = int(args[i + 1]); i += 2
        elif a == "--pages" and i + 1 < len(args):
            parts = args[i + 1].split(":")
            p["pages"] = (int(parts[0]),
                          int(parts[1]) if len(parts) > 1 else int(parts[0]) + 1)
            i += 2
        elif a == "--mode" and i + 1 < len(args):
            m = args[i + 1].upper()
            if m in ("PHRASE", "ANY", "ALL"):
                p["mode"] = m
                if m == "ALL" and not p["proximity"]:
                    p["proximity"] = "40"
            i += 2
        elif a == "--proximity" and i + 1 < len(args):
            p["proximity"] = args[i + 1]; i += 2
        elif a == "--court" and i + 1 < len(args):
            p["court"] = args[i + 1].lower(); i += 2
        elif a == "--state" and i + 1 < len(args):
            p["state"] = args[i + 1]; i += 2
        elif a == "--judge" and i + 1 < len(args):
            p["judge"] = args[i + 1]; i += 2
        elif a == "--from" and i + 1 < len(args):
            p["from_date"] = args[i + 1]; i += 2
        elif a == "--to" and i + 1 < len(args):
            p["to_date"] = args[i + 1]; i += 2
        elif a == "--all":
            p["all"] = True; i += 1
        elif a == "--csv":
            p["csv"] = True; i += 1
        elif a == "--no-download":
            p["no_dl"] = True; i += 1
        elif a == "--from-csv" and i + 1 < len(args):
            p["from_csv"] = args[i + 1]; i += 2
        elif a == "--out" and i + 1 < len(args):
            p["out"] = args[i + 1]; i += 2
        elif a.startswith("--"):
            log.error("Unknown option: %s" % a)
            sys.exit(1)
        else:
            if pos == 0:
                p["search"] = a
            elif pos == 1:
                p["count"] = int(a)
            pos += 1
            i += 1

    # --from-csv bypasses search term requirement
    if p["from_csv"]:
        p["out"] = p["from_csv"]
        return p

    # Default output dir: ~/myJud/<sanitized_search_term>
    if not p["out"]:
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", p["search"]).strip("_").lower() or "search"
        p["out"] = os.path.join(os.path.expanduser("~/myJud"), safe)

    if not p["search"]:
        print("Usage: python3 main.py <search_term> [count] [options]")
        print("  --court NAME            Filter by High Court (e.g. bombay, delhi)")
        print("  --mode PHRASE|ANY|ALL   Search mode (default: PHRASE)")
        print("  --proximity N           Word proximity for ALL mode (20-100)")
        print("  --page N                Page number (default: 0)")
        print("  --pages M:N             Page range")
        print("  --all                   Download ALL matching results")
        print("  --csv                   Export results as CSV (metadata)")
        print("  --no-download           Skip PDF download, list only")
        print("  --from-csv DIR          Download PDFs from saved CSV")
        print("  --state CODE            Filter by state code")
        print("  --judge NAME            Filter by judge name")
        print("  --from DATE             Start date DD-MM-YYYY")
        print("  --to DATE               End date DD-MM-YYYY")
        print("  --out DIR               Output directory")
        print("")
        print("Available courts: " + ", ".join(sorted(COURT_NAMES.keys())))
        sys.exit(1)

    return p


# ── page downloader ──

def download_page(ec, page_num, page_size, downloaded_cnrs=None):
    """Fetch one page of results, optionally download PDFs."""
    if downloaded_cnrs is None:
        downloaded_cnrs = set()

    log.info("")
    log.info("  Page %d (offset=%d)" % (page_num, page_num * page_size))
    entries, total = ec.get_results(
        P["search"], page=page_num, page_size=page_size,
        mode=P["mode"], state_code=P["state"],
        judge_name=P["judge"], from_date=P["from_date"],
        to_date=P["to_date"], proximity=P["proximity"],
    )
    if not entries:
        return 0, []

    for e in entries:
        cnr = e.get("cnr", "") or e.get("case_title", "?")[:40]
        log.info("    " + cnr)

    if not os.path.exists(P["out"]):
        os.makedirs(P["out"], exist_ok=True)

    dl_count = 0
    page_entries = []

    for e in entries:
        cnr = e.get("cnr", "").replace("/", "_").replace(" ", "_")
        if not cnr or cnr == "N/A":
            cnr = "judgment_%d" % (hash(e.get("path", "")) % 1000000)

        page_entries.append(e)

        if cnr in downloaded_cnrs:
            log.info("    (dup: %s)" % cnr)
            dl_count += 1
            continue

        # --no-download: skip PDF entirely
        if P["no_dl"]:
            dl_count += 1
            continue

        filename = os.path.join(P["out"], cnr + ".pdf")
        if os.path.exists(filename) and os.path.getsize(filename) > 1000:
            downloaded_cnrs.add(cnr)
            dl_count += 1
            continue

        log.info("    Downloading %s..." % cnr)
        url = ec.get_pdf_url(e)
        if url:
            sz = ec.download_pdf(url, filename)
            if sz > 1000:
                log.info("       OK %s (%d bytes)" % (os.path.basename(filename), sz))
                dl_count += 1
            else:
                safe_remove(filename)
        else:
            log.info("       Could not get PDF URL")

    return dl_count, page_entries


def safe_remove(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ═══════════════ MAIN ═══════════════

def run_cli():
    """Entry point for the srchigh command-line tool."""
    global P

    # ── First-run setup ──
    if is_first_run() and len(sys.argv) > 1:
        first_run_setup()
    elif is_first_run():
        # Just showing help, mark as done silently
        mark_first_run_done()

    # ── Parse CLI args + merge with saved config ──
    P = parse_args()
    P = apply_config_to_params(P)

    # Route: --from-csv
    if P["from_csv"]:
        print("=" * 60)
        print("  eCourts India — Download from CSV")
        print("  CSV dir:  %s" % P["from_csv"])
        print("=" * 60)
        print("")
        download_from_csv(P["from_csv"])
        print("")
        print("=" * 60)
        print("  Done!")
        print("=" * 60)
        sys.exit(0)

    # Header
    mode_label = MODE_LABELS.get(P["mode"], P["mode"])
    if P["mode"] == "ALL" and P["proximity"]:
        mode_label += " (prox=" + P["proximity"] + ")"
    modes = [mode_label]
    if P["all"]:
        modes.append("ALL RESULTS")

    print("=" * 60)
    print("  eCourts India — HC Judgments Scraper")
    print("  Search: '%s'  |  %s" % (P["search"], " + ".join(modes)))
    parts = []
    if P["court"]: parts.append("court=" + P["court"])
    if P["state"]: parts.append("state=" + P["state"])
    if P["judge"]: parts.append("judge=" + P["judge"])
    if P["from_date"]: parts.append("from=" + P["from_date"])
    if P["to_date"]: parts.append("to=" + P["to_date"])
    if parts: print("  Filters: " + ", ".join(parts))
    print("  Output:  " + P["out"])
    print("=" * 60)

    # Session setup
    ec = ECourtSession()
    print("")
    print("[1] Establishing session...")
    ec.s.get(BASE_URL, timeout=30)
    print("[2] Solving captcha...")
    court_code = ""
    if P["court"]:
        court_code = str(COURT_NAMES.get(P["court"], ""))
        if not court_code:
            for name, code in COURT_NAMES.items():
                if P["court"] in name:
                    court_code = str(code)
                    break
    P["state"] = court_code or P["state"]
    captcha_text, token = ec.solve_captcha(search_text=P["search"], search_opt=P["mode"])
    print("     Token: " + token[:16] + "...")
    print("[3] Loading search page...")
    ec.load_results_page(P["search"], mode=P["mode"])

    # Warmup and total count
    page_size = min(P["count"], 25)
    if P["all"]:
        page_size = 200
    for _ in range(3):
        ec.get_results(P["search"], page=0, page_size=page_size, mode=P["mode"],
                       state_code=P["state"], proximity=P["proximity"])
    test_entries, total = ec.get_results(
        P["search"], page=0, page_size=page_size, mode=P["mode"],
        state_code=P["state"], proximity=P["proximity"],
    )

    # Pages to fetch
    pages_to_fetch = []
    total_pages = 0
    if P["all"]:
        total_pages = (total // page_size) + 1
        total_pages = min(total_pages, 500)
        pages_to_fetch = list(range(total_pages))
    elif P["pages"]:
        pages_to_fetch = list(range(P["pages"][0], P["pages"][1]))
        total_pages = len(pages_to_fetch)
    else:
        pages_to_fetch = [P["page"]]
        total_pages = 1

    # Summary
    print("")
    print("  " + "─" * 45)
    print("    Total matching:  %s" % ("{:,}".format(total) if total else "?"))
    print("    Page size:       %d per page" % page_size)
    print("    Total pages:     %d" % total_pages)
    print("    Max downloads:   %d" % (total_pages * page_size))
    if P["all"]:
        eta = total_pages * page_size * 2
        if eta > 120:
            print("    Est. time:       ~%d min" % (eta // 60))
        else:
            print("    Est. time:       ~%d sec" % eta)
    print("  " + "─" * 45)

    # Existing files
    downloaded_cnrs = set()
    if os.path.exists(P["out"]):
        for f in os.listdir(P["out"]):
            if f.endswith(".pdf"):
                downloaded_cnrs.add(f[:-4])
        log.info("     Already have %d PDFs in %s/" % (len(downloaded_cnrs), P["out"]))

    # Download loop
    print("")
    print("[4] Downloading %d page(s)..." % len(pages_to_fetch))
    total_dl = 0
    dl_since_refresh = 0
    all_entries = []

    for pg in pages_to_fetch:
        try:
            dl_count, page_entries = download_page(ec, pg, page_size, downloaded_cnrs)
            total_dl += dl_count
            dl_since_refresh += dl_count
            all_entries.extend(page_entries)

            if not P["no_dl"] and dl_since_refresh >= 20:
                log.info("  === Rotating session (%d downloads) ===" % 20)
                ec = ECourtSession()
                ec.s.get(BASE_URL, timeout=30)
                ct, tk = ec.solve_captcha(search_text=P["search"], search_opt=P["mode"])
                ec.load_results_page(P["search"], captcha=ct, mode=P["mode"])
                dl_since_refresh = 0

        except Exception as ex:
            log.error("  Failed page %d: %s" % (pg, ex))
            if not P["no_dl"]:
                ec = ECourtSession()
                ec.s.get(BASE_URL, timeout=30)
                ct, tk = ec.solve_captcha(search_text=P["search"], search_opt=P["mode"])
                ec.load_results_page(P["search"], captcha=ct, mode=P["mode"])
                dl_since_refresh = 0

    # CSV export
    if P["csv"] and all_entries:
        csv_path = write_results_csv(P["out"], all_entries)
        if csv_path:
            log.info("  CSV saved: %s (%d entries)" % (csv_path, len(all_entries)))

    # Done
    print("")
    print("=" * 60)
    if P["no_dl"]:
        print("  Done! %d results. Use --from-csv to download PDFs later." % len(all_entries))
    else:
        print("  Done! %d PDF(s) downloaded to %s/" % (total_dl, P["out"]))
    print("=" * 60)

if __name__ == "__main__":
    run_cli()
