"""
CSV export — write search results metadata to _results.csv
"""

import csv
import os


CSV_HEADERS = [
    "CNR", "Case Title", "Court", "Judge",
    "Reg Date", "Decision Date", "Disposal Nature", "PDF Path",
]


def write_results_csv(out_dir, all_entries):
    """Write _results.csv with all collected entries."""
    if not all_entries:
        return None
    csv_path = os.path.join(out_dir, "_results.csv")
    os.makedirs(out_dir, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADERS)
        for e in all_entries:
            w.writerow([
                e.get("cnr", ""),
                e.get("case_title", ""),
                e.get("court", ""),
                e.get("judge", ""),
                e.get("reg_date", ""),
                e.get("decision_date", ""),
                e.get("disposal_nature", ""),
                e.get("path", ""),
            ])
    return csv_path


def read_results_csv(csv_path):
    """Load entries from an existing _results.csv."""
    if not os.path.exists(csv_path):
        return None
    entries = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(dict(row))
    return entries
