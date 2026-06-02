"""
Smoke tests — quick end-to-end checks that the project works.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestCliNoArguments:
    """The CLI shows help when called with no arguments."""

    def test_shows_usage(self):
        import sys as _sys
        from io import StringIO
        from srchigh.main import parse_args

        saved = _sys.argv
        _sys.argv = ["main.py"]
        try:
            with pytest.raises(SystemExit):
                parse_args()
        finally:
            _sys.argv = saved


class TestCliHelp:
    """--help equivalent: no search term should show help."""

    def test_help_contains_court_list(self):
        from srchigh.config import COURT_NAMES
        assert "bombay" in COURT_NAMES
        assert "delhi" in COURT_NAMES
        assert "kerala" in COURT_NAMES

    def test_help_contains_flags(self):
        from srchigh.config import MODE_LABELS
        assert "PHRASE" in MODE_LABELS
        assert "ANY" in MODE_LABELS
        assert "ALL" in MODE_LABELS


class TestParseArgs:
    """Arg parsing logic."""

    def test_default_search(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "divorce"]
        try:
            p = parse_args()
            assert p["search"] == "divorce"
            assert p["count"] == 5
            assert p["mode"] == "PHRASE"
        finally:
            _sys.argv = saved

    def test_custom_count(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "divorce", "10"]
        try:
            p = parse_args()
            assert p["search"] == "divorce"
            assert p["count"] == 10
        finally:
            _sys.argv = saved

    def test_court_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "divorce", "--court", "bombay"]
        try:
            p = parse_args()
            assert p["court"] == "bombay"
        finally:
            _sys.argv = saved

    def test_all_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "divorce", "--all"]
        try:
            p = parse_args()
            assert p["all"] is True
        finally:
            _sys.argv = saved

    def test_no_download_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "divorce", "--no-download"]
        try:
            p = parse_args()
            assert p["no_dl"] is True
        finally:
            _sys.argv = saved

    def test_download_db_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--download-db"]
        try:
            p = parse_args()
            assert p["download_db"] is True
        finally:
            _sys.argv = saved

    def test_status_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--status"]
        try:
            p = parse_args()
            assert p["status"] is True
        finally:
            _sys.argv = saved

    def test_export_csv_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--export-csv", "/tmp/out.csv"]
        try:
            p = parse_args()
            assert p["export_csv"] == "/tmp/out.csv"
        finally:
            _sys.argv = saved

    def test_from_csv_alias_sets_download_db(self):
        """--from-csv is a deprecated v1 alias for --download-db (README still references it)."""
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--from-csv", "/tmp/some_csv_dir"]
        try:
            p = parse_args()
            assert p["download_db"] is True
        finally:
            _sys.argv = saved


class TestParseArgsEdgeCases:
    def test_unknown_flag_exits_with_code_1(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--not-a-real-flag"]
        try:
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code == 1
        finally:
            _sys.argv = saved

    def test_court_normalized_to_lowercase(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--court", "BOMBAY"]
        try:
            p = parse_args()
            assert p["court"] == "bombay"
        finally:
            _sys.argv = saved

    def test_pages_range_syntax_two_values(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--pages", "0:10"]
        try:
            p = parse_args()
            assert p["pages"] == (0, 10)
        finally:
            _sys.argv = saved

    def test_pages_single_value_becomes_range(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--pages", "5"]
        try:
            p = parse_args()
            # Single value "5" splits to ("5", "5"), int("5")=5, +1=6
            assert p["pages"] == (5, 6)
        finally:
            _sys.argv = saved

    def test_dump_all_with_scr_search_term_redirects_to_scr_source(self):
        # `srchigh scr --dump-all` historically interpreted "scr" as a search
        # term. The parser patches this: it should detect "scr" as the
        # SCR-source marker and clear the search term.
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "scr", "--dump-all"]
        try:
            p = parse_args()
            assert p["scr"] is True
            assert p["search"] == ""
        finally:
            _sys.argv = saved

    def test_bulk_dump_forces_no_dl_and_all(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "divorce", "--bulk-dump"]
        try:
            p = parse_args()
            assert p["all"] is True
            assert p["no_dl"] is True
        finally:
            _sys.argv = saved

    def test_short_verbose_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "-v"]
        try:
            p = parse_args()
            assert p.get("verbose") is True
        finally:
            _sys.argv = saved

    def test_long_verbose_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--verbose"]
        try:
            p = parse_args()
            assert p.get("verbose") is True
        finally:
            _sys.argv = saved

    def test_version_flag_exits_zero(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--version"]
        try:
            with pytest.raises(SystemExit) as exc:
                parse_args()
            assert exc.value.code == 0
        finally:
            _sys.argv = saved

    def test_default_page_is_zero(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x"]
        try:
            p = parse_args()
            assert p["page"] == 0
            assert p["pages"] is None
        finally:
            _sys.argv = saved

    def test_default_mode_is_phrase(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x"]
        try:
            p = parse_args()
            assert p["mode"] == "PHRASE"
        finally:
            _sys.argv = saved

    def test_default_count_is_5(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x"]
        try:
            p = parse_args()
            assert p["count"] == 5
        finally:
            _sys.argv = saved

    def test_all_works_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--all-words"]
        try:
            p = parse_args()
            assert p["mode"] == "ALL"
            # ALL mode without explicit --proximity gets default 40
            assert p["proximity"] == "40"
        finally:
            _sys.argv = saved

    def test_all_words_with_explicit_proximity(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--all-words", "--proximity", "100"]
        try:
            p = parse_args()
            assert p["mode"] == "ALL"
            assert p["proximity"] == "100"
        finally:
            _sys.argv = saved

    def test_any_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--any"]
        try:
            p = parse_args()
            assert p["mode"] == "ANY"
        finally:
            _sys.argv = saved

    def test_boolean_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "murder AND bail", "--boolean"]
        try:
            p = parse_args()
            assert p["mode"] == "BOOLEAN"
            assert p["search"] == "murder AND bail"
        finally:
            _sys.argv = saved

    def test_sci_flag_sets_source(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--sci", "--from", "01-01-2024", "--to", "31-01-2024"]
        try:
            p = parse_args()
            assert p["sci"] is True
            assert p["from_date"] == "01-01-2024"
            assert p["to_date"] == "31-01-2024"
        finally:
            _sys.argv = saved

    def test_scr_flag_with_citation_filters(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = [
            "main.py", "x", "--scr",
            "--citation-year", "2024", "--citation-vol", "1",
            "--citation-supl", "2", "--citation-page", "100",
        ]
        try:
            p = parse_args()
            assert p["scr"] is True
            assert p["citation_year"] == "2024"
            assert p["citation_vol"] == "1"
            assert p["citation_supl"] == "2"
            assert p["citation_page"] == "100"
        finally:
            _sys.argv = saved

    def test_out_flag_overrides_default(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--out", "/tmp/custom_dir"]
        try:
            p = parse_args()
            assert p["out"] == "/tmp/custom_dir"
        finally:
            _sys.argv = saved

    def test_csv_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--csv"]
        try:
            p = parse_args()
            assert p["csv"] is True
        finally:
            _sys.argv = saved

    def test_no_download_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "x", "--no-download"]
        try:
            p = parse_args()
            assert p["no_dl"] is True
        finally:
            _sys.argv = saved

    def test_clear_db_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--clear-db"]
        try:
            p = parse_args()
            assert p["clear_db"] is True
        finally:
            _sys.argv = saved

    def test_status_flag(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "--status"]
        try:
            p = parse_args()
            assert p["status"] is True
        finally:
            _sys.argv = saved

    def test_mode_any(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "test", "--mode", "any"]
        try:
            p = parse_args()
            assert p["mode"] == "ANY"
        finally:
            _sys.argv = saved

    def test_mode_all_sets_default_proximity(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "test", "--mode", "all"]
        try:
            p = parse_args()
            assert p["mode"] == "ALL"
            assert p["proximity"] == "40"
        finally:
            _sys.argv = saved

    def test_custom_proximity_does_not_get_overridden(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "test", "--mode", "all", "--proximity", "80"]
        try:
            p = parse_args()
            assert p["mode"] == "ALL"
            assert p["proximity"] == "80"
        finally:
            _sys.argv = saved

    def test_default_out_dir_uses_search_term(self):
        import sys as _sys
        from srchigh.main import parse_args
        saved = _sys.argv
        _sys.argv = ["main.py", "anticipatory bail"]
        try:
            p = parse_args()
            assert "anticipatory_bail" in p["out"]
        finally:
            _sys.argv = saved


class TestModuleImports:
    """All modules import without errors."""

    def test_import_config(self):
        from srchigh import config
        assert hasattr(config, "COURT_CODES")
        assert hasattr(config, "COURT_NAMES")
        assert hasattr(config, "BASE_URL")

    def test_import_parser(self):
        from srchigh import parser
        assert hasattr(parser, "parse_entry")
        assert hasattr(parser, "parse_results_page")

    def test_import_db(self):
        from srchigh import db
        assert hasattr(db, "init_db")
        assert hasattr(db, "insert_judgment")
        assert hasattr(db, "get_undownloaded")
        assert hasattr(db, "DB_PATH")

    def test_import_session(self):
        from srchigh import session
        assert hasattr(session, "ECourtSession")

    def test_import_download(self):
        from srchigh import download
        assert hasattr(download, "download_from_db")

    def test_import_main(self):
        from srchigh import main as srchigh_main
        assert hasattr(srchigh_main, "main")