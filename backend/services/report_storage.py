"""
报告持久化存储 - 纯 Markdown 文件方案

所有报告以 .md 文件存储在 reports/ 目录下，无需数据库或 JSON 索引。
文件名即为报告 ID（时间戳），内容即为完整报告 Markdown 正文。
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

# 项目根目录下的 reports/ 目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTS_DIR = Path(os.path.join(ROOT_DIR, "reports"))


def ensure_reports_dir():
    """确保 reports 目录存在"""
    REPORTS_DIR.mkdir(exist_ok=True)


def save_report(markdown_content: str, title: str = None,
                trace: str = None, stats: dict = None) -> str:
    """
    保存报告为 .md 文件，返回报告 ID（文件名时间戳）。

    Args:
        markdown_content: 完整的报告 Markdown 字符串
        title: 报告标题（可选，不提供则从内容第一行提取）
        trace: 数据溯源附录（可选，拼接到报告末尾）
        stats: 统计数据字典（可选，作为 YAML frontmatter 存储）

    Returns:
        报告 ID，格式为 YYYYMMDD_HHMMSS
    """
    ensure_reports_dir()

    # 生成时间戳 ID（精确到秒）
    report_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = REPORTS_DIR / f"{report_id}.md"

    # 防止同一秒内重复（加后缀 _2, _3...）
    counter = 2
    while file_path.exists():
        report_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{counter}"
        file_path = REPORTS_DIR / f"{report_id}.md"
        counter += 1

    # 如果标题未提供，从内容第一行提取
    if not title:
        title = _extract_title(markdown_content)
        if not title:
            title = f"市场调研报告 {report_id}"

    # 构建最终文件内容
    parts = []

    # 1. YAML frontmatter（元数据）
    frontmatter_lines = ["---"]
    frontmatter_lines.append(f"title: \"{title}\"")
    frontmatter_lines.append(f"created_at: \"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"")
    if stats:
        frontmatter_lines.append(f"total_chunks: {stats.get('total_chunks', 0)}")
        frontmatter_lines.append(f"total_numbers: {stats.get('total_numbers', 0)}")
        frontmatter_lines.append(f"verified_count: {stats.get('verified_count', 0)}")
        frontmatter_lines.append(f"missing_count: {stats.get('missing_count', 0)}")
        frontmatter_lines.append(f"revision_count: {stats.get('revision_count', 0)}")
    frontmatter_lines.append("---")
    parts.append("\n".join(frontmatter_lines))

    # 2. 报告正文
    parts.append("")
    parts.append(markdown_content.strip())

    # 3. 数据溯源附录（如果有）
    if trace and trace.strip():
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append("## 数据溯源附录")
        parts.append("")
        parts.append(trace.strip())

    # 写入文件
    final_content = "\n".join(parts) + "\n"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(final_content)

    return report_id


def get_all_reports() -> list[dict]:
    """
    获取所有报告的摘要列表，按时间降序排列。

    扫描 reports/ 目录下所有 .md 文件，从文件名解析 ID 和时间，
    从文件首行提取标题。

    Returns:
        报告列表，每项包含 id, title, created_at, status
    """
    ensure_reports_dir()
    reports = []

    for file_path in sorted(REPORTS_DIR.glob("*.md"), reverse=True):
        report_id = file_path.stem

        # 从文件名解析时间
        created_at = _parse_time_from_filename(report_id)

        # 从文件内容提取标题（优先读 frontmatter，其次读首行）
        title = _extract_title_from_file(file_path)

        reports.append({
            "id": report_id,
            "title": title,
            "created_at": created_at,
            "agent_count": 4,
            "status": "done",
        })

    return reports


def get_report(report_id: str) -> Optional[dict]:
    """
    根据报告 ID 获取完整报告数据。

    读取 .md 文件，解析 frontmatter 元数据和正文内容。

    Args:
        report_id: 报告 ID（文件名不含 .md 后缀）

    Returns:
        报告字典 {title, markdown, trace, stats, created_at}，不存在返回 None
    """
    file_path = REPORTS_DIR / f"{report_id}.md"
    if not file_path.exists():
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 解析 frontmatter 和正文
    title = f"市场调研报告 {report_id}"
    created_at = _parse_time_from_filename(report_id)
    stats = {}
    markdown = content
    trace = ""

    # 尝试解析 YAML frontmatter
    fm_match = re.match(r'^---\n(.*?)\n---\n?', content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        # 提取字段
        for line in fm_text.splitlines():
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("created_at:"):
                created_at = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("total_chunks:"):
                stats["total_chunks"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("total_numbers:"):
                stats["total_numbers"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("verified_count:"):
                stats["verified_count"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("missing_count:"):
                stats["missing_count"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("revision_count:"):
                stats["revision_count"] = int(line.split(":", 1)[1].strip())

        # 正文 = frontmatter 之后的内容
        markdown = content[fm_match.end():]

    # 分离溯源附录（以 "## 数据溯源附录" 为界）
    trace_marker = "## 数据溯源附录"
    if trace_marker in markdown:
        parts = markdown.split(trace_marker, 1)
        markdown = parts[0].rstrip()
        trace = parts[1].strip()
        # 去掉正文末尾的分隔线
        markdown = re.sub(r'\n---\s*$', '', markdown).rstrip()

    return {
        "title": title,
        "markdown": markdown,
        "trace": trace,
        "stats": stats,
        "created_at": created_at,
    }


def delete_report(report_id: str) -> bool:
    """
    删除指定报告。

    Args:
        report_id: 报告 ID

    Returns:
        是否删除成功
    """
    file_path = REPORTS_DIR / f"{report_id}.md"
    if file_path.exists():
        file_path.unlink()
        return True
    return False


def get_report_count() -> int:
    """获取报告总数"""
    ensure_reports_dir()
    return len(list(REPORTS_DIR.glob("*.md")))


def get_all_stats() -> dict:
    """
    批量读取所有报告的统计数据（仅解析 frontmatter，不读取全文）。
    返回聚合后的统计：total_chunks, total_numbers, verified_count, latest_qc
    """
    ensure_reports_dir()
    total_chunks = 0
    total_verified = 0
    total_numbers = 0
    latest_created = ""
    latest_stats = {}

    for file_path in sorted(REPORTS_DIR.glob("*.md"), reverse=True):
        stats = _extract_stats_from_frontmatter(file_path)
        total_chunks += stats.get("total_chunks", 0)
        total_verified += stats.get("verified_count", 0)
        total_numbers += stats.get("total_numbers", 0)

        # 跟踪最新报告
        if not latest_created:
            created = _parse_time_from_filename(file_path.stem)
            if created != "未知时间":
                latest_created = created
                latest_stats = stats

    return {
        "total_chunks": total_chunks,
        "total_numbers": total_numbers,
        "verified_count": total_verified,
        "latest_stats": latest_stats,
    }


def _extract_stats_from_frontmatter(file_path: Path) -> dict:
    """仅从文件 frontmatter 中提取统计字段，不读取全文"""
    stats = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 20:  # frontmatter 在前 20 行内
                    break
                line = line.strip()
                for key in ("total_chunks", "total_numbers", "verified_count",
                            "missing_count", "revision_count"):
                    if line.startswith(f"{key}:"):
                        try:
                            stats[key] = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            pass
    except Exception:
        pass
    return stats


# ── 内部工具函数 ────────────────────────────────────────────

def _extract_title(content: str) -> Optional[str]:
    """从 Markdown 内容的第一行提取标题（# 开头）"""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _extract_title_from_file(file_path: Path) -> str:
    """
    从文件中提取标题。
    优先读 YAML frontmatter 中的 title 字段，其次读首行 # 标题。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # 读取前 20 行足够找到标题
            lines = [f.readline() for _ in range(20)]
    except Exception:
        return "未命名报告"

    in_frontmatter = False
    for line in lines:
        line = line.rstrip("\n")
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            else:
                # frontmatter 结束，还没找到标题
                break
        if in_frontmatter and line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"')
        if not in_frontmatter and line.startswith("# "):
            return line[2:].strip()

    return "未命名报告"


def _parse_time_from_filename(report_id: str) -> str:
    """
    从文件名（报告 ID）解析时间。
    支持格式：YYYYMMDD_HHMMSS 或 YYYYMMDD_HHMMSS_N（同秒多报告计数器）
    """
    # 先尝试直接解析 YYYYMMDD_HHMMSS
    try:
        dt = datetime.strptime(report_id, "%Y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass

    # 去掉末尾计数器后缀 _N（单个数字），再试一次
    # 注意：不要用 r'_\d+$'，会误伤时间秒数部分（如 _091547 的 _547）
    m = re.match(r'^(\d{8}_\d{6})_(\d{1,2})$', report_id)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass

    print(f"[警告] 无法解析报告时间: {report_id}")
    return "未知时间"
