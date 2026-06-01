import logging
import os

def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    
    logger = logging.getLogger("srchigh")
    logger.setLevel(logging.DEBUG)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("%(message)s"))
    
    # File handler
    log_dir = os.path.expanduser("~/myJud/logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "srchigh.log"))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    
    logger.handlers.clear()
    logger.addHandler(ch)
    logger.addHandler(fh)
    
    return logger
