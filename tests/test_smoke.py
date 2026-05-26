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