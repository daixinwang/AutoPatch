#!/usr/bin/env python
"""
scripts/test_retrieve.py
------------------------
手动测试语义检索效果的 CLI 脚本。

用法：
    python scripts/test_retrieve.py [repo_path]

如果不指定 repo_path，默认使用当前目录（AutoPatch 自身）。
需要设置 OPENAI_EMBED_API_KEY 环境变量。
"""
import os
import sys
import time

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from core.rag.chunker import CodeChunker
from core.rag.indexer import CodeIndexer
from core.rag.retriever import CodeRetriever
import openai
from core.config import (
    RAG_EMBEDDING_MODEL,
    RAG_EMBEDDING_DIMENSIONS,
    OPENAI_EMBED_API_KEY,
    OPENAI_EMBED_BASE_URL,
)
from core.logging_config import setup_logging

setup_logging()

REPO = sys.argv[1] if len(sys.argv) > 1 else "."

print(f"\n=== AutoPatch 语义检索测试 ===")
print(f"仓库路径: {os.path.abspath(REPO)}")
print(f"Embedding 模型: {RAG_EMBEDDING_MODEL}")
if RAG_EMBEDDING_DIMENSIONS > 0:
    print(f"Embedding 维度: {RAG_EMBEDDING_DIMENSIONS}")

if not OPENAI_EMBED_API_KEY:
    print("\n⚠️  警告: OPENAI_EMBED_API_KEY 未设置，向量检索不可用，将仅使用 BM25。")

# 1. 切分代码
print("\n[1/3] 切分代码库...")
t0 = time.time()
chunks = CodeChunker().chunk_directory(Path(REPO))
print(f"  完成: {len(chunks)} 个 chunk，耗时 {time.time()-t0:.2f}s")

# 2. 构建索引（如果有 API Key）
print("\n[2/3] 构建向量索引...")
indexer = CodeIndexer(REPO)
if OPENAI_EMBED_API_KEY:
    t0 = time.time()
    n = indexer.build_or_update(chunks)
    print(f"  完成: 新增 {n} 个 chunk，耗时 {time.time()-t0:.2f}s")
else:
    print("  跳过（无 API Key），向量检索降级为 BM25-only 模式")

# 3. 初始化检索器
print("\n[3/3] 初始化检索器...")
openai_client = openai.OpenAI(
    api_key=OPENAI_EMBED_API_KEY or "dummy",
    base_url=OPENAI_EMBED_BASE_URL or None,
)
retriever = CodeRetriever(
    collection=indexer.get_collection(),
    chunks=chunks,
    embedding_model=RAG_EMBEDDING_MODEL,
    embedding_dimensions=RAG_EMBEDDING_DIMENSIONS,
    openai_client=openai_client,
)
print("  就绪!")

# 4. 交互式查询
print("\n" + "="*50)
print("输入自然语言查询，按回车搜索，空行退出。")
print("="*50)

while True:
    try:
        q = input("\n查询> ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not q:
        break

    results = retriever.retrieve(q, top_k=5)

    if not results:
        print("  (无结果)")
        continue

    print(f"\n找到 {len(results)} 个相关代码片段:\n")
    for i, c in enumerate(results, 1):
        print(f"[{i}] {c.file_path}:{c.start_line}-{c.end_line}  ({c.symbol_type}: {c.symbol_name})")
        if c.docstring:
            print(f"    # {c.docstring[:100]}")
        preview = c.code[:200].replace('\n', '\n    ')
        print(f"    {preview}")
        if len(c.code) > 200:
            print("    ...")
        print()

print("\n再见！")
