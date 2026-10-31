"""
app.py — OpenPath Streamlit UI

Single-page app with 4 sequential steps:
  Step 1 → Profile form (sidebar)
  Step 2 → Ranked repository cards
  Step 3 → Repo overview + beginner issue list
  Step 4 → Contribution plan + PR draft
"""

import html
import re
import streamlit as st

from modules.finder import search_repositories, RateLimitError, SearchError
from modules.ranker import rank_repositories
from modules import github_data
from modules.pr_buddy import get_repo_overview, get_contribution_plan

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG — must be the very first Streamlit call
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="OpenPath",
    page_icon="🛤️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL STYLES
# ══════════════════════════════════════════════════════════════════════════════

st.markdown(
    """
    <style>
    /* ── fonts & base ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ── hide the default Streamlit top decoration bar ── */
    #MainMenu { visibility: hidden; }
    footer     { visibility: hidden; }
    header     { visibility: hidden; }

    /* ── repo / issue cards ── */
    .card {
        background: #1E2130;
        border: 1px solid #2D3148;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 16px;
        transition: border-color 0.2s;
    }
    .card:hover { border-color: #6C63FF; }

    /* ── ai reason pill ── */
    .ai-pill {
        background: rgba(108,99,255,0.15);
        border-left: 3px solid #6C63FF;
        border-radius: 0 8px 8px 0;
        padding: 10px 14px;
        margin-top: 10px;
        font-size: 0.9rem;
        color: #C9C5FF;
    }

    /* ── stat badges ── */
    .badge {
        display: inline-block;
        background: #2D3148;
        border-radius: 20px;
        padding: 3px 10px;
        font-size: 0.78rem;
        color: #8B949E;
        margin-right: 6px;
    }

    /* ── section headers ── */
    .section-title {
        font-size: 1.4rem;
        font-weight: 700;
        color: #FAFAFA;
        margin-bottom: 4px;
    }

    /* ── step indicator pill ── */
    .step-pill {
        display: inline-block;
        background: #6C63FF;
        color: white;
        border-radius: 20px;
        padding: 2px 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-bottom: 12px;
    }

    /* ── plan output box ── */
    .plan-box {
        background: #1E2130;
        border: 1px solid #2D3148;
        border-radius: 12px;
        padding: 24px;
    }

    /* ── disclaimer ── */
    .disclaimer {
        background: rgba(255,165,0,0.1);
        border: 1px solid rgba(255,165,0,0.3);
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 0.82rem;
        color: #FFA500;
        margin-top: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE — initialise all keys once
# ══════════════════════════════════════════════════════════════════════════════

_DEFAULTS = {
    "step": 1,
    "profile": {},
    "candidates": [],
    "ranked_repos": [],
    "relaxation_note": "",
    "selected_repo": None,
    "repo_readme": "",
    "repo_tree": [],
    "repo_contributing": "",
    "repo_overview": "",
    "beginner_issues": [],
    "selected_issue": None,
    "contribution_plan": "",
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def reset_all():
    """Wipe session state and go back to step 1."""
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


def fmt_date(iso: str) -> str:
    """Turn '2024-10-15T08:22:11Z' into '2024-10-15'."""
    return iso[:10] if iso else "Unknown"


def clean_issue_text(text: str, max_len: int = 240) -> str:
    """Strip GitHub issue form boilerplate, markdown headers, and excess newlines."""
    if not text:
        return "No description provided."
    # Remove markdown image/link syntax artifacts
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Remove markdown headings (#, ##, ###)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Remove GitHub template fields that say 'No response'
    text = re.sub(r"(?i)\b(Type\(s\) of Problems|URL|Operating System|Screenshots?):\s*No response\b", "", text)
    text = re.sub(r"(?i)\bNo response\b", "", text)
    # Clean multiple spaces and blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = " ".join(lines)
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "…"
    return cleaned or "No description provided."


def _select_repo(repo: dict):
    """
    Called when the user clicks 'Select →' on a repo card.
    Fetches all repo data + generates the AI overview.
    Stored in session state so we don't re-fetch on every rerun.
    """
    st.session_state.selected_repo = repo

    with st.spinner("📖 Loading repository information..."):
        st.session_state.repo_readme       = github_data.get_readme(repo["full_name"])
        st.session_state.repo_tree         = github_data.get_top_level_tree(repo["full_name"])
        st.session_state.repo_contributing = github_data.get_contributing_guide(repo["full_name"])
        st.session_state.beginner_issues   = github_data.get_beginner_issues(repo["full_name"])

    with st.spinner("🤖 PR Buddy is reading the repository..."):
        st.session_state.repo_overview = get_repo_overview(
            repo,
            st.session_state.repo_readme,
            st.session_state.repo_tree,
            st.session_state.repo_contributing,
        )

    st.session_state.step = 3
    st.rerun()


def _select_issue(issue: dict):
    """
    Called when the user clicks 'Pick →' on an issue card.
    Generates the contribution plan using PR Buddy.
    """
    st.session_state.selected_issue = issue

    with st.spinner("📋 PR Buddy is writing your contribution plan..."):
        st.session_state.contribution_plan = get_contribution_plan(
            st.session_state.selected_repo,
            issue,
            st.session_state.repo_overview,
        )

    st.session_state.step = 4
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — STEP 1: Profile Form
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    # ── Brand header ──────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style='text-align:center; padding: 8px 0 16px 0;'>
            <div style='font-size:2.4rem;'>🛤️</div>
            <div style='font-size:1.5rem; font-weight:700; color:#FAFAFA;'>OpenPath</div>
            <div style='font-size:0.8rem; color:#8B949E; margin-top:2px;'>
                Your guide to a first open-source contribution
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Step indicator ────────────────────────────────────────────────────────
    step_labels = {1: "Step 1 of 4", 2: "Step 2 of 4", 3: "Step 3 of 4", 4: "Step 4 of 4"}
    st.markdown(
        f"<span class='step-pill'>{step_labels[st.session_state.step]}</span>",
        unsafe_allow_html=True,
    )

    st.markdown("### 👤 Your Profile")

    # ── Form fields ───────────────────────────────────────────────────────────
    language_input = st.text_input(
        "Main programming language *",
        placeholder="e.g. Python, JavaScript, Rust",
        help="Enter one primary language. This is the most important filter.",
    )

    topics_input = st.text_input(
        "Topics or frameworks (optional)",
        placeholder="e.g. machine learning, react, cli",
        help="Comma-separated. Leave blank for no topic filter.",
    )

    experience = st.selectbox(
        "Your experience level *",
        options=["Absolute beginner", "Some projects", "Comfortable"],
        help="This helps the AI tailor its explanations.",
    )

    notes = st.text_area(
        "Anything else? (optional)",
        placeholder="e.g. I'm interested in documentation, I like small projects...",
        height=80,
        help="Free text — the AI reads this when ranking repos.",
    )

    st.markdown("")  # spacing

    find_btn = st.button("🔍 Find Repositories", type="primary", use_container_width=True)

    # ── Find button logic ─────────────────────────────────────────────────────
    if find_btn:
        if not language_input.strip():
            st.error("Please enter at least one programming language.")
        else:
            languages = [l.strip() for l in language_input.split(",") if l.strip()]
            topics    = [t.strip() for t in topics_input.split(",")   if t.strip()]

            # Save profile to session state
            st.session_state.profile = {
                "languages": languages,
                "topics": topics,
                "experience": experience,
                "notes": notes,
            }

            try:
                with st.spinner("🔍 Searching GitHub for matching repositories..."):
                    candidates, note = search_repositories(
                        language=languages[0],
                        topics=topics,
                    )
                    st.session_state.candidates      = candidates
                    st.session_state.relaxation_note = note

                if not candidates:
                    st.warning(
                        "No repositories found. Try a different language "
                        "or remove some topic filters."
                    )
                else:
                    with st.spinner("🤖 Gemma 4 is ranking and explaining repositories..."):
                        ranked = rank_repositories(
                            repos=candidates,
                            languages=languages,
                            topics=topics,
                            experience=experience,
                            notes=notes,
                        )
                    st.session_state.ranked_repos = ranked
                    st.session_state.step = 2
                    st.rerun()

            except RateLimitError as e:
                st.error(
                    f"⏳ GitHub rate limit reached. "
                    f"Please wait **{e.wait_seconds} seconds** and try again."
                )
            except SearchError as e:
                st.error(f"🔍 Search failed: {e}")
            except Exception as e:
                st.error(
                    f"Something went wrong: {e}\n\n"
                    "Check your API keys in `.env` and try again."
                )

    # ── Start Over ────────────────────────────────────────────────────────────
    if st.session_state.step > 1:
        st.divider()
        if st.button("🔄 Start Over", use_container_width=True):
            reset_all()

    # ── Footer ────────────────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        """
        <div style='font-size:0.75rem; color:#8B949E; line-height:1.6;'>
            🤖 Powered by <strong>Gemma 4</strong> via Google AI Studio<br>
            📡 Data from <strong>GitHub REST API</strong>
        </div>
        <div class='disclaimer' style='margin-top:10px;'>
            ⚠️ Suggestions are advisory. Always read the repository's own
            contributing guide before submitting a pull request.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 LANDING — shown before any search
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step == 1:
    # Hero section
    st.markdown(
        """
        <div style='text-align:center; padding: 60px 20px 40px 20px;'>
            <div style='font-size:3.5rem; margin-bottom:12px;'>🛤️</div>
            <h1 style='font-size:2.8rem; font-weight:800; color:#FAFAFA; margin:0;'>
                Welcome to OpenPath
            </h1>
            <p style='font-size:1.15rem; color:#8B949E; margin-top:12px; max-width:560px;
                      margin-left:auto; margin-right:auto; line-height:1.7;'>
                Making your first open-source contribution is hard.<br>
                OpenPath finds you the right repo, explains it clearly,<br>
                and gives you a step-by-step plan to get started.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # How it works — 4 cards in a row
    c1, c2, c3, c4 = st.columns(4)
    steps_info = [
        ("👤", "Tell us your stack", "Language, topics, experience level"),
        ("🔍", "We search GitHub", "Active, beginner-friendly repos only"),
        ("🤖", "Gemma 4 ranks them", "Explains why each repo fits you"),
        ("📋", "Get a plan", "Which files to change, step by step"),
    ]
    for col, (icon, title, desc) in zip([c1, c2, c3, c4], steps_info):
        with col:
            st.markdown(
                f"""
                <div class='card' style='text-align:center; padding:20px 12px;'>
                    <div style='font-size:2rem; margin-bottom:8px;'>{icon}</div>
                    <div style='font-weight:600; font-size:0.95rem; color:#FAFAFA;'>{title}</div>
                    <div style='font-size:0.8rem; color:#8B949E; margin-top:6px;'>{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        "<p style='text-align:center; color:#8B949E; margin-top:30px;'>"
        "← Fill in your profile in the sidebar to get started</p>",
        unsafe_allow_html=True,
    )
    st.stop()  # Don't render anything below step 1


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Repository Cards
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step >= 2:
    profile = st.session_state.profile

    if st.session_state.step == 2:
        # User is actively picking a repository
        st.markdown("<div class='step-pill'>Step 2 — Pick a Repository</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='section-title'>Repositories for "
            f"<span style='color:#6C63FF;'>{', '.join(profile.get('languages', []))}</span>"
            f" developers</div>",
            unsafe_allow_html=True,
        )

        if st.session_state.relaxation_note:
            st.info(f"ℹ️ {st.session_state.relaxation_note}")

        repos = st.session_state.ranked_repos
        if not repos:
            st.warning(
                "No repositories found. Try a different language or remove some topic filters."
            )
        else:
            st.caption(
                f"Found {len(repos)} repositories, ranked by Gemma 4 for your profile. "
                "Click **Select →** to explore one."
            )
            st.markdown("")

            for idx, repo in enumerate(repos):
                desc       = html.escape(repo["description"] or "No description provided.")
                ai_reason  = html.escape(repo.get("ai_reason", ""))
                topics_str = "  ".join(
                    f"`{t}`" for t in repo.get("topics", [])[:5]
                ) or ""

                with st.container(border=True):
                    col_info, col_action = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f"""
                            <div>
                                <a href='{repo["url"]}' target='_blank'
                                   style='font-size:1.15rem; font-weight:700; color:#6C63FF; text-decoration:none;'>
                                    {repo["full_name"]} ↗
                                </a>
                                <span class='badge' style='margin-left:8px;'>{repo["language"]}</span>
                                <span class='badge' style='background:rgba(0,201,167,0.15); color:#00C9A7;'>
                                    🐣 beginner issues ✓
                                </span>
                            </div>
                            <div style='color:#8B949E; font-size:0.88rem; margin:6px 0 8px 0;'>{desc}</div>
                            <div>
                                <span class='badge'>⭐ {repo["stars"]:,}</span>
                                <span class='badge'>🕒 {fmt_date(repo["last_pushed"])}</span>
                                <span class='badge'>📄 {repo.get("license","Unknown")}</span>
                            </div>
                            {f"<div style='margin-top:6px; font-size:0.8rem; color:#8B949E;'>{topics_str}</div>" if topics_str else ""}
                            <div class='ai-pill'>🤖 {ai_reason}</div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with col_action:
                        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
                        if st.button(
                            "Select →",
                            key=f"sel_{idx}_{repo['full_name']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            _select_repo(repo)

        st.divider()

    else:
        # Step >= 3: Repo already selected! Show a sleek summary banner instead of the full list
        repo = st.session_state.selected_repo
        c_title, c_btn = st.columns([4, 1])
        with c_title:
            st.markdown(
                f"<div style='background:#1E2130; border:1px solid #2D3148; border-radius:10px; padding:10px 16px; margin-bottom:12px;'>"
                f"Selected Repository: <strong style='color:#6C63FF;'>{repo['full_name']}</strong> "
                f"<span class='badge'>⭐ {repo['stars']:,}</span> "
                f"<span class='badge'>{repo['language']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with c_btn:
            if st.button("← Change Repo", key="change_repo_btn", use_container_width=True):
                st.session_state.step = 2
                st.session_state.selected_repo = None
                st.session_state.selected_issue = None
                st.session_state.contribution_plan = ""
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Repo Overview + Issue Selection
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step >= 3 and st.session_state.selected_repo:
    repo = st.session_state.selected_repo

    if st.session_state.step == 3:
        # User is actively reading the repo overview and picking an issue
        st.markdown("<div class='step-pill'>Step 3 — Understand the Repository</div>", unsafe_allow_html=True)

        ov_col, link_col = st.columns([5, 1])
        with ov_col:
            st.markdown(
                f"<div class='section-title'>{repo['full_name']}</div>",
                unsafe_allow_html=True,
            )
        with link_col:
            st.markdown(
                f"<a href='{repo['url']}' target='_blank' "
                f"style='color:#6C63FF; font-size:0.85rem;'>Open on GitHub ↗</a>",
                unsafe_allow_html=True,
            )

        # ── Overview text (from PR Buddy) ─────────────────────────────────────────
        with st.container(border=True):
            st.markdown(st.session_state.repo_overview)

        st.divider()

        # ── Issue list ────────────────────────────────────────────────────────────
        st.markdown("### 🐣 Pick a Beginner-Friendly Issue")
        st.caption(
            "These issues are labelled `good first issue` or similar in the repository. "
            "Click **Pick →** to get a contribution plan."
        )

        issues = st.session_state.beginner_issues
        if not issues:
            st.warning(
                "No beginner-friendly issues found in this repository right now. "
                "Try selecting a different repository."
            )
        else:
            for i_idx, issue in enumerate(issues):
                label_str    = "  ".join(f"`{lb}`" for lb in issue.get("labels", [])[:4])
                safe_title   = html.escape(issue["title"])
                clean_preview = html.escape(clean_issue_text(issue.get("body_excerpt", "")))

                with st.container(border=True):
                    col_info, col_btn = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f"""
                            <div>
                                <a href='{issue["url"]}' target='_blank'
                                   style='font-weight:700; color:#00C9A7; text-decoration:none; font-size:1.02rem;'>
                                    #{issue["number"]} — {safe_title} ↗
                                </a>
                            </div>
                            <div style='margin:4px 0 6px 0; font-size:0.8rem;'>{label_str}</div>
                            <div style='font-size:0.86rem; color:#8B949E; line-height:1.5; margin-bottom:8px;'>
                                {clean_preview}
                            </div>
                            <div>
                                <span class='badge'>💬 {issue["comments_count"]} comments</span>
                                <span class='badge'>🕒 {fmt_date(issue["created_at"])}</span>
                                <span class='badge'>👤 {issue["user"]}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with col_btn:
                        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                        if st.button(
                            "Pick →",
                            key=f"iss_{i_idx}_{issue['number']}",
                            type="primary",
                            use_container_width=True,
                        ):
                            _select_issue(issue)

        st.divider()

    else:
        # Step >= 4: Issue already chosen! Show compact summary and collapsible overview
        issue = st.session_state.selected_issue
        c_iss, c_btn = st.columns([4, 1])
        with c_iss:
            st.markdown(
                f"<div style='background:#1E2130; border:1px solid #2D3148; border-radius:10px; padding:10px 16px; margin-bottom:12px;'>"
                f"Selected Issue: <strong style='color:#00C9A7;'>#{issue['number']} — {html.escape(issue['title'])}</strong>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with c_btn:
            if st.button("← Pick Another Issue", key="change_issue_btn", use_container_width=True):
                st.session_state.step = 3
                st.session_state.selected_issue = None
                st.session_state.contribution_plan = ""
                st.rerun()

        with st.expander("📖 View Repository Overview"):
            st.markdown(st.session_state.repo_overview)
        st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Contribution Plan
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.step >= 4 and st.session_state.contribution_plan:
    issue = st.session_state.selected_issue
    repo  = st.session_state.selected_repo

    st.markdown("<div class='step-pill'>Step 4 — Your Contribution Plan</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='section-title'>🎉 Plan for: "
        f"<span style='color:#00C9A7;'>#{issue['number']} — {issue['title']}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Repository: [{repo['full_name']}]({repo['url']})")
    st.markdown("")

    # ── Plan content ──────────────────────────────────────────────────────────
    plan_text = st.session_state.contribution_plan

    # Split out the PR draft section so we can put it in a copyable box
    pr_match = re.search(
        r"(?:^|\n)\s*(?:#{1,3}\s*|\*+\s*)*(?:Draft\s*(?:pull\s*request|PR)[^\n*]*)",
        plan_text,
        re.IGNORECASE
    )
    if pr_match:
        split_idx = pr_match.start()
        plan_body = plan_text[:split_idx].strip()
        pr_section = plan_text[split_idx:].strip()
    else:
        plan_body = plan_text
        pr_section = ""

    # Main plan
    with st.container(border=True):
        st.markdown(plan_body)

    # PR draft in its own copyable box
    if pr_section:
        st.markdown("")
        st.markdown("### 📝 Draft Pull Request")
        st.markdown(
            "<div style='font-size:0.82rem; color:#8B949E; margin-bottom:8px;'>"
            "Copy this into the GitHub pull request description field."
            "</div>",
            unsafe_allow_html=True,
        )
        # Extract just the text below the heading for the text area
        lines = pr_section.split("\n")
        pr_body_lines = [l for l in lines[1:] if l.strip()]  # skip the heading line
        pr_body_text  = "\n".join(pr_body_lines).strip()
        st.text_area(
            label="Pull Request Draft",
            value=pr_body_text,
            height=220,
            label_visibility="collapsed",
        )

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.markdown("")
    st.markdown(
        """
        <div class='disclaimer'>
            ⚠️ This plan is AI-generated and advisory only. The AI may not have
            seen every file in the repository. Always:<br>
            1. Read the repo's <strong>CONTRIBUTING.md</strong> before starting.<br>
            2. Run the test suite after your change.<br>
            3. Ask in the issue comments if anything is unclear — maintainers are usually happy to help!
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Next steps callout ────────────────────────────────────────────────────
    st.markdown("")
    st.success(
        "🚀 **You're ready to start!**  \n"
        "Fork the repo, create a branch, make your change, and open a pull request.  \n"
        "Good luck with your first contribution — you've got this!"
    )

    st.markdown("")
    # ── Action buttons ────────────────────────────────────────────────────────
    a_col, b_col, _ = st.columns([1, 1, 3])
    with a_col:
        st.link_button(
            "Open Repository ↗",
            url=repo["url"],
            use_container_width=True,
        )
    with b_col:
        st.link_button(
            "Open Issue ↗",
            url=issue["url"],
            use_container_width=True,
        )
