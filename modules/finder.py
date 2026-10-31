"""
modules/finder.py — GitHub repository search.

NO AI logic here. Calls the GitHub Search API with filters and returns
clean, structured Python dicts. If the strict search returns too few
results, it automatically relaxes filters one step at a time.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import config

# Labels that indicate beginner-friendly issues (GitHub uses these widely)
_BEGINNER_LABELS = [
    "good first issue",
    "good-first-issue",
    "beginner",
    "beginner-friendly",
    "easy",
    "starter",
    "first-timers-only",
]


def _active_since() -> str:
    """Return an ISO date string N days ago for the `pushed:` filter."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=config.ACTIVITY_DAYS)
    return cutoff.strftime("%Y-%m-%d")


def _build_query(
    language: str,
    topics: list[str],
    stars_min: int,
    stars_max: int,
    activity_date: str,
) -> str:
    """Compose a GitHub search query string."""
    parts = [
        f"language:{language}",
        f"stars:{stars_min}..{stars_max}",
        f"pushed:>{activity_date}",
        "archived:false",
        # Require at least 1 good-first-issue (correct repo search qualifier)
        "good-first-issues:>0",
    ]
    # Add up to 2 topic keywords — GitHub topics use hyphens, not spaces
    for topic in topics[:2]:
        slug = topic.lower().replace(" ", "-")
        parts.append(f"topic:{slug}")
    return " ".join(parts)


def _fetch_page(query: str, page: int = 1, per_page: int = 20) -> dict[str, Any]:
    """Call the GitHub search/repositories endpoint and return raw JSON."""
    url = f"{config.GITHUB_API_BASE}/search/repositories"
    params = {
        "q": query,
        "sort": "updated",
        "order": "desc",
        "per_page": per_page,
        "page": page,
    }
    resp = requests.get(url, headers=config.GITHUB_HEADERS, params=params, timeout=15)

    if resp.status_code == 403:
        reset = resp.headers.get("X-RateLimit-Reset")
        wait = int(reset) - int(time.time()) + 2 if reset else 60
        raise RateLimitError(
            f"GitHub API rate limit hit. Resets in ~{wait}s.", wait_seconds=wait
        )
    if resp.status_code == 422:
        raise SearchError(f"GitHub rejected the query: {resp.json().get('message')}")
    resp.raise_for_status()
    return resp.json()


def _count_beginner_issues(owner: str, repo: str) -> int:
    """
    Count open issues with any beginner-friendly label.
    Returns 0 on any error (non-critical — used for display only).
    """
    total = 0
    for label in _BEGINNER_LABELS:
        url = f"{config.GITHUB_API_BASE}/search/issues"
        params = {
            "q": f'repo:{owner}/{repo} is:open is:issue label:"{label}"',
            "per_page": 1,
        }
        try:
            resp = requests.get(
                url, headers=config.GITHUB_HEADERS, params=params, timeout=10
            )
            if resp.status_code == 200:
                total += resp.json().get("total_count", 0)
        except Exception:
            pass
        # Small delay to avoid secondary rate limits
        time.sleep(0.1)
    return total


def _parse_repo(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract the fields we care about from a raw GitHub repo object."""
    owner = raw["owner"]["login"]
    name = raw["name"]
    return {
        "id": raw["id"],
        "full_name": raw["full_name"],          # "owner/repo"
        "owner": owner,
        "name": name,
        "description": raw.get("description") or "No description provided.",
        "url": raw["html_url"],
        "stars": raw["stargazers_count"],
        "language": raw.get("language") or "Unknown",
        "topics": raw.get("topics", []),
        "last_pushed": raw["pushed_at"],        # ISO 8601
        "open_issues_total": raw["open_issues_count"],
        "beginner_issues": 0,                   # filled in below (optional)
        "license": (raw.get("license") or {}).get("spdx_id", "Unknown"),
    }


def search_repositories(
    language: str,
    topics: list[str] | None = None,
    *,
    stars_min: int | None = None,
    stars_max: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Search GitHub for beginner-friendly repositories.

    Returns (results, relaxation_note) where:
      - results is a list of structured repo dicts (up to MAX_CANDIDATES)
      - relaxation_note is an empty string unless filters were relaxed

    Raises RateLimitError or SearchError on unrecoverable problems.
    """
    topics = topics or []
    stars_min = stars_min if stars_min is not None else config.STARS_MIN
    stars_max = stars_max if stars_max is not None else config.STARS_MAX
    activity_date = _active_since()
    relaxation_note = ""

    # --- Attempt 1: strict search ------------------------------------------------
    query = _build_query(language, topics, stars_min, stars_max, activity_date)
    data = _fetch_page(query, per_page=config.MAX_CANDIDATES)
    items = data.get("items", [])

    # --- Attempt 2: widen star range ---------------------------------------------
    if len(items) < 3:
        stars_min_wide = max(10, stars_min // 2)
        stars_max_wide = min(50_000, stars_max * 3)
        query = _build_query(
            language, topics, stars_min_wide, stars_max_wide, activity_date
        )
        data = _fetch_page(query, per_page=config.MAX_CANDIDATES)
        items = data.get("items", [])
        if items:
            relaxation_note = (
                f"The strict star filter ({stars_min}–{stars_max}) returned too few "
                f"results, so the range was widened to {stars_min_wide}–{stars_max_wide}."
            )

    # --- Attempt 3: widen activity window ----------------------------------------
    if len(items) < 3:
        wide_date = (
            datetime.now(tz=timezone.utc) - timedelta(days=365)
        ).strftime("%Y-%m-%d")
        query = _build_query(language, topics, stars_min, stars_max, wide_date)
        data = _fetch_page(query, per_page=config.MAX_CANDIDATES)
        items = data.get("items", [])
        if items:
            relaxation_note = (
                "Very few recently active repos matched your filters. "
                "The activity window was widened to the last 12 months."
            )

    # --- Attempt 4: drop topic filters -------------------------------------------
    if len(items) < 3 and topics:
        query = _build_query(language, [], stars_min, stars_max, activity_date)
        data = _fetch_page(query, per_page=config.MAX_CANDIDATES)
        items = data.get("items", [])
        if items:
            relaxation_note = (
                f"No repos matched your topic filters ({', '.join(topics)}), "
                "so results are based on language only."
            )

    repos = [_parse_repo(r) for r in items[: config.MAX_CANDIDATES]]

    # Accurate per-label counting is too slow (7 API calls × N repos).
    # Since good-first-issues:>0 is already a search filter, every result
    # is guaranteed to have at least one — mark them all as confirmed.
    for repo in repos:
        repo["beginner_issues"] = 1  # confirmed >= 1 via good-first-issues:>0 filter

    return repos, relaxation_note


# ── Custom exceptions ─────────────────────────────────────────────────────────

class RateLimitError(Exception):
    def __init__(self, message: str, wait_seconds: int = 60):
        super().__init__(message)
        self.wait_seconds = wait_seconds


class SearchError(Exception):
    pass
