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
from .log_setup import setup_logging

is_verbose = "-v" in sys.argv or "--verbose" in sys.argv
log = setup_logging(verbose=is_verbose)

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
from .sci import SCISession, _split_date_range, _parse_sci_date, _month_range, _fmt_date


def parse_args():
    args = sys.argv[1:]
    p = {
        "search": "", "count": 5, "mode": "PHRASE", "proximity": "",
        "page": 0, "pages": None, "state": "", "judge": "",
        "from_date": "", "to_date": "", "out": "",
        "court": "", "all": False, "no_dl": False, "dump_all": False,
        "download_db": False, "status": False, "export_csv": "", "csv": False,
        "stats": False, "scr": False,
        "citation_year": "", "citation_vol": "", "citation_supl": "",
        "citation_page": "", "ncn": "", "neu_cit_year": "",
        "neu_no": "", "sel_lang": "",
        "sci": False,
        "month_sci": "", "year_sci": "",
        "bulk_dump": False,
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
            if m in ("PHRASE", "ANY", "ALL", "BOOLEAN"):
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
        elif a == "--sci":
            p["sci"] = True; i += 1
        elif a == "--month" and i + 1 < len(args):
            p["month_sci"] = args[i + 1]; i += 2
        elif a == "--year" and i + 1 < len(args):
            p["year_sci"] = args[i + 1]; i += 2
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
        elif a == "--all-words":
            p["mode"] = "ALL"
            if not p["proximity"]: p["proximity"] = "40"
            i += 1
        elif a == "--any":
            p["mode"] = "ANY"; i += 1
        elif a == "--boolean":
            p["mode"] = "BOOLEAN"; i += 1
        elif a in ("--verbose", "-v"):
            p["verbose"] = True; i += 1
        elif a == "--dump-all":
            p["dump_all"] = True; i += 1
        elif a == "--bulk-dump":
            p["bulk_dump"] = True; i += 1
        elif a == "--no-download":
            p["no_dl"] = True; i += 1
        elif a == "--download-db":
            p["download_db"] = True; i += 1
        elif a == "--from-csv":
            # Deprecated v1 alias for --download-db. The README still documents
            # this workflow; the underlying implementation reads from SQLite
            # (not the CSV), so the old flag is functionally a no-op shortcut.
            log.warning("--from-csv is deprecated; use --download-db instead")
            p["download_db"] = True; i += 1
        elif a == "--status":
            p["status"] = True; i += 1
        elif a == "--csv":
            p["csv"] = True; i += 1
        elif a == "--stats":
            p["stats"] = True; i += 1
        elif a == "--export-csv" and i + 1 < len(args):
            p["export_csv"] = args[i + 1]; i += 2
        elif a == "--out" and i + 1 < len(args):
            p["out"] = args[i + 1]; i += 2
        elif a == "--clear-db":
            p["clear_db"] = True; i += 1
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

    # Fix for `srchigh scr --dump-all` interpreting "scr" as search term
    if (p.get("dump_all") or p.get("bulk_dump")) and p["search"].lower() == "scr":
        p["scr"] = True
        p["search"] = ""

    if p.get("bulk_dump"):
        p["search"] = ""
        p["all"] = True
        p["no_dl"] = True  # Default to metadata only for bulk dump unless overridden
        # We can let the user override with a future flag, but safety first.

    if not p["search"] and not p.get("dump_all") and not p.get("bulk_dump") and not p["download_db"] and not p["status"] and not p.get("export_csv") and not p.get("stats") and not p.get("sci") and not p.get("clear_db"):
        court_list = ", ".join(sorted(COURT_NAMES.keys()))
        log.info("Usage: python3 main.py <search_term> [count] [options]")
        log.info("")
        log.info("  Search sources:")
        log.info("    (default)            High Courts via eCourts portal")
        log.info("    --scr                Supreme Court Reports (SCR) portal")
        log.info("    --sci                SCI Judgment Date portal")
        log.info("")
        log.info("  Search options:")
        log.info("    --mode PHRASE|ANY|ALL|BOOLEAN Search mode (default: PHRASE)")
        log.info("    --all-words             Match all words in text")
        log.info("    --any                   Match any word in text")
        log.info("    --boolean               Use boolean search (e.g., 'murder AND theft')")
        log.info("    --proximity N           Max words between terms (for ALL mode, default 40)")
        log.info("    --page N                Page number (default: 0)")
        log.info("    --pages M:N             Page range")
        log.info("    --all                   Fetch ALL matching results (all pages)")
        log.info("    --dump-all              Fetch EVERY judgment (no search term needed)")
        log.info("    --bulk-dump             Dump ENTIRE database (organized by year, metadata first)")
        log.info("    --verbose, -v           Enable detailed debug output")
        log.info("")
        log.info("  Court scope:")
        log.info("    (default)               Search ALL 25 High Courts in one pass")
        log.info("    --court NAME            Restrict to a single High Court")
        log.info("                           Available: %s" % court_list)
        log.info("    --state CODE            Alias for --court (state code)")
        log.info("    --judge NAME            Filter by judge name")
        log.info("    --from DATE             Start date DD-MM-YYYY")
        log.info("    --to DATE               End date DD-MM-YYYY")
        log.info("")
        log.info("  SCR scope:")
        log.info("    (default)               Search all volumes / years")
        log.info("    --citation-year YYYY    Restrict to citation year")
        log.info("    --citation-vol N        Restrict to citation volume")
        log.info("    --citation-supl SUPPL   Restrict to citation supplement")
        log.info("    --citation-page N       Restrict to citation page")
        log.info("    --ncn CODE              Restrict to neutral citation")
        log.info("    --neu-cit-year YYYY     Restrict to NCN year")
        log.info("    --neu-no N              Restrict to NCN number")
        log.info("    --sel-lang CODE         Restrict to language")
        log.info("")
        log.info("  SCI options:")
        log.info("    --from DATE             Start date DD-MM-YYYY")
        log.info("    --to DATE               End date DD-MM-YYYY")
        log.info("    --month MM-YYYY         Month to download")
        log.info("    --year YYYY             Year to download")
        log.info("    (max 30-day range per request, auto-split into chunks)")
        log.info("")
        log.info("  Output options:")
        log.info("    --dump-all              Fetch EVERY judgment (no search term needed)")
        log.info("    --no-download           Skip PDF download, store in DB only")
        log.info("    --csv                   Export search results directly to CSV")
        log.info("    --download-db           Download pending PDFs from DB")
        log.info("    --stats                 Show per-court breakdown of results (no download)")
        log.info("    --status                Show DB status for a search term")
        log.info("    --clear-db              Clear the local SQLite database")
        log.info("    --export-csv PATH       Export DB results to CSV")
        log.info("    --out DIR               Output directory")
        sys.exit(1)

    if not p["out"] and (p["search"] or p.get("dump_all") or p.get("bulk_dump")):
        if p.get("bulk_dump"):
            if p.get("scr"):
                p["out"] = os.path.join(os.path.expanduser("~/myJud"), "dump", "scr")
            else:
                p["out"] = os.path.join(os.path.expanduser("~/myJud"), "dump", "ecourts")
        else:
            safe = re.sub(r"[^a-zA-Z0-9]+", "_", p["search"]).strip("_").lower() or "_all_judgments"
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
        label = e.get("citation", "") or e.get("cnr", "") or e.get("case_title", "?")[:40]
        log.info("    " + label)

    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    dl_count = 0
    page_entries = []

    for e in entries:
        # SCR: use citation as filename; else CNR; else deterministic hash.
        if P.get("scr") and e.get("citation"):
            cnr = e["citation"].replace(" ", "_").replace(".", "").replace(",", "")
        else:
            from .parser import make_safe_filename
            cnr = make_safe_filename(
                e.get("cnr", ""),
                e.get("path", ""),
                source="scr" if P.get("scr") else "ecourts",
            )

        page_entries.append(e)

        if cnr in downloaded_cnrs:
            log.info("    (dup: %s)" % cnr)
            dl_count += 1
            continue

        if no_dl:
            dl_count += 1
            continue

        # For bulk dump, route to year subdirectories
        file_out_dir = out_dir
        if P.get("bulk_dump"):
            # Try to get year from citation or decision date
            year = ""
            if P.get("scr") and e.get("citation_year"):
                year = e.get("citation_year")
            elif e.get("decision_date"):
                year = e.get("decision_date").split("-")[-1]
            if not year or len(year) != 4:
                year = "unknown_year"
            file_out_dir = os.path.join(out_dir, year)
            if not os.path.exists(file_out_dir):
                os.makedirs(file_out_dir, exist_ok=True)

        filename = os.path.join(file_out_dir, cnr + ".pdf")
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

    log.info("=" * 60)
    log.info("  srchigh — %s" % source_name)
    log.info("  Search: '%s'  |  %s" % (P["search"], " + ".join(modes)))
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
    if parts: log.info("  Filters: " + ", ".join(parts))
    log.info("  Output:  " + P["out"])
    log.info("=" * 60)

    fcourt = "3" if is_scr else "2"
    ec = ECourtSession(base_url=base_url, fcourt_type=fcourt)
    log.info("")
    log.info("[1] Establishing session...")
    await ec.client.get(base_url)
    log.info("[2] Solving captcha...")
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
    log.debug("     Token: " + token[:16] + "...")
    log.info("[3] Loading search page...")
    await ec.load_results_page(P["search"], mode=P["mode"])

    scr_params = _build_scr_params()
    page_size = min(P["count"], 25)
    if P["all"]:
        page_size = ALL_PAGE_SIZE
    for _ in range(3):
        await ec.get_results(P["search"], page=0, page_size=page_size, mode=P["mode"],
                             state_code=P["state"], proximity=P["proximity"],
                             **scr_params)
    test_entries, total, facets = await ec.get_results_with_facets(
        P["search"], page=0, page_size=page_size, mode=P["mode"],
        state_code=P["state"], proximity=P["proximity"],
        **scr_params,
    )

    # If --stats flag is set, print stats and exit (no PDF download).
    if P.get("stats"):
        log.info("")
        log.info("  " + "─" * 50)
        log.info("  STATS for '%s' (all 25 High Courts, no downloads)" % P["search"])
        log.info("  " + "─" * 50)
        log.info("    Total judgments:    %s" % "{:,}".format(total))
        log.info("")
        if facets.get("courts"):
            log.info("    Per-court breakdown (%d HCs with cases):" % len(facets["courts"]))
            log.info("")
            for i, (name, code, count) in enumerate(facets["courts"], 1):
                bar = "█" * min(40, int(40 * count / max(c for _, _, c in facets["courts"])))
                log.info("    %2d. %-38s [%2s] %6s  %s" % (
                    i, name, code, "{:,}".format(count), bar))
        if facets.get("years"):
            log.info("")
            log.info("    Per-year breakdown:")
            for year, count in facets["years"][:10]:
                log.info("      %s: %s" % (year, "{:,}".format(count)))
        await ec.close()
        return

    pages_to_fetch = []
    total_pages = 0
    if P["all"]:
        total_pages = (total // page_size) + 1 if total else 1
        total_pages = min(total_pages, MAX_PAGES_ALL)
        pages_to_fetch = list(range(total_pages))
    elif P["pages"]:
        pages_to_fetch = list(range(P["pages"][0], P["pages"][1]))
        total_pages = len(pages_to_fetch)
    else:
        pages_to_fetch = [P["page"]]
        total_pages = 1

    log.info("")
    log.info("  " + "─" * 45)
    if is_scr:
        any_scr = any(P.get(f) for f in ["citation_year", "citation_vol", "citation_supl", "citation_page", "ncn", "neu_cit_year", "neu_no"])
        scope = "1 filter set (%s)" % ", ".join(k for k in ["citation_year", "citation_vol", "citation_supl", "citation_page", "ncn", "neu_cit_year", "neu_no"] if P.get(k)) if any_scr else "all volumes / years"
        log.info("    Scope:           %s" % scope)
    else:
        if P["court"]:
            scope = "1 High Court (%s)" % P["court"]
        elif P["state"]:
            scope = "1 state (code %s)" % P["state"]
        else:
            scope = "all 25 High Courts"
        log.info("    Scope:           %s" % scope)
    log.info("    Total matching:  %s" % ("{:,}".format(total) if total else "?"))
    log.info("    Page size:       %d per page" % page_size)
    log.info("    Total pages:     %d" % total_pages)
    log.info("    Max downloads:   %d" % (total_pages * page_size))
    if P["all"] and total:
        eta = total_pages * page_size * 2
        if eta > 120:
            log.info("    Est. time:       ~%d min" % (eta // 60))
        else:
            log.info("    Est. time:       ~%d sec" % eta)
    log.info("  " + "─" * 45)

    downloaded_cnrs = set()
    if os.path.exists(P["out"]):
        for f in os.listdir(P["out"]):
            if f.endswith(".pdf"):
                downloaded_cnrs.add(f[:-4])
        log.info("     Already have %d PDFs in %s/" % (len(downloaded_cnrs), P["out"]))

    log.info("")
    log.info("[4] Fetching %d page(s)..." % len(pages_to_fetch))
    total_dl = 0
    dl_since_refresh = 0
    total_entries_stored = 0

    for pg in pages_to_fetch:
        try:
            dl_count, page_entries = await download_page(
                ec, pg, page_size, P["search"], P["out"], downloaded_cnrs, P["no_dl"]
            )
            total_dl += dl_count
            dl_since_refresh += dl_count
            
            if page_entries:
                cnrs = [e.get("cnr") for e in page_entries if e.get("cnr")]
                source = "scr" if P.get("scr") else "ecourts"
                existing = await db.check_existing_cnrs(cnrs, P["search"], source=source)
                
                await db.insert_judgments_batch(page_entries, P["search"], source=source)
                total_entries_stored += len(page_entries)
                
                if (P.get("all") or P.get("bulk_dump")) and existing >= len(page_entries) and len(page_entries) > 0:
                    log.info("  [Incremental] All %d cases on page already in DB. Stopping early." % existing)
                    break

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

    if total_entries_stored > 0:
        await db.upsert_search(P["search"], P["mode"], P["court"], total)
        log.info("  Stored %d entries in DB" % total_entries_stored)

    await ec.close()

    log.info("")
    log.info("=" * 60)
    if P["no_dl"]:
        log.info("  Done! %d results fetched. Use --download-db to download PDFs." % total_entries_stored)
    else:
        log.info("  Done! %d PDF(s) downloaded to %s/" % (total_dl, P["out"]))
    if P["csv"]:
        out_csv = os.path.join(P["out"], "_results.csv")
        source = "scr" if P.get("scr") else "ecourts"
        await db.export_to_csv(P["search"], out_csv, source=source)
        log.info("  Results exported to %s" % out_csv)
    log.info("=" * 60)


def _resolve_sci_dates():
    """Resolve SCI date parameters into (from_date, to_date) date objects."""
    from datetime import date as dt_date
    if P.get("from_date") and P.get("to_date"):
        return _parse_sci_date(P["from_date"]), _parse_sci_date(P["to_date"])
    if P.get("month_sci"):
        parts = P["month_sci"].split("-")
        y, m = int(parts[1]), int(parts[0])
        return _month_range(y, m)
    if P.get("year_sci"):
        y = int(P["year_sci"])
        return dt_date(y, 1, 1), dt_date(y, 12, 31)
    return None, None


async def run_sci_search():
    """Search SCI by date range, download PDFs organized by year/month."""
    from datetime import date as dt_date

    await db.init_db()

    from_dt, to_dt = _resolve_sci_dates()
    if not from_dt or not to_dt:
        log.error("SCI mode requires --from/--to, --month, or --year")
        return
    if from_dt > to_dt:
        log.error("from_date must be before to_date")
        return

    log.info("=" * 60)
    log.info("  srchigh — SCI Judgment Date")
    log.info("  Range: %s  →  %s" % (_fmt_date(from_dt), _fmt_date(to_dt)))
    base_out = os.path.expanduser("~/myJud/sci")
    log.info("  Output: %s/" % base_out)
    log.info("=" * 60)

    chunks = _split_date_range(from_dt, to_dt)
    log.info("\n  Splitting into %d chunk(s) (max %d days each)" % (len(chunks), 30))

    total_downloaded = 0
    total_found = 0

    for chunk_idx, (chunk_from, chunk_to) in enumerate(chunks, 1):
        log.info("\n" + "─" * 50)
        log.info("  Chunk %d/%d: %s  →  %s" % (chunk_idx, len(chunks),
                                               _fmt_date(chunk_from), _fmt_date(chunk_to)))

        ec = SCISession()
        log.info("  [1] Fetching homepage...")
        await ec.fetch_homepage()
        log.info("  [2] Solving captcha...")
        await ec.solve_captcha()
        log.info("  [3] Searching...")
        # Retry search with fresh captcha on captcha failure
        entries = []
        captcha_failed = False
        for sci_retry in range(5):
            entries, captcha_ok = await ec.search(chunk_from, chunk_to)
            if captcha_ok:
                break
            captcha_failed = True
            log.debug("    Captcha rejected, retrying with fresh session...")
            await ec.fresh()
            await ec.solve_captcha()

        if not entries:
            if captcha_failed:
                log.info("  No results after captcha retries exhausted.")
            else:
                log.info("  No judgments found for this date range.")
            await ec.close()
            continue

        total_found += len(entries)
        log.info("  Found %d judgment(s)" % len(entries))

        for idx, entry in enumerate(entries, 1):
            diary_no = entry.get("diary_no", "")
            pdf_url = entry.get("pdf_url", "")
            label = entry.get("case_no", "") or entry.get("diary_no", "")
            log.debug("\n  [%d/%d] %s" % (idx, len(entries), label))

            # Extract judgment date from PDF filename like "..._Judgement_02-Jan-2024.pdf"
            dec_date = ""
            if pdf_url:
                dm = re.search(r'Judgement_(\d{2}-[A-Z][a-z]+-\d{4})\.pdf', pdf_url)
                if dm:
                    dec_date = dm.group(1)

            # Parse date for folder organization: ~/myJud/sci/<year>/<month>/
            try:
                d = _parse_sci_date(dec_date) if dec_date else chunk_from
            except (ValueError, IndexError):
                d = chunk_from
            month_dir = os.path.join(base_out, str(d.year), "%02d" % d.month)

            # Safe filename from diary_no (which may contain /)
            safe_name = diary_no.replace("/", "_").replace(" ", "_")
            pdf_path = os.path.join(month_dir, "%s.pdf" % safe_name)

            # Skip if already downloaded
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
                log.debug("    Already exists, skipping")
                continue

            if pdf_url:
                log.debug("    Downloading PDF...")
                sz = await ec.download_pdf(pdf_url, pdf_path)
                if sz > 1000:
                    log.debug("    OK (%d bytes)" % sz)
                    total_downloaded += 1
                else:
                    log.debug("    Failed (empty or invalid)")
            else:
                log.debug("    No PDF URL found in details")

        await ec.close()

    log.info("\n" + "=" * 60)
    log.info("  Done! %d PDF(s) downloaded to %s/" % (total_downloaded, base_out))
    log.info("  Total judgments found: %d" % total_found)
    if P["csv"] and total_found:
        if P.get("out"):
            out_csv = os.path.join(P["out"], "_results.csv")
        else:
            safe_term = re.sub(r"[^a-zA-Z0-9]+", "_", P.get("search", "")).strip("_").lower() or "all_judgments"
            out_csv = os.path.join(os.path.expanduser("~/myJud"), safe_term, "_results.csv")
        source = "scr" if P.get("scr") else "ecourts"
        await db.export_to_csv(P.get("search", ""), out_csv, source=source)
        log.info("  CSV exported to: %s" % out_csv)
    log.info("=" * 60)


async def run_download_db():
    await db.init_db()
    log.info("=" * 60)
    log.info("  eCourts India — Download from DB")
    log.info("=" * 60)
    log.info("")
    await download_from_db(search_term=P.get("search", ""), out_dir=P.get("out"))
    log.info("")
    log.info("=" * 60)
    log.info("  Done!")
    log.info("=" * 60)


async def run_status():
    await db.init_db()
    search_term = P.get("search", "")
    stats = await db.get_stats(search_term)
    entries = await db.get_all_judgments(search_term) if search_term else []
    log.info("=" * 60)
    log.info("  DB Status for: %s" % (search_term or "all searches"))
    log.info("=" * 60)
    log.info("  Total judgments:  %d" % stats["total"])
    log.info("  Downloaded:      %d" % stats["downloaded"])
    log.info("  Pending:         %d" % stats["pending"])
    if entries:
        log.info("")
        log.info("  Recent entries:")
        for e in entries[:10]:
            dl = "✓" if e.get("downloaded") else "✗"
            log.info("    [%s] %s | %s" % (dl, e.get("cnr", "?"), e.get("case_title", "?")[:50]))
    log.info("=" * 60)


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

    if P.get("clear_db"):
        log.info("Clearing database...")
        import aiosqlite
        from srchigh.db import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM judgments")
            await db.execute("DELETE FROM searches")
            await db.execute("DELETE FROM download_log")
            await db.commit()
            await db.execute("VACUUM")
        log.info("Database cleared successfully!")
        sys.exit(0)

    if P.get("sci"):
        await run_sci_search()
    elif P["status"]:
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