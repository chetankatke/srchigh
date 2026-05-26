"""Unit tests for parser.py — HTML parsing and data extraction."""

import pytest
from srchigh.parser import parse_entry, parse_results_page, get_court_code


class TestParseEntry:
    def test_extracts_cnr(self, sample_entry_complete):
        result = parse_entry(sample_entry_complete)
        assert result.get("cnr") == "APHC010460892016"

    def test_extracts_case_title(self, sample_entry_complete):
        result = parse_entry(sample_entry_complete)
        title = result.get("case_title", "")
        assert "WP/12923/2016" in title
        assert "SEENAPPA" in title

    def test_extracts_judge(self, sample_entry_complete):
        result = parse_entry(sample_entry_complete)
        assert "TARLADA RAJASEKHAR RAO" in result.get("judge", "")

    def test_extracts_court(self, sample_entry_complete):
        result = parse_entry(sample_entry_complete)
        assert "Andhra Pradesh" in result.get("court", "")

    def test_extracts_path(self, sample_entry_complete):
        result = parse_entry(sample_entry_complete)
        path = result.get("path", "")
        assert path.startswith("court/cnrorders/")
        assert path.endswith(".pdf")
        assert "#" not in path  # hash fragment stripped

    def test_extracts_val(self, sample_entry_complete):
        result = parse_entry(sample_entry_complete)
        assert result.get("val") == "0"

    def test_extracts_bombay_cnr(self, sample_entry_bombay):
        result = parse_entry(sample_entry_bombay)
        assert result.get("cnr") == "HCBM030439682025"

    def test_extracts_bombay_court(self, sample_entry_bombay):
        result = parse_entry(sample_entry_bombay)
        assert "Bombay" in result.get("court", "")

    def test_extracts_bombay_judge(self, sample_entry_bombay):
        result = parse_entry(sample_entry_bombay)
        assert "SANDIPKUMAR C. MORE" in result.get("judge", "")

    def test_extracts_reg_date(self, sample_entry_bombay):
        result = parse_entry(sample_entry_bombay)
        assert result.get("reg_date") == "29-10-2025"

    def test_extracts_decision_date(self, sample_entry_bombay):
        result = parse_entry(sample_entry_bombay)
        assert result.get("decision_date") == "23-12-2025"

    def test_extracts_disposal_nature(self, sample_entry_bombay):
        result = parse_entry(sample_entry_bombay)
        assert result.get("disposal_nature") == "DISPOSED OFF"

    def test_minimal_entry(self, sample_entry_minimal):
        result = parse_entry(sample_entry_minimal)
        assert result.get("cnr") == "XXHC0000000000"
        assert result.get("case_title") == "Case ABC"
        assert result.get("decision_date") == "01-01-2024"


class TestParseResultsPage:
    def test_returns_entries_and_total(self, sample_datatable_response):
        entries, total = parse_results_page(sample_datatable_response)
        assert len(entries) == 2
        assert total == 17622456

    def test_each_entry_is_a_dict(self, sample_datatable_response):
        entries, _ = parse_results_page(sample_datatable_response)
        for e in entries:
            assert isinstance(e, dict)

    def test_entries_have_cnr(self, sample_datatable_response):
        entries, _ = parse_results_page(sample_datatable_response)
        cnrs = [e.get("cnr") for e in entries]
        assert "APHC010460892016" in cnrs
        assert "HCBM030439682025" in cnrs

    def test_empty_response(self):
        entries, total = parse_results_page({})
        assert entries == []
        assert total == 0

    def test_missing_reportrow(self):
        entries, total = parse_results_page({"foo": "bar"})
        assert entries == []
        assert total == 0


class TestGetCourtCode:
    def test_bombay_exact(self):
        assert get_court_code("bombay") == "27"

    def test_delhi_exact(self):
        assert get_court_code("delhi") == "7"

    def test_kerala_exact(self):
        assert get_court_code("kerala") == "32"

    def test_bombay_uppercase(self):
        assert get_court_code("BOMBAY") == "27"

    def test_bombay_with_extra_spaces(self):
        assert get_court_code("  bombay  ") == "27"
