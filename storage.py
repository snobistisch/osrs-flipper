"""Atomic JSON replacement shared by disposable caches and durable state."""
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def state_lock(directory: Path):
    """Serialize read/modify/write commands across cron and CLI processes."""
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(directory / ".state-lock.sqlite"), timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield
    finally:
        connection.rollback()
        connection.close()


def write_json(path: Path, payload) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # A unique sibling prevents concurrent writers from sharing a .tmp file.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
