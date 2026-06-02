import logging
import os
import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class _AnsiStripFilter(logging.Filter):
    """Remove ANSI escape codes from log records before they hit the file handler.

    The captcha debug logs in :mod:`srchigh.session` and :mod:`srchigh.sci`
    embed ANSI colour codes for terminal output. The file handler should
    produce a grep-friendly, editor-friendly log file with no escapes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _ANSI_RE.sub("", record.msg)
        if record.args:
            # Best-effort: skip if args is not a tuple of strings
            try:
                record.args = tuple(
                    _ANSI_RE.sub("", a) if isinstance(a, str) else a
                    for a in record.args
                )
            except TypeError:
                pass
        return True


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO

    logger = logging.getLogger("srchigh")
    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("%(message)s"))

    # File handler — strip ANSI escapes so the log file is grep-friendly
    log_dir = os.path.expanduser("~/myJud/logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "srchigh.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    fh.addFilter(_AnsiStripFilter())

    logger.handlers.clear()
    logger.addHandler(ch)
    logger.addHandler(fh)

    return logger
