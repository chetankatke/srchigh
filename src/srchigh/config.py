"""
eCourts India — High Court Judgments Scraper
Configuration, first-run detection, and user preferences.
"""

import json
import os
import shutil
import sys

# ── Constants ──

BASE_URL = "https://judgments.ecourts.gov.in/pdfsearch/"
SCR_BASE_URL = "https://scr.sci.gov.in/scrsearch/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SOURCE_LABELS = {
    "ecourts": "High Court (eCourts)",
    "scr": "Supreme Court (SCR)",
    "sci": "SCI Judgment Date",
}

# Numeric state_code → High Court name
COURT_CODES = {
    1: "jammu & kashmir", 2: "himachal pradesh", 3: "punjab & haryana",
    5: "uttarakhand", 7: "delhi", 8: "rajasthan", 9: "allahabad",
    10: "patna (bihar)", 11: "sikkim", 16: "tripura", 17: "meghalaya",
    18: "gauhati", 19: "calcutta", 20: "jharkhand", 21: "orissa",
    22: "chhattisgarh", 24: "gujarat", 27: "bombay",
    28: "andhra pradesh", 29: "karnataka", 32: "kerala",
    33: "madras", 36: "telangana",
}
COURT_NAMES = {v: k for k, v in COURT_CODES.items()}

MODE_LABELS = {"PHRASE": "Phrase(s)", "ANY": "Any Words", "ALL": "All Words"}

DOWNLOADS_PER_SESSION = 20
ALL_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 25
MAX_PAGES_ALL = 500

# ── Config paths ──

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "srchigh")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
FIRST_RUN_FILE = os.path.join(CONFIG_DIR, ".first_run_done")


# ── Default settings ──

DEFAULT_CONFIG = {
    "default_court": "",
    "default_count": 5,
    "default_mode": "PHRASE",
    "show_welcome": True,
}


# ── Config read/write ──

def load_config():
    """Load user config from ~/.config/srchigh/config.json."""
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def save_config(config):
    """Save user config to ~/.config/srchigh/config.json."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


# ── First-run detection ──

def is_first_run():
    """Return True if this is the first time running srchigh."""
    return not os.path.exists(FIRST_RUN_FILE)


def mark_first_run_done():
    """Create marker file so subsequent runs are not 'first'."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(FIRST_RUN_FILE, "w") as f:
        f.write("1")


# ── System checks ──

def check_tesseract():
    """Return (installed: bool, path: str or None, version: str or None)."""
    path = shutil.which("tesseract")
    if not path:
        return False, None, None
    import subprocess
    try:
        out = subprocess.check_output(["tesseract", "--version"], stderr=subprocess.STDOUT,
                                       timeout=10).decode().strip()
        version = out.split("\n")[0] if out else "unknown"
        return True, path, version
    except Exception:
        return True, path, "unknown"


def check_python():
    """Return Python version string."""
    return sys.version.split()[0]


# ── First-run welcome ──

WELCOME = r"""
╔══════════════════════════════════════════════════════╗
║            srchigh — eCourts Judgments              ║
║     Indian High Court Judgments Downloader v2.0     ║
╚══════════════════════════════════════════════════════╝

  First-time setup complete. Configuration saved to:
    ~/.config/srchigh/config.json

  Quick start:
    srchigh "divorce" 5
    srchigh "divorce" 5 --court bombay
    srchigh "divorce" --court bombay --all --csv --no-download

  Need help?
    srchigh

  Happy scraping! ⚖️
"""


def first_run_setup():
    """Run first-time configuration checks and setup."""
    print(WELCOME)

    # Check tesseract
    installed, path, ver = check_tesseract()
    if not installed:
        print("  ⚠  Tesseract OCR not found!")
        print("     Captcha solving requires tesseract.")
        print("     Install with:")
        print("       macOS: brew install tesseract")
        print("       Ubuntu: sudo apt install tesseract-ocr")
        print("       Fedora: sudo dnf install tesseract")
        print()

    # Create default output dir
    default_out = os.path.expanduser("~/myJud")
    os.makedirs(default_out, exist_ok=True)
    print("  ✓ Output directory: %s" % default_out)

    # Save config
    save_config(DEFAULT_CONFIG)
    mark_first_run_done()
    print("  ✓ Config saved to: %s" % CONFIG_FILE)
    print()


# ── Merge config with CLI params ──

def apply_config_to_params(params):
    """Merge saved config into CLI params for any unset values."""
    cfg = load_config()
    if not params.get("court") and cfg.get("default_court"):
        params["court"] = cfg["default_court"]
    if params.get("count") == 5 and cfg.get("default_count") != 5:
        params["count"] = cfg["default_count"]
    return params
