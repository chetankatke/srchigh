"""
eCourts India — High Court Judgments Scraper
Configuration and constants.
"""

BASE_URL = "https://judgments.ecourts.gov.in/pdfsearch/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Numeric state_code → High Court name (from server-side court filter)
COURT_CODES = {
    1: "jammu & kashmir",
    2: "himachal pradesh",
    3: "punjab & haryana",
    5: "uttarakhand",
    7: "delhi",
    8: "rajasthan",
    9: "allahabad",
    10: "patna (bihar)",
    11: "sikkim",
    16: "tripura",
    17: "meghalaya",
    18: "gauhati",
    19: "calcutta",
    20: "jharkhand",
    21: "orissa",
    22: "chhattisgarh",
    24: "gujarat",
    27: "bombay",
    28: "andhra pradesh",
    29: "karnataka",
    32: "kerala",
    33: "madras",
    36: "telangana",
}

# Lowercase name → numeric code (reverse lookup)
COURT_NAMES = {v: k for k, v in COURT_CODES.items()}

# Search mode labels
MODE_LABELS = {"PHRASE": "Phrase(s)", "ANY": "Any Words", "ALL": "All Words"}

# Session rotation
DOWNLOADS_PER_SESSION = 20
ALL_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 25
MAX_PAGES_ALL = 500
