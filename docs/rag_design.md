# RAG Integration Design for AutoPatch

## 1. Existing Architecture Summary

AutoPatch implements a four-stage LangGraph pipeline: a **Planner** agent decomposes the GitHub issue into an ordered repair plan; a **Coder** agent executes edits via file-system tools in a loop with a `tool_node`; a **TestRunner** agent verifies the changes by running tests; and a **Reviewer** agent performs a final quality gate before the workflow terminates. Each run operates on a shallow-cloned repository whose path is stored in a per-task `ContextVar`, ensuring full isolation when multiple issues are processed concurrently.

---

## 2. Integration Points

### 2.1 Retriever Tool Registration

The retriever tool should be added to `agent/graph.py` in the `TOOLS` list defined at approximately lines 103–141. Concretely:

```python
# agent/graph.py  (around line 118, inside the TOOLS list)
from tools.rag_retriever import retrieve_context   # new import

TOOLS = [
    read_file,
    edit_file,
    write_and_replace_file,
    list_directory,
    search_codebase,
    find_definition,
    grep_in_file,
    verify_importable,
    retrieve_context,      # ← ADD HERE
]
```

`retrieve_context` is the only new entry. It accepts a natural-language query and returns ranked code snippets from the per-task Chroma index.

### 2.2 Which Agents Receive the Retriever

| Agent | Receives retriever? | Rationale |
|---|---|---|
| **Coder** | Yes | Already bound to `TOOLS` via `_llm_coder_base.bind_tools(TOOLS)`; adding the tool here is sufficient. |
| **Planner** | Via prompt only | Planner does not call tools; relevant context should be injected into its system/human prompt as a pre-formatted string before the node executes. |
| **TestRunner** | No | Uses `TEST_RUNNER_TOOLS` (execution-only); RAG context is irrelevant for running test suites. |
| **Reviewer** | Optional | Can be considered in a later iteration; not required for the initial implementation. |

### 2.3 When to Build the RAG Index

The index should be built in a new `index_builder_node` inserted between `START` and `planner_node` inside `build_graph()` (lines 737–816 of `agent/graph.py`):

```
START → index_builder_node → planner_node → coder_node ⇄ tool_node → test_runner_node → reviewer_node → END
```

`index_builder_node` should:

1. Read `state["working_dir"]` (already populated by `set_workspace()` in `autopatch.py::run_agent_on_issue()` before the graph is invoked).
2. Enumerate Python source files under that directory.
3. Build or load a Chroma collection keyed by the repository's content hash.
4. Store the resulting `retriever` object (or collection name) back into state.
5. Fail gracefully — if the directory contains no Python files, or if Chroma raises an exception, log a warning and continue; **do not raise**, so the main pipeline is not blocked.

### 2.4 Passing the Retriever via ContextVar

Follow the same pattern established in `tools/workspace.py`:

```python
# tools/rag_context.py  (new file, mirroring workspace.py)
from contextvars import ContextVar
from typing import Optional
import chromadb

_rag_retriever: ContextVar[Optional[object]] = ContextVar("_rag_retriever", default=None)

def set_retriever(retriever) -> object:
    return _rag_retriever.set(retriever)

def reset_retriever(token) -> None:
    _rag_retriever.reset(token)

def get_retriever():
    return _rag_retriever.get()
```

`index_builder_node` calls `set_retriever(retriever)` after building the index. `retrieve_context` tool calls `get_retriever()` at query time. Because `ContextVar` is async-task-scoped, concurrent issue runs each hold their own retriever without interference — exactly the same guarantee that `_workspace_dir` provides for file paths.

---

## 3. Dependency Additions

The following packages should be added to `requirements.txt`:

| Package | Version (min) | Purpose |
|---|---|---|
| `chromadb` | ≥ 0.5 | Persistent vector store; stores per-repository embeddings and exposes a retrieval API compatible with LangChain. |
| `rank-bm25` | ≥ 0.2.2 | Sparse BM25 scorer for hybrid retrieval (dense + sparse fusion). Improves recall on exact identifiers such as function names and error codes that dense embeddings sometimes miss. |

Both packages are pure-Python-friendly and add no compiled binary dependencies beyond what `chromadb` already pulls in (its default embedding uses ONNX).

---

## 4. Key Notes and Gotchas

### 4.1 API Key Separation — Anthropic vs. OpenAI Embeddings

The project switched from OpenAI to Anthropic on 2026-04-08 (commit `ffb7a05`). The environment variable `OPENAI_API_KEY` **now holds an Anthropic key** and is forwarded to `https://api.anthropic.com`. If OpenAI text-embedding models are used for RAG (e.g., `text-embedding-3-small`), a **separate** environment variable must be introduced:

```
OPENAI_EMBED_API_KEY=sk-...   # dedicated key for OpenAI Embeddings endpoint only
```

`index_builder_node` and `retrieve_context` must read `OPENAI_EMBED_API_KEY` explicitly, not `OPENAI_API_KEY`, to avoid sending an Anthropic key to the OpenAI API.

Alternatively, use a local embedding model (e.g., `all-MiniLM-L6-v2` via `sentence-transformers`) to eliminate the OpenAI embedding dependency entirely. This is the recommended path for self-hosted deployments.

### 4.2 Non-Python Repositories Must Be Skipped Silently

`index_builder_node` must detect whether the cloned repository contains Python source files before attempting to build an index. If no `.py` files are found:

- Log an `INFO` message: `"No Python source files found; skipping RAG index build."`
- Set retriever state to `None`.
- Continue to `planner_node` without error.

Raising an exception or returning an error state here would abort the entire pipeline for legitimate non-Python issues.

### 4.3 Index Build Failures Must Not Block the Pipeline

Network errors (embedding API unavailable), disk quota issues, or Chroma version mismatches must be caught inside `index_builder_node` with a broad `except Exception` guard:

```python
try:
    retriever = build_chroma_index(working_dir)
    set_retriever(retriever)
except Exception as exc:
    logger.warning("RAG index build failed (%s); continuing without retrieval.", exc)
    # retriever ContextVar remains None; retrieve_context tool returns empty list
```

`retrieve_context` should check `if get_retriever() is None: return []` so Coder receives an empty but valid response rather than an unhandled tool error.

### 4.4 Checkpoint Compatibility

The `PostgresSaver` checkpointer (initialised in `server.py` lifespan) serialises LangGraph state between steps. The `retriever` object (a live Chroma client) **cannot be pickled** and must not be stored in graph state. Only lightweight identifiers (e.g., the Chroma collection name or a boolean `rag_available` flag) should travel through the state dict. The actual retriever lives exclusively in the `ContextVar`.
