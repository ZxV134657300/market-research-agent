"""
数据校验工具模块
负责验证报告中的数字是否有原始文档支撑，防止幻觉
"""

import re
from typing import TypedDict


class VerificationResult(TypedDict):
    """单条数据的校验结果"""
    number: str              # 报告中提到的数字
    found: bool              # 是否在原文中找到依据
    source_chunk: str        # 匹配到的原文片段（如有）
    source_file: str         # 来源文件名（如有）
    match_type: str          # exact（精确匹配）/ partial（近似匹配）/ missing（未找到）


class FullVerificationReport(TypedDict):
    """完整校验报告"""
    total_numbers: int       # 报告中数字总数
    verified_count: int      # 已验证数量
    missing_count: int       # 幻觉/未找到数量
    results: list[VerificationResult]
    is_valid: bool           # 是否全部通过校验


def verify_data_against_sources(
    draft: str,
    source_chunks: list[dict],
) -> FullVerificationReport:
    """
    验证报告草稿中的所有数字是否能在原始文档中找到依据

    Args:
        draft: 报告草稿文本
        source_chunks: 原始文档分段列表，每个元素需包含 "text" 和 "source" 字段

    Returns:
        完整校验报告，包含每条数字的验证结果
    """
    # 从草稿中提取所有数字
    draft_numbers = _extract_numbers(draft)

    # 构建原始文档的数字索引
    source_numbers_map = _build_source_number_map(source_chunks)

    # 逐个验证
    results: list[VerificationResult] = []
    for num_str in draft_numbers:
        result = _verify_single_number(num_str, source_chunks, source_numbers_map)
        results.append(result)

    verified_count = sum(1 for r in results if r["found"])
    missing_count = sum(1 for r in results if not r["found"])

    return FullVerificationReport(
        total_numbers=len(results),
        verified_count=verified_count,
        missing_count=missing_count,
        results=results,
        is_valid=(missing_count == 0),
    )


def _extract_numbers(text: str) -> list[str]:
    """
    从文本中提取所有有意义的数字
    匹配：百分比、带单位的数字、纯数字（至少2位有效数字）
    """
    patterns = [
        r'\d+\.?\d*%',                    # 百分比: 6.2%, 100%
        r'\d+\.?\d*\s*[万亿百千]+',        # 中文单位: 4580亿, 2.85万
        r'\d+\.?\d*\s*(?:美元|元|欧元|人民币)',  # 货币: 4580美元
        r'\d+\.?\d*\s*(?:km|公里|米|mm)',   # 距离: 520公里
        r'\d+\.?\d*\s*(?:万部|万辆|万个|万台)',  # 数量单位: 12.4亿部
        r'\d+\.?\d*亿',                    # 亿级数字
        r'\d{2,}\.?\d*',                   # 2位及以上纯数字
    ]

    combined = "|".join(f"({p})" for p in patterns)
    matches = re.findall(combined, text)

    # 去重并清理
    numbers = []
    seen = set()
    for match_groups in matches:
        for m in match_groups:
            if m and m.strip():
                cleaned = m.strip()
                if cleaned not in seen and len(cleaned) >= 2:
                    seen.add(cleaned)
                    numbers.append(cleaned)

    return numbers


def _build_source_number_map(chunks: list[dict]) -> dict[str, list[dict]]:
    """构建源文档中数字到源片段的映射"""
    number_map: dict[str, list[dict]] = {}
    for chunk in chunks:
        text = chunk.get("text", "")
        source = chunk.get("source", "unknown")
        nums = _extract_numbers(text)
        for n in nums:
            if n not in number_map:
                number_map[n] = []
            number_map[n].append({"text": text, "source": source})
    return number_map


def _verify_single_number(
    num_str: str,
    source_chunks: list[dict],
    source_number_map: dict,
) -> VerificationResult:
    """验证单个数字是否能在源文档中找到"""
    # 1. 精确匹配
    if num_str in source_number_map:
        chunk = source_number_map[num_str][0]
        return VerificationResult(
            number=num_str,
            found=True,
            source_chunk=chunk["text"][:200],
            source_file=chunk["source"],
            match_type="exact",
        )

    # 2. 数值近似匹配（提取纯数字部分进行比较）
    numeric_value = _parse_numeric_value(num_str)
    if numeric_value is not None:
        for src_num, src_chunks_list in source_number_map.items():
            src_value = _parse_numeric_value(src_num)
            if src_value is not None and src_value != 0:
                # 允许 1% 的误差（四舍五入差异）
                if abs(numeric_value - src_value) / max(abs(src_value), 1e-10) < 0.01:
                    chunk = src_chunks_list[0]
                    return VerificationResult(
                        number=num_str,
                        found=True,
                        source_chunk=chunk["text"][:200],
                        source_file=chunk["source"],
                        match_type="partial",
                    )

    # 3. 文本片段搜索（检查数字是否出现在任何源文本中）
    for chunk in source_chunks:
        if num_str in chunk.get("text", ""):
            return VerificationResult(
                number=num_str,
                found=True,
                source_chunk=chunk["text"][:200],
                source_file=chunk.get("source", "unknown"),
                match_type="exact",
            )

    # 4. 未找到
    return VerificationResult(
        number=num_str,
        found=False,
        source_chunk="",
        source_file="",
        match_type="missing",
    )


def _parse_numeric_value(num_str: str) -> float | None:
    """从数字字符串中提取纯数值"""
    # 移除非数字字符（保留小数点和负号）
    cleaned = re.sub(r'[^\d.\-]', '', num_str)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None
