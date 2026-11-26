"""File locations for development and the packaged Mac app."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

APP_NAME = "Ganorabricks"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parent


def bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return project_root()


def data_dir() -> Path:
    if is_frozen():
        folder = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        folder = project_root() / "data"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def database_path() -> Path:
    """Development keeps data/lotledger.db. The Mac app copies that file once."""
    target = data_dir() / "lotledger.db"
    if is_frozen() and not target.exists():
        seed = bundle_root() / "data" / "lotledger.db"
        if seed.is_file():
            shutil.copy2(seed, target)
    return target
