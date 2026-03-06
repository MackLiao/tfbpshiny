"""Lazy VDB singleton — one global VirtualDB with all data preloaded."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from tfbpapi import VirtualDB

logger = logging.getLogger("shiny")
_DEFAULT_CONFIG = Path(__file__).parent / "brentlab_yeast_collection.yaml"

_vdb: VirtualDB | None = None
_vdb_lock = threading.Lock()


def get_vdb() -> VirtualDB:
    """Return the shared VirtualDB instance, creating lazily on first call."""
    global _vdb
    if _vdb is None:
        with _vdb_lock:
            if _vdb is None:
                config_path = os.getenv("VDB_CONFIG_PATH", str(_DEFAULT_CONFIG))
                logger.info("VDB config path: %s", config_path)
                _vdb = VirtualDB(config_path)
                logger.info("VDB initialized with tables: %s", _vdb.tables())
    return _vdb
