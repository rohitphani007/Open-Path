"""
modules/ranker.py — AI ranking and explanation of candidate repositories.

Sends the user's profile + candidate list to Gemma 4 and gets back
a ranked, explained list in structured JSON.

NO GitHub API calls here — only AI inference.
"""

from __future__ import annotations

import json
import re
from typing import Any

import google.generativeai as genai

import config

# Configure the SDK once at import time
genai.configure(api_key=config.GEMINI_API_KEY)


# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a helpful assistant for beginner open-source contributors.
Your job is to rank a list of GitHub repositories and explain why each one
suits the given developer profile.

Rules you must follow:
1. Only use information provided to you. Never invent stars, topics, dates or descriptions.
2. Rank repositories from most suitable to least suitable for this specific profile.
3. Keep each reason to 1–2 sentences. Mention the language/topic match and beginner-friendliness.
4. Return ONLY valid JSON — no markdown fences, no preamble, no trailing text.
5. If a repository seems poorly suited, you may still include it but rank it lower.
"""

_USER_PROMPT_TEMPLATE = """\
## Developer Profile
- Main language(s): {languages}
- Topics / frameworks of interest: {topics}
- Experience level: {experience}
- Additional interests: {notes}

## Candidate Repositories ({count} total)
{repo_list}

## Task
Return a JSON array. Each element must have exactly these keys:
  "full_name"  – the repository's full_name (owner/repo), copied exactly
  "reason"     – 1–2 sentence explanation tailored to the profile above

Order the array from best match (index 0) to worst match (last index).
Return ONLY the JSON array. No other text.
"""


def _format_repo_list(repos: list[dict[str, Any]]) -> str:
    """Convert repo dicts into a compact numbered list for the prompt."""
    lines = []
    for i, r in enumerate(repos, 1):
        topics = ", ".join(r.get("topics", [])[:5]) or "none listed"
        lines.append(
            f"{i}. {r['full_name']}\n"
            f"   Description: {r['description']}\n"
            f"   Language: {r['language']} | Stars: {r['stars']:,} | "
            f"Last pushed: {r['last_pushed'][:10]} | "
            f"Beginner issues: {r.get('beginner_issues', '?')}\n"
            f"   Topics: {topics}"
        )
    return "\n\n".join(lines)


def _extract_json(text: str) -> list[dict]:
    """
    Extract a JSON array from model output even if it contains
    extra whitespace or accidental markdown fences.
    """
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first '[' ... ']' block
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from model response:\n{text[:500]}")


# ── Public API ────────────────────────────────────────────────────────────────

def rank_repositories(
    repos: list[dict[str, Any]],
    languages: list[str],
    topics: list[str],
    experience: str,
    notes: str = "",
) -> list[dict[str, Any]]:
    """
    Rank and annotate `repos` using Gemma 4.

    Returns a new list of repo dicts in ranked order, each enriched with:
      "ai_reason" – the model's explanation string

    Falls back to the original order if the model response can't be parsed.
    """
    if not repos:
        return []

    model = genai.GenerativeModel(
        model_name=config.GEMMA_MODEL,
        system_instruction=_SYSTEM_PROMPT,
    )

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        languages=", ".join(languages) or "Not specified",
        topics=", ".join(topics) or "None",
        experience=experience,
        notes=notes or "None",
        count=len(repos),
        repo_list=_format_repo_list(repos),
    )

    response = model.generate_content(
        user_prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.2,       # Low temp for consistent ranking
            max_output_tokens=1024,
        ),
    )

    raw_text = response.text.strip()

    # Parse JSON ranking
    try:
        ranked_json = _extract_json(raw_text)
    except ValueError:
        # Fallback: return original order with a generic reason
        for repo in repos:
            repo.setdefault("ai_reason", "AI ranking unavailable — shown in original order.")
        return repos

    # Build a lookup so we can merge ai_reason into the full repo dicts
    reason_map: dict[str, str] = {
        item["full_name"]: item.get("reason", "")
        for item in ranked_json
        if "full_name" in item
    }

    # Reorder repos according to the model's ranking
    ordered_names = [item["full_name"] for item in ranked_json if "full_name" in item]
    repo_lookup = {r["full_name"]: r for r in repos}

    ranked_repos: list[dict] = []
    for name in ordered_names:
        if name in repo_lookup:
            repo = dict(repo_lookup[name])      # shallow copy
            repo["ai_reason"] = reason_map.get(name, "")
            ranked_repos.append(repo)

    # Append any repos the model didn't mention (shouldn't happen, but safe)
    mentioned = set(ordered_names)
    for repo in repos:
        if repo["full_name"] not in mentioned:
            repo = dict(repo)
            repo["ai_reason"] = ""
            ranked_repos.append(repo)

    # Trim to display limit
    return ranked_repos[: config.MAX_RESULTS]
