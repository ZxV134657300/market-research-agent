"""
智能体 C：报告写手官 (Writer)
职责：结合采集官和情报官的数据，生成结构化的 Markdown 报告

v2.0 增强：
- 完善错误处理，捕获异常并返回错误信息
- 记录详细日志
- 支持错误恢复
"""

import json
import logging
from typing import TypedDict, Optional

from .llm_client import call_llm
from .collector import CollectorOutput
from .analyst import AnalystOutput

# 日志配置
logger = logging.getLogger("writer_agent")


class WriterOutput(TypedDict):
    """写手官输出数据结构"""
    draft: str              # Markdown 格式的报告初稿
    sections: list[str]     # 各章节标题列表
    error: Optional[str]    # 错误信息（如果有）


# 报告的5个固定章节结构
REPORT_SECTIONS = [
    "市场概况",
    "竞争格局",
    "用户痛点",
    "未来预测",
    "战略建议",
]


# 错误时的默认报告模板
ERROR_REPORT_TEMPLATE = """# 市场调研报告（生成失败）

## ⚠️ 报告生成异常

**错误信息：** {error_message}

**可能原因：**
1. DeepSeek API 连接超时
2. API 配额不足
3. 网络连接问题
4. 请求内容过大

**建议操作：**
1. 检查网络连接
2. 验证 API Key 是否有效
3. 稍后重试
4. 检查后端日志获取详细错误信息

---

## 📊 已采集的数据摘要

**采集到的实体数据：**
{entities_summary}

**趋势分析：**
{trends_summary}

**数据来源数量：** {source_count} 个来源

---

> 💡 此报告由系统自动生成（错误恢复模式），请根据上述数据手动分析或修复问题后重新生成。
"""


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
        logger.info("✍️ 写手官开始工作...")

        try:
            # 构建提示词
            prompt = self._build_prompt(collector_output, analyst_output)
            logger.info(f"📝 提示词构建完成，长度: {len(prompt)} 字符")

            # 调用 LLM
            logger.info("🚀 调用 LLM 生成报告...")
            draft, error = call_llm(
                prompt,
                self.SYSTEM_PROMPT,
                temperature=0.4,
                max_tokens=4096,
                timeout=180.0,
            )

            if error:
                logger.error(f"❌ LLM 调用失败: {error}")
                # 返回错误报告
                error_report = self._generate_error_report(
                    error,
                    collector_output,
                    analyst_output,
                )
                return WriterOutput(
                    draft=error_report,
                    sections=REPORT_SECTIONS,
                    error=error,
                )

            if not draft or len(draft.strip()) < 100:
                error_msg = f"LLM 返回内容过短或为空 (长度: {len(draft) if draft else 0})"
                logger.warning(f"⚠️ {error_msg}")
                error_report = self._generate_error_report(
                    error_msg,
                    collector_output,
                    analyst_output,
                )
                return WriterOutput(
                    draft=error_report,
                    sections=REPORT_SECTIONS,
                    error=error_msg,
                )

            logger.info(f"✅ 报告生成成功，长度: {len(draft)} 字符")
            return WriterOutput(
                draft=draft,
                sections=REPORT_SECTIONS,
                error=None,
            )

        except Exception as e:
            error_msg = f"写手官异常: {type(e).__name__}: {str(e)}"
            logger.error(f"💥 {error_msg}", exc_info=True)

            # 返回错误报告
            error_report = self._generate_error_report(
                error_msg,
                collector_output,
                analyst_output,
            )
            return WriterOutput(
                draft=error_report,
                sections=REPORT_SECTIONS,
                error=error_msg,
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

    def _generate_error_report(
        self,
        error_message: str,
        collector_output: CollectorOutput,
        analyst_output: AnalystOutput,
    ) -> str:
        """生成错误恢复报告"""
        entities = collector_output["entities"]
        trends = analyst_output["trends"]
        raw_chunks = collector_output["raw_chunks"]

        # 构建实体摘要
        entities_summary_parts = []
        for entity_type, entity_list in entities.items():
            if entity_list:
                entities_summary_parts.append(f"- {entity_type}: {len(entity_list)} 项")
        entities_summary = "\n".join(entities_summary_parts) if entities_summary_parts else "无数据"

        # 构建趋势摘要
        trends_summary_parts = []
        for trend in trends[:5]:  # 最多显示5条
            if isinstance(trend, dict):
                trends_summary_parts.append(f"- {trend.get('description', str(trend))}")
            else:
                trends_summary_parts.append(f"- {str(trend)}")
        trends_summary = "\n".join(trends_summary_parts) if trends_summary_parts else "无数据"

        return ERROR_REPORT_TEMPLATE.format(
            error_message=error_message,
            entities_summary=entities_summary,
            trends_summary=trends_summary,
            source_count=len(raw_chunks),
        )
