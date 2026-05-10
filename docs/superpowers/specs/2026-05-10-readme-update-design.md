# README Update Design

**Date:** 2026-05-10
**Topic:** Split and restructure README into English + Chinese files

---

## Goal

Split the current single-file bilingual `README.md` into two separate files (`README.md` for English, `README.zh.md` for Chinese), restructure the content order to follow a "show results first, explain later" flow, add new feature documentation, and insert screenshot placeholders for the Web Dashboard.

---

## Files Affected

| File | Action |
|------|--------|
| `README.md` | Full rewrite — English only, restructured |
| `README.zh.md` | New file — Chinese only, same structure |
| `docs/images/.gitkeep` | New file — placeholder for screenshot directory |

---

## Document Structure (Both Files)

```
1. Header
2. Demo
3. Features
4. Web Dashboard (screenshots)
5. Architecture
6. Quick Start
7. CLI Options
8. Tech Stack
9. Security
```

---

## Section Details

### 1. Header

- Badges: build status style badge, Python version, license
- Title: `AutoPatch`
- One-line description
- Language toggle link: `README.md` ↔ `README.zh.md`

### 2. Demo

Concrete end-to-end example using `daixinwang/bug-test` issue #1:

**Web UI flow:**
1. Enter repo URL + issue number → click "Run AutoPatch"
2. Watch live agent pipeline: Planner → Coder → TestRunner → Reviewer
3. Download `.diff` or click "Create PR"

**CLI flow:**
```bash
python autopatch.py https://github.com/daixinwang/bug-test 1
# → patches/issue-1_20260510_120000.diff
git apply patches/issue-1_20260510_120000.diff
```

Screenshot placeholders:
- `![Running](docs/images/dashboard-running.png)`
- `![Result](docs/images/dashboard-result.png)`

### 3. Features

**Core capabilities** (existing):
- Autonomous codebase navigation
- Automated code repair
- Multi-language test execution
- Review-and-retry loop (up to 3 retries)
- Standard `.diff` output

**New features** (to be added):
- 🔄 **Checkpoint Resume** — interrupted tasks resume from last PostgreSQL checkpoint (requires `DATABASE_URL`)
- 🔀 **Create PR** — one-click GitHub Pull Request creation from the result page
- 🌐 **i18n Interface** — Web Dashboard supports Chinese/English toggle
- 📋 **History Sidebar** — all tasks persisted, accessible from collapsible sidebar

### 4. Web Dashboard

Three screenshot placeholders:
```markdown
<!-- screenshot: idle input state -->
![Dashboard idle state](docs/images/dashboard-idle.png)

<!-- screenshot: agent pipeline running -->
![Dashboard running](docs/images/dashboard-running.png)

<!-- screenshot: completed result with diff preview and Create PR button -->
![Dashboard result](docs/images/dashboard-result.png)
```

Directory: `docs/images/` (created with `.gitkeep`)

### 5. Architecture

Keep existing ASCII diagram unchanged. Add one line after diagram:

> Checkpoints are persisted to PostgreSQL after each node — enabling resume after interruption.

### 6. Quick Start

Keep existing four startup options (Docker, CLI, Debug, Manual). Add:

- Under Docker option: note that frontend is embedded, no separate start needed
- Under environment config: document `DATABASE_URL` for checkpoint resume
- Under Docker option: note checkpoint resume is automatically enabled when `DATABASE_URL` is set

### 7. CLI Options

No changes from current content.

### 8. Tech Stack

Add two new rows:

| Layer | Technology |
|-------|-----------|
| Checkpoint Storage | PostgreSQL 16 (via `langgraph-checkpoint-postgres`) |
| Internationalization | React Context + JSON translation files (zh/en) |

### 9. Security

No changes from current content.

---

## Screenshot Placeholder Convention

Use this pattern throughout both files:

```markdown
<!-- screenshot: brief description of what should be captured -->
![Alt text](docs/images/filename.png)
```

Filenames:
- `dashboard-idle.png` — main input screen (idle state)
- `dashboard-running.png` — agent workflow visualization mid-run
- `dashboard-result.png` — completed task: diff preview + Create PR button

---

## Cross-linking

Top of `README.md`:
```markdown
[中文版](README.zh.md)
```

Top of `README.zh.md`:
```markdown
[English](README.md)
```

---

## Out of Scope

- Roadmap / future plans section
- Removing any existing content (Security, CLI Options, Tech Stack stay intact)
- Actual screenshot capture (user handles this manually)
