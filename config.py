"""
config.py — loads all settings from environment variables / .env file.
Every other module imports from here. Never import os.environ directly elsewhere.
"""

import os
from dotenv import load_dotenv

# Load .env from the project root (one level up from this file if needed)
load_dotenv()


def _require(key: str) -> str:
    """Return the env var or raise a clear error."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Copy .env.example to .env and fill in your values."
        )
    return value


# ── API keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
GITHUB_TOKEN: str = _require("GITHUB_TOKEN")

# ── Model ─────────────────────────────────────────────────────────────────────
# Default to the lighter MoE variant; override in .env to use gemma-4-31b-it
GEMMA_MODEL: str = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")

# ── GitHub search tuning ──────────────────────────────────────────────────────
# Stars range for repos — neither abandoned nor overwhelming
STARS_MIN: int = int(os.getenv("STARS_MIN", "50"))
STARS_MAX: int = int(os.getenv("STARS_MAX", "5000"))

# Days since last push to consider a repo "active"
ACTIVITY_DAYS: int = int(os.getenv("ACTIVITY_DAYS", "60"))

# How many repos to fetch before AI ranking
MAX_CANDIDATES: int = int(os.getenv("MAX_CANDIDATES", "20"))

# How many repos to show the user after ranking
MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "8"))

# Max iterations for the PR Buddy tool-use loop
MAX_TOOL_ITERATIONS: int = int(os.getenv("MAX_TOOL_ITERATIONS", "5"))

# Max characters to send per file to the model (prevents context overflow)
FILE_EXCERPT_CHARS: int = int(os.getenv("FILE_EXCERPT_CHARS", "3000"))

# ── GitHub API ────────────────────────────────────────────────────────────────
GITHUB_API_BASE = "https://api.github.com"
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
