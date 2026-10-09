"""HTTP helpers for adapters: polite user agent, retries with backoff, cached downloads.

Everything fetched is cached under raw_dir/<source>/ so re-running the pipeline
(or running offline) reuses it instead of hitting the source again.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "SiteScore/0.1 (location-revenue research prototype)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """A source could not be fetched after retries."""


def client(timeout: float = 120.0) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)


def request(method: str, url: str, *, retries: int = 4, backoff: float = 5.0,
            **kwargs: Any) -> httpx.Response:
    """Send a request, retrying on timeouts, connection errors and 429/5xx."""
    last: Exception | None = None
    with client(kwargs.pop("timeout", 120.0)) as c:
        for attempt in range(retries + 1):
            try:
                resp = c.request(method, url, **kwargs)
                if resp.status_code not in RETRY_STATUS:
                    resp.raise_for_status()
                    return resp
                last = FetchError(f"HTTP {resp.status_code} from {url}")
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
            if attempt < retries:
                wait = backoff * 2 ** attempt
                log.info("retrying %s in %.0fs (%s)", url, wait, last)
                time.sleep(wait)
    raise FetchError(f"giving up on {url}: {last}") from last


def download(url: str, dest: Path) -> Path:
    """Download to dest once (atomic rename); later calls return the cached file."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    with client(timeout=900) as c, c.stream("GET", url) as resp:
        resp.raise_for_status()
        with part.open("wb") as f:
            for chunk in resp.iter_bytes(1 << 20):
                f.write(chunk)
    part.replace(dest)
    log.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


def cached_json(path: Path, fetch: Callable[[], Any]) -> Any:
    """Return the JSON cached at path, or fetch it, cache it and return it."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)
    return data
