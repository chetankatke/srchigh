"""
Batch download — download PDFs from a previously saved _results.csv.
Uses openpdfcaptcha with the stored PDF path.
"""

import os
import re
import logging

from config import DOWNLOADS_PER_SESSION, BASE_URL
from session import ECourtSession
from export import read_results_csv

log = logging.getLogger(__name__)


def download_from_csv(csv_dir):
    """Read _results.csv and download all PDFs listed in it.
    
    Session is rotated every DOWNLOADS_PER_SESSION files 
    to avoid rate-limiting.
    """
    csv_path = os.path.join(csv_dir, "_results.csv")
    entries = read_results_csv(csv_path)
    if entries is None:
        log.error("  _results.csv not found in %s" % csv_dir)
        return
    if not entries:
        log.error("  No entries in CSV")
        return

    log.info("  Loaded %d entries from %s" % (len(entries), csv_path))
    os.makedirs(csv_dir, exist_ok=True)

    # Files already on disk
    already = set()
    for f in os.listdir(csv_dir):
        if f.endswith(".pdf"):
            already.add(f[:-4])

    ec = ECourtSession()
    total_dl = 0
    dl_since = 0

    for idx, entry in enumerate(entries):
        cnr = entry.get("CNR", "").replace("/", "_").replace(" ", "_")
        if not cnr:
            cnr = "jd_%d" % idx
        pdf_path = entry.get("PDF Path", "")

        filename = os.path.join(csv_dir, cnr + ".pdf")

        # Skip if already downloaded
        if cnr in already or (
            os.path.exists(filename) and os.path.getsize(filename) > 1000
        ):
            if idx % 50 == 0:
                log.info("    (%d/%d skipped, %d downloaded)" % (
                    idx, len(entries), total_dl))
            continue

        log.info("    [%d/%d] %s..." % (idx + 1, len(entries), cnr))

        # Rotate session every N downloads
        if dl_since >= DOWNLOADS_PER_SESSION:
            log.info("     Rotating session...")
            ec = ECourtSession()
            dl_since = 0

        # Fresh session init
        if dl_since == 0:
            ec.s.get(BASE_URL, timeout=30)
            ct, tk = ec.solve_captcha()
            r = ec.s.get(
                BASE_URL + "?p=pdf_search/home&text=_batch&captcha=" + ct +
                "&search_opt=PHRASE&fcourt_type=2&app_token=" + tk,
                timeout=30,
            )
            m = re.search(r'app_token=([^"&\s<>]+)', r.text)
            if m:
                ec.app_token = m.group(1)
            for _ in range(3):
                ec.get_results("_batch", page=0, page_size=5)

        url = ec.get_pdf_url_for_path(pdf_path)
        if url:
            sz = ec.download_pdf(url, filename)
            if sz > 1000:
                total_dl += 1
                dl_since += 1
            else:
                safe_remove(filename)
        else:
            log.info("       Could not get PDF URL")

    log.info("  Downloaded %d PDFs to %s/" % (total_dl, csv_dir))


def safe_remove(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
