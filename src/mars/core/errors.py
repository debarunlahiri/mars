"""Exceptions whose messages are safe to show to API clients."""

from __future__ import annotations


class MarsError(Exception):
    status_code = 500
    code = "internal_error"


class RunTimeout(MarsError):
    status_code = 504
    code = "run_timeout"


class SearchError(MarsError):
    status_code = 502
    code = "search_failed"


class UnsafeURL(ValueError):
    """The URL is not a public http(s) address (SSRF guard)."""


class StructuredOutputError(RuntimeError):
    """The model returned output that does not match the requested schema."""
