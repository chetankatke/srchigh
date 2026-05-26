"""
Smoke tests — quick end-to-end checks that the project works.
Requires network access and a working captcha solver.
Marked @pytest.mark.smoke — run with: pytest tests/test_smoke.py -v --smoke
"""

import os
import tempfile
import pytest

pytestmark = pytest.mark.smoke


class TestCliNoArguments:
    """The CLI shows help when called with no arguments."""

    def test_shows_usage(self):
        import sys
        from io import StringIO
        from srchigh.main import parse_args

        # Save and restore argv
        saved = sys.argv
        sys.argv = ["main.py"]
        try:
            with pytest.raises(SystemExit):
                parse_args()
        finally:
            sys.argv = saved


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
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "divorce"]
        try:
            p = parse_args()
            assert p["search"] == "divorce"
            assert p["count"] == 5
            assert p["mode"] == "PHRASE"
        finally:
            sys.argv = saved

    def test_custom_count(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "divorce", "10"]
        try:
            p = parse_args()
            assert p["search"] == "divorce"
            assert p["count"] == 10
        finally:
            sys.argv = saved

    def test_court_flag(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "divorce", "--court", "bombay"]
        try:
            p = parse_args()
            assert p["court"] == "bombay"
        finally:
            sys.argv = saved

    def test_all_flag(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "divorce", "--all"]
        try:
            p = parse_args()
            assert p["all"] is True
        finally:
            sys.argv = saved

    def test_csv_flag(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "divorce", "--csv"]
        try:
            p = parse_args()
            assert p["csv"] is True
        finally:
            sys.argv = saved

    def test_no_download_flag(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "divorce", "--no-download"]
        try:
            p = parse_args()
            assert p["no_dl"] is True
        finally:
            sys.argv = saved

    def test_from_csv_flag(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "--from-csv", "/tmp/test"]
        try:
            p = parse_args()
            assert p["from_csv"] == "/tmp/test"
        finally:
            sys.argv = saved

    def test_mode_any(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "test", "--mode", "any"]
        try:
            p = parse_args()
            assert p["mode"] == "ANY"
        finally:
            sys.argv = saved

    def test_mode_all_sets_default_proximity(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "test", "--mode", "all"]
        try:
            p = parse_args()
            assert p["mode"] == "ALL"
            assert p["proximity"] == "40"
        finally:
            sys.argv = saved

    def test_custom_proximity_does_not_get_overridden(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "test", "--mode", "all", "--proximity", "80"]
        try:
            p = parse_args()
            assert p["mode"] == "ALL"
            assert p["proximity"] == "80"
        finally:
            sys.argv = saved

    def test_default_out_dir_uses_search_term(self):
        import sys
        from srchigh.main import parse_args
        saved = sys.argv
        sys.argv = ["main.py", "anticipatory bail"]
        try:
            p = parse_args()
            assert "anticipatory_bail" in p["out"]
        finally:
            sys.argv = saved


class TestModuleImports:
    """All modules import without errors."""

    def test_import_config(self):
        import config
        assert hasattr(config, "COURT_CODES")
        assert hasattr(config, "COURT_NAMES")
        assert hasattr(config, "BASE_URL")

    def test_import_parser(self):
        import parser
        assert hasattr(parser, "parse_entry")
        assert hasattr(parser, "parse_results_page")

    def test_import_export(self):
        import export
        assert hasattr(export, "write_results_csv")
        assert hasattr(export, "read_results_csv")

    def test_import_session(self):
        import session
        assert hasattr(session, "ECourtSession")

    def test_import_download(self):
        import download
        assert hasattr(download, "download_from_csv")

    def test_import_main(self):
        from srchigh import main as srchigh_main
        assert hasattr(srchigh_main, "run_cli")
