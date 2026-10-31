# OpenPath

**Helping beginner developers make their first open-source contribution with confidence.**

Built for Hacktoberfest Hack Day Hyderabad x AI Community Hyderabad (31 October 2026). Powered by Google Gemma 4 and the GitHub REST API. Released under the MIT license.

Live demo: not deployed yet (a Cloudways deployment is planned, see "Deployment" below).

## The problem

Most beginners want to contribute to open source but get stuck in two places:

1. **Discovery.** It is hard to tell which repositories are active, welcoming and a good match for your language and skill level. Many repos are dead or far too big to start with.
2. **Guidance.** Even after picking a repo, a beginner doesn't know how it is organised, which issue to take, or what a first contribution actually involves.

## What OpenPath does

You tell OpenPath your languages, interests and experience level. It then:

1. Searches live GitHub data for active repositories that have open beginner-friendly issues (`good first issue`).
2. Uses Gemma 4 to rank those repositories against your profile and explain, in plain language, why each one fits you.
3. Lets you pick a repository, then explains its structure, how to run it locally, and its contribution rules (from `CONTRIBUTING.md` when available).
4. Lets you pick a beginner issue and produces a concrete plan: what the issue really asks for, which files are likely involved, step-by-step instructions (fork, branch, edit, test, commit), a pre-submission checklist, and a draft pull request title and description you can copy.

OpenPath is advisory only. It never forks, edits, commits to or opens pull requests on any repository.

## How it works

```
User profile form (sidebar)
        |
        v
modules/finder.py -------> GitHub Search API
                           (language, stars, recent activity, good-first-issues, not archived)
        |
        v
modules/ranker.py -------> Gemma 4 via Gemini API
                           (structured JSON ranking and reasons per repo)
        |
   user selects a repo
        |
        v
modules/github_data.py --> GitHub REST API
                           (README, file tree, contributing guide, beginner issues)
        |
   user selects an issue
        |
        v
modules/pr_buddy.py -----> Gemma 4 (with tool use)
                           (reads files on request, writes the plan and PR draft)
        |
        v
app.py: Streamlit interface
```

## Tech stack

- Python 3.10 or newer
- Streamlit for the interface
- Google Gemma 4 (`gemma-4-26b-a4b-it` by default) through the Gemini API and Google AI Studio, using the `google-genai` SDK
- GitHub REST API through `requests`
- `python-dotenv` for configuration

## Getting started

### 1. Prerequisites

- Python 3.10 or newer
- A GitHub personal access token (free; only public read access is needed)
- A Google AI Studio API key with access to Gemma 4

### 2. Clone and install

```bash
git clone https://github.com/rohitphani007/Open-Path.git
cd Open-Path

python -m venv venv

# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure your keys

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

On Windows (Command Prompt) use `copy .env.example .env` instead.

```
GEMINI_API_KEY=your_google_ai_studio_key_here
GITHUB_TOKEN=your_github_personal_access_token_here
GEMMA_MODEL=gemma-4-26b-a4b-it
```

Never commit your `.env` file. It is already listed in `.gitignore`.

### 4. Run the app

```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Project structure

```
app.py            Streamlit interface that ties the steps together
config.py         Loads settings and keys from environment variables
check_models.py   Helper script to check which models your API key can use
modules/
  finder.py       Searches GitHub for suitable repositories
  ranker.py       Ranks and explains repositories with Gemma 4
  github_data.py  Fetches README, file tree, contributing guide and issues
  pr_buddy.py     Repository overview and contribution plan with Gemma 4
.env.example      Template for required environment variables
```

## Screenshots

Screenshots of the profile form, the ranked results and the contribution plan will be added here.

## Limitations

- The plans are suggestions written by an AI model. They can be wrong or incomplete, so always read the repository's own contributing guide before you start.
- Large repositories cannot be sent to the model whole. OpenPath sends the README, the top-level file tree and only the files it needs, so the overview may miss details.
- The GitHub API is rate limited. A personal access token is strongly recommended.
- Only public repositories are supported.

## Deployment (planned)

A deployment on Cloudways (DigitalOcean) is planned after the hackathon submission. The steps below are a draft and have not been verified yet; this section and the live demo link at the top will be updated once the deployment is tested.

1. Create a server on Cloudways and connect over SSH.
2. Clone the repository, create a virtual environment and install `requirements.txt`.
3. Create the `.env` file with your keys.
4. Run Streamlit bound to the local address, for example `streamlit run app.py --server.port 8501 --server.address 127.0.0.1`, kept alive with a process manager such as systemd or tmux.
5. Put a reverse proxy (Nginx) in front of port 8501 so the app is served over HTTP and HTTPS.

## Hackathon categories

- **Best Use of Gemma 4:** Gemma 4 powers the repository ranking, the codebase overview and the issue-to-plan step.
- **Best Open-Source AI Project:** the project is MIT licensed and built around an open-weight model. The model is configurable through the `GEMMA_MODEL` setting.
- **Best Use of Cloudways:** deployment is planned (see above).

## Contributing

Issues and pull requests are welcome. If you are new to open source, this is a good place to try your first contribution.

## License

Distributed under the MIT License. See the `LICENSE` file for details.
