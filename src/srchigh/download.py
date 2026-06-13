"""
Concurrent batch download — download PDFs from DB using asyncio concurrency.
Uses a semaphore to limit parallel downloads and session rotation.
"""

import asyncio
import os
import re
import logging

from .config import DOWNLOADS_PER_SESSION, BASE_URL, SCR_BASE_URL
from .session import ECourtSession
from . import db

log = logging.getLogger(__name__)

MAX_CONCURRENT = 5
_stats_lock = asyncio.Lock()


async def _run_session(ec, search_term):
    await ec.client.get(ec.base_url)
    ct, tk = await ec.solve_captcha(search_text=search_term)
    r = await ec.client.get(
        ec.base_url + "?p=pdf_search/home&text=" + search_term + "&captcha=" + ct +
        "&search_opt=PHRASE&fcourt_type=%s&app_token=" % ec.fcourt_type + tk,
    )
    m = re.search(r'app_token=([^\"&\\s<>]+)', r.text)
    if m:
        ec.app_token = m.group(1)
    for _ in range(3):
        await ec.get_results(search_term, page=0, page_size=5)


async def download_from_db(search_term="", out_dir=None, max_results=1000, source=None):
    if out_dir is None:
        out_dir = os.path.join(os.path.expanduser("~"), "myJud", search_term or "download")
    os.makedirs(out_dir, exist_ok=True)

    entries = await db.get_undownloaded(search_term, limit=max_results)
    if not entries:
        log.info("  No undownloaded entries in DB for '%s'" % search_term)
        return None

    # Detect source from first entry if not given
    if source is None:
        source = entries[0].get("source", "ecourts") if entries else "ecourts"
    base_url = SCR_BASE_URL if source == "scr" else BASE_URL
    fcourt = "3" if source == "scr" else "2"

    log.info("  Loaded %d undownloaded entries from DB (%s)" % (len(entries), source))

    already = set()
    for f in os.listdir(out_dir):
        if f.endswith(".pdf"):
            already.add(f[:-4])

    filtered = [e for e in entries if e.get("cnr") not in already]
    log.info("  %d to download after skipping existing" % len(filtered))

    stats = {"downloaded": 0, "failed": 0, "skipped": 0}

    ec = ECourtSession(base_url=base_url, fcourt_type=fcourt)
    dl_count = 0
    await _run_session(ec, search_term)

    # Open a single persistent DB connection to reuse across updates
    import aiosqlite
    from .db import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db_conn:
        chunk_size = MAX_CONCURRENT
        for i in range(0, len(filtered), chunk_size):
            chunk = filtered[i:i+chunk_size]

            # Step 1: Fetch PDF URLs sequentially
            fetch_tasks = []
            for entry in chunk:
                # check if session rotation is needed
                if dl_count >= DOWNLOADS_PER_SESSION:
                    log.info("  === Rotating session (%d downloads) ===" % DOWNLOADS_PER_SESSION)
                    await ec.close()
                    ec = ECourtSession(base_url=base_url, fcourt_type=fcourt)
                    await _run_session(ec, search_term)
                    dl_count = 0

                cnr = entry.get("cnr", "")
                if not cnr:
                    cnr = entry.get("case_title", "?")[:40].replace("/", "_").replace(" ", "_")
                filename = os.path.join(out_dir, cnr + ".pdf")

                # Check if file already exists
                if os.path.exists(filename) and os.path.getsize(filename) > 1000:
                    async with _stats_lock:
                        stats["skipped"] += 1
                    continue

                log.info("    [%s] Fetching URL for %s..." % (search_term[:20], cnr))
                url = await ec.get_pdf_url(entry)
                if not url:
                    async with _stats_lock:
                        stats["failed"] += 1
                    continue

                fetch_tasks.append((entry, url, filename, cnr))
                dl_count += 1

            if not fetch_tasks:
                continue

            # Step 2: Download the PDFs concurrently in the current chunk
            async def download_one_file(entry, url, filename, cnr):
                sz = await ec.download_pdf(url, filename)
                if sz > 1000:
                    pdf_path = entry.get("pdf_path") or entry.get("path", "")
                    await db.mark_downloaded(cnr, sz, search_term, conn=db_conn)
                    await db.log_download(cnr, pdf_path, search_term, True, sz, conn=db_conn)
                    async with _stats_lock:
                        stats["downloaded"] += 1
                else:
                    if os.path.exists(filename):
                        try:
                            os.remove(filename)
                        except OSError:
                            pass
                    async with _stats_lock:
                        stats["failed"] += 1

            tasks = [download_one_file(entry, url, filename, cnr) for entry, url, filename, cnr in fetch_tasks]
            await asyncio.gather(*tasks)

            # Print progress periodically
            completed_count = min(i + chunk_size, len(filtered))
            if completed_count % 50 == 0 or completed_count == len(filtered):
                log.info("    progress: %d/%d (downloaded=%d, failed=%d, skipped=%d)" % (
                    completed_count, len(filtered), stats["downloaded"], stats["failed"], stats["skipped"]))

    await ec.close()
    log.info("  Downloaded %d PDFs to %s/ (failed=%d)" % (
        stats["downloaded"], out_dir, stats["failed"]))
    return stats