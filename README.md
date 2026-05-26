# srchigh — eCourts India High Court Judgments Scraper

**Search, filter, export metadata, and download judgments from all Indian High Courts.**

Reverse-engineers the [eCourts PDF Search](https://judgments.ecourts.gov.in/pdfsearch/) portal to provide a programmatic interface for bulk downloading High Court judgments. Handles captcha solving, session rotation, pagination, and rate-limiting automatically.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
  - [Search Modes](#search-modes)
  - [Court Filtering](#court-filtering)
  - [Pagination](#pagination)
  - [CSV Export](#csv-export)
  - [Batch Download from CSV](#batch-download-from-csv)
- [First-Run Setup](#first-run-setup)
- [Project Structure](#project-structure)
- [Captcha Solving](#captcha-solving)
- [Session Rotation](#session-rotation)
- [Common Workflows](#common-workflows)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Building a Standalone Binary](#building-a-standalone-binary)
- [Technical Architecture](#technical-architecture)
- [License](#license)

---

## How It Works

The eCourts portal is a PHP MVC application with server-side DataTables. Judgments are **not directly accessible** — they must be retrieved through a multi-step flow:

```
   Browser / srchigh
         │
         ▼
┌────────────────────┐
│  1. Homepage GET   │  →  Establish PHP session cookie
│  /pdfsearch/       │  →  Get CSRF token (app_token)
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  2. Captcha Image  │  →  Download Securimage PNG
│  securimage_show   │  →  OCR with Tesseract (7 thresholds)
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  3. Validate       │  →  POST captcha + search term
│  checkCaptcha      │  →  Receive app_token
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  4. Search Results │  →  GET pdf_search/home with params
│  (GET)             │  →  Server caches search context
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  5. DataTable POST │  →  Server-side pagination via
│  pdf_search/home   │     iDisplayStart, iDisplayLength
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  6. PDF Download   │  →  POST openpdfcaptcha with
│  openpdfcaptcha    │     judgment path from step 5
└────────┬───────────┘
         │
         ▼
      ┌─────┐
      │ PDF │  ←  Temporary URL returned by server
      └─────┘
```

**Key insight:** The server ignores `search_txt` and filters by **`search_txt1`** (the "search within results" / FTS1 field). The JavaScript moves the keyword from the main field to FTS1 on page load.

---

## Prerequisites

| Dependency | Required for | Install |
|---|---|---|
| **Python 3.9+** | Runtime | `brew install python` / `apt install python3` |
| **Tesseract OCR** | Captcha solving | `brew install tesseract` / `apt install tesseract-ocr` |
| **Pip modules** | All functionality | `pip3 install -r requirements.txt` |

### Installing Tesseract

```bash
# macOS
brew install tesseract

# Ubuntu / Debian
sudo apt install tesseract-ocr

# Fedora / RHEL
sudo dnf install tesseract

# Arch Linux
sudo pacman -S tesseract

# Windows
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
```

Verify installation:

```bash
tesseract --version
# → tesseract 5.x
```

---

## Installation

### Option 1: Direct run (no install, always works)

```bash
git clone <repo-url> ~/srchigh
cd ~/srchigh
pip3 install -r requirements.txt
python3 main.py "divorce" 5
```

### Option 2: System-wide install (`srchigh` command)

```bash
cd ~/srchigh
pip3 install -e .
srchigh "divorce" 5 --court bombay
```

### Option 3: Makefile

```bash
cd ~/srchigh
make install
srchigh "divorce" 5
```

### Option 4: Install script

```bash
cd ~/srchigh
bash install.sh
```

---

## Quick Start

```bash
# Search and download 5 "divorce" judgments
srchigh "divorce" 5

# Search + court filter + download
srchigh "divorce" 5 --court bombay

# Export ALL results as CSV (no PDFs)
srchigh "divorce" --court bombay --all --csv --no-download

# Download PDFs from a previously saved CSV
srchigh --from-csv ~/myJud/divorce

# Get help
srchigh
```

**Output** lands in `~/myJud/<search_term>/` by default (e.g., `~/myJud/divorce/`).

---

## Usage Guide

### Basic options

```
srchigh <search_term> [count] [options]

Positional:
  search_term           Keyword to search (required)
  count                 Number of results per page (default: 5)

Options:
  --court NAME          Filter by High Court
  --mode MODE           Search mode: PHRASE | ANY | ALL (default: PHRASE)
  --proximity N         Word proximity for ALL mode (20-100, default: 40)
  --page N              Page number (default: 0)
  --pages M:N           Page range (e.g. 0:10)
  --all                 Fetch ALL matching results (paginates automatically)
  --csv                 Export results as CSV
  --no-download         Skip PDF download, show/list only
  --from-csv DIR        Download PDFs from a saved CSV
  --state CODE          Filter by state code (numeric)
  --judge NAME          Filter by judge name
  --from DATE           Start date DD-MM-YYYY
  --to DATE             End date DD-MM-YYYY
  --out DIR             Output directory (default: ~/myJud/<search_term>)
```

### Search Modes

The eCourts portal supports three search modes, matching the radio buttons on the website:

| Flag | Website Label | Behavior | Proximity? |
|---|---|---|---|
| `--mode PHRASE` (default) | **Phrase(s)** | Exact phrase match — "divorce custody" finds that exact phrase | No |
| `--mode ANY` | **Any Words** | OR search — finds judgments with "divorce" OR "custody" | No |
| `--mode ALL` | **All Words** | AND search — finds judgments with "divorce" AND "custody" | Yes, default 40 |

```bash
# Exact phrase (default)
srchigh "anticipatory bail" 5

# Any word (OR)
srchigh "divorce custody" 5 --mode any

# All words (AND) with proximity 40 (default)
srchigh "divorce custody" 5 --mode all

# All words with custom proximity (words must be within 20 of each other)
srchigh "divorce custody" 5 --mode all --proximity 20
```

**Proximity** controls how close the words must be in the judgment text. Values: 20, 40, 60, 80, 100. Lower = closer. Only applies to `--mode ALL`.

### Court Filtering

Filter by High Court using the `--court` flag. This uses the server-side numeric state codes discovered by reverse-engineering the court filter sidebar.

```bash
srchigh "divorce" 5 --court bombay      # Bombay High Court
srchigh "divorce" 5 --court delhi       # Delhi High Court
srchigh "divorce" 5 --court kerala      # Kerala High Court
srchigh "divorce" 5 --court patna       # Patna High Court (Bihar)
srchigh "divorce" 5 --court gujarat     # Gujarat High Court
srchigh "divorce" 5 --court allahabad   # Allahabad High Court
```

**Available courts:**

```
allahabad, andhra pradesh, bombay, calcutta, chhattisgarh, delhi,
gauhati, gujarat, himachal pradesh, jammu & kashmir, jharkhand,
karnataka, kerala, madras, meghalaya, orissa, patna (bihar),
punjab & haryana, rajasthan, sikkim, telangana, tripura, uttarakhand
```

The matching is case-insensitive and substring-based (`bombay` matches all Bombay benches).

### Pagination

```bash
# First page (default)
srchigh "divorce" 5 --page 0

# Specific page
srchigh "divorce" 5 --page 100

# Page range (pages 0 through 4)
srchigh "divorce" 5 --pages 0:5

# ALL results (up to 12,500 = 500 pages × 25/page)
srchigh "divorce" --court bombay --all
```

With `--all`, the script automatically paginates through every page of results. Page size is set to **200** (for speed) and capped at **500 pages** (12,500 judgments) to avoid abuse.

### CSV Export

Export search results as a structured CSV file without downloading PDFs:

```bash
srchigh "divorce" 50 --court bombay --csv --no-download
```

This creates `~/myJud/divorce/_results.csv` with columns:

| Column | Description | Example |
|---|---|---|
| **CNR** | Unique case number | `HCBM030439682025` |
| **Case Title** | Party names and case number | `APPLN/4098/2025 of PRABHABAI...` |
| **Court** | High Court name | `Bombay High Court` |
| **Judge** | Presiding judge(s) | `HON'BLE SHRI JUSTICE SANDIPKUMAR C. MORE...` |
| **Reg Date** | Date of registration | `29-10-2025` |
| **Decision Date** | Date of decision | `23-12-2025` |
| **Disposal Nature** | Case outcome | `DISPOSED OFF`, `DISMISSED`, `ALLOWED` |
| **PDF Path** | Server-side path for download | `court/cnrorders/hcaurdb/orders/HCBM...pdf` |

### Batch Download from CSV

A two-step workflow for reliable large-scale downloads:

**Step 1 — Export metadata (fast, no PDFs):**

```bash
srchigh "divorce" --court bombay --all --csv --no-download
```
→ Creates `~/myJud/divorce/_results.csv` with up to 12,500 entries

**Step 2 — Download PDFs from CSV (with session rotation):**

```bash
srchigh --from-csv ~/myJud/divorce
```

This reads the CSV and downloads each PDF using the stored path. Features:
- Rotates PHP session every 20 downloads (avoids rate-limiting)
- Skips already-downloaded files (by CNR)
- Can be interrupted and resumed — re-running skips existing files
- Works from any machine — just copy the CSV

---

## First-Run Setup

On the very first execution, srchigh runs a one-time setup:

```bash
╔══════════════════════════════════════════════════════╗
║            srchigh — eCourts Judgments              ║
║     Indian High Court Judgments Downloader v2.0     ║
╚══════════════════════════════════════════════════════╝

  ✓ Output directory: /Users/you/myJud
  ✓ Config saved to: ~/.config/srchigh/config.json
```

- Checks if **Tesseract OCR** is installed (warns if missing)
- Creates **`~/.config/srchigh/config.json`** with defaults
- Creates **`~/myJud/`** output directory
- Creates a **`.first_run_done`** marker file

### Config file (`~/.config/srchigh/config.json`)

```json
{
  "default_court": "",
  "default_count": 5,
  "default_mode": "PHRASE",
  "show_welcome": true
}
```

Edit this file to set persistent preferences. For example, setting `"default_court": "bombay"` means you can run `srchigh "divorce" 5` without `--court bombay` every time.

---

## Project Structure

```
~/srchigh/
├── src/srchigh/             # ← pip-installable Python package
│   ├── __init__.py
│   ├── config.py            # Constants, court codes, first-run detection
│   ├── session.py           # ECourtSession — captcha, search, PDF download
│   ├── parser.py            # CSS-selector-based HTML parsing (parsel)
│   ├── export.py            # CSV read/write
│   ├── download.py          # Batch download from saved CSV
│   └── main.py              # CLI entry point + arg parsing
├── main.py                  # Convenience runner (python3 main.py)
├── setup.py                 # pip install configuration
├── pyproject.toml           # Modern Python packaging
├── requirements.txt         # Dependencies
├── Makefile                 # make install / make test / make binary
├── install.sh               # One-command install script
├── README.md                # This file
└── tests/                   # 74+ tests (pytest)
    ├── conftest.py          # Test fixtures with realistic HTML samples
    ├── test_config.py       # Court code mappings (8 tests)
    ├── test_parser.py       # HTML parsing (23 tests)
    ├── test_export.py       # CSV read/write (10 tests)
    ├── test_session.py      # Integration tests — real server (10 tests)
    └── test_smoke.py        # CLI args, imports, flags (20 tests)
```

---

## Captcha Solving

The eCourts portal uses **Securimage**, a PHP CAPTCHA library that generates distorted text images (215×70 PNG). The solving pipeline:

### 1. Download
```python
cr = session.get("vendor/securimage/securimage_show.php")
```

### 2. OCR with multiple preprocessing passes

Tesseract alone can't reliably read Securimage. We try **7 different binarization thresholds** to handle varying contrast and noise:

```python
for thresh in (110, 120, 130, 140, 150, 160, 170):
    bw = gray.point(lambda x: 0 if x < thresh else 255)
    text = pytesseract.image_to_string(bw, config="--psm 8 ...")
```

| Step | Purpose |
|---|---|
| Grayscale | Remove color noise |
| Threshold (×7) | Convert to pure black/white at 7 different cutoffs |
| OCR | Read binarized image, alphanumeric chars only |
| Filter | Strip non-alphanumeric garbage |
| Validate length | Must be 4-6 characters (Securimage standard) |

### 3. Validate against server

Each unique OCR guess is POSTed to `checkCaptcha`. The server responds with `captcha_status: "Y"` or `"N"`.

### 4. Retry loop

Up to **30 attempts**, with session refresh every 5 failures. Success rate: **~90% within 1-3 tries**.

### Why not a captcha service?

| Method | Accuracy | Cost |
|---|---|---|
| Tesseract OCR (current) | ~90% | Free |
| 2captcha / Anti-Captcha | ~99% | ~$0.002/solve |
| Manual input | 100% | User must be present |

The Tesseract approach is free, offline, and fast enough for automation.

### Why not Scrapling's `solve_cloudflare`?

Scrapling handles **Cloudflare Turnstile** (a JS challenge). The eCourts site uses **Securimage** (a server-generated image captcha). Different technology, so we still need Tesseract.

---

## Session Rotation

When downloading many PDFs, the server may rate-limit or expire the session. The script automatically rotates sessions every **20 downloads**:

```
  [1/11937] HCBM030439682025...
  [2/11937] HCBM030304852022...
  ...
  === Rotating session (20 downloads reached) ===
  ✓ Captcha solved: 'a3k9' (attempt 1)
  [21/11937] HCBM...
```

Each rotation:
1. Destroys the old `requests.Session()` (clears cookies)
2. Creates a new session with fresh Chrome TLS fingerprint
3. Solves a new captcha
4. Continues from where it left off

This prevents the server from blocking bulk downloads.

---

## Common Workflows

### Quick batch of a specific court

```bash
srchigh "divorce" 10 --court bombay
# → 10 PDFs in ~/myJud/divorce/
```

### Large-scale metadata export

```bash
srchigh "divorce" --court bombay --all --csv --no-download
# → ~/myJud/divorce/_results.csv with 11,937 entries
```

### Reliable full download (two-step)

```bash
# Step 1: Export (fast)
srchigh "divorce" --court bombay --all --csv --no-download

# Step 2: Download (with session rotation, resumable)
srchigh --from-csv ~/myJud/divorce
```

### Filter by date range

```bash
srchigh "divorce" 5 --court bombay --from 01-01-2024 --to 31-12-2024
```

### Multiple search terms (OR mode)

```bash
srchigh "divorce custody maintenance" 10 --mode any
```

### Specific judge

```bash
srchigh "divorce" 5 --court bombay --judge "SANDIPKUMAR"
```

---

## Troubleshooting

### "Tesseract not found"

```bash
# macOS
brew install tesseract

# Ubuntu
sudo apt install tesseract-ocr

# Verify
tesseract --version
```

### "Captcha failed after 30 tries"

The OCR couldn't read the captcha. This happens ~10% of the time. Try:
1. Run the command again — a fresh captcha will be served
2. Ensure Tesseract is properly installed (`tesseract --version`)
3. Check that the captcha image is downloading correctly (network issues)

### "403 Access Denied"

The PHP session expired or the CSRF token is invalid. The script auto-recovers by creating a fresh session, but if it persists:
1. Check your internet connection
2. The eCourts server might be blocking your IP (too many requests)
3. Try again after a few minutes

### "0 results / empty CSV"

1. The search term might be too specific — try a broader term
2. The court filter might be too restrictive — try without `--court`
3. Check that the eCourts website is accessible in your browser

### "PDF download failed"

Temporary PDF URLs expire. The script retries automatically, but if it consistently fails:
1. Run `--from-csv` again — it skips already-downloaded files
2. The eCourts server might be temporarily unavailable

### Permission errors during install

```bash
# macOS system Python — use --user flag
pip3 install --user -r requirements.txt
pip3 install --user -e .

# Or use python3 main.py directly (no pip install needed)
python3 main.py "divorce" 5
```

---

## Testing

The project has **74 tests** across unit, smoke, and integration layers.

### Run all tests (no network needed for most)

```bash
cd ~/srchigh
python3 -m pytest tests/ -v
```

### Run only fast unit tests

```bash
python3 -m pytest tests/test_config.py tests/test_parser.py tests/test_export.py -v
```

### Run integration tests (requires network + captcha solving)

```bash
python3 -m pytest tests/test_session.py -v --network
```

### Test coverage

| Test file | Count | Type | What it covers |
|---|---|---|---|
| `test_config.py` | 8 | Unit | Court code mappings, bidirectional lookup |
| `test_parser.py` | 23 | Unit | HTML parsing, CSS selector extraction |
| `test_export.py` | 10 | Unit | CSV read/write, headers, edge cases |
| `test_session.py` | 10 | Integration | Real server: homepage, captcha, search, pagination, PDF download |
| `test_smoke.py` | 20 | Smoke | Module imports, CLI arg parsing, flag handling |
| **Total** | **71+** | | |

---

## Building a Standalone Binary

You can build a single executable file with PyInstaller. Note: **Tesseract must still be installed** on the target machine (it can't be bundled).

```bash
cd ~/srchigh
make binary
# → dist/srchigh — standalone executable
```

Or manually:

```bash
pip3 install pyinstaller
pyinstaller --onefile --name srchigh src/srchigh/main.py
./dist/srchigh "divorce" 5 --court bombay
```

The binary bundles Python, all pip dependencies, and the application code into a single file you can copy to any macOS/Linux machine.

---

## Technical Architecture

### Module responsibilities

| Module | Responsibility | Key class/function |
|---|---|---|
| `config.py` | Constants, court codes, first-run detection, config persistence | `load_config()`, `first_run_setup()` |
| `session.py` | HTTP session, captcha solving, search, PDF download | `ECourtSession` |
| `parser.py` | HTML parsing from DataTable responses | `parse_entry()`, `parse_results_page()` |
| `export.py` | CSV read/write | `write_results_csv()`, `read_results_csv()` |
| `download.py` | Batch download from saved CSV | `download_from_csv()` |
| `main.py` | CLI entry point, arg parsing, main orchestration | `run_cli()`, `parse_args()`, `download_page()` |

### Dependencies

| Package | Purpose | Alternative |
|---|---|---|
| `requests` | HTTP client | `httpx`, `aiohttp` |
| `Pillow` | Image processing for captcha | `opencv-python` |
| `pytesseract` | OCR engine binding | — |
| `parsel` | CSS/XPath selectors for HTML parsing | `BeautifulSoup`, `lxml` |
| `cssselect` | CSS selector → XPath translation | (parsel dependency) |

### Anti-bot measures handled

1. **CAPTCHA** — Securimage solved via Tesseract OCR
2. **CSRF tokens** — `app_token` extracted from every response, sent with every request
3. **Session cookies** — `JUDGEMENTSSEARCH_SESSID` maintained via `requests.Session()`
4. **Rate limiting** — Session rotation every 20 downloads
5. **TLS fingerprinting** — Chrome 120+ headers (`Sec-Ch-Ua`, `Sec-Fetch-*`)
6. **Optional Scrapling** — Even better stealth if `scrapling` is installed

---

## License

MIT
