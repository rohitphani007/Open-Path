"""
modules/pr_buddy.py — AI assistant that produces a repository overview
and a concrete first-contribution plan.

Two public functions:
  get_repo_overview(repo, readme, tree, contributing)
      → beginner-friendly explanation of the project

  get_contribution_plan(repo, issue, overview, repo_full_name)
      → step-by-step plan with a PR draft

The model is given 2–3 tools so it can request specific files.
A hard cap of MAX_TOOL_ITERATIONS prevents infinite loops.
Falls back to a fixed pipeline if tool-use fails.
"""

from __future__ import annotations

import re
from typing import Any

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

import config
from modules import github_data

genai.configure(api_key=config.GEMINI_API_KEY)


# ── Shared system prompt ───────────────────────────────────────────────────────

_SYSTEM = """\
You are PR Buddy, a friendly assistant helping beginner developers make their
first open-source contribution. You explain things in plain, encouraging language.

Rules:
- Be honest. If you are not sure about something, say so explicitly.
- Never claim certainty about code you have not seen.
- Keep technical jargon to a minimum, and explain it when you do use it.
- Format your output with clear headings and bullet points.
"""


# ── Overview ──────────────────────────────────────────────────────────────────

_OVERVIEW_PROMPT = """\
Write a clear, thorough, beginner-friendly explanation of the GitHub repository '{full_name}'.
DO NOT repeat these instructions.
DO NOT output meta commentary or role summaries.
Immediately write the actual guide with these exact four markdown (##) headings:

## What this project does
Explain what this project does, who uses it, and why it exists in simple, encouraging terms.

## How the project is organised
Explain where the main code, documentation, and tests live based on the file tree and README.

## How to run it locally
Provide the practical terminal commands to clone, install, and run this project locally based on the README.

## How to contribute (rules and process)
Explain the contribution process, pull request etiquette, and guidelines from the contributing guide or README.

---
Repository: {full_name}
Stars: {stars} | Language: {language} | License: {license}

### README
{readme}

### Top-level file tree
{tree}

### Contributing guide
{contributing}
"""


def get_repo_overview(
    repo: dict[str, Any],
    readme: str,
    tree: list[dict],
    contributing: str,
) -> str:
    """
    Ask Gemma 4 to produce a beginner-friendly overview of the repository.
    Returns the overview as a markdown string.
    """
    tree_text = _render_tree(tree)

    prompt = _OVERVIEW_PROMPT.format(
        full_name=repo["full_name"],
        stars=f"{repo['stars']:,}",
        language=repo["language"],
        license=repo.get("license", "Unknown"),
        readme=readme or "(README not found)",
        tree=tree_text or "(file tree unavailable)",
        contributing=contributing or "(No contributing guide found)",
    )

    try:
        # Do not use system_instruction with Gemma 4 for overview — it causes prompt echoing
        model = genai.GenerativeModel(
            model_name=config.GEMMA_MODEL,
        )
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=2000,
            ),
        )
        text = response.text.strip()

        # Check if the real overview is present and trim any chain-of-thought preamble
        cleaned = _clean_overview_markdown(text)
        if cleaned and len(cleaned) > 250 and not cleaned.startswith("* Role:"):
            return cleaned

    except Exception:
        pass

    # High-quality fallback if model echoes prompt or errors
    return (
        f"## What this project does\n"
        f"**{repo['full_name']}** is an active open-source project written in **{repo['language']}** "
        f"with {repo['stars']:,} stars. \n\n"
        f"{repo.get('description', '')}\n\n"
        f"## How the project is organised\n"
        f"The repository is structured with the following top-level components:\n\n"
        f"{tree_text}\n\n"
        f"## How to run it locally\n"
        f"```bash\n"
        f"# 1. Clone your fork of the repository\n"
        f"git clone https://github.com/<your-username>/{repo['name']}.git\n"
        f"cd {repo['name']}\n\n"
        f"# 2. Inspect the README for specific environment and build dependencies\n"
        f"```\n\n"
        f"## How to contribute (rules and process)\n"
        f"{contributing[:600] if contributing else 'Always create a feature branch, keep your changes focused, test locally, and refer to the project issues before opening a pull request.'}\n"
    )


# ── Contribution plan — tool definitions ──────────────────────────────────────

def _make_tools(repo_full_name: str) -> tuple[Tool, dict]:
    """
    Build the Tool object and a dispatch table for the model's function calls.
    Returns (tool, dispatch_map).
    """
    read_file_fn = FunctionDeclaration(
        name="read_file",
        description=(
            "Read the contents of a specific file in the repository. "
            "Use this when you need to understand a file before suggesting changes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the repository root, e.g. 'src/utils.py'",
                },
            },
            "required": ["path"],
        },
    )

    list_directory_fn = FunctionDeclaration(
        name="list_directory",
        description=(
            "List all files and folders inside a directory. "
            "Use this to explore a specific folder before deciding which file to read."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to the repository root, e.g. 'src'",
                },
            },
            "required": ["path"],
        },
    )

    tool = Tool(function_declarations=[read_file_fn, list_directory_fn])

    def _dispatch(fn_name: str, args: dict) -> str:
        if fn_name == "read_file":
            content = github_data.get_file_content(repo_full_name, args["path"])
            return content if content is not None else f"File not found: {args['path']}"
        elif fn_name == "list_directory":
            items = github_data.list_directory(repo_full_name, args["path"])
            if items is None:
                return f"Directory not found: {args['path']}"
            return "\n".join(
                f"{'[dir]' if i['type'] == 'dir' else '[file]'} {i['path']}"
                for i in items
            )
        return f"Unknown function: {fn_name}"

    return tool, _dispatch


# ── Contribution plan prompt ──────────────────────────────────────────────────

_PLAN_SYSTEM = """\
You are PR Buddy, a friendly assistant helping beginner developers make their
first open-source contribution.

You have tools available to read files and list directories in the repository.
Use them to look at relevant files before suggesting changes. Stop after at most
{max_iter} tool calls.

Rules:
- Be honest. If you are not sure, say so.
- Never claim certainty about code you have not seen.
- Do NOT output intermediate brainstorming notes or preamble.
- Do NOT wrap headings in bullet points or asterisks.
- Start directly with your section headings using standard markdown (##):

## What this issue is asking for
## Files likely involved
## Step-by-step instructions
## Before you submit — checklist
## Draft pull request title and description
"""

_PLAN_USER_PROMPT = """\
## Repository overview (already written for this user)
{overview}

## The issue the user chose
Title: {issue_title}
URL: {issue_url}
Labels: {issue_labels}

### Issue description
{issue_body}

### Top comments
{comments}

---
Please investigate the repository using your tools as needed, then produce a
complete, beginner-friendly contribution plan following the required sections.
"""


def get_contribution_plan(
    repo: dict[str, Any],
    issue: dict[str, Any],
    overview: str,
) -> str:
    """
    Ask Gemma 4 to produce a contribution plan for the issue.
    First tries with automatic tool use so the model can inspect repo files.
    If tool use yields an incomplete or brief thought, falls back to the reliable
    fixed pipeline with README, tree, issue and comments.
    """
    repo_full_name = repo["full_name"]

    # Python callables for SDK-level automatic function calling
    def read_file(path: str) -> str:
        """Read the contents of a specific file in the repository."""
        content = github_data.get_file_content(repo_full_name, path)
        return content if content is not None else f"File not found: {path}"

    def list_directory(path: str) -> str:
        """List all files and folders inside a directory."""
        items = github_data.list_directory(repo_full_name, path)
        if items is None:
            return f"Directory not found: {path}"
        return "\n".join(
            f"{'[dir]' if i['type'] == 'dir' else '[file]'} {i['path']}"
            for i in items
        )

    # Fetch comments to give the model more context upfront
    comments_data = github_data.get_issue_comments(
        repo["full_name"], issue["number"]
    )
    comments_text = "\n\n".join(
        f"**{c['user']}**: {c['body_excerpt']}" for c in comments_data
    ) or "(No comments)"

    user_prompt = _PLAN_USER_PROMPT.format(
        overview=overview,
        issue_title=issue["title"],
        issue_url=issue["url"],
        issue_labels=", ".join(issue.get("labels", [])),
        issue_body=issue.get("body_excerpt") or "(No description)",
        comments=comments_text,
    )

    try:
        model = genai.GenerativeModel(
            model_name=config.GEMMA_MODEL,
            system_instruction=_PLAN_SYSTEM.format(max_iter=config.MAX_TOOL_ITERATIONS),
            tools=[read_file, list_directory],
        )

        chat = model.start_chat(enable_automatic_function_calling=True)
        response = chat.send_message(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2500,
            ),
        )

        plan_text = _extract_text(response)

        # Validate that the model produced a real plan, not just an intermediate thought
        if plan_text and len(plan_text) > 300 and ("## " in plan_text or "What this issue" in plan_text):
            return _normalize_plan_markdown(plan_text)

    except Exception as e:
        return _fixed_pipeline_plan(repo, issue, overview, comments_text, error_note=str(e))

    # If the tool-use response was incomplete or truncated, use the reliable direct pipeline
    return _fixed_pipeline_plan(repo, issue, overview, comments_text)


def _fixed_pipeline_plan(
    repo: dict[str, Any],
    issue: dict[str, Any],
    overview: str,
    comments_text: str,
    error_note: str = "",
) -> str:
    """
    Fallback: fetch README + a few key files manually, then ask the model
    to write the plan without tool use.
    """
    # Gather whatever data we can
    readme = github_data.get_readme(repo["full_name"])
    tree = github_data.get_top_level_tree(repo["full_name"])
    tree_text = _render_tree(tree)

    note = ""
    if error_note:
        note = f"\n\n> ⚠️ Tool-use was unavailable ({error_note[:120]}). Plan is based on README and file tree only.\n"

    prompt = f"""\
## Repository: {repo['full_name']}
## README (excerpt)
{readme}

## Top-level file tree
{tree_text}

## Repository overview
{overview}

## Issue
Title: {issue['title']}
Labels: {', '.join(issue.get('labels', []))}
Description: {issue.get('body_excerpt') or '(No description)'}

## Comments
{comments_text}

---
Produce a complete, beginner-friendly contribution plan with these exact markdown (##) section headings:
Do NOT output intermediate rambling notes. Start immediately with ##:

## What this issue is asking for
## Files likely involved
## Step-by-step instructions
## Before you submit — checklist
## Draft pull request title and description

Be honest about what you don't know. Say clearly when you are guessing.
{note}
"""

    model = genai.GenerativeModel(
        model_name=config.GEMMA_MODEL,
    )
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=2500,
        ),
    )
    return _normalize_plan_markdown(response.text.strip())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_overview_markdown(text: str) -> str:
    """Trim any chain-of-thought or checklist bullets that appear before the first section."""
    if not text:
        return text
    # Match the beginning of ## What this project does (or variants)
    match = re.search(r"(?mi)^\s*(?:#{1,3}\s*|\*+\s*)*What this project does", text)
    if match and match.start() > 0:
        text = text[match.start():]
    return text.strip()


def _render_tree(tree: list[dict]) -> str:
    lines = []
    for item in tree:
        icon = "📁" if item["type"] == "dir" else "📄"
        size = f" ({item['size']:,} bytes)" if item["type"] == "file" and item.get("size") else ""
        lines.append(f"{icon} {item['path']}{size}")
    return "\n".join(lines) if lines else "(empty)"


def _normalize_plan_markdown(text: str) -> str:
    """Ensure standard markdown ## headers even if model used bullets or asterisks."""
    if not text:
        return text

    # If there are stray scratchpad notes before the first real section heading, trim them
    first_heading_match = re.search(
        r"(?mi)^\s*(?:\*\s*)?(?:#{1,3}\s*)?\*{0,2}(?:Section\s*\d+:?\s*)?What this issue is asking for",
        text
    )
    if first_heading_match and first_heading_match.start() > 0:
        text = text[first_heading_match.start():]

    # Convert '* **Section 1: ...**' or '**Section 1: ...**' or '* ## ...' into clean '## ...'
    text = re.sub(
        r"(?mi)^\s*(?:\*\s*)?(?:#{1,3}\s*)?\*{0,2}(?:Section\s*\d+:?\s*)?(What this issue is asking for|Files likely involved|Step-by-step instructions|Before you submit\s*[-—:]?\s*checklist|Draft pull request[^\n*:]*)\*{0,2}\s*:?\s*$",
        r"## \1",
        text
    )
    return text.strip()


def _extract_text(response: Any) -> str:
    """Pull plain text from a GenerateContentResponse."""
    try:
        return _normalize_plan_markdown(response.text.strip())
    except Exception:
        pass
    try:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    return _normalize_plan_markdown(part.text.strip())
    except Exception:
        pass
    return ""
