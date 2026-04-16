<div align="center">

<img src="https://img.shields.io/badge/AutoPatch-AI%20Agent-6366f1?style=for-the-badge&logo=github&logoColor=white" alt="AutoPatch" />

# 🤖 AutoPatch

**AI-powered GitHub Issue Auto-Fix Agent**

*Automatically analyze, fix, and generate patches for GitHub Issues using a multi-agent pipeline.*

---

[English](#english) · [中文](#chinese)

---

</div>

---

<a name="english"></a>

## 🇺🇸 English

### What is AutoPatch?

AutoPatch is an intelligent code repair system built on [LangGraph](https://github.com/langchain-ai/langgraph). It accepts a GitHub repository URL and an Issue number, automatically pulls the Issue content and clones the codebase, then runs a **four-stage multi-agent pipeline** to analyze the bug, write a fix, run tests, and generate a standard `.diff` patch file — ready to `git apply`.

### ✨ Features

- 🔍 **Autonomous codebase navigation** — `list_directory`, `search_codebase`, `find_definition`, `grep_in_file`
- ✍️ **Automated code repair** — Coder agent reads, writes, and verifies files
- 🌐 **Multi-language test execution** — Runs `pytest`, `npm test`, `cargo test`, `go test`, `mvn test`, `make test`, and more
- 🔄 **Review-and-retry loop** — Reviewer sends failed patches back to Coder (up to 3 retries)
- 📄 **Standard `.diff` output** — Apply with `git apply`, no manual editing required
- 🌊 **Real-time token streaming** — LLM output streams character-by-character in the terminal window
- 🖥️ **Modern Web Dashboard** — Real-time agent workflow visualizer + live streaming terminal
- 🔐 **API Authentication** — Optional Bearer token authentication for all mutation endpoints
- 🐳 **Docker Support** — One-command deployment with `docker-compose up`
- ✅ **Test Suite** — 31 unit/integration tests covering core modules

### 🏗️ Architecture

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

### 🗂️ Project Structure

```
AutoPatch/
├── autopatch.py          # CLI entry point — full end-to-end pipeline
├── main.py               # Debug entry — run with hardcoded test issue
├── server.py             # FastAPI backend — SSE streaming + checkpoint resume
├── config.py             # Centralized configuration (env-var overridable)
├── logging_config.py     # Structured logging setup
├── github_client.py      # GitHub REST API client + repo clone manager
├── diff_generator.py     # git diff generator → writes .diff files
├── task_store.py         # Task metadata persistence (JSON-based)
│
├── agent/
│   └── graph.py          # LangGraph StateGraph — all nodes & routing
│
├── tools/
│   ├── workspace.py      # Thread-safe workspace dir (ContextVar, path-traversal protected)
│   ├── file_tools.py     # read_file / write_and_replace_file / edit_file
│   ├── search_tools.py   # list_directory / search_codebase / find_definition / grep_in_file
│   └── execute_tools.py  # run_pytest / run_python_script / run_test_command (sandboxed)
│
├── tests/                # pytest test suite (31 tests)
│   ├── conftest.py       # Shared fixtures (tmp_workspace, sample_repo)
│   ├── test_workspace.py # Path traversal prevention tests
│   ├── test_file_tools.py
│   ├── test_github_client.py
│   ├── test_task_store.py
│   └── test_server.py    # API endpoint + auth tests
│
├── eval/                 # SWE-bench evaluation framework
├── frontend/             # React 18 + TypeScript + Vite dashboard
│
├── Dockerfile            # Multi-stage build (Node frontend + Python backend)
├── docker-compose.yml    # app + PostgreSQL one-command deployment
├── pyproject.toml        # Project metadata, dev deps, tool config
└── requirements.txt      # Production dependencies
```

### 🚀 Quick Start

#### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- Git

#### 1. Clone & Install

```bash
git clone https://github.com/daixinwang/AutoPatch.git
cd AutoPatch

# Backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install
```

#### 2. Configure Environment

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

# Server options
CORS_ORIGINS=http://localhost:5173        # Comma-separated allowed origins (default: localhost dev ports)
MAX_CONCURRENT_PATCHES=3                  # Max simultaneous pipeline runs (default: 3)
AUTOPATCH_API_KEY=your-secret-key         # Optional: enable Bearer token auth for API endpoints
LOG_LEVEL=INFO                            # Logging level: DEBUG / INFO / WARNING / ERROR

# Agent tuning (optional)
MAX_REVIEW_RETRIES=3                      # Max reviewer reject-and-retry cycles (default: 3)
MAX_CODER_STEPS=25                        # Max tool calls per coder attempt (default: 25)
```

#### 3. Run

**Option A — Docker (recommended):**

```bash
# Starts backend + PostgreSQL (checkpoint resume enabled)
docker-compose up --build

# Browser: http://localhost:8000
```

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

# Browser: http://localhost:5173
```

#### 4. Apply the Generated Patch

```bash
# In your target repository
git apply patches/issue-42_20260402_120000.diff
```

### ⚙️ CLI Options

```
python autopatch.py <repo_url> <issue_number> [options]

Options:
  --output-dir DIR       Output directory for .diff files (default: ./patches)
  --branch BRANCH        Clone a specific branch (default: repo default)
  --workspace-dir DIR    Use existing local repo (skip clone)
  --keep-workspace       Keep the cloned temp directory after run
  --no-comments          Skip fetching issue comments
```

### 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | [LangGraph](https://github.com/langchain-ai/langgraph) 0.2.x |
| LLM | OpenAI GPT-4o (via `langchain-openai`, token streaming enabled) |
| Code Search | Python AST + `re` (no external deps) |
| Test Execution | `subprocess` sandboxed runner — Python, Node.js, Rust, Go, Java, Make |
| GitHub Integration | GitHub REST API v3 (`requests`) |
| Backend API | FastAPI + Uvicorn (SSE streaming) |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS (dark / light / system theme) |
| Icons | lucide-react |

### 🔒 Security

- **Tool permissions** are layered: Coder (read+write+search), TestRunner (execute-only), Reviewer (read-only)
- **Path traversal protection** — all file operations are sandboxed within the workspace directory; absolute paths and `../` traversal are rejected
- **Command execution** is sandboxed: whitelist-only (`pytest`, `python`, `npm test`, `cargo test`, `go test`, `mvn test`, `gradle test`, `make test`), timeout limits (max 120s), output truncation (max 8KB)
- **API authentication** — optional Bearer token auth via `AUTOPATCH_API_KEY` env var; protects all mutation endpoints
- **Task ID validation** — UUID format enforced, preventing path injection in task storage
- **Concurrency** is capped via semaphore (`MAX_CONCURRENT_PATCHES`) to prevent resource exhaustion
- **API keys** are loaded via `.env` — never committed (`.gitignore` enforced)

---

<a name="chinese"></a>

## 🇨🇳 中文

### 项目简介

AutoPatch 是一个基于 [LangGraph](https://github.com/langchain-ai/langgraph) 构建的智能代码修复系统。输入一个 GitHub 仓库地址和 Issue 编号，它会自动拉取 Issue 内容、克隆代码库，然后运行**四阶段多智能体流水线**分析 Bug、编写修复、运行测试，最终生成标准 `.diff` 补丁文件 — 可直接 `git apply`。

### ✨ 核心功能

- 🔍 **自主代码库检索** — `list_directory`、`search_codebase`、`find_definition`、`grep_in_file`
- ✍️ **自动代码修复** — Coder 智能体读取、写入、验证文件
- 🌐 **多语言测试执行** — 支持 `pytest`、`npm test`、`cargo test`、`go test`、`mvn test`、`make test` 等
- 🔄 **评审-重试循环** — Reviewer 将不通过的补丁打回给 Coder（最多3次，自动压缩历史上下文）
- 📄 **标准 `.diff` 输出** — 通过 `git apply` 应用，无需手动修改
- 🌊 **Token 级实时流式输出** — LLM 输出逐字符流入终端窗口
- 🖥️ **现代化 Web 看板** — 实时 Agent 工作流可视化 + 流式终端日志
- 🔐 **API 认证** — 可选的 Bearer token 认证，保护所有写入端点
- 🐳 **Docker 支持** — `docker-compose up` 一键部署
- ✅ **测试套件** — 31 个单元/集成测试，覆盖核心模块

### 🏗️ 系统架构

```
START
  │
  ▼
📋 Planner          分析 Issue + 仓库语言，产出结构化执行计划
  │
  ▼
💻 Coder ◄──────────────────────────────────────────┐
  │                                                  │  REJECT
  ├── tool_calls ──► 🔧 Tools（读/写/搜索）          │  (最多3次打回，自动压缩消息历史)
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

### 🗂️ 目录结构

```
AutoPatch/
├── autopatch.py          # CLI 入口 — 完整端到端流水线
├── main.py               # 调试入口 — 使用内置测试 Issue 运行
├── server.py             # FastAPI 后端 — SSE 流式推送 + 断点续传
├── config.py             # 集中配置管理（支持环境变量覆盖）
├── logging_config.py     # 结构化日志配置
├── github_client.py      # GitHub REST API 封装 + 仓库克隆管理
├── diff_generator.py     # git diff 生成器，写入 .diff 文件
├── task_store.py         # 任务元数据持久化（JSON）
│
├── agent/
│   └── graph.py          # LangGraph StateGraph — 节点定义与路由
│
├── tools/
│   ├── workspace.py      # 线程安全工作目录（ContextVar，路径遍历防护）
│   ├── file_tools.py     # read_file / write_and_replace_file / edit_file
│   ├── search_tools.py   # list_directory / search_codebase / find_definition / grep_in_file
│   └── execute_tools.py  # run_pytest / run_python_script / run_test_command（沙箱执行）
│
├── tests/                # pytest 测试套件（31 个测试）
│   ├── conftest.py       # 共享 Fixtures
│   ├── test_workspace.py # 路径遍历防护测试
│   ├── test_file_tools.py
│   ├── test_github_client.py
│   ├── test_task_store.py
│   └── test_server.py    # API 端点 + 认证测试
│
├── eval/                 # SWE-bench 评测框架
├── frontend/             # React 18 + TypeScript + Vite 前端看板
│
├── Dockerfile            # 多阶段构建（Node 前端 + Python 后端）
├── docker-compose.yml    # app + PostgreSQL 一键部署
├── pyproject.toml        # 项目配置、开发依赖、工具配置
└── requirements.txt      # 生产依赖
```

### 🚀 快速开始

#### 环境要求

- Python 3.10+
- Node.js 18+（运行前端）
- Git

#### 1. 克隆并安装依赖

```bash
git clone https://github.com/daixinwang/AutoPatch.git
cd AutoPatch

# 后端
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 前端
cd frontend && npm install
```

#### 2. 配置环境变量

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

# 服务器配置
CORS_ORIGINS=http://localhost:5173        # 允许的跨域来源，逗号分隔（默认：本地开发端口）
MAX_CONCURRENT_PATCHES=3                  # 最大并发流水线数量（默认：3）
AUTOPATCH_API_KEY=your-secret-key         # 可选：启用 API 端点 Bearer token 认证
LOG_LEVEL=INFO                            # 日志级别：DEBUG / INFO / WARNING / ERROR

# Agent 调参（可选）
MAX_REVIEW_RETRIES=3                      # Reviewer 最大打回次数（默认：3）
MAX_CODER_STEPS=25                        # Coder 单次最大工具调用数（默认：25）
```

#### 3. 运行

**方式 A — Docker（推荐）：**

```bash
# 启动后端 + PostgreSQL（自动启用断点续传）
docker-compose up --build

# 浏览器访问 http://localhost:8000
```

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

#### 4. 应用生成的补丁

```bash
# 在目标仓库根目录执行
git apply patches/issue-42_20260402_120000.diff
```

### ⚙️ CLI 参数说明

```
python autopatch.py <repo_url> <issue_number> [选项]

选项：
  --output-dir DIR       .diff 文件输出目录（默认：./patches）
  --branch BRANCH        克隆指定分支（默认：仓库默认分支）
  --workspace-dir DIR    使用已有本地仓库（跳过 clone）
  --keep-workspace       运行结束后保留临时 clone 目录
  --no-comments          拉取 Issue 时跳过评论
```

### 🛠️ 技术栈

| 层次 | 技术 |
|------|------|
| Agent 框架 | [LangGraph](https://github.com/langchain-ai/langgraph) 0.2.x |
| 大语言模型 | OpenAI GPT-4o（via `langchain-openai`，已启用 token 流式输出）|
| 代码检索 | Python AST + `re`（无额外依赖）|
| 测试执行 | `subprocess` 沙箱运行器 — Python、Node.js、Rust、Go、Java、Make |
| GitHub 集成 | GitHub REST API v3（`requests`）|
| 后端 API | FastAPI + Uvicorn（SSE 流式推送）|
| 前端框架 | React 18 + TypeScript + Vite |
| 样式方案 | Tailwind CSS（深色 / 浅色 / 跟随系统）|
| 图标库 | lucide-react |

### 🔒 安全设计

- **工具权限分层**：Coder（读+写+搜索）、TestRunner（仅执行）、Reviewer（仅读）
- **路径遍历防护** — 所有文件操作限定在工作目录内，拒绝绝对路径和 `../` 遍历
- **命令执行沙箱**：白名单制（`pytest`、`python`、`npm test`、`cargo test`、`go test`、`mvn test`、`gradle test`、`make test`），超时限制（最大120秒），输出截断（最大8KB）
- **API 认证** — 通过 `AUTOPATCH_API_KEY` 环境变量启用 Bearer token 认证，保护写入端点
- **Task ID 校验** — 强制 UUID 格式，防止路径注入
- **并发保护**：信号量限制同时进行的流水线数量（`MAX_CONCURRENT_PATCHES`），防止资源耗尽
- **API Key 保护**：通过 `.env` 加载，`.gitignore` 强制排除，绝不提交

---

<div align="center">

Made with ❤️ using LangGraph + React

[⬆ Back to top](#)

</div>
