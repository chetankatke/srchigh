#!/usr/bin/env python3
"""
eCourts India — High Court Judgments Scraper
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Search, store, and download judgments from all Indian High Courts.

Usage:
  python3 main.py <search_term> [count] [options]

Examples:
  python3 main.py "divorce" 5
  python3 main.py "divorce" 5 --court bombay
  python3 main.py "divorce" --court bombay --all --no-download
  python3 main.py --download-db
  python3 main.py --status
"""

import sys
import os
import re
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

from .config import (
    COURT_NAMES, MODE_LABELS, DOWNLOADS_PER_SESSION,
    ALL_PAGE_SIZE, DEFAULT_PAGE_SIZE, MAX_PAGES_ALL, BASE_URL, SCR_BASE_URL,
    is_first_run, first_run_setup, apply_config_to_params,
    mark_first_run_done,
)
from .session import ECourtSession, httpx
from . import db
from .download import download_from_db
from . import __version__


def parse_args():
    args = sys.argv[1:]
    p = {
        "search": "", "count": 5, "mode": "PHRASE", "proximity": "",
        "page": 0, "pages": None, "state": "", "judge": "",
        "from_date": "", "to_date": "", "out": "",
        "court": "", "all": False, "no_dl": False,
        "download_db": False, "status": False, "export_csv": "",
        "scr": False,
        "citation_year": "", "citation_vol": "", "citation_supl": "",
        "citation_page": "", "ncn": "", "neu_cit_year": "",
        "neu_no": "", "sel_lang": "",
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
        elif a == "--scr":
            p["scr"] = True; i += 1
        elif a == "--citation-year" and i + 1 < len(args):
            p["citation_year"] = args[i + 1]; i += 2
        elif a == "--citation-vol" and i + 1 < len(args):
            p["citation_vol"] = args[i + 1]; i += 2
        elif a == "--citation-supl" and i + 1 < len(args):
            p["citation_supl"] = args[i + 1]; i += 2
        elif a == "--citation-page" and i + 1 < len(args):
            p["citation_page"] = args[i + 1]; i += 2
        elif a == "--ncn" and i + 1 < len(args):
            p["ncn"] = args[i + 1]; i += 2
        elif a == "--neu-cit-year" and i + 1 < len(args):
            p["neu_cit_year"] = args[i + 1]; i += 2
        elif a == "--neu-no" and i + 1 < len(args):
            p["neu_no"] = args[i + 1]; i += 2
        elif a == "--sel-lang" and i + 1 < len(args):
            p["sel_lang"] = args[i + 1]; i += 2
        elif a == "--all":
            p["all"] = True; i += 1
        elif a == "--no-download":
            p["no_dl"] = True; i += 1
        elif a == "--download-db":
            p["download_db"] = True; i += 1
        elif a == "--status":
            p["status"] = True; i += 1
        elif a == "--export-csv" and i + 1 < len(args):
            p["export_csv"] = args[i + 1]; i += 2
        elif a == "--out" and i + 1 < len(args):
            p["out"] = args[i + 1]; i += 2
        elif a == "--version":
            print("srchigh v%s" % __version__)
            sys.exit(0)
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

    if not p["search"] and not p["download_db"] and not p["status"] and not p["export_csv"]:
        court_list = ", ".join(sorted(COURT_NAMES.keys()))
        print("Usage: python3 main.py <search_term> [count] [options]")
        print("")
        print("  Search sources:")
        print("    (default)            High Courts via eCourts portal")
        print("    --scr                Supreme Court Reports (SCR) portal")
        print("")
        print("  Search options:")
        print("    --mode PHRASE|ANY|ALL   Search mode (default: PHRASE)")
        print("    --proximity N           Word proximity for ALL mode (20-100)")
        print("    --page N                Page number (default: 0)")
        print("    --pages M:N             Page range")
        print("    --all                   Fetch ALL matching results")
        print("")
        print("  High Court filters:")
        print("    --court NAME            Filter by High Court (%s)" % court_list)
        print("    --state CODE            Filter by state code")
        print("    --judge NAME            Filter by judge name")
        print("    --from DATE             Start date DD-MM-YYYY")
        print("    --to DATE               End date DD-MM-YYYY")
        print("")
        print("  SCR filters:")
        print("    --citation-year YYYY    Citation year")
        print("    --citation-vol N        Citation volume")
        print("    --citation-supl SUPPL   Citation supplement")
        print("    --citation-page N       Citation page")
        print("    --ncn CODE              Neutral citation number")
        print("    --neu-cit-year YYYY     Neutral citation year")
        print("    --neu-no N              Neutral citation number")
        print("    --sel-lang CODE         Language")
        print("")
        print("  Output options:")
        print("    --no-download           Skip PDF download, store in DB only")
        print("    --download-db           Download pending PDFs from DB")
        print("    --status                Show DB status for a search term")
        print("    --export-csv PATH       Export DB results to CSV")
        print("    --out DIR               Output directory")
        sys.exit(1)

    if not p["out"] and p["search"]:
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", p["search"]).strip("_").lower() or "search"
        if p.get("scr"):
            p["out"] = os.path.join(os.path.expanduser("~/myJud"), "scr", safe)
        else:
            p["out"] = os.path.join(os.path.expanduser("~/myJud"), safe)

    return p


async def download_page(ec, page_num, page_size, search_term, out_dir, downloaded_cnrs=None, no_dl=False):
    if downloaded_cnrs is None:
        downloaded_cnrs = set()

    scr_params = {}
    if P["scr"]:
        for k in ("citation_year", "citation_vol", "citation_supl",
                   "citation_page", "ncn", "neu_cit_year", "neu_no", "sel_lang"):
            if P.get(k):
                scr_params[k] = P[k]

    log.info("")
    log.info("  Page %d (offset=%d)" % (page_num, page_num * page_size))
    entries, total = await ec.get_results(
        search_term, page=page_num, page_size=page_size,
        mode=P["mode"], state_code=P["state"],
        judge_name=P["judge"], from_date=P["from_date"],
        to_date=P["to_date"], proximity=P["proximity"],
        **scr_params,
    )
    if not entries:
        return 0, []

    for e in entries:
        cnr = e.get("cnr", "") or e.get("case_title", "?")[:40]
        log.info("    " + cnr)

    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

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

        if no_dl:
            dl_count += 1
            continue

        filename = os.path.join(out_dir, cnr + ".pdf")
        if os.path.exists(filename) and os.path.getsize(filename) > 1000:
            downloaded_cnrs.add(cnr)
            dl_count += 1
            continue

        log.info("    Downloading %s..." % cnr)
        url = await ec.get_pdf_url(e)
        if url:
            sz = await ec.download_pdf(url, filename)
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


def _build_scr_params():
    """Build dict of SCR extra params from global P that are non-empty."""
    params = {}
    for k in ("citation_year", "citation_vol", "citation_supl",
              "citation_page", "ncn", "neu_cit_year", "neu_no", "sel_lang"):
        if P.get(k):
            params[k] = P[k]
    return params


async def run_search():
    global P
    await db.init_db()

    is_scr = P["scr"]
    base_url = SCR_BASE_URL if is_scr else BASE_URL
    source_name = "Supreme Court (SCR)" if is_scr else "High Courts (eCourts)"

    mode_label = MODE_LABELS.get(P["mode"], P["mode"])
    if P["mode"] == "ALL" and P["proximity"]:
        mode_label += " (prox=" + P["proximity"] + ")"
    modes = [mode_label]
    if P["all"]:
        modes.append("ALL RESULTS")

    print("=" * 60)
    print("  srchigh — %s" % source_name)
    print("  Search: '%s'  |  %s" % (P["search"], " + ".join(modes)))
    parts = []
    if P["court"]: parts.append("court=" + P["court"])
    if P["state"]: parts.append("state=" + P["state"])
    if P["judge"]: parts.append("judge=" + P["judge"])
    if P["from_date"]: parts.append("from=" + P["from_date"])
    if P["to_date"]: parts.append("to=" + P["to_date"])
    if is_scr:
        scr_display = _build_scr_params()
        for k, v in scr_display.items():
            parts.append("%s=%s" % (k, v))
    if parts: print("  Filters: " + ", ".join(parts))
    print("  Output:  " + P["out"])
    print("=" * 60)

    fcourt = "3" if is_scr else "2"
    ec = ECourtSession(base_url=base_url, fcourt_type=fcourt)
    print("")
    print("[1] Establishing session...")
    await ec.client.get(base_url)
    print("[2] Solving captcha...")
    court_code = ""
    if not is_scr and P["court"]:
        court_code = str(COURT_NAMES.get(P["court"], ""))
        if not court_code:
            for name, code in COURT_NAMES.items():
                if P["court"] in name:
                    court_code = str(code)
                    break
    P["state"] = court_code or P["state"]
    captcha_text, token = await ec.solve_captcha(search_text=P["search"], search_opt=P["mode"])
    print("     Token: " + token[:16] + "...")
    print("[3] Loading search page...")
    await ec.load_results_page(P["search"], mode=P["mode"])

    scr_params = _build_scr_params()
    page_size = min(P["count"], 25)
    if P["all"]:
        page_size = 200
    for _ in range(3):
        await ec.get_results(P["search"], page=0, page_size=page_size, mode=P["mode"],
                             state_code=P["state"], proximity=P["proximity"],
                             **scr_params)
    test_entries, total = await ec.get_results(
        P["search"], page=0, page_size=page_size, mode=P["mode"],
        state_code=P["state"], proximity=P["proximity"],
        **scr_params,
    )

    pages_to_fetch = []
    total_pages = 0
    if P["all"]:
        total_pages = (total // page_size) + 1 if total else 1
        total_pages = min(total_pages, 500)
        pages_to_fetch = list(range(total_pages))
    elif P["pages"]:
        pages_to_fetch = list(range(P["pages"][0], P["pages"][1]))
        total_pages = len(pages_to_fetch)
    else:
        pages_to_fetch = [P["page"]]
        total_pages = 1

    print("")
    print("  " + "─" * 45)
    print("    Total matching:  %s" % ("{:,}".format(total) if total else "?"))
    print("    Page size:       %d per page" % page_size)
    print("    Total pages:     %d" % total_pages)
    print("    Max downloads:   %d" % (total_pages * page_size))
    if P["all"] and total:
        eta = total_pages * page_size * 2
        if eta > 120:
            print("    Est. time:       ~%d min" % (eta // 60))
        else:
            print("    Est. time:       ~%d sec" % eta)
    print("  " + "─" * 45)

    downloaded_cnrs = set()
    if os.path.exists(P["out"]):
        for f in os.listdir(P["out"]):
            if f.endswith(".pdf"):
                downloaded_cnrs.add(f[:-4])
        log.info("     Already have %d PDFs in %s/" % (len(downloaded_cnrs), P["out"]))

    print("")
    print("[4] Fetching %d page(s)..." % len(pages_to_fetch))
    total_dl = 0
    dl_since_refresh = 0
    all_entries = []

    for pg in pages_to_fetch:
        try:
            dl_count, page_entries = await download_page(
                ec, pg, page_size, P["search"], P["out"], downloaded_cnrs, P["no_dl"]
            )
            total_dl += dl_count
            dl_since_refresh += dl_count
            all_entries.extend(page_entries)

            if not P["no_dl"] and dl_since_refresh >= 20:
                log.info("  === Rotating session (%d downloads) ===" % 20)
                await ec.close()
                ec = ECourtSession(base_url=base_url, fcourt_type=fcourt)
                await ec.client.get(base_url)
                ct, tk = await ec.solve_captcha(search_text=P["search"], search_opt=P["mode"])
                await ec.load_results_page(P["search"], captcha=ct, mode=P["mode"])
                dl_since_refresh = 0

        except (httpx.HTTPError, asyncio.TimeoutError) as ex:
            log.error("  Failed page %d: %s" % (pg, ex))
            if not P["no_dl"]:
                await ec.close()
                ec = ECourtSession(base_url=base_url, fcourt_type=fcourt)
                await ec.client.get(base_url)
                ct, tk = await ec.solve_captcha(search_text=P["search"], search_opt=P["mode"])
                await ec.load_results_page(P["search"], captcha=ct, mode=P["mode"])
                dl_since_refresh = 0

    if all_entries:
        source = "scr" if P.get("scr") else "ecourts"
        await db.insert_judgments_batch(all_entries, P["search"], source=source)
        await db.upsert_search(P["search"], P["mode"], P["court"], total)
        log.info("  Stored %d entries in DB" % len(all_entries))

    await ec.close()

    print("")
    print("=" * 60)
    if P["no_dl"]:
        print("  Done! %d results stored in DB. Use --download-db to download PDFs." % len(all_entries))
    else:
        print("  Done! %d PDF(s) downloaded to %s/" % (total_dl, P["out"]))
    print("=" * 60)


async def run_download_db():
    await db.init_db()
    print("=" * 60)
    print("  eCourts India — Download from DB")
    print("=" * 60)
    print("")
    await download_from_db(search_term=P.get("search", ""), out_dir=P.get("out"))
    print("")
    print("=" * 60)
    print("  Done!")
    print("=" * 60)


async def run_status():
    await db.init_db()
    search_term = P.get("search", "")
    stats = await db.get_stats(search_term)
    entries = await db.get_all_judgments(search_term) if search_term else []
    print("=" * 60)
    print("  DB Status for: %s" % (search_term or "all searches"))
    print("=" * 60)
    print("  Total judgments:  %d" % stats["total"])
    print("  Downloaded:      %d" % stats["downloaded"])
    print("  Pending:         %d" % stats["pending"])
    if entries:
        print("")
        print("  Recent entries:")
        for e in entries[:10]:
            dl = "✓" if e.get("downloaded") else "✗"
            print("    [%s] %s | %s" % (dl, e.get("cnr", "?"), e.get("case_title", "?")[:50]))
    print("=" * 60)


async def run_export_csv():
    await db.init_db()
    search_term = P.get("search", "")
    out_path = P.get("export_csv", "")
    if not out_path:
        out_path = os.path.join(os.path.expanduser("~"), "myJud", search_term or "export", "_results.csv")
    result = await db.export_to_csv(search_term, out_path)
    if result:
        log.info("  Exported to %s" % result)
    else:
        log.info("  No entries to export")


async def run_cli():
    global P

    if is_first_run() and len(sys.argv) > 1:
        first_run_setup()
    elif is_first_run():
        mark_first_run_done()

    P = parse_args()
    P = apply_config_to_params(P)

    if P["status"]:
        await run_status()
    elif P["export_csv"]:
        await run_export_csv()
    elif P["download_db"]:
        await run_download_db()
    else:
        await run_search()


P = {}


def main():
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()