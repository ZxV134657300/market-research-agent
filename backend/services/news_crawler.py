"""
新闻爬虫服务 - 从 RSS 源和 Firecrawl AI 爬虫自动抓取市场新闻/研报
使用 feedparser 解析 RSS，Firecrawl 抓取整站内容
支持去重、超时熔断、按日期存储
支持从 SubscriptionService 动态加载订阅源
"""

import os
import sys
import re
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import socket
socket.setdefaulttimeout(15)  # RSS 源响应较慢，延长超时
import feedparser

# [Firecrawl] 导入 Firecrawl 服务
from backend.services.firecrawl_service import get_firecrawl_service

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.services.subscription_service import SubscriptionService

# 数据存储目录
CRAWL_DIR = os.path.join(ROOT_DIR, "crawled_data")
HASH_FILE = os.path.join(CRAWL_DIR, "seen_hashes.json")

# 日志
logger = logging.getLogger("news_crawler")

# 订阅源服务实例（延迟初始化）
_sub_service: Optional[SubscriptionService] = None


def _get_sub_service() -> SubscriptionService:
    """延迟初始化订阅源服务"""
    global _sub_service
    if _sub_service is None:
        _sub_service = SubscriptionService()
    return _sub_service


def _get_active_sources() -> list[dict]:
    """从订阅源服务获取所有已启用的源"""
    service = _get_sub_service()
    enabled = service.get_enabled()
    # 转换为爬虫需要的格式，确保有 category 和 type 字段
    sources = []
    for s in enabled:
        sources.append({
            "name": s["name"],
            "url": s["url"],
            "category": s.get("category", "未分类"),
            "type": s.get("type", "rss"),  # [Firecrawl] 新增类型字段
        })
    return sources

# ── 连续失败计数器（内存中，重启后重置） ──────────────────────
_consecutive_fails: dict[str, int] = {}   # {source_name: count}
MAX_CONSECUTIVE_FAILS = 3

# ── 爬取状态（供 API 查询） ──────────────────────────────────
_crawl_status: dict = {
    "last_run": None,
    "last_duration": 0,
    "total_articles": 0,
    "new_articles": 0,
    "sources_status": [],
    "running": False,
}


def get_crawl_status() -> dict:
    """获取最近一次爬取状态"""
    return dict(_crawl_status)


def _compute_hash(title: str, link: str) -> str:
    """基于标题+链接计算去重哈希"""
    raw = f"{title.strip()}|{link.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _load_seen_hashes() -> set:
    """加载已抓取文章的哈希集合"""
    if not os.path.exists(HASH_FILE):
        return set()
    try:
        with open(HASH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except (json.JSONDecodeError, Exception):
        return set()


def _save_seen_hashes(hashes: set):
    """保存已抓取文章的哈希集合"""
    os.makedirs(CRAWL_DIR, exist_ok=True)
    # 只保留最近 5000 条哈希，防止文件无限增长
    recent = sorted(hashes)[-5000:]
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        json.dump(recent, f, ensure_ascii=False)


def _clean_html(raw: str) -> str:
    """清理 HTML 标签并截断"""
    text = re.sub(r"<[^>]+>", "", raw).strip()
    # 替换常见 HTML 实体
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    if len(text) > 1000:
        text = text[:1000] + "…"
    return text


def _fetch_single_source(source: dict, seen_hashes: set) -> tuple[list[dict], int, str]:
    """
    抓取单个 RSS 源

    Returns:
        (新文章列表, 去重跳过数, 错误信息或 "ok")
    """
    name = source["name"]
    articles: list[dict] = []
    skipped = 0
    error_msg = "ok"

    # 熔断检查：连续失败太多次，直接跳过
    if _consecutive_fails.get(name, 0) >= MAX_CONSECUTIVE_FAILS:
        error_msg = f"连续失败 {_consecutive_fails[name]} 次，已自动跳过"
        logger.warning(f"[{name}] {error_msg}")
        return articles, skipped, error_msg

    try:
        feed = feedparser.parse(source["url"])

        if feed.bozo and not feed.entries:
            error_msg = f"RSS 解析失败: {getattr(feed, 'bozo_exception', 'unknown')}"
            logger.warning(f"[{name}] {error_msg}")
            _consecutive_fails[name] = _consecutive_fails.get(name, 0) + 1
            return articles, skipped, error_msg

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()

            if not title or not link:
                continue

            # 去重检查
            h = _compute_hash(title, link)
            if h in seen_hashes:
                skipped += 1
                continue

            seen_hashes.add(h)

            # 提取摘要
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
            elif hasattr(entry, "description"):
                summary = entry.description
            summary = _clean_html(summary)

            # 解析发布时间
            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            articles.append({
                "title": title,
                "link": link,
                "summary": summary,
                "source": name,
                "category": source["category"],
                "published": published,
                "crawled_at": datetime.now().isoformat(),
            })

        # 成功，重置失败计数
        _consecutive_fails[name] = 0
        logger.info(f"[{name}] 抓取到 {len(articles)} 篇新文章，跳过 {skipped} 篇重复")

    except Exception as e:
        error_msg = str(e)
        _consecutive_fails[name] = _consecutive_fails.get(name, 0) + 1
        fail_count = _consecutive_fails[name]
        if fail_count >= MAX_CONSECUTIVE_FAILS:
            logger.error(f"[{name}] 抓取异常（第 {fail_count} 次，已达上限，下次将自动跳过）: {error_msg}")
        else:
            logger.error(f"[{name}] 抓取异常（第 {fail_count}/{MAX_CONSECUTIVE_FAILS} 次）: {error_msg}")

    return articles, skipped, error_msg


# [Firecrawl] 新增：抓取 Firecrawl 源
def _fetch_firecrawl_source(source: dict, seen_hashes: set) -> tuple[list[dict], int, str]:
    """
    抓取单个 Firecrawl 源（整站爬取）

    Args:
        source: 订阅源信息 {"name": ..., "url": ..., "category": ..., "type": "firecrawl"}
        seen_hashes: 已抓取文章的哈希集合

    Returns:
        (新文章列表, 去重跳过数, 错误信息或 "ok")
    """
    name = source["name"]
    articles: list[dict] = []
    skipped = 0
    error_msg = "ok"

    # 熔断检查
    if _consecutive_fails.get(name, 0) >= MAX_CONSECUTIVE_FAILS:
        error_msg = f"连续失败 {_consecutive_fails[name]} 次，已自动跳过"
        logger.warning(f"[{name}] {error_msg}")
        return articles, skipped, error_msg

    try:
        firecrawl = get_firecrawl_service()

        if not firecrawl.is_available():
            error_msg = "Firecrawl API Key 未配置"
            logger.warning(f"[{name}] {error_msg}")
            return articles, skipped, error_msg

        # 爬取网站（限制 20 页，控制 API 用量）
        crawled_articles = firecrawl.crawl_website(source["url"], limit=20)

        for article in crawled_articles:
            # [修复] 统一字段名：Firecrawl 返回的是 url/content，需要转换为 link/summary
            title = article.get("title", "").strip()
            link = article.get("url", "").strip()

            if not title or not link:
                continue

            # 去重检查
            h = _compute_hash(title, link)
            if h in seen_hashes:
                skipped += 1
                continue

            seen_hashes.add(h)

            # [修复] 统一字段名：content -> summary
            content = article.get("content", "")
            if len(content) > 1000:
                content = content[:1000] + "…"

            # [修复] 确保返回的文章格式与 RSS 源一致
            articles.append({
                "title": title,
                "link": link,                    # 统一为 link（不是 url）
                "summary": content,              # 统一为 summary（不是 content）
                "source": name,                  # 统一为 source（不是 source_name）
                "category": source["category"],
                "published": article.get("crawled_at", ""),
                "crawled_at": datetime.now().isoformat(),
            })

        # 成功，重置失败计数
        _consecutive_fails[name] = 0
        logger.info(f"[{name}] Firecrawl 抓取到 {len(articles)} 篇新文章，跳过 {skipped} 篇重复")

    except Exception as e:
        error_msg = str(e)
        _consecutive_fails[name] = _consecutive_fails.get(name, 0) + 1
        fail_count = _consecutive_fails[name]
        if fail_count >= MAX_CONSECUTIVE_FAILS:
            logger.error(f"[{name}] Firecrawl 抓取异常（第 {fail_count} 次，已达上限，下次将自动跳过）: {error_msg}")
        else:
            logger.error(f"[{name}] Firecrawl 抓取异常（第 {fail_count}/{MAX_CONSECUTIVE_FAILS} 次）: {error_msg}")

    return articles, skipped, error_msg


def crawl_all() -> dict:
    """
    执行全量抓取，返回爬取结果摘要

    Returns:
        {
            "total": 抓取到的新文章总数,
            "sources": [{name, count, skipped, error}],
            "saved_to": 保存的文件路径,
            "duration": 耗时秒数,
        }
    """
    global _crawl_status
    start_time = datetime.now()

    _crawl_status["running"] = True
    _crawl_status["sources_status"] = []

    os.makedirs(CRAWL_DIR, exist_ok=True)
    seen_hashes = _load_seen_hashes()

    all_articles: list[dict] = []
    sources_result: list[dict] = []

    # ── 逐源抓取（从订阅源服务动态加载） ──
    active_sources = _get_active_sources()
    if not active_sources:
        logger.warning("没有启用的订阅源，跳过抓取")
        return {
            "total": 0,
            "sources": [],
            "saved_to": "",
            "duration": 0,
        }

    for source in active_sources:
        # [Firecrawl] 根据源类型分别处理
        source_type = source.get("type", "rss")
        if source_type == "firecrawl":
            articles, skipped, error = _fetch_firecrawl_source(source, seen_hashes)
        else:
            articles, skipped, error = _fetch_single_source(source, seen_hashes)

        all_articles.extend(articles)
        sources_result.append({
            "name": source["name"],
            "type": source_type,
            "count": len(articles),
            "skipped": skipped,
            "error": error if error != "ok" else None,
        })

    # ── 保存到 JSON 文件 ──
    today_str = datetime.now().strftime("%Y-%m-%d")
    save_path = os.path.join(CRAWL_DIR, f"{today_str}.json")

    # 如果今天已有数据，合并追加
    existing: list[dict] = []
    if os.path.exists(save_path):
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, Exception):
            existing = []

    existing.extend(all_articles)

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # 保存去重哈希
    _save_seen_hashes(seen_hashes)

    duration = round((datetime.now() - start_time).total_seconds(), 1)

    # ── 更新状态 ──
    _crawl_status.update({
        "last_run": datetime.now().isoformat(),
        "last_duration": duration,
        "total_articles": len(existing),
        "new_articles": len(all_articles),
        "sources_status": sources_result,
        "running": False,
    })

    # ── 汇总日志 ──
    summary_parts = []
    for s in sources_result:
        if s["error"]:
            summary_parts.append(f"{s['name']}:失败({s['error'][:30]})")
        else:
            summary_parts.append(f"{s['name']}:{s['count']}篇")

    logger.info(
        f"爬取完成 | 新增 {len(all_articles)} 篇 | "
        f"{'，'.join(summary_parts)} | "
        f"耗时 {duration}s | 保存至 {save_path}"
    )

    return {
        "total": len(all_articles),
        "sources": sources_result,
        "saved_to": save_path,
        "duration": duration,
    }


def load_crawled_data(days: int = 3) -> list[dict]:
    """
    读取最近 N 天爬取的文章数据

    Args:
        days: 读取最近几天的数据，默认 3 天

    Returns:
        文章列表，按日期倒序排列
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


def get_today_article_count() -> int:
    """获取今天爬取的文章数量"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    file_path = os.path.join(CRAWL_DIR, f"{today_str}.json")

    if not os.path.exists(file_path):
        return 0

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
            return len(articles)
    except (json.JSONDecodeError, Exception):
        return 0


def get_daily_article_counts(days: int = 7) -> dict[str, int]:
    """
    获取最近 N 天每天的文章数量

    Returns:
        {"2026-06-15": 12, "2026-06-16": 8, ...}
    """
    counts: dict[str, int] = {}

    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        file_path = os.path.join(CRAWL_DIR, f"{date_str}.json")

        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                    counts[date_str] = len(articles)
            except (json.JSONDecodeError, Exception):
                counts[date_str] = 0
        else:
            counts[date_str] = 0

    return counts
