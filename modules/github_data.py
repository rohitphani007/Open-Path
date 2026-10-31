"""
modules/github_data.py — Fetches detailed data for a single chosen repository.

After the user selects a repo this module gathers:
  - Repo metadata
  - README content (decoded, truncated)
  - Top-level file/folder tree
  - CONTRIBUTING guide (if it exists)
  - Open beginner-friendly issues (with body + comments)
  - Individual file contents on demand (used by PR Buddy)

All results are cached in a simple dict for the session so we don't
hammer the API with duplicate requests.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import requests

import config
from modules.finder import RateLimitError

# ── Simple in-process cache (session-level) ───────────────────────────────────
_cache: dict[str, Any] = {}


def _cache_key(*parts: str) -> str:
    return ":".join(parts)


def _get(url: str, params: dict | None = None) -> Any:
    """GET with auth headers, raise on rate limit, return parsed JSON."""
    resp = requests.get(
        url, headers=config.GITHUB_HEADERS, params=params, timeout=15
    )
    if resp.status_code == 403:
        reset = resp.headers.get("X-RateLimit-Reset")
        wait = int(reset) - int(time.time()) + 2 if reset else 60
        raise RateLimitError(
            f"GitHub API rate limit hit. Resets in ~{wait}s.", wait_seconds=wait
        )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


# ── README ─────────────────────────────────────────────────────────────────────

def get_readme(full_name: str) -> str:
    """
    Return the README text for `owner/repo`, truncated to FILE_EXCERPT_CHARS.
    Returns an empty string if no README exists.
    """
    key = _cache_key("readme", full_name)
    if key in _cache:
        return _cache[key]

    url = f"{config.GITHUB_API_BASE}/repos/{full_name}/readme"
    data = _get(url)
    if not data:
        _cache[key] = ""
        return ""

    # GitHub returns base64-encoded content
    raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    truncated = _truncate(raw)
    _cache[key] = truncated
    return truncated


# ── File tree ─────────────────────────────────────────────────────────────────

def get_top_level_tree(full_name: str, default_branch: str = "main") -> list[dict]:
    """
    Return a list of top-level files/folders as dicts with keys:
      path, type ("file" | "dir"), size (bytes, files only)
    Falls back to "master" if "main" 404s.
    """
    key = _cache_key("tree", full_name)
    if key in _cache:
        return _cache[key]

    for branch in [default_branch, "master", "develop"]:
        url = f"{config.GITHUB_API_BASE}/repos/{full_name}/git/trees/{branch}"
        data = _get(url)
        if data:
            tree = [
                {
                    "path": item["path"],
                    "type": "dir" if item["type"] == "tree" else "file",
                    "size": item.get("size", 0),
                }
                for item in data.get("tree", [])
                # Skip deep paths (we want top-level only)
                if "/" not in item["path"]
            ]
            _cache[key] = tree
            return tree

    _cache[key] = []
    return []


# ── Contributing guide ────────────────────────────────────────────────────────

_CONTRIB_PATHS = [
    "CONTRIBUTING.md",
    "CONTRIBUTING.rst",
    "CONTRIBUTING.txt",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
]


def get_contributing_guide(full_name: str) -> str:
    """
    Return the CONTRIBUTING guide text, truncated. Empty string if not found.
    """
    key = _cache_key("contrib", full_name)
    if key in _cache:
        return _cache[key]

    for path in _CONTRIB_PATHS:
        url = f"{config.GITHUB_API_BASE}/repos/{full_name}/contents/{path}"
        data = _get(url)
        if data and "content" in data:
            raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            result = _truncate(raw)
            _cache[key] = result
            return result

    _cache[key] = ""
    return ""


# ── Issues ────────────────────────────────────────────────────────────────────

_BEGINNER_LABELS = [
    "good first issue",
    "good-first-issue",
    "beginner",
    "beginner-friendly",
    "easy",
    "starter",
    "first-timers-only",
]


def get_beginner_issues(full_name: str, max_issues: int = 15) -> list[dict]:
    """
    Return open issues with beginner-friendly labels.
    Each issue dict has: number, title, url, labels, body_excerpt, comments_count.
    """
    key = _cache_key("issues", full_name)
    if key in _cache:
        return _cache[key]

    seen_ids: set[int] = set()
    issues: list[dict] = []

    for label in _BEGINNER_LABELS:
        if len(issues) >= max_issues:
            break
        url = f"{config.GITHUB_API_BASE}/repos/{full_name}/issues"
        params = {
            "state": "open",
            "labels": label,
            "per_page": max_issues,
            "sort": "created",
            "direction": "desc",
        }
        data = _get(url, params=params)
        if not data:
            continue
        for raw in data:
            if raw["id"] in seen_ids:
                continue
            seen_ids.add(raw["id"])
            issues.append(
                {
                    "number": raw["number"],
                    "title": raw["title"],
                    "url": raw["html_url"],
                    "labels": [lb["name"] for lb in raw.get("labels", [])],
                    "body_excerpt": _truncate(raw.get("body") or "", max_chars=800),
                    "comments_count": raw["comments"],
                    "created_at": raw["created_at"],
                    "user": raw["user"]["login"],
                }
            )
        time.sleep(0.1)

    _cache[key] = issues
    return issues


def get_issue_comments(full_name: str, issue_number: int) -> list[dict]:
    """
    Return comments for a specific issue (up to 5, truncated bodies).
    """
    key = _cache_key("comments", full_name, str(issue_number))
    if key in _cache:
        return _cache[key]

    url = f"{config.GITHUB_API_BASE}/repos/{full_name}/issues/{issue_number}/comments"
    data = _get(url, params={"per_page": 5}) or []
    comments = [
        {
            "user": c["user"]["login"],
            "body_excerpt": _truncate(c.get("body") or "", max_chars=500),
            "created_at": c["created_at"],
        }
        for c in data[:5]
    ]
    _cache[key] = comments
    return comments


# ── Individual file contents ──────────────────────────────────────────────────

def get_file_content(full_name: str, path: str) -> str | None:
    """
    Fetch and decode a single file by path. Returns None if not found.
    Truncated to FILE_EXCERPT_CHARS.
    """
    key = _cache_key("file", full_name, path)
    if key in _cache:
        return _cache[key]

    url = f"{config.GITHUB_API_BASE}/repos/{full_name}/contents/{path}"
    data = _get(url)
    if not data or "content" not in data:
        _cache[key] = None
        return None

    raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    result = _truncate(raw)
    _cache[key] = result
    return result


def list_directory(full_name: str, path: str) -> list[dict] | None:
    """
    List contents of a directory by path.
    Returns list of {path, type, size} dicts, or None if not found.
    """
    key = _cache_key("dir", full_name, path)
    if key in _cache:
        return _cache[key]

    url = f"{config.GITHUB_API_BASE}/repos/{full_name}/contents/{path}"
    data = _get(url)
    if not data or not isinstance(data, list):
        _cache[key] = None
        return None

    result = [
        {
            "path": item["path"],
            "type": "dir" if item["type"] == "dir" else "file",
            "size": item.get("size", 0),
        }
        for item in data
    ]
    _cache[key] = result
    return result


# ── Repo metadata ─────────────────────────────────────────────────────────────

def get_repo_metadata(full_name: str) -> dict | None:
    """Return raw GitHub repo metadata dict."""
    key = _cache_key("meta", full_name)
    if key in _cache:
        return _cache[key]

    url = f"{config.GITHUB_API_BASE}/repos/{full_name}"
    data = _get(url)
    _cache[key] = data
    return data


# ── Cache control ─────────────────────────────────────────────────────────────

def clear_cache() -> None:
    """Clear the in-process cache (call between sessions if needed)."""
    _cache.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate(text: str, max_chars: int | None = None) -> str:
    """Truncate text to max_chars, appending a notice if cut."""
    limit = max_chars or config.FILE_EXCERPT_CHARS
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[... truncated at {limit} characters ...]"
