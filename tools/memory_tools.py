"""
ChromaDB 长期记忆工具模块
负责向量存储和检索，实现跨会话的知识记忆

使用 ChromaDB 自带的 DefaultEmbeddingFunction（基于 onnxruntime），
无需下载 sentence-transformers / torch 等大型依赖。
"""

import os
from typing import TypedDict

# ChromaDB 持久化存储路径
MEMORY_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory_db")


class MemoryResult(TypedDict):
    """记忆检索结果"""
    content: str
    metadata: dict
    distance: float


# 全局 ChromaDB 客户端（延迟初始化）
_chroma_client = None
_collection = None


def _get_collection():
    """获取或创建 ChromaDB collection（延迟初始化，使用轻量嵌入函数）"""
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    try:
        import chromadb
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    except ImportError:
        raise ImportError(
            "需要安装 chromadb 和 onnxruntime：\n"
            "  pip install chromadb onnxruntime numpy"
        )

    os.makedirs(MEMORY_DB_PATH, exist_ok=True)

    # 显式指定轻量级嵌入函数，避免隐式拉取 sentence-transformers
    embedding_fn = DefaultEmbeddingFunction()

    _chroma_client = chromadb.PersistentClient(path=MEMORY_DB_PATH)
    _collection = _chroma_client.get_or_create_collection(
        name="market_research_memory",
        metadata={"description": "市场调研报告长期记忆存储"},
        embedding_function=embedding_fn,
    )
    return _collection


def add_to_memory(
    content: str,
    metadata: dict,
    doc_id: str | None = None,
) -> str:
    """
    将文本片段存入 ChromaDB 长期记忆

    Args:
        content: 要存储的文本内容
        metadata: 元数据（如 industry, year, key_metrics 等）
        doc_id: 文档ID，不提供则自动生成

    Returns:
        存储的文档ID
    """
    import hashlib
    import time

    if doc_id is None:
        doc_id = hashlib.md5(
            f"{content[:100]}{time.time()}".encode()
        ).hexdigest()

    collection = _get_collection()
    collection.upsert(
        ids=[doc_id],
        documents=[content],
        metadatas=[metadata],
    )
    return doc_id


def search_vector_memory(query: str, top_k: int = 3) -> list[MemoryResult]:
    """
    从 ChromaDB 中检索与查询最相关的历史记忆

    Args:
        query: 查询文本
        top_k: 返回最相关的条数

    Returns:
        检索结果列表，按相关性排序
    """
    collection = _get_collection()

    # 如果集合为空，直接返回空列表
    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
    )

    memory_results: list[MemoryResult] = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            memory_results.append(MemoryResult(
                content=doc,
                metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                distance=results["distances"][0][i] if results["distances"] else 0.0,
            ))

    return memory_results
