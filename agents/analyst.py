"""
智能体 B：竞品情报官 (Analyst)
职责：接收采集官数据，利用 ChromaDB 长期记忆检索历史数据，计算趋势
"""

import json
from typing import TypedDict

from tools.memory_tools import search_vector_memory
from .llm_client import call_llm
from .collector import CollectorOutput


class AnalystOutput(TypedDict):
    """情报官输出数据结构"""
    trends: dict                    # 趋势分析数据
    historical_context: str         # 历史背景摘要
    enhanced_entities: dict         # 增强后的实体数据
    memory_references: list[dict]   # 引用的历史记忆


class AnalystAgent:
    """竞品情报官智能体"""

    SYSTEM_PROMPT = """你是一个资深的市场情报分析师。你的任务是：
1. 结合当前数据和历史记忆数据，分析市场趋势
2. 计算同比/环比变化
3. 识别竞争格局的变化

请以严格的 JSON 格式返回分析结果：
{
  "trends": {
    "market_growth": "市场整体趋势描述",
    "brand_trends": {"品牌名": "趋势描述"},
    "emerging_patterns": ["新兴趋势1", "新兴趋势2"],
    "risk_factors": ["风险因素1"]
  },
  "historical_context": "与历史数据对比的总结段落",
  "key_insights": ["关键洞察1", "关键洞察2", "关键洞察3"]
}

返回纯 JSON，不要包含其他解释文字。"""

    def __init__(self):
        pass

    def run(self, collector_output: CollectorOutput) -> AnalystOutput:
        """
        执行竞品分析任务

        Args:
            collector_output: 采集官的输出数据

        Returns:
            包含趋势分析的增强数据
        """
        entities = collector_output["entities"]
        raw_chunks = collector_output["raw_chunks"]

        # 1. 检索长期记忆
        memory_results = self._search_historical_memory(entities)

        # 2. 计算趋势
        trends_data = self._analyze_trends(entities, memory_results)

        return AnalystOutput(
            trends=trends_data.get("trends", {}),
            historical_context=trends_data.get("historical_context", ""),
            enhanced_entities=entities,
            memory_references=memory_results,
        )

    def _search_historical_memory(self, entities: dict) -> list[dict]:
        """从 ChromaDB 检索相关历史记忆"""
        # 构建查询文本
        brands = entities.get("brands", [])
        query_parts = []
        if brands:
            query_parts.append(f"品牌: {', '.join(brands[:3])}")
        if entities.get("numbers", {}).get("market_size"):
            query_parts.append(f"市场规模: {entities['numbers']['market_size']}")
        if entities.get("key_findings"):
            query_parts.append(entities["key_findings"][0])

        query = " ".join(query_parts) if query_parts else "市场调研报告"

        # 检索记忆
        results = search_vector_memory(query, top_k=3)

        memory_refs = []
        for r in results:
            memory_refs.append({
                "content": r["content"],
                "metadata": r["metadata"],
                "relevance_score": round(1 - r["distance"], 4),
            })

        return memory_refs

    def _analyze_trends(self, entities: dict, memory_results: list[dict]) -> dict:
        """利用 LLM 分析趋势"""
        # 构建分析上下文
        context_parts = ["当前数据："]
        context_parts.append(json.dumps(entities, ensure_ascii=False, indent=2))

        if memory_results:
            context_parts.append("\n\n历史记忆数据：")
            for i, mem in enumerate(memory_results):
                context_parts.append(
                    f"[记忆{i + 1}] (相关度: {mem['relevance_score']})\n{mem['content']}"
                )
        else:
            context_parts.append("\n\n（无历史记忆数据，这是首次分析该领域）")

        context = "\n".join(context_parts)

        prompt = f"""请基于以下当前数据和历史记忆数据，进行市场趋势分析：

{context}

请分析：
1. 市场整体增长趋势
2. 各品牌的发展趋势对比
3. 新兴市场模式和机会
4. 潜在风险因素
5. 与历史数据的对比（如有历史数据）"""

        try:
            response = call_llm(prompt, self.SYSTEM_PROMPT)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            return json.loads(response)
        except (json.JSONDecodeError, Exception):
            return {
                "trends": {
                    "market_growth": "数据不足，无法判断趋势",
                    "brand_trends": {},
                    "emerging_patterns": [],
                    "risk_factors": [],
                },
                "historical_context": "暂无历史数据可对比",
                "key_insights": ["需要更多数据支持分析"],
            }
