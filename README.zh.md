<div align="center">

<img src="https://img.shields.io/badge/AutoPatch-AI%20Agent-6366f1?style=for-the-badge&logo=github&logoColor=white" alt="AutoPatch" />

# AutoPatch

**AI 驱动的 GitHub Issue 自动修复 Agent**

输入 Issue 编号，自动分析、修复、生成补丁 — 基于多智能体流水线。

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

<!-- screenshot: agent pipeline running mid-task -->
![看板运行中](docs/images/dashboard-running.png)

<!-- screenshot: completed result with diff preview and Create PR button -->
![任务完成结果](docs/images/dashboard-result.png)

看板提供完整的 Web 操作界面：提交 Issue、实时监控 Agent 工作流、查看修复结果 — 包含 diff 查看器和直接创建 PR 功能。

---

## 系统架构

```text
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

> 每个节点完成后，Agent 完整状态自动 checkpoint 保存到 PostgreSQL — 任何中断后均可无缝恢复，无需重跑已完成阶段。

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

```text
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
| ---- | ---- |
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

Made with ❤️ using LangGraph + React
