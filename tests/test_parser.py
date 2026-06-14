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

    def test_extracts_scr_citation(self):
        """SCR entry with citation in text [2026] 2 S.C.R. 231."""
        html = (
            '<button aria-label="[2026] 2 S.C.R. 231 pdf" '
            'onclick="open_pdf(\'0\',\'\',\'court/scr/2026_2_231.pdf\');">'
            '<font>[2026] 2 S.C.R. 231</font></button><br>'
            '<strong>Judge : JUSTICE X</strong><br>'
            '<strong class="caseDetailsTD">'
            '<span style="color:#212F3D"> CNR :</span>'
            '<font color="green"> SCR202600020231</font>'
            '<span style="color:#212F3D"> | Decision Date :</span>'
            '<font color="green"> 01-01-2026</font><br>'
            '<span style="opacity: 0.5;">Court : Supreme Court of India</span>'
            '</strong>'
        )
        result = parse_entry(html)
        assert result.get("citation") == "[2026] 2 S.C.R. 231"

    def test_extracts_scr_citation_with_dots(self):
        """SCR citation with variable spacing: 2024 (2) S.C.R. 123"""
        html = (
            '<button aria-label="(2024) 2 S.C.R. 123 pdf" '
            'onclick="open_pdf(\'0\',\'\',\'court/scr/2024_2_123.pdf\');">'
            '<font>(2024) 2 S.C.R. 123</font></button><br>'
            '<strong>Judge : JUSTICE Y</strong><br>'
            '<strong class="caseDetailsTD">'
            '<span style="opacity: 0.5;">Court : Supreme Court of India</span>'
            '</strong>'
        )
        result = parse_entry(html)
        assert result.get("citation") == "[2024] 2 S.C.R. 123"

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


class TestGetCourtCodeEdgeCases:
    def test_partial_substring_match_bombay_in_phrase(self):
        # get_court_code uses `name in key or key in name`
        # "bombay high" should match the "bombay" key
        assert get_court_code("bombay high") == "27"

    def test_unknown_court_returns_empty(self):
        assert get_court_code("atlantis") == ""

    def test_patna_bihar_exact(self):
        # Key includes the parenthetical
        assert get_court_code("patna (bihar)") == "10"

    def test_patna_substring(self):
        # "patna" appears in "patna (bihar)" so should match
        assert get_court_code("patna") == "10"

    def test_case_insensitive(self):
        assert get_court_code("KERALA") == "32"
        assert get_court_code("KeRaLa") == "32"

    def test_whitespace_stripped(self):
        assert get_court_code("  delhi  ") == "7"

    def test_empty_string_returns_first_match(self):
        # Known quirk: "" is a substring of every key, so the loop returns
        # the first court code (1 = "jammu & kashmir"). Documenting this
        # behavior; users should not pass empty strings.
        assert get_court_code("") == "1"


class TestMakeSafeFilename:
    """make_safe_filename — deterministic, collision-free PDF filenames."""

    def test_cnr_used_when_present(self):
        from srchigh.parser import make_safe_filename
        assert make_safe_filename("ABC/123/2024", "p.pdf") == "ABC_123_2024"

    def test_n_a_treated_as_missing(self):
        from srchigh.parser import make_safe_filename
        result = make_safe_filename("N/A", "some/path.pdf")
        assert result.startswith("judgment_")
        assert "N/A" not in result

    def test_missing_cnr_hashes_path(self):
        from srchigh.parser import make_safe_filename
        result = make_safe_filename("", "court/orders/HCBM001.pdf")
        assert result.startswith("judgment_")
        # sha256 hex[:16] = 16 chars; "judgment_" + 16 = 25 chars
        assert len(result) == len("judgment_") + 16

    def test_different_sources_dont_collide(self):
        """Same path under different sources should yield different filenames."""
        from srchigh.parser import make_safe_filename
        a = make_safe_filename("", "same.pdf", source="ecourts")
        b = make_safe_filename("", "same.pdf", source="scr")
        assert a != b

    def test_same_inputs_yield_same_hash(self):
        """Determinism — same inputs must always produce same output."""
        from srchigh.parser import make_safe_filename
        a = make_safe_filename("", "court/x.pdf", source="sci")
        b = make_safe_filename("", "court/x.pdf", source="sci")
        assert a == b

    def test_distinct_paths_yield_distinct_hashes(self):
        from srchigh.parser import make_safe_filename
        a = make_safe_filename("", "court/x.pdf", source="ecourts")
        b = make_safe_filename("", "court/y.pdf", source="ecourts")
        assert a != b

    def test_both_empty_returns_unknown(self):
        from srchigh.parser import make_safe_filename
        assert make_safe_filename("", "") == "unknown"

    def test_whitespace_in_cnr_replaced(self):
        from srchigh.parser import make_safe_filename
        assert make_safe_filename("ABC 123 2024", "p.pdf") == "ABC_123_2024"


class TestParseFacets:
    """parse_facets — extract per-court/year/judge counts from search response."""

    def test_courts_extracted(self):
        from srchigh.parser import parse_facets
        html = (
            "<ul><li><a href=\"javascript:get_details('','','9','Allahabad High Court');\">"
            "Allahabad High Court&nbsp;"
            "<span class='badge rounded-pill text-bg-light'>2008</span></a></li>"
            "<li><a href=\"javascript:get_details('','','10','Patna High Court');\">"
            "Patna High Court&nbsp;"
            "<span class='badge rounded-pill text-bg-light'>891</span></a></li></ul>"
        )
        result = parse_facets({"court_dtls": html})
        assert len(result["courts"]) == 2
        assert result["courts"][0] == ("Allahabad High Court", "9", 2008)
        assert result["courts"][1] == ("Patna High Court", "10", 891)

    def test_courts_sorted_descending(self):
        from srchigh.parser import parse_facets
        html = (
            "<ul><li><a href=\"javascript:get_details('','','1','A');\">A&nbsp;"
            "<span class='badge rounded-pill text-bg-light'>10</span></a></li>"
            "<li><a href=\"javascript:get_details('','','2','B');\">B&nbsp;"
            "<span class='badge rounded-pill text-bg-light'>100</span></a></li>"
            "<li><a href=\"javascript:get_details('','','3','C');\">C&nbsp;"
            "<span class='badge rounded-pill text-bg-light'>50</span></a></li></ul>"
        )
        result = parse_facets({"court_dtls": html})
        names = [c[0] for c in result["courts"]]
        assert names == ["B", "C", "A"]

    def test_dedup_modal_pane(self):
        from srchigh.parser import parse_facets
        html = (
            "<ul><li><a href=\"javascript:get_details('','','9','Allahabad');\">"
            "Allahabad&nbsp;<span class='badge rounded-pill text-bg-light'>2008</span></a></li></ul>"
            "<div class='modal-body'><ul><li>"
            "<a href=\"javascript:get_details('','','9','Allahabad');\">"
            "Allahabad&nbsp;<span class='badge rounded-pill text-bg-light'>2008</span></a></li></ul></div>"
        )
        result = parse_facets({"court_dtls": html})
        assert len(result["courts"]) == 1
        assert result["courts"][0] == ("Allahabad", "9", 2008)

    def test_empty_court_dtls(self):
        from srchigh.parser import parse_facets
        result = parse_facets({"court_dtls": ""})
        assert result["courts"] == []

    def test_missing_court_dtls(self):
        from srchigh.parser import parse_facets
        result = parse_facets({})
        assert result["courts"] == []

    def test_handles_thousands_separator_in_count(self):
        from srchigh.parser import parse_facets
        html = (
            "<ul><li><a href=\"javascript:get_details('','','9','X');\">X&nbsp;"
            "<span class='badge rounded-pill text-bg-light'>1,234</span></a></li></ul>"
        )
        result = parse_facets({"court_dtls": html})
        assert result["courts"][0][2] == 1234

    def test_returns_dict_with_all_keys(self):
        from srchigh.parser import parse_facets
        result = parse_facets({})
        assert "courts" in result
        assert "years" in result
        assert "judges" in result
        assert result["courts"] == []
        assert result["years"] == []
        assert result["judges"] == []
