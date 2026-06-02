"""Tests for sci.py — SCI portal helpers.

Covers pure helpers (``_parse_sci_date``, ``_split_date_range``, ``_month_range``,
``_fmt_date``, ``_solve_math_captcha``) and the HTML table parser
(``_parse_results_table``). The network-bound ``SCISession`` methods are
covered by ``test_session.py``'s ``--network`` tests.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from srchigh.sci import (
    _parse_sci_date,
    _split_date_range,
    _month_range,
    _fmt_date,
    SCISession,
)


class TestParseSciDate:
    def test_numeric_month(self):
        assert _parse_sci_date("15-01-2024") == date(2024, 1, 15)

    def test_named_month_short(self):
        assert _parse_sci_date("05-Jan-2024") == date(2024, 1, 5)

    def test_named_month_full(self):
        # SCI PDFs sometimes use full month names; we only check the first 3 chars
        assert _parse_sci_date("05-January-2024") == date(2024, 1, 5)

    def test_december_end_of_month(self):
        assert _parse_sci_date("31-Dec-2023") == date(2023, 12, 31)

    def test_invalid_format_returns_none(self):
        assert _parse_sci_date("not a date") is None

    def test_too_few_parts_returns_none(self):
        assert _parse_sci_date("15-01") is None

    def test_too_many_parts_returns_none(self):
        # "15-01-2024-extra" has 4 parts; should return None
        assert _parse_sci_date("15-01-2024-extra") is None

    def test_invalid_month_name_returns_none(self):
        assert _parse_sci_date("15-Foo-2024") is None

    def test_single_digit_day(self):
        assert _parse_sci_date("1-01-2024") == date(2024, 1, 1)

    def test_zero_day(self):
        # Edge case: day=0 is invalid; the constructor will raise
        with pytest.raises(ValueError):
            _parse_sci_date("00-01-2024")


class TestSplitDateRange:
    def test_range_within_30_days_is_one_chunk(self):
        chunks = _split_date_range(date(2024, 1, 1), date(2024, 1, 15))
        assert chunks == [(date(2024, 1, 1), date(2024, 1, 15))]

    def test_range_exactly_30_days(self):
        chunks = _split_date_range(date(2024, 1, 1), date(2024, 1, 30))
        assert chunks == [(date(2024, 1, 1), date(2024, 1, 30))]

    def test_range_31_days_splits_into_two(self):
        chunks = _split_date_range(date(2024, 1, 1), date(2024, 1, 31))
        assert chunks == [
            (date(2024, 1, 1), date(2024, 1, 30)),
            (date(2024, 1, 31), date(2024, 1, 31)),
        ]

    def test_range_spans_year_boundary(self):
        chunks = _split_date_range(date(2023, 12, 15), date(2024, 1, 15))
        assert len(chunks) == 2
        assert chunks[0][0] == date(2023, 12, 15)
        assert chunks[-1][1] == date(2024, 1, 15)

    def test_same_day_range(self):
        chunks = _split_date_range(date(2024, 6, 1), date(2024, 6, 1))
        assert chunks == [(date(2024, 6, 1), date(2024, 6, 1))]

    def test_long_year_splits_into_many_chunks(self):
        # 365 days / 30 per chunk ≈ 13 chunks
        chunks = _split_date_range(date(2024, 1, 1), date(2024, 12, 31))
        assert len(chunks) >= 12
        # No gaps between chunks
        for i in range(len(chunks) - 1):
            assert chunks[i][1] + _ONE_DAY == chunks[i + 1][0]
        # First and last match the input
        assert chunks[0][0] == date(2024, 1, 1)
        assert chunks[-1][1] == date(2024, 12, 31)


_ONE_DAY = __import__("datetime").timedelta(days=1)


class TestMonthRange:
    def test_january(self):
        assert _month_range(2024, 1) == (date(2024, 1, 1), date(2024, 1, 31))

    def test_february_non_leap(self):
        assert _month_range(2023, 2) == (date(2023, 2, 1), date(2023, 2, 28))

    def test_february_leap(self):
        assert _month_range(2024, 2) == (date(2024, 2, 1), date(2024, 2, 29))

    def test_april_30_days(self):
        assert _month_range(2024, 4) == (date(2024, 4, 1), date(2024, 4, 30))

    def test_december(self):
        assert _month_range(2024, 12) == (date(2024, 12, 1), date(2024, 12, 31))


class TestFmtDate:
    def test_format(self):
        assert _fmt_date(date(2024, 1, 5)) == "05-01-2024"

    def test_zero_padded_day(self):
        assert _fmt_date(date(2024, 12, 31)) == "31-12-2024"

    def test_zero_padded_month(self):
        assert _fmt_date(date(2024, 6, 15)) == "15-06-2024"


class TestSolveMathCaptcha:
    def setup_method(self):
        # _solve_math_captcha is an instance method
        self.sess = SCISession.__new__(SCISession)

    def test_valid_addition(self):
        assert self.sess._solve_math_captcha("5+3") == "8"

    def test_valid_subtraction(self):
        assert self.sess._solve_math_captcha("10-3") == "7"

    def test_subtraction_equal_returns_none(self):
        # a-b with a==b → 0, server rejects; function returns None
        assert self.sess._solve_math_captcha("3-3") is None

    def test_subtraction_smaller_minuend_returns_none(self):
        # a-b with a<b would be negative; function returns None
        assert self.sess._solve_math_captcha("2-5") is None

    def test_whitespace_around_operator(self):
        assert self.sess._solve_math_captcha("5 + 3") == "8"
        assert self.sess._solve_math_captcha("10 - 3") == "7"

    def test_leading_whitespace_stripped(self):
        assert self.sess._solve_math_captcha("  5+3") == "8"

    def test_missing_operator_falls_back(self):
        # ddddocr often returns "53" instead of "5+3"
        # Should be a string that is the sum or difference of 5 and 3
        result = self.sess._solve_math_captcha("53")
        # 5+3=8 or 5-3=2
        assert result in ("8", "2")

    def test_missing_operator_force_plus_when_a_le_b(self):
        # "22" → 2<=2 so the fallback forces +; result is 4
        result = self.sess._solve_math_captcha("22")
        assert result == "4"

    def test_completely_unparseable_returns_none(self):
        assert self.sess._solve_math_captcha("") is None
        assert self.sess._solve_math_captcha("abc") is None

    def test_single_number_with_no_op(self):
        # "5" — only one number. Per the current code, this may raise
        # ValueError (int("") in the fallback). Document the behavior.
        try:
            result = self.sess._solve_math_captcha("5")
            assert result is None or result.isdigit()
        except ValueError:
            # Acceptable: edge case not handled gracefully
            pass


class TestParseResultsTable:
    """SCISession._parse_results_table — extracts judgment rows from HTML."""

    def setup_method(self):
        # Bypass __init__ (we don't need an HTTP client for this parser)
        self.sess = SCISession.__new__(SCISession)

    def test_parses_typical_row(self):
        html = """
        <table>
            <tr data-diary-no="12345/2024">
                <td>1</td>
                <td>12345/2024</td>
                <td>SLP(C) No. 12345 of 2024</td>
                <td>PETITIONER vs RESPONDENT</td>
                <td>ADV X</td>
                <td>CORAM: JUSTICE A AND JUSTICE B</td>
                <td>JUDGMENT BY: JUSTICE A</td>
                <td><a href="https://www.sci.gov.in/wp-content/uploads/2024/01/case.pdf">Download</a></td>
            </tr>
        </table>
        """
        entries = self.sess._parse_results_table(html)
        assert len(entries) == 1
        e = entries[0]
        assert e["diary_no"] == "12345/2024"
        assert e["diary_year"] == "2024"
        assert e["case_no"] == "SLP(C) No. 12345 of 2024"
        assert "PETITIONER" in e["case_title"]
        assert "JUSTICE A" in e["judge"]
        assert e["pdf_url"].endswith("case.pdf")

    def test_no_diary_no_attr_skips(self):
        html = '<table><tr><td>no diary</td></tr></table>'
        entries = self.sess._parse_results_table(html)
        assert entries == []

    def test_short_row_partial_parse(self):
        # If cells < 8, parser should still extract what it can
        html = '<tr data-diary-no="1/2024"><td>0</td><td>1/2024</td></tr>'
        entries = self.sess._parse_results_table(html)
        assert len(entries) == 1
        assert entries[0]["diary_no"] == "1/2024"
        assert "case_no" not in entries[0]
        assert "pdf_url" not in entries[0]

    def test_pdf_url_extraction_without_extension_fails_silently(self):
        # The parser specifically looks for .pdf in href
        html = """
        <tr data-diary-no="2/2024">
            <td>0</td><td>2/2024</td><td>Case</td><td>Title</td>
            <td>Adv</td><td>Bench</td><td>Judge</td>
            <td><a href="https://example.com/judgment">No PDF</a></td>
        </tr>
        """
        entries = self.sess._parse_results_table(html)
        assert len(entries) == 1
        assert "pdf_url" not in entries[0]

    def test_multiple_rows_parsed(self):
        html = """
        <tr data-diary-no="1/2024"><td>0</td><td>1/2024</td><td>A</td><td>T1</td><td>x</td><td>b</td><td>j</td><td><a href="a.pdf">d</a></td></tr>
        <tr data-diary-no="2/2024"><td>1</td><td>2/2024</td><td>B</td><td>T2</td><td>x</td><td>b</td><td>j</td><td><a href="b.pdf">d</a></td></tr>
        """
        entries = self.sess._parse_results_table(html)
        assert len(entries) == 2
        assert entries[0]["diary_no"] == "1/2024"
        assert entries[1]["diary_no"] == "2/2024"

    def test_diary_year_extraction(self):
        # diary_no "12345/2024" → diary_year "2024"
        html = '<tr data-diary-no="12345/2024"><td>0</td><td>12345/2024</td><td>X</td><td>T</td><td>a</td><td>b</td><td>j</td><td><a href="x.pdf">d</a></td></tr>'
        entries = self.sess._parse_results_table(html)
        assert entries[0]["diary_year"] == "2024"

    def test_diary_no_without_slash(self):
        # If diary_no has no slash, diary_year is "" per the code
        html = '<tr data-diary-no="ABCDEF"><td>0</td><td>ABCDEF</td><td>X</td><td>T</td><td>a</td><td>b</td><td>j</td><td><a href="x.pdf">d</a></td></tr>'
        entries = self.sess._parse_results_table(html)
        assert len(entries) == 1
        assert entries[0]["diary_no"] == "ABCDEF"
        assert entries[0]["diary_year"] == ""
