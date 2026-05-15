<div align="center">

<img src="https://img.shields.io/badge/AutoPatch-AI%20Agent-6366f1?style=for-the-badge&logo=github&logoColor=white" alt="AutoPatch" />

# AutoPatch

**AI-powered GitHub Issue Auto-Fix Agent**

*Automatically analyze, fix, and generate patches for GitHub Issues using a multi-agent pipeline.*

[中文版](README.zh.md)

</div>

---

## Demo

Point AutoPatch at any GitHub issue and get a ready-to-apply patch in minutes.

**Web UI:**

1. Enter a repository URL and issue number, then click **Run AutoPatch**

![Dashboard idle state](assets/dashboard-idle.png)

2. Watch the live agent pipeline: Planner → Coder → TestRunner → Reviewer

![Dashboard running](assets/dashboard-running.png)

3. Download the generated `.diff` or click **Create PR** to open a pull request directly

![Dashboard result](assets/dashboard-result.png)

**CLI:**

```bash
python autopatch.py https://github.com/daixinwang/bug-test 1
# → patches/issue-1_20260510_120000.diff

# Apply the patch to your local checkout
git apply patches/issue-1_20260510_120000.diff
```

---

## Features

**Core capabilities:**

- 🔍 **Autonomous codebase navigation** — `list_directory`, `search_codebase`, `find_definition`, `grep_in_file`
- ✍️ **Automated code repair** — Coder agent reads, writes, and verifies files
- 🌐 **Multi-language test execution** — `pytest`, `npm test`, `cargo test`, `go test`, `mvn test`, `make test`, and more
- 🔄 **Review-and-retry loop** — Reviewer sends failed patches back to Coder (up to 3 retries, history trimmed automatically)
- 📄 **Standard `.diff` output** — Apply with `git apply`, no manual editing required
- 🌊 **Real-time token streaming** — LLM output streams character-by-character in the terminal window

**New in this release:**

- ♻️ **Checkpoint resume** — Interrupted tasks resume from the last saved state; no need to restart from scratch (requires `DATABASE_URL`)
- 🔀 **Create PR** — One-click GitHub Pull Request creation directly from the result page
- 🌐 **i18n interface** — Web Dashboard supports Chinese / English toggle
- 📋 **History sidebar** — All tasks are persisted and accessible from a collapsible sidebar

---

## Architecture

```text
START
  │
  ▼
📋 Planner          Analyzes Issue + repo language, produces structured execution plan
  │
  ▼
💻 Coder ◄──────────────────────────────────────────┐
  │                                                  │  REJECT
  ├── tool_calls ──► 🔧 Tools (read/write/search)   │  (max 3 retries, history trimmed)
  │                          │                       │
  │                          └──► Coder (loop)       │
  │                                                  │
  └── done ──► 🧪 TestRunner (multi-language tests)  │
                        │                            │
                        ▼                            │
                  🔍 Reviewer ────────────────────────┘
                        │
                        └── PASS ──► 📄 .diff file ──► END
```

> Checkpoints are persisted to PostgreSQL after each node — enabling resume after interruption.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend, only if running manually)
- Git

### 1. Clone & Install

```bash
git clone https://github.com/daixinwang/AutoPatch.git
cd AutoPatch

# Backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend (only needed for Option D)
cd frontend && npm install
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```ini
OPENAI_API_KEY=sk-your-openai-key-here
GITHUB_TOKEN=ghp_your-github-token-here   # Optional, prevents rate limiting

# Optional overrides
OPENAI_MODEL_NAME=gpt-4o
OPENAI_BASE_URL=https://your-proxy/v1     # If using a proxy

# Checkpoint resume (optional — enables task resume after interruption)
DATABASE_URL=postgresql://user:password@host:5432/autopatch

# Server options
CORS_ORIGINS=http://localhost:5173        # Comma-separated allowed origins
MAX_CONCURRENT_PATCHES=3                  # Max simultaneous pipeline runs (default: 3)
AUTOPATCH_API_KEY=your-secret-key         # Optional: enable Bearer token auth
LOG_LEVEL=INFO                            # DEBUG / INFO / WARNING / ERROR

# Agent tuning (optional)
MAX_REVIEW_RETRIES=3                      # Max reviewer reject-and-retry cycles (default: 3)
MAX_CODER_STEPS=25                        # Max tool calls per coder attempt (default: 25)
```

### 3. Run

**Option A — Docker (recommended):**

```bash
# Starts backend + frontend + PostgreSQL (checkpoint resume enabled automatically)
docker-compose up --build

# Open: http://localhost:8000
```

> The Docker image bundles the compiled frontend — no separate frontend process needed.

**Option B — CLI (full pipeline):**

```bash
source .venv/bin/activate
python autopatch.py https://github.com/owner/repo 42
```

**Option C — Debug mode (hardcoded test issue):**

```bash
python main.py
```

**Option D — Web Dashboard (manual):**

```bash
# Terminal 1: start backend
source .venv/bin/activate
uvicorn server:app --reload --port 8000

# Terminal 2: start frontend
npm --prefix frontend run dev

# Open: http://localhost:5173
```

### 4. Apply the Generated Patch

```bash
# In your target repository
git apply patches/issue-42_20260402_120000.diff
```

---

## CLI Options

```text
python autopatch.py <repo_url> <issue_number> [options]

Options:
  --output-dir DIR       Output directory for .diff files (default: ./patches)
  --branch BRANCH        Clone a specific branch (default: repo default)
  --workspace-dir DIR    Use existing local repo (skip clone)
  --keep-workspace       Keep the cloned temp directory after run
  --no-comments          Skip fetching issue comments
```

---

## Tech Stack

| Layer | Technology |
| ----- | ---------- |
| Agent Framework | [LangGraph](https://github.com/langchain-ai/langgraph) 0.2.x |
| LLM | OpenAI GPT-4o (via `langchain-openai`, token streaming enabled) |
| Code Search | Python AST + `re` (no external deps) |
| Test Execution | `subprocess` sandboxed runner — Python, Node.js, Rust, Go, Java, Make |
| GitHub Integration | GitHub REST API v3 (`requests`) |
| Backend API | FastAPI + Uvicorn (SSE streaming) |
| Checkpoint Storage | PostgreSQL 16 (via `langgraph-checkpoint-postgres`) |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS (dark / light / system theme) |
| Icons | lucide-react |
| Internationalization | React Context + JSON translation files (zh/en) |

---

## Security

- **Tool permissions** are layered: Coder (read+write+search), TestRunner (execute-only), Reviewer (read-only)
- **Path traversal protection** — all file operations are sandboxed within the workspace directory; absolute paths and `../` traversal are rejected
- **Command execution** is sandboxed: whitelist-only (`pytest`, `python`, `npm test`, `cargo test`, `go test`, `mvn test`, `gradle test`, `make test`), timeout limits (max 120s), output truncation (max 8KB)
- **API authentication** — optional Bearer token auth via `AUTOPATCH_API_KEY` env var; protects all mutation endpoints
- **Task ID validation** — UUID format enforced, preventing path injection in task storage
- **Concurrency** is capped via semaphore (`MAX_CONCURRENT_PATCHES`) to prevent resource exhaustion
- **API keys** are loaded via `.env` — never committed (`.gitignore` enforced)

---

Made with ❤️ using LangGraph + React
