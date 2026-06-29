"""
智能体 C：报告写手官 (Writer)
职责：结合采集官和情报官的数据，生成结构化的 Markdown 报告
"""

import json
from typing import TypedDict

from .llm_client import call_llm
from .collector import CollectorOutput
from .analyst import AnalystOutput


class WriterOutput(TypedDict):
    """写手官输出数据结构"""
    draft: str              # Markdown 格式的报告初稿
    sections: list[str]     # 各章节标题列表


# 报告的5个固定章节结构
REPORT_SECTIONS = [
    "市场概况",
    "竞争格局",
    "用户痛点",
    "未来预测",
    "战略建议",
]


class WriterAgent:
    """报告写手官智能体"""

    SYSTEM_PROMPT = """你是一个专业的市场调研报告撰写专家。你的任务是根据提供的数据，撰写一份结构清晰、数据详实的市场分析报告。

要求：
1. 严格按照以下5个章节结构撰写：市场概况、竞争格局、用户痛点、未来预测、战略建议
2. 报告必须使用 Markdown 格式
3. 所有数据必须来自提供的原始数据，不得编造任何数字
4. 每个数字后面标注来源（如：[来源: xxx]）
5. 使用专业的商业分析语言
6. 每个章节至少包含3-5个要点
7. 在报告末尾添加"数据来源"附录，列出所有引用的数据来源

报告格式要求：
- 使用 # 作为主标题
- 使用 ## 作为章节标题
- 使用 ### 作为子标题
- 关键数字使用 **加粗** 标注
- 使用表格展示对比数据"""

    def __init__(self):
        pass

    def run(
        self,
        collector_output: CollectorOutput,
        analyst_output: AnalystOutput,
    ) -> WriterOutput:
        """
        执行报告撰写任务

        Args:
            collector_output: 采集官的输出数据
            analyst_output: 情报官的输出数据

        Returns:
            Markdown 格式的报告初稿
        """
        prompt = self._build_prompt(collector_output, analyst_output)
        draft = call_llm(prompt, self.SYSTEM_PROMPT, temperature=0.4)

        return WriterOutput(
            draft=draft,
            sections=REPORT_SECTIONS,
        )

    def _build_prompt(
        self,
        collector_output: CollectorOutput,
        analyst_output: AnalystOutput,
    ) -> str:
        """构建写手提示词"""
        entities = collector_output["entities"]
        raw_chunks = collector_output["raw_chunks"]
        trends = analyst_output["trends"]
        historical_context = analyst_output["historical_context"]

        # 构建原始数据摘要
        source_summary = []
        for chunk in raw_chunks[:10]:  # 最多取10个分段
            source_summary.append(f"[来源: {chunk['source']}] {chunk['text'][:300]}")

        prompt = f"""请根据以下数据撰写一份完整的市场调研分析报告。

## 提取的核心数据
{json.dumps(entities, ensure_ascii=False, indent=2)}

## 趋势分析
{json.dumps(trends, ensure_ascii=False, indent=2)}

## 历史背景
{historical_context}

## 原始文档片段
{chr(10).join(source_summary)}

## 报告结构要求
请严格按照以下5个章节撰写：
1. 市场概况 - 市场规模、增长率、整体趋势
2. 竞争格局 - 各品牌市场份额、竞争态势
3. 用户痛点 - 用户反馈的主要问题
4. 未来预测 - 基于数据的趋势预测
5. 战略建议 - 基于分析的可操作建议

注意：所有引用的数字必须来自上述原始数据，不得编造！"""

        return prompt
