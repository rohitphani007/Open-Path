# 🛤️ OpenPath

> **Helping beginner developers make their very first open-source contribution with confidence.**

OpenPath solves the two biggest hurdles newcomers face when getting into open source:
1. **Discovery:** Finding active, welcoming repositories tailored to their language, skill level, and interests (no dead or intimidating projects).
2. **Guidance:** Demystifying unfamiliar codebases, picking a manageable issue, and building a concrete step-by-step contribution plan.

Powered by **Google Gemma 4** (via Google AI Studio) and the **GitHub REST API**, OpenPath acts as an advisory companion that guides you from curiosity to opening your first pull request.

---

## 🌟 Key Features

- **Personalized Repo Finder:** Queries live GitHub repositories filtered for recent activity, active maintainers, and confirmed beginner-friendly issues (`good first issue`).
- **AI Ranking & Fit Explanations:** **Gemma 4** (`gemma-4-26b-a4b-it`) analyzes candidate repositories against the developer's profile and returns structured rationale for why each project fits.
- **Repository Deep Dive:** PR Buddy breaks down project structure, how to run the repo locally, and key contribution rules from `CONTRIBUTING.md`.
- **Actionable Contribution Plans:** For any selected beginner issue, Gemma 4 provides:
  - What the issue actually asks for (stripping template boilerplate).
  - Files likely involved.
  - Step-by-step instructions (fork, branch, edit, test, commit).
  - Pre-submission checklist.
  - **Ready-to-use Draft Pull Request title and description** in a 1-click copy box.
- **Privacy & Safety First:** OpenPath is strictly advisory. It never modifies repositories, makes commits, or submits PRs on your behalf.

---

## 🏗️ Architecture

```
User Profile Form (Sidebar)
       │
       ▼
[modules/finder.py] ──────► GitHub Search API
                             (filtered by language, stars, pushed date, good-first-issues)
       │
       ▼
[modules/ranker.py] ──────► Google Gemma 4 API
                             (structured JSON ranking & personalized reasoning)
       │
  Select Repo
       │
       ▼
[modules/github_data.py] ──► GitHub REST API
                             (fetches README, tree, contributing guide, good-first-issues)
       │
  Select Issue
       │
       ▼
[modules/pr_buddy.py] ────► Google Gemma 4 API (with tool use)
                             (inspects files, produces step-by-step plan & PR draft)
       │
       ▼
Streamlit Interactive UI (app.py)
```

---

## 🚀 Quickstart (Local Development)

### 1. Prerequisites
- Python 3.10+
- A GitHub Personal Access Token (free, public read access only)
- A Google AI Studio API Key (with access to Gemma 4)

### 2. Clone and Setup Environment
```bash
git clone https://github.com/your-username/openpath.git
cd openpath

# Create and activate virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Secrets
Copy the `.env.example` template:
```bash
cp .env.example .env
```
Open `.env` and fill in your keys:
```env
GEMINI_API_KEY=your_google_ai_studio_key_here
GITHUB_TOKEN=your_github_personal_access_token_here
GEMMA_MODEL=gemma-4-26b-a4b-it
```

### 4. Run the App
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## ☁️ Deployment on Cloudways (DigitalOcean)

OpenPath is designed to deploy seamlessly to a Cloudways Flexible Server (Ubuntu 22.04 LTS / PHP-Stack or Custom Application):

1. **SSH into your Cloudways server**:
   ```bash
   ssh master_username@your_server_ip
   ```
2. **Clone the repository**:
   ```bash
   cd /home/master/applications/your_app/public_html
   git clone https://github.com/your-username/openpath.git .
   ```
3. **Set up Python environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Create `.env`**:
   ```bash
   cp .env.example .env
   nano .env
   ```
5. **Run Streamlit in background with systemd or tmux/nohup**:
   ```bash
   nohup venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &
   ```
   *(Configure an Nginx reverse proxy from port 80/443 to port 8501 for domain mapping with SSL).*

---

## 🏆 Hackathon Alignment

- **Best Use of Gemma 4:** Gemma 4 powers core project recommendation ranking, codebase onboarding, issue triage, and automated PR draft synthesis.
- **Best Open-Source AI Project:** 100% open-source under the MIT license, using open-weight models and zero vendor lock-in.
- **Best Use of Cloudways:** Fully deployable on DigitalOcean infrastructure via Cloudways.

---

## 📜 License

Distributed under the [MIT License](LICENSE).
