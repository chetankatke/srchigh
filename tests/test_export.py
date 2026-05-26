"""Unit tests for export.py — CSV read/write."""

import os
import tempfile
import pytest
from srchigh.export import write_results_csv, read_results_csv, CSV_HEADERS


class TestWriteResultsCsv:
    @pytest.fixture
    def sample_entries(self):
        return [
            {
                "cnr": "HCBM0000001",
                "case_title": "Case A vs State",
                "court": "Bombay High Court",
                "judge": "JUSTICE X",
                "reg_date": "01-01-2024",
                "decision_date": "15-06-2024",
                "disposal_nature": "DISMISSED",
                "path": "court/orders/HCBM0000001.pdf",
            },
            {
                "cnr": "DLHC0000002",
                "case_title": "Case B vs Union",
                "court": "Delhi High Court",
                "judge": "JUSTICE Y",
                "reg_date": "05-03-2024",
                "decision_date": "20-08-2024",
                "disposal_nature": "ALLOWED",
                "path": "court/orders/DLHC0000002.pdf",
            },
        ]

    def test_writes_csv_file(self, sample_entries):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_results_csv(tmpdir, sample_entries)
            assert path is not None
            assert os.path.exists(path)
            assert path.endswith("_results.csv")

    def test_csv_has_header(self, sample_entries):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_results_csv(tmpdir, sample_entries)
            with open(path) as f:
                header = f.readline().strip()
            for field in CSV_HEADERS:
                assert field in header

    def test_csv_has_correct_row_count(self, sample_entries):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_results_csv(tmpdir, sample_entries)
            with open(path) as f:
                lines = f.readlines()
            # header + 2 entries
            assert len(lines) == 3

    def test_csv_contains_cnr(self, sample_entries):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_results_csv(tmpdir, sample_entries)
            content = open(path).read()
            assert "HCBM0000001" in content
            assert "DLHC0000002" in content

    def test_empty_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_results_csv(tmpdir, [])
            assert path is None


class TestReadResultsCsv:
    @pytest.fixture
    def csv_with_data(self):
        """Create a temp CSV and return its path."""
        entries = [
            {"CNR": "HCBM0001", "Case Title": "Test Case",
             "Court": "Bombay HC", "Judge": "JUSTICE Z",
             "Reg Date": "01-01-2024", "Decision Date": "15-06-2024",
             "Disposal Nature": "DISMISSED", "PDF Path": "path/a.pdf"},
        ]
        import tempfile
        import csv as csv_mod
        from srchigh.export import CSV_HEADERS
        tmpdir = tempfile.mkdtemp()
        csv_path = os.path.join(tmpdir, "_results.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv_mod.writer(f)
            w.writerow(CSV_HEADERS)
            for e in entries:
                w.writerow([
                    e["CNR"], e["Case Title"], e["Court"], e["Judge"],
                    e["Reg Date"], e["Decision Date"],
                    e["Disposal Nature"], e["PDF Path"],
                ])
        yield csv_path
        import shutil
        shutil.rmtree(os.path.dirname(csv_path))

    def test_reads_csv(self, csv_with_data):
        entries = read_results_csv(csv_with_data)
        assert entries is not None
        assert len(entries) == 1

    def test_reads_cnr_field(self, csv_with_data):
        entries = read_results_csv(csv_with_data)
        assert entries[0]["CNR"] == "HCBM0001"

    def test_reads_case_title(self, csv_with_data):
        entries = read_results_csv(csv_with_data)
        assert entries[0]["Case Title"] == "Test Case"

    def test_reads_pdf_path(self, csv_with_data):
        entries = read_results_csv(csv_with_data)
        assert entries[0]["PDF Path"] == "path/a.pdf"

    def test_nonexistent_file(self):
        entries = read_results_csv("/nonexistent/path/_results.csv")
        assert entries is None
