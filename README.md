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
- 🧪 **Real test execution** — Runs `pytest` or scripts to validate the fix
- 🔄 **Review-and-retry loop** — Reviewer sends failed patches back to Coder (up to 3 retries)
- 📄 **Standard `.diff` output** — Apply with `git apply`, no manual editing required
- 🖥️ **Modern Web Dashboard** — Real-time agent workflow visualizer + terminal log window

### 🏗️ Architecture

```
START
  │
  ▼
📋 Planner          Analyzes Issue, produces structured execution plan
  │
  ▼
💻 Coder ◄──────────────────────────────────────────┐
  │                                                  │  REJECT
  ├── tool_calls ──► 🔧 Tools (read/write/search)   │  (max 3 retries)
  │                          │                       │
  │                          └──► Coder (loop)       │
  │                                                  │
  └── done ──► 🧪 TestRunner (pytest / script)       │
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
├── github_client.py      # GitHub REST API client + repo clone manager
├── diff_generator.py     # git diff generator → writes .diff files
│
├── agent/
│   └── graph.py          # LangGraph StateGraph — all nodes & routing
│
├── tools/
│   ├── file_tools.py     # read_file / write_and_replace_file
│   ├── search_tools.py   # list_directory / search_codebase / find_definition / grep_in_file
│   └── execute_tools.py  # run_pytest / run_python_script (sandboxed)
│
└── frontend/             # React 18 + TypeScript + Vite dashboard
    └── src/
        ├── components/   # Header / InputSection / WorkflowVisualizer / TerminalWindow / ResultArea
        └── hooks/        # usePatchTask — state machine + mock pipeline
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
```

#### 3. Run

**Option A — CLI (full pipeline):**

```bash
source .venv/bin/activate
python autopatch.py https://github.com/owner/repo 42
```

**Option B — Debug mode (hardcoded test issue):**

```bash
python main.py
```

**Option C — Web Dashboard:**

```bash
# Terminal 1: start frontend
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
| LLM | OpenAI GPT-4o (via `langchain-openai`) |
| Code Search | Python AST + `re` (no external deps) |
| Test Execution | `subprocess` sandboxed runner |
| GitHub Integration | GitHub REST API v3 (`requests`) |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS (dark mode) |
| Icons | lucide-react |

### 🔒 Security

- **Tool permissions** are layered: Coder (read+write+search), TestRunner (execute-only), Reviewer (read-only)
- **Command execution** is sandboxed: timeout limits (max 120s), output truncation (max 8KB), `.py`-only whitelist
- **API keys** are loaded via `.env` — never committed (`.gitignore` enforced)

---

<a name="chinese"></a>

## 🇨🇳 中文

### 项目简介

AutoPatch 是一个基于 [LangGraph](https://github.com/langchain-ai/langgraph) 构建的智能代码修复系统。输入一个 GitHub 仓库地址和 Issue 编号，它会自动拉取 Issue 内容、克隆代码库，然后运行**四阶段多智能体流水线**分析 Bug、编写修复、运行测试，最终生成标准 `.diff` 补丁文件 — 可直接 `git apply`。

### ✨ 核心功能

- 🔍 **自主代码库检索** — `list_directory`、`search_codebase`、`find_definition`、`grep_in_file`
- ✍️ **自动代码修复** — Coder 智能体读取、写入、验证文件
- 🧪 **真实测试执行** — 运行 `pytest` 或脚本验证修复结果
- 🔄 **评审-重试循环** — Reviewer 将不通过的补丁打回给 Coder（最多3次）
- 📄 **标准 `.diff` 输出** — 通过 `git apply` 应用，无需手动修改
- 🖥️ **现代化 Web 看板** — 实时 Agent 工作流可视化 + 终端日志窗口

### 🏗️ 系统架构

```
START
  │
  ▼
📋 Planner          分析 Issue，产出结构化执行计划
  │
  ▼
💻 Coder ◄──────────────────────────────────────────┐
  │                                                  │  REJECT
  ├── tool_calls ──► 🔧 Tools（读/写/搜索）          │  (最多3次打回)
  │                          │                       │
  │                          └──► Coder（循环）       │
  │                                                  │
  └── 完成 ──► 🧪 TestRunner（pytest / 脚本）        │
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
├── github_client.py      # GitHub REST API 封装 + 仓库克隆管理
├── diff_generator.py     # git diff 生成器，写入 .diff 文件
│
├── agent/
│   └── graph.py          # LangGraph StateGraph — 节点定义与路由
│
├── tools/
│   ├── file_tools.py     # read_file / write_and_replace_file
│   ├── search_tools.py   # list_directory / search_codebase / find_definition / grep_in_file
│   └── execute_tools.py  # run_pytest / run_python_script（沙箱执行）
│
└── frontend/             # React 18 + TypeScript + Vite 前端看板
    └── src/
        ├── components/   # Header / InputSection / WorkflowVisualizer / TerminalWindow / ResultArea
        └── hooks/        # usePatchTask — 状态机 + Mock 流水线
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
```

#### 3. 运行

**方式 A — CLI（完整流水线）：**

```bash
source .venv/bin/activate
python autopatch.py https://github.com/owner/repo 42
```

**方式 B — 调试模式（内置测试 Issue）：**

```bash
python main.py
```

**方式 C — Web 看板：**

```bash
# 终端启动前端
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
| 大语言模型 | OpenAI GPT-4o（via `langchain-openai`）|
| 代码检索 | Python AST + `re`（无额外依赖）|
| 测试执行 | `subprocess` 沙箱运行器 |
| GitHub 集成 | GitHub REST API v3（`requests`）|
| 前端框架 | React 18 + TypeScript + Vite |
| 样式方案 | Tailwind CSS（默认深色模式）|
| 图标库 | lucide-react |

### 🔒 安全设计

- **工具权限分层**：Coder（读+写+搜索）、TestRunner（仅执行）、Reviewer（仅读）
- **命令执行沙箱**：超时限制（最大120秒）、输出截断（最大8KB）、仅允许 `.py` 文件
- **API Key 保护**：通过 `.env` 加载，`.gitignore` 强制排除，绝不提交

---

<div align="center">

Made with ❤️ using LangGraph + React

[⬆ Back to top](#)

</div>
