"""Research Workspace (b7): local-first SQLite storage for
projects, saved documents, citations, notes, history and
comparisons. See docs/b7-research-workspace.md."""
from __future__ import annotations

from .paths import resolve_db_path
from .policy import classify_rights, evaluate as evaluate_rights
from .store import FutureSchemaError, WorkspaceStore

__all__ = ["WorkspaceStore", "FutureSchemaError", "resolve_db_path",
           "classify_rights", "evaluate_rights"]
