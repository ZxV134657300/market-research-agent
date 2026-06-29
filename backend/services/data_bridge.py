"""
数据桥接服务 - 将爬取的 JSON 数据转换为智能体可用的纯文本格式
负责读取 crawled_data/ 中的文章，拼接成类似 mock_data/*.txt 的结构化文本
"""

import os
import sys
import json
from datetime import datetime, timedelta

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

CRAWL_DIR = os.path.join(ROOT_DIR, "crawled_data")


def get_latest_crawled_data(days: int = 3) -> list[dict]:
    """
    读取最近 N 天爬取的文章数据，返回文章列表

    Args:
        days: 读取最近几天的数据，默认 3 天

    Returns:
        文章列表，每篇包含 title/link/summary/source/category/published/crawled_at
    """
    all_articles: list[dict] = []

    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        file_path = os.path.join(CRAWL_DIR, f"{date_str}.json")

        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                    all_articles.extend(articles)
            except (json.JSONDecodeError, Exception):
                continue

    return all_articles


def format_crawled_data_for_agent(articles: list[dict]) -> str:
    """
    将爬取的文章列表转换为智能体可读的纯文本格式
    风格类似 mock_data/*.txt，按来源分组，每篇文章作为一个段落

    Args:
        articles: 文章字典列表

    Returns:
        拼接后的纯文本字符串
    """
    if not articles:
        return ""

    # 按来源分组
    by_source: dict[str, list[dict]] = {}
    for article in articles:
        source = article.get("source", "未知来源")
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(article)

    lines: list[str] = []
    lines.append(f"自动采集市场新闻数据（采集日期: {datetime.now().strftime('%Y-%m-%d')}）")
    lines.append(f"共 {len(articles)} 篇文章，来自 {len(by_source)} 个信息源")
    lines.append("")

    section_num = 1
    for source_name, source_articles in by_source.items():
        lines.append(f"{'一二三四五六七八九十'[min(section_num - 1, 9)]}、来源：{source_name}（{len(source_articles)} 篇）")
        lines.append("")

        for i, article in enumerate(source_articles, 1):
            title = article.get("title", "无标题")
            # [兼容] 优先使用 summary，其次使用 content 或 text
            summary = article.get("summary", "").strip()
            if not summary:
                summary = article.get("content", "").strip()
            if not summary:
                summary = article.get("text", "").strip()
            published = article.get("published", "")
            category = article.get("category", "")

            lines.append(f"{i}. 【{title}】")
            if category:
                lines.append(f"   分类: {category}")
            if published:
                lines.append(f"   发布时间: {published}")
            if summary:
                # 限制每篇摘要长度，避免过长
                if len(summary) > 800:
                    summary = summary[:800] + "…"
                lines.append(f"   摘要: {summary}")
            lines.append("")

        section_num += 1

    return "\n".join(lines)


def save_crawled_as_txt(articles: list[dict], output_path: str | None = None) -> str:
    """
    将爬取数据保存为 txt 文件（与 mock_data 格式一致），
    可直接传给 CollectorAgent 的 file_paths

    Args:
        articles: 文章列表
        output_path: 输出文件路径，默认保存到 crawled_data/当天日期.txt

    Returns:
        保存的文件路径
    """
    if output_path is None:
        today_str = datetime.now().strftime("%Y-%m-%d")
        output_path = os.path.join(CRAWL_DIR, f"{today_str}.txt")

    text = format_crawled_data_for_agent(articles)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    return output_path


def get_crawled_data_as_file_paths(days: int = 3) -> list[str]:
    """
    获取最近 N 天爬取数据的 txt 文件路径列表
    如果 txt 不存在，自动从 JSON 生成

    Returns:
        txt 文件路径列表，可直接传给 start_pipeline()
    """
    file_paths: list[str] = []

    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        json_path = os.path.join(CRAWL_DIR, f"{date_str}.json")
        txt_path = os.path.join(CRAWL_DIR, f"{date_str}.txt")

        if not os.path.exists(json_path):
            continue

        # 如果 txt 不存在或比 json 旧，重新生成
        need_regen = True
        if os.path.exists(txt_path):
            json_mtime = os.path.getmtime(json_path)
            txt_mtime = os.path.getmtime(txt_path)
            if txt_mtime >= json_mtime:
                need_regen = False

        if need_regen:
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                save_crawled_as_txt(articles, txt_path)
            except Exception:
                continue

        if os.path.exists(txt_path):
            file_paths.append(txt_path)

    return file_paths
