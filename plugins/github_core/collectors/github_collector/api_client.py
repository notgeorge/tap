"""Minimal stdlib HTTP client for GitHub's REST API.

Stays on stdlib (`urllib`) to avoid adding a new dependency. PAT auth, basic
pagination via the `Link: rel="next"` header, and a structured `GithubAPIError`
for non-200 responses. Used by the collector during the collection phase.

Empty-body-404 retry: GitHub returns intermittent 404s with empty response
bodies on `/actions/*` endpoints under conditions that are not documented
(rate-limit docs explicitly state secondary rate limits return 403/429, not
404). Observed signature: valid `X-GitHub-Request-Id`, `Server: github.com`,
HTTP 404, zero-length body. Real GitHub 404s (missing resource, permission
denied) always carry a JSON `{"message": "Not Found"}` body. This client
retries empty-body 404s with exponential backoff bounded to a small ceiling
so real 404s still fail loudly with their explanatory body.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')

# Identifies our collector in GitHub's user-agent logs (req: API politeness).
USER_AGENT = "tap-github-core-collector/0.1"

# Empty-body-404 retry policy (see module docstring).
_EMPTY_404_MAX_RETRIES = 5
_EMPTY_404_INITIAL_BACKOFF_SECONDS = 0.5


@dataclass(frozen=True)
class GithubAPIError(Exception):
    """A GitHub API call returned a non-success status."""

    status: int
    url: str
    body: str

    def __str__(self) -> str:
        return f"GitHub API {self.status} on {self.url}: {self.body[:200]}"


class GithubClient:
    """A thin authenticated HTTP wrapper around GitHub's REST API."""

    def __init__(self, *, token: str, api_base_url: str = "https://api.github.com") -> None:
        self._token = token
        self._api_base_url = api_base_url.rstrip("/")

    def get(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        """Single GET; returns decoded JSON. Raises GithubAPIError on non-2xx."""
        url = self._build_url(path, params)
        return self._request(url)

    def get_paginated(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        item_path: str | None = None,
        max_pages: int = 100,
    ) -> list[Any]:
        """Walk Link-header pagination, accumulate items.

        If `item_path` is given (e.g. "workflow_runs"), extract that array
        from each page; otherwise flatten the page if it's a list.
        """
        url = self._build_url(path, params)
        items: list[Any] = []
        pages = 0
        while url and pages < max_pages:
            payload = self._request(url)
            page_items = payload.get(item_path, []) if item_path else payload
            if isinstance(page_items, list):
                items.extend(page_items)
            url = self._next_link
            pages += 1
        return items

    def _build_url(self, path: str, params: dict[str, str] | None) -> str:
        if path.startswith("http"):
            return path
        parsed = urlparse(self._api_base_url + path)
        query = urlencode(params or {})
        return urlunparse(parsed._replace(query=query))

    def _request(self, url: str) -> Any:
        backoff = _EMPTY_404_INITIAL_BACKOFF_SECONDS
        for attempt in range(_EMPTY_404_MAX_RETRIES + 1):
            try:
                return self._request_once(url)
            except GithubAPIError as exc:
                # Real 404s carry a JSON body explaining the failure. Empty-body
                # 404 is GitHub's undocumented intermittent quirk — retry it.
                # See module docstring for evidence + reasoning.
                if exc.status == 404 and not exc.body and attempt < _EMPTY_404_MAX_RETRIES:
                    logger.warning(
                        "[c1d4] github empty-body 404 on %s (attempt %d/%d); "
                        "retrying after %.2fs",
                        url,
                        attempt + 1,
                        _EMPTY_404_MAX_RETRIES,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise
        raise GithubAPIError(
            status=404,
            url=url,
            body=f"persistent empty-body 404 after {_EMPTY_404_MAX_RETRIES} retries",
        )

    def _request_once(self, url: str) -> Any:
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(req, timeout=30) as resp:  # noqa: S310 - controlled hostname
                body = resp.read().decode("utf-8")
                self._next_link = self._parse_next_link(resp.headers.get("Link", ""))
                return json.loads(body) if body else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise GithubAPIError(status=exc.code, url=url, body=body) from exc
        except URLError as exc:
            raise GithubAPIError(status=0, url=url, body=str(exc.reason)) from exc

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        if not link_header:
            return None
        m = _LINK_RE.search(link_header)
        return m.group(1) if m else None
