"""Filesystem locations.

Stdlib only: run.py imports this before the virtualenv exists.

Large, regenerable files (virtualenv, raw downloads) go to a machine-local folder.
If the repo sits inside a cloud-synced folder (OneDrive, Dropbox, ...) that folder
is placed outside it, so we don't sync ~1 GB of packages and zips or hit file locks.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
PROCESSED_DIR = ROOT / "data" / "processed"
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

_SYNCED_FOLDER_PREFIXES = ("onedrive", "dropbox", "google drive", "icloud drive", "box")


def inside_synced_folder(path: Path = ROOT) -> bool:
    return any(part.lower().startswith(_SYNCED_FOLDER_PREFIXES) for part in path.parts)


def local_home() -> Path:
    """Machine-local folder for large regenerable files."""
    override = os.environ.get("SITESCORE_CACHE_DIR")
    if override:
        return Path(override)
    if inside_synced_folder():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
        return Path(base) / "SiteScore"
    return ROOT / ".local"


def venv_dir() -> Path:
    if not inside_synced_folder() and not os.environ.get("SITESCORE_CACHE_DIR"):
        return ROOT / ".venv"
    return local_home() / "venv"


def raw_dir() -> Path:
    """Downloaded source files, exactly as fetched."""
    return local_home() / "raw"
