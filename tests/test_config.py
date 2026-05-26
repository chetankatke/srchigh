"""Unit tests for config.py — court code mappings."""

import pytest
from srchigh.config import COURT_CODES, COURT_NAMES


class TestCourtCodes:
    def test_all_court_codes_have_names(self):
        """Every numeric code has a corresponding name."""
        for code, name in COURT_CODES.items():
            assert isinstance(code, int)
            assert isinstance(name, str)
            assert len(name) > 0

    def test_all_names_have_codes(self):
        """Every name in COURT_NAMES has a matching code in COURT_CODES."""
        for name, code in COURT_NAMES.items():
            assert isinstance(name, str)
            assert isinstance(code, int)
            assert COURT_CODES[code] == name

    def test_bidirectional_mapping(self):
        """COURT_CODES and COURT_NAMES are bidirectional."""
        for code, name in COURT_CODES.items():
            assert COURT_NAMES[name] == code

    def test_bombay_exists(self):
        assert COURT_NAMES["bombay"] == 27

    def test_delhi_exists(self):
        assert COURT_NAMES["delhi"] == 7

    def test_kerala_exists(self):
        assert COURT_NAMES["kerala"] == 32

    def test_unique_names(self):
        """No duplicate court names."""
        assert len(COURT_NAMES) == len(set(COURT_NAMES.keys()))

    def test_unique_codes(self):
        """No duplicate numeric codes."""
        assert len(COURT_CODES) == len(set(COURT_CODES.keys()))
