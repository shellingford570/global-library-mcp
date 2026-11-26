"""Workspace data location (b7, brief section 6).

Local-first: the research database lives in the user's own
data directory, never inside the repository. The location
can be pinned with the GLM_WORKSPACE_PATH environment
variable or the web --workspace-path option: a path ending
in .db/.sqlite is the database file itself; anything else
is treated as a directory holding workspace.db.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_VAR = "GLM_WORKSPACE_PATH"


def default_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "GlobalLibraryMCP"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "GlobalLibraryMCP"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "global-library-mcp"


def resolve_db_path(explicit: str | None = None) -> Path:
    raw = explicit or os.environ.get(ENV_VAR)
    if raw:
        p = Path(raw).expanduser()
        if p.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
            return p
        return p / "workspace.db"
    return default_data_dir() / "workspace.db"


def ensure_parent(path: Path) -> Path:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    return path
