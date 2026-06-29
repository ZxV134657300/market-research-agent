"""
智能体 A：信息采集官 (Collector)
职责：读取用户上传的原始文档，提取核心实体，输出结构化 JSON
"""

import json
from typing import TypedDict

from tools.file_parser import parse_document, DocumentChunk
from .llm_client import call_llm


class CollectorOutput(TypedDict):
    """采集官输出数据结构"""
    entities: dict          # 提取的核心实体
    raw_chunks: list[dict]  # 原始文档分段
    file_names: list[str]   # 处理的文件名列表


class CollectorAgent:
    """信息采集官智能体"""

    SYSTEM_PROMPT = """你是一个专业的市场数据采集专家。你的任务是从原始文档中提取关键实体信息。

请从以下文本中提取核心实体，以严格的 JSON 格式返回，格式如下：
{
  "brands": ["品牌名1", "品牌名2"],
  "numbers": {
    "market_size": "市场规模数字",
    "growth_rate": "增长率",
    "market_share": {"品牌名": "份额数字"},
    "revenue": "营收数字",
    "other_metrics": {"指标名": "数值"}
  },
  "time_periods": ["涉及的时间段"],
  "positive_feedback": ["正面评价关键词"],
  "negative_feedback": ["负面评价关键词"],
  "key_findings": ["关键发现1", "关键发现2"]
}

注意：
1. 只提取文档中明确提到的数字，不要编造
2. 如果某个字段没有对应数据，返回空列表或空对象
3. 保持原始数字的精度，不要四舍五入
4. 返回纯 JSON，不要包含其他解释文字"""

    def __init__(self):
        pass

    def run(self, file_paths: list[str]) -> CollectorOutput:
        """
        执行信息采集任务

        Args:
            file_paths: 用户上传的文件路径列表

        Returns:
            结构化的采集结果
        """
        all_chunks: list[DocumentChunk] = []
        all_entities: dict = {
            "brands": [],
            "numbers": {},
            "time_periods": [],
            "positive_feedback": [],
            "negative_feedback": [],
            "key_findings": [],
        }
        file_names: list[str] = []

        for file_path in file_paths:
            # 解析文档
            chunks = parse_document(file_path)
            all_chunks.extend(chunks)
            file_names.append(chunks[0]["source"] if chunks else file_path)

            # 合并所有分段文本用于实体提取
            full_text = "\n\n".join(c["text"] for c in chunks)

            # 调用 LLM 提取实体
            entities = self._extract_entities(full_text)
            self._merge_entities(all_entities, entities)

        return CollectorOutput(
            entities=all_entities,
            raw_chunks=[dict(c) for c in all_chunks],
            file_names=file_names,
        )

    def _extract_entities(self, text: str) -> dict:
        """使用 LLM 从文本中提取实体"""
        prompt = f"请从以下市场文档中提取关键实体：\n\n{text[:6000]}"

        try:
            response, error = call_llm(prompt, self.SYSTEM_PROMPT)
            if error:
                return {
                    "brands": [],
                    "numbers": {},
                    "time_periods": [],
                    "positive_feedback": [],
                    "negative_feedback": [],
                    "key_findings": [],
                }
            # 尝试解析 JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            return json.loads(response)
        except (json.JSONDecodeError, Exception) as e:
            # 如果 LLM 返回解析失败，返回空结构
            return {
                "brands": [],
                "numbers": {},
                "time_periods": [],
                "positive_feedback": [],
                "negative_feedback": [],
                "key_findings": [],
            }

    def _merge_entities(self, target: dict, source: dict):
        """合并实体数据"""
        for key in ["brands", "time_periods", "positive_feedback",
                     "negative_feedback", "key_findings"]:
            if key in source and isinstance(source[key], list):
                existing = set(target.get(key, []))
                for item in source[key]:
                    if item not in existing:
                        target[key].append(item)
                        existing.add(item)

        if "numbers" in source and isinstance(source["numbers"], dict):
            for k, v in source["numbers"].items():
                if k not in target["numbers"]:
                    target["numbers"][k] = v
                elif isinstance(v, dict) and isinstance(target["numbers"][k], dict):
                    target["numbers"][k].update(v)
