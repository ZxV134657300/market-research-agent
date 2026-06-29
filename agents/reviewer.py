"""
智能体 D：质检验收官 (Reviewer)
职责：检查报告中的数字是否能在原始文档中找到依据，消除幻觉
"""

import json
from typing import TypedDict

from tools.validation_tools import verify_data_against_sources, FullVerificationReport
from .llm_client import call_llm
from .writer import WriterOutput
from .collector import CollectorOutput


class ReviewerOutput(TypedDict):
    """检验收官输出数据结构"""
    final_report: str                   # 终版报告
    verification_report: FullVerificationReport  # 校验报告
    sourcing_appendix: str              # 数据溯源附录
    revision_count: int                 # 修订次数


class ReviewerAgent:
    """质检验收官智能体"""

    SYSTEM_PROMPT = """你是一个严谨的报告质检专家。你的任务是：
1. 检查报告中提到的所有数字是否有原始数据支撑
2. 发现幻觉（无法溯源的数字）后，修正报告中的相关内容
3. 确保最终报告的每一个数字都有据可查

当发现幻觉数字时，请修正报告，将无法溯源的数字替换为：
- 如果是估算值，标注"（估算）"
- 如果完全无法溯源，删除该数字并改为定性描述

请返回修正后的完整报告（Markdown 格式），只返回报告内容，不要包含其他解释。"""

    MAX_REVISIONS = 2  # 最大修订次数

    def __init__(self):
        pass

    def run(
        self,
        writer_output: WriterOutput,
        collector_output: CollectorOutput,
    ) -> ReviewerOutput:
        """
        执行质检任务

        Args:
            writer_output: 写手官的输出
            collector_output: 采集官的输出（原始数据）

        Returns:
            终版报告和质检结果
        """
        draft = writer_output["draft"]
        source_chunks = collector_output["raw_chunks"]

        # 执行数字校验
        verification = verify_data_against_sources(draft, source_chunks)

        revision_count = 0
        final_report = draft

        # 如果发现幻觉，执行修正循环
        if not verification["is_valid"] and revision_count < self.MAX_REVISIONS:
            final_report, revision_count = self._revise_report(
                draft, verification, source_chunks, revision_count
            )

            # 重新校验修正后的报告
            final_verification = verify_data_against_sources(final_report, source_chunks)
            verification = final_verification

        # 生成数据溯源附录
        sourcing_appendix = self._generate_sourcing_appendix(verification, source_chunks)

        return ReviewerOutput(
            final_report=final_report,
            verification_report=verification,
            sourcing_appendix=sourcing_appendix,
            revision_count=revision_count,
        )

    def _revise_report(
        self,
        draft: str,
        verification: FullVerificationReport,
        source_chunks: list[dict],
        revision_count: int,
    ) -> tuple[str, int]:
        """修正报告中的幻觉数字"""
        # 收集需要修正的数字
        missing_numbers = [
            r for r in verification["results"]
            if not r["found"]
        ]

        if not missing_numbers:
            return draft, revision_count

        # 构建修正提示
        missing_info = []
        for r in missing_numbers:
            missing_info.append(f"- 数字「{r['number']}」在原始文档中找不到依据")

        source_texts = [f"[{c['source']}] {c['text'][:200]}" for c in source_chunks[:5]]

        prompt = f"""请修正以下报告中无法溯源的数字：

## 需要修正的数字：
{chr(10).join(missing_info)}

## 原始文档参考：
{chr(10).join(source_texts)}

## 原始报告：
{draft}

请返回修正后的完整报告。对于无法溯源的数字，请删除或改为定性描述。"""

        try:
            revised, error = call_llm(prompt, self.SYSTEM_PROMPT, temperature=0.2)
            if error:
                return draft, revision_count
            revision_count += 1
            return revised, revision_count
        except Exception:
            return draft, revision_count

    def _generate_sourcing_appendix(
        self,
        verification: FullVerificationReport,
        source_chunks: list[dict],
    ) -> str:
        """生成数据溯源附录"""
        appendix_lines = ["## 数据溯源附录\n"]
        appendix_lines.append(
            f"本报告共包含 **{verification['total_numbers']}** 个数据引用，"
            f"其中 **{verification['verified_count']}** 个已验证，"
            f"**{verification['missing_count']}** 个未找到明确来源。\n"
        )

        # 按来源文件分组
        sourcing_by_file: dict[str, list[dict]] = {}
        for r in verification["results"]:
            if r["found"] and r["source_file"]:
                if r["source_file"] not in sourcing_by_file:
                    sourcing_by_file[r["source_file"]] = []
                sourcing_by_file[r["source_file"]].append(r)

        for file_name, results in sourcing_by_file.items():
            appendix_lines.append(f"### 📄 {file_name}\n")
            for r in results:
                match_label = "✅ 精确匹配" if r["match_type"] == "exact" else "🔄 近似匹配"
                appendix_lines.append(f"- **{r['number']}** ({match_label})")
                if r["source_chunk"]:
                    snippet = r["source_chunk"][:100].replace("\n", " ")
                    appendix_lines.append(f"  > 原文片段: \"{snippet}...\"")
            appendix_lines.append("")

        # 列出未找到来源的数字
        missing = [r for r in verification["results"] if not r["found"]]
        if missing:
            appendix_lines.append("### ⚠️ 未找到明确来源的数据\n")
            for r in missing:
                appendix_lines.append(f"- **{r['number']}** - 该数字在原始文档中未找到依据")
            appendix_lines.append("")

        return "\n".join(appendix_lines)
