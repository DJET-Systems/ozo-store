"""Pytest fixtures and PostgreSQL concurrency helpers."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import connections


def run_concurrently[T](fn: Callable[[int], T], workers: int) -> list[T]:
    """Run fn(worker_index) across N threads, closing Django DB connections cleanly per thread."""

    def _wrapped(idx: int) -> T:
        connections.close_all()
        try:
            return fn(idx)
        finally:
            connections.close_all()

    results: list[T] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_wrapped, idx) for idx in range(workers)]
        for future in as_completed(futures):
            results.append(future.result())
    return results
