from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from global_library_mcp.models import SearchResult


class AdapterError(RuntimeError):
    def __init__(self, library_id: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.library_id = library_id
        self.retryable = retryable


class LibraryAdapter(ABC):
    library_id: str
    library_name: str

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        raise NotImplementedError

    async def get_document(self, record_id: str) -> dict[str, Any]:
        raise AdapterError(self.library_id, "Document retrieval is not implemented for this adapter")
