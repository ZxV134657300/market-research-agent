"""ChromaDB 记忆服务 - 封装跨会话记忆的存取操作"""

import os
import sys

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tools.memory_tools import add_to_memory, search_vector_memory


def store_report_memory(title: str, markdown: str, entities: dict, trace: str):
    """将生成完毕的报告关键信息压缩存入 ChromaDB"""
    brands = entities.get("brands", [])
    findings = entities.get("key_findings", [])

    content = (
        f"报告标题: {title}\n"
        f"涉及品牌: {', '.join(brands[:5]) if brands else '未识别'}\n"
        f"关键发现: {'; '.join(findings[:3]) if findings else '未提取'}\n"
        f"报告摘要: {markdown[:600]}"
    )
    metadata = {"type": "report", "title": title}
    add_to_memory(content, metadata)


def query_memory(question: str, top_k: int = 3) -> list[dict]:
    """检索与问题相关的历史记忆"""
    results = search_vector_memory(question, top_k=top_k)
    return [
        {
            "content": r["content"],
            "metadata": r["metadata"],
            "relevance": round(1 - r["distance"], 4),
        }
        for r in results
    ]
