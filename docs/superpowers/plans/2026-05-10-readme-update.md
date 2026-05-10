# README Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the current bilingual README.md into separate English (README.md) and Chinese (README.zh.md) files, restructure both with a "show results first" layout, document new features, and insert screenshot placeholders.

**Architecture:** Three-file change — rewrite README.md (English only), create README.zh.md (Chinese only, same structure), create docs/images/.gitkeep as screenshot directory scaffold. No code changes. No tests needed — verification is visual inspection of rendered Markdown.

**Tech Stack:** Markdown, GitHub Flavored Markdown image/link syntax.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `docs/images/.gitkeep` | Scaffold screenshot directory |
| Rewrite | `README.md` | English README, restructured |
| Create | `README.zh.md` | Chinese README, same structure |

---

### Task 1: Create screenshot directory scaffold

**Files:**
- Create: `docs/images/.gitkeep`

- [ ] **Step 1: Create the file**

```bash
touch /Users/davian/Desktop/Code/AutoPatch/docs/images/.gitkeep
```

- [ ] **Step 2: Verify**

```bash
ls docs/images/
```
Expected: `.gitkeep`

- [ ] **Step 3: Commit**

```bash
git add docs/images/.gitkeep
git commit -m "chore: add docs/images directory for README screenshots"
```

---

### Task 2: Rewrite README.md (English)

**Files:**
- Rewrite: `README.md`

- [ ] **Step 1: Replace the entire file with the following content**

Write `README.md` with this exact content:

````markdown
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
2. Watch the live agent pipeline: Planner → Coder → TestRunner → Reviewer
3. Download the generated `.diff` or click **Create PR** to open a pull request directly

<!-- screenshot: agent pipeline running mid-task -->
![Dashboard running](docs/images/dashboard-running.png)

<!-- screenshot: completed result with diff preview and Create PR button -->
![Dashboard result](docs/images/dashboard-result.png)

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

## Web Dashboard

<!-- screenshot: idle input state -->
![Dashboard idle state](docs/images/dashboard-idle.png)

The dashboard provides a full-featured interface for submitting issues, monitoring the live agent workflow, and reviewing results — including a diff viewer and direct PR creation.

---

## Architecture

```
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

After each node completes, the full agent state is checkpointed to PostgreSQL — enabling resume after any interruption without re-running earlier stages.

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

```
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
|-------|-----------|
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

<div align="center">

Made with ❤️ using LangGraph + React

[⬆ Back to top](#)

</div>
````

- [ ] **Step 2: Verify the file renders correctly**

Open `README.md` in a Markdown previewer or run:
```bash
wc -l README.md
```
Expected: > 150 lines. Confirm the section order is: Demo → Features → Web Dashboard → Architecture → Quick Start → CLI Options → Tech Stack → Security.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README.md in English with restructured layout"
```

---

### Task 3: Create README.zh.md (Chinese)

**Files:**
- Create: `README.zh.md`

- [ ] **Step 1: Create the file with the following content**

Write `README.zh.md` with this exact content:

````markdown
<div align="center">

<img src="https://img.shields.io/badge/AutoPatch-AI%20Agent-6366f1?style=for-the-badge&logo=github&logoColor=white" alt="AutoPatch" />

# AutoPatch

**AI 驱动的 GitHub Issue 自动修复 Agent**

*输入 Issue 编号，自动分析、修复、生成补丁 — 基于多智能体流水线。*

[English](README.md)

</div>

---

## 演示

将 AutoPatch 指向任意 GitHub Issue，几分钟内获得可直接应用的补丁。

**Web 界面：**

1. 输入仓库地址和 Issue 编号，点击 **Run AutoPatch**
2. 实时观看 Agent 流水线运行：Planner → Coder → TestRunner → Reviewer
3. 下载生成的 `.diff` 文件，或点击 **Create PR** 直接创建 Pull Request

<!-- screenshot: agent pipeline running mid-task -->
![看板运行中](docs/images/dashboard-running.png)

<!-- screenshot: completed result with diff preview and Create PR button -->
![任务完成结果](docs/images/dashboard-result.png)

**命令行：**

```bash
python autopatch.py https://github.com/daixinwang/bug-test 1
# → patches/issue-1_20260510_120000.diff

# 在目标仓库中应用补丁
git apply patches/issue-1_20260510_120000.diff
```

---

## 功能特性

**核心能力：**

- 🔍 **自主代码库检索** — `list_directory`、`search_codebase`、`find_definition`、`grep_in_file`
- ✍️ **自动代码修复** — Coder 智能体读取、写入、验证文件
- 🌐 **多语言测试执行** — 支持 `pytest`、`npm test`、`cargo test`、`go test`、`mvn test`、`make test` 等
- 🔄 **评审-重试循环** — Reviewer 将不通过的补丁打回给 Coder（最多 3 次，自动压缩历史上下文）
- 📄 **标准 `.diff` 输出** — 通过 `git apply` 应用，无需手动修改
- 🌊 **Token 级实时流式输出** — LLM 输出逐字符流入终端窗口

**新增功能：**

- ♻️ **断点续传** — 任务中断后可从上次保存的 checkpoint 恢复，无需重新运行（需配置 `DATABASE_URL`）
- 🔀 **一键创建 PR** — 在结果页直接调用 GitHub API 提交 Pull Request
- 🌐 **中英文界面** — Web 看板支持中/英文切换
- 📋 **历史记录侧边栏** — 所有任务持久化存储，随时从可折叠侧边栏回溯历史结果

---

## Web 看板

<!-- screenshot: idle input state -->
![看板空闲状态](docs/images/dashboard-idle.png)

看板提供完整的 Web 操作界面：提交 Issue、实时监控 Agent 工作流、查看修复结果 — 包含 diff 查看器和直接创建 PR 功能。

---

## 系统架构

```
START
  │
  ▼
📋 Planner          分析 Issue + 仓库语言，产出结构化执行计划
  │
  ▼
💻 Coder ◄──────────────────────────────────────────┐
  │                                                  │  REJECT
  ├── tool_calls ──► 🔧 Tools（读/写/搜索）          │  （最多 3 次打回，自动压缩消息历史）
  │                          │                       │
  │                          └──► Coder（循环）       │
  │                                                  │
  └── 完成 ──► 🧪 TestRunner（多语言测试）            │
                        │                            │
                        ▼                            │
                  🔍 Reviewer ────────────────────────┘
                        │
                        └── PASS ──► 📄 .diff 文件 ──► END
```

每个节点完成后，Agent 完整状态自动 checkpoint 保存到 PostgreSQL — 任何中断后均可无缝恢复，无需重跑已完成阶段。

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（仅手动启动前端时需要）
- Git

### 1. 克隆并安装依赖

```bash
git clone https://github.com/daixinwang/AutoPatch.git
cd AutoPatch

# 后端
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 前端（仅方式 D 需要）
cd frontend && npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
OPENAI_API_KEY=sk-your-openai-key-here
GITHUB_TOKEN=ghp_your-github-token-here   # 可选，防止 API 限速

# 可选配置
OPENAI_MODEL_NAME=gpt-4o
OPENAI_BASE_URL=https://your-proxy/v1     # 使用代理时填写

# 断点续传（可选 — 启用后任务中断可恢复）
DATABASE_URL=postgresql://user:password@host:5432/autopatch

# 服务器配置
CORS_ORIGINS=http://localhost:5173        # 允许的跨域来源，逗号分隔
MAX_CONCURRENT_PATCHES=3                  # 最大并发流水线数量（默认：3）
AUTOPATCH_API_KEY=your-secret-key         # 可选：启用 Bearer token 认证
LOG_LEVEL=INFO                            # 日志级别：DEBUG / INFO / WARNING / ERROR

# Agent 调参（可选）
MAX_REVIEW_RETRIES=3                      # Reviewer 最大打回次数（默认：3）
MAX_CODER_STEPS=25                        # Coder 单次最大工具调用数（默认：25）
```

### 3. 运行

**方式 A — Docker（推荐）：**

```bash
# 启动后端 + 前端 + PostgreSQL（自动启用断点续传）
docker-compose up --build

# 浏览器访问 http://localhost:8000
```

> Docker 镜像已内嵌编译好的前端，无需单独启动前端进程。

**方式 B — CLI（完整流水线）：**

```bash
source .venv/bin/activate
python autopatch.py https://github.com/owner/repo 42
```

**方式 C — 调试模式（内置测试 Issue）：**

```bash
python main.py
```

**方式 D — Web 看板（手动启动）：**

```bash
# 终端 1：启动后端
source .venv/bin/activate
uvicorn server:app --reload --port 8000

# 终端 2：启动前端
npm --prefix frontend run dev

# 浏览器访问 http://localhost:5173
```

### 4. 应用生成的补丁

```bash
# 在目标仓库根目录执行
git apply patches/issue-42_20260402_120000.diff
```

---

## CLI 参数说明

```
python autopatch.py <repo_url> <issue_number> [选项]

选项：
  --output-dir DIR       .diff 文件输出目录（默认：./patches）
  --branch BRANCH        克隆指定分支（默认：仓库默认分支）
  --workspace-dir DIR    使用已有本地仓库（跳过 clone）
  --keep-workspace       运行结束后保留临时 clone 目录
  --no-comments          拉取 Issue 时跳过评论
```

---

## 技术栈

| 层次 | 技术 |
|------|------|
| Agent 框架 | [LangGraph](https://github.com/langchain-ai/langgraph) 0.2.x |
| 大语言模型 | OpenAI GPT-4o（via `langchain-openai`，已启用 token 流式输出）|
| 代码检索 | Python AST + `re`（无额外依赖）|
| 测试执行 | `subprocess` 沙箱运行器 — Python、Node.js、Rust、Go、Java、Make |
| GitHub 集成 | GitHub REST API v3（`requests`）|
| 后端 API | FastAPI + Uvicorn（SSE 流式推送）|
| Checkpoint 存储 | PostgreSQL 16（via `langgraph-checkpoint-postgres`）|
| 前端框架 | React 18 + TypeScript + Vite |
| 样式方案 | Tailwind CSS（深色 / 浅色 / 跟随系统）|
| 图标库 | lucide-react |
| 国际化 | React Context + JSON 翻译文件（zh/en）|

---

## 安全设计

- **工具权限分层**：Coder（读+写+搜索）、TestRunner（仅执行）、Reviewer（仅读）
- **路径遍历防护** — 所有文件操作限定在工作目录内，拒绝绝对路径和 `../` 遍历
- **命令执行沙箱**：白名单制（`pytest`、`python`、`npm test`、`cargo test`、`go test`、`mvn test`、`gradle test`、`make test`），超时限制（最大 120 秒），输出截断（最大 8KB）
- **API 认证** — 通过 `AUTOPATCH_API_KEY` 环境变量启用 Bearer token 认证，保护所有写入端点
- **Task ID 校验** — 强制 UUID 格式，防止路径注入
- **并发保护**：信号量限制同时进行的流水线数量（`MAX_CONCURRENT_PATCHES`），防止资源耗尽
- **API Key 保护**：通过 `.env` 加载，`.gitignore` 强制排除，绝不提交

---

<div align="center">

Made with ❤️ using LangGraph + React

[⬆ 回到顶部](#)

</div>
````

- [ ] **Step 2: Verify the file exists and has content**

```bash
wc -l README.zh.md
```
Expected: > 150 lines.

- [ ] **Step 3: Verify cross-links are correct**

Check that `README.md` contains `[中文版](README.zh.md)` and `README.zh.md` contains `[English](README.md)`:

```bash
grep -n "README.zh.md" README.md
grep -n "README.md" README.zh.md
```

Expected: one match in each file.

- [ ] **Step 4: Commit**

```bash
git add README.zh.md
git commit -m "docs: add Chinese README (README.zh.md) with restructured layout"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|-----------------|-----------|
| Split into README.md + README.zh.md | Task 2 + Task 3 |
| Restructured order (Demo first) | Task 2 + Task 3 — Demo is section 1 after header |
| New features: checkpoint resume | Task 2 + Task 3 — "New in this release" section |
| New features: Create PR | Task 2 + Task 3 — listed in new features |
| New features: i18n | Task 2 + Task 3 — listed in new features |
| New features: history sidebar | Task 2 + Task 3 — listed in new features |
| Screenshot placeholders (3 images) | Task 2 + Task 3 — dashboard-idle, dashboard-running, dashboard-result |
| docs/images/ directory | Task 1 |
| Cross-links between files | Task 3 Step 3 verifies |
| DATABASE_URL in Quick Start | Task 2 + Task 3 — added to .env config section |
| Docker note: frontend embedded | Task 2 + Task 3 — note under Option A |
| Architecture: PostgreSQL checkpoint note | Task 2 + Task 3 — paragraph after ASCII diagram |
| Tech Stack: PostgreSQL + i18n rows | Task 2 + Task 3 — two new rows added |

**Placeholder scan:** No TBD, TODO, or "similar to Task N" patterns present. All steps include exact file content or exact commands.

**Type consistency:** N/A — documentation only, no code types involved.
