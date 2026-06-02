"""Tests for log_setup.py — ensure file handler is ANSI-free and console still works."""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from srchigh import log_setup


def _patched_expanduser_for(tmp_path):
    """Return an expanduser that maps '~/<rest>' → tmp_path/<rest>."""
    def _expand(p):
        if p == "~" or p.startswith("~/"):
            return os.path.join(str(tmp_path), p[2:])
        return p
    return _expand


def test_file_log_is_ansi_free(tmp_path, monkeypatch):
    """File log output must not contain ANSI escape codes (grep-friendly)."""
    monkeypatch.setattr(log_setup.os.path, "expanduser", _patched_expanduser_for(tmp_path))

    log = log_setup.setup_logging(verbose=False)
    log.info("\033[1;31mThis is a red test message\033[0m")
    # File handler is the second one added
    log.handlers[1].flush()

    log_path = tmp_path / "myJud" / "logs" / "srchigh.log"
    assert log_path.exists(), f"Expected log file at {log_path}"
    content = log_path.read_text()
    assert "\033[" not in content, f"ANSI leaked into log file: {content!r}"
    assert "This is a red test message" in content


def test_console_log_still_has_message(tmp_path, monkeypatch):
    """Plain messages should appear in the file log verbatim."""
    monkeypatch.setattr(log_setup.os.path, "expanduser", _patched_expanduser_for(tmp_path))

    log = log_setup.setup_logging(verbose=False)
    log.info("plain text message")
    log.handlers[1].flush()
    log_path = tmp_path / "myJud" / "logs" / "srchigh.log"
    assert "plain text message" in log_path.read_text()


def test_ansi_filter_strips_multiple_escapes(tmp_path, monkeypatch):
    """Multiple ANSI escapes in one message must all be removed."""
    monkeypatch.setattr(log_setup.os.path, "expanduser", _patched_expanduser_for(tmp_path))

    log = log_setup.setup_logging(verbose=False)
    log.info("\033[1;36m━━━ Step 1 ━━━\033[0m getting \033[1;32mthing\033[0m done")
    log.handlers[1].flush()
    content = (tmp_path / "myJud" / "logs" / "srchigh.log").read_text()
    assert "\033[" not in content
    assert "Step 1" in content
    assert "thing" in content
    assert "done" in content
