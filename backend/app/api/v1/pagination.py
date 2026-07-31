"""Cursor pagination — the only pagination this codebase uses.

CLAUDE.md PERFORMANCE: "Cursor pagination only on list endpoints; never
OFFSET on a table that can grow past a few thousand rows." A generic
Page[T] envelope keeps every list endpoint's response shape identical, so
the frontend's TanStack Query pagination logic is written once.
"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None  # opaque to the client; pass back verbatim to continue
