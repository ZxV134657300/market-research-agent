"""
Firecrawl AI 爬虫服务 - 使用 Firecrawl API 抓取网站内容
替代传统 RSS，支持整站爬取和单页抓取

v2.0 优化：
- 增强抓取参数（waitFor、移除导航/广告选择器）
- 内容质量过滤（长度、导航关键词检测）
- URL 黑名单（跳过评论/登录/搜索页）
- 智能正文提取（从导航混杂的内容中提取正文）
"""

import os
import sys
import re
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

logger = logging.getLogger("firecrawl_service")


# ── 内容质量配置 ──────────────────────────────────────────────

# URL 黑名单路径模式（跳过这些页面）
URL_BLACKLIST_PATTERNS = [
    '/comment/',      # 评论区
    '/login',         # 登录页
    '/search',        # 搜索页
    '/tag/',          # 标签页
    '/author/',       # 作者页
    '/page/',         # 分页
    '#',              # 锚点链接
    '/about',         # 关于页
    '/contact',       # 联系页
    '/privacy',       # 隐私政策
    '/terms',         # 服务条款
    '/faq',           # FAQ
]

# 导航关键词（用于检测内容是否为导航菜单）
NAV_KEYWORDS = [
    '新浪首页', '新闻', '体育', '娱乐', '财经', '科技', '博客', '微博',
    '首页', '导航', '菜单', '更多', '登录', '注册', '搜索',
    '头条', '推荐', '热门', '排行', '专题',
    '广告服务', '关于我们', '联系方式', '招聘信息',
    '海量资讯', '精准捕捉', '滚动新闻', '最新消息',
    '频道', '栏目', '板块', '分类',
]

# 导航/广告/侧边栏选择器（CSS 选择器，用于移除）
REMOVE_SELECTORS = [
    '.ad', '.ads', '.advertisement',
    '.nav', '.navbar', '.navigation', '.menu',
    '.footer', '.header', '.sidebar',
    '.comment', '.comments',
    '.related', '.recommend',
    '.social', '.share',
    '#header', '#footer', '#nav', '#sidebar',
    '.gg', '.guanggao',  # 中文广告
]


class FirecrawlService:
    """Firecrawl AI 爬虫服务"""

    def __init__(self):
        self.api_key = os.getenv("FIRECRAWL_API_KEY", "")
        self._client = None

        if not self.api_key:
            logger.warning("FIRECRAWL_API_KEY 未配置，Firecrawl 服务不可用")

    def _get_client(self):
        """延迟初始化 Firecrawl 客户端"""
        if self._client is None:
            if not self.api_key:
                raise ValueError("FIRECRAWL_API_KEY 未配置")
            try:
                from firecrawl import FirecrawlApp
                self._client = FirecrawlApp(api_key=self.api_key)
                logger.info("Firecrawl 客户端初始化成功 (v4.x API)")
            except ImportError:
                raise ImportError("请安装 firecrawl-py: pip install firecrawl-py>=1.0.0")
        return self._client

    def _is_url_blacklisted(self, url: str) -> bool:
        """检查 URL 是否在黑名单中"""
        url_lower = url.lower()
        for pattern in URL_BLACKLIST_PATTERNS:
            if pattern in url_lower:
                return True
        return False

    def _is_nav_content(self, content: str) -> bool:
        """检测内容是否主要是导航菜单"""
        if not content:
            return False

        # 统计导航关键词出现次数
        nav_count = sum(1 for kw in NAV_KEYWORDS if kw in content)
        # 如果导航关键词超过 5 个，认为是导航内容
        if nav_count >= 5:
            return True

        # 检测链接密度（导航内容通常链接密度很高）
        link_pattern = r'\[([^\]]+)\]\([^)]+\)'
        links = re.findall(link_pattern, content)
        link_chars = sum(len(link) for link in links)
        total_chars = len(content)

        # 如果链接文字占比超过 60%，认为是导航内容
        if total_chars > 0 and link_chars / total_chars > 0.6:
            return True

        return False

    def _extract_main_content(self, content: str) -> str:
        """
        从可能包含导航的内容中提取正文
        尝试找到真正的文章内容
        """
        if not content:
            return ""

        # 策略1: 查找 Markdown 标题后的内容（# 开头的标题通常在正文前）
        lines = content.split('\n')
        content_start = -1
        for i, line in enumerate(lines):
            # 找到第一个标题或较长的段落
            if line.startswith('#') or (len(line.strip()) > 50 and not line.strip().startswith('[')):
                content_start = i
                break

        if content_start > 0:
            # 跳过前面的导航内容
            content = '\n'.join(lines[content_start:])

        # 策略2: 移除典型的导航行（以 [文字](链接) 开头的连续行）
        lines = content.split('\n')
        filtered_lines = []
        nav_block = False

        for line in lines:
            stripped = line.strip()
            # 检测导航块开始
            if stripped.startswith('[') and '](' in stripped and stripped.endswith(')'):
                if not nav_block:
                    nav_block = True
                continue
            # 检测导航块结束（遇到非链接内容）
            elif nav_block:
                if stripped and not stripped.startswith('['):
                    nav_block = False
                    filtered_lines.append(line)
                continue

            filtered_lines.append(line)

        content = '\n'.join(filtered_lines)

        # 策略3: 移除连续的短行（可能是菜单项）
        lines = content.split('\n')
        filtered_lines = []
        short_line_count = 0

        for line in lines:
            stripped = line.strip()
            if len(stripped) < 10 and stripped:
                short_line_count += 1
                if short_line_count > 3:
                    continue
            else:
                short_line_count = 0
            filtered_lines.append(line)

        content = '\n'.join(filtered_lines)

        # 清理多余的空行
        content = re.sub(r'\n{3,}', '\n\n', content)

        return content.strip()

    def _validate_article_quality(self, title: str, content: str, url: str) -> tuple[bool, str]:
        """
        验证文章质量

        Returns:
            (是否通过, 原因)
        """
        # 处理 None 值
        title = title or ''
        content = content or ''

        # 检查标题
        if not title or len(title.strip()) < 5:
            # 如果标题为空，尝试从内容中提取标题
            if content:
                first_line = content.split('\n')[0].strip()
                if first_line.startswith('#'):
                    title = first_line.lstrip('#').strip()
                elif len(first_line) > 5:
                    title = first_line[:50]

            if not title or len(title.strip()) < 5:
                return False, "标题过短或为空"

        # 检查 URL 黑名单
        if self._is_url_blacklisted(url):
            return False, "URL 在黑名单中"

        # 检查内容长度
        if len(content) < 200:
            return False, f"内容过短 ({len(content)} 字符)"

        # 检查是否为导航内容
        if self._is_nav_content(content):
            return False, "内容主要是导航菜单"

        return True, "通过"

    def scrape_url(self, url: str) -> Optional[dict]:
        """
        抓取单个 URL，返回结构化内容

        Args:
            url: 目标网页 URL

        Returns:
            {
                "title": "页面标题",
                "content": "Markdown 格式内容",
                "url": "来源 URL",
                "description": "页面描述",
            }
            如果失败返回 None
        """
        try:
            client = self._get_client()

            # 增强抓取参数
            result = client.scrape(
                url,
                formats=['markdown'],
                only_main_content=True,
                wait_for=2000,  # 等待 2 秒渲染
            )

            if not result:
                logger.warning(f"抓取失败: {url} - 返回空结果")
                return None

            # v4.x 返回的是 Document 对象
            if isinstance(result, dict):
                metadata = result.get("metadata", {})
                content = result.get("markdown", "")
                title = metadata.get("title", "") or ""
            else:
                metadata = result.metadata if hasattr(result, 'metadata') else {}
                content = result.markdown if hasattr(result, 'markdown') else ""
                title = (metadata.title if hasattr(metadata, 'title') else "") or ""

            # 智能正文提取
            if self._is_nav_content(content):
                logger.info(f"检测到导航内容，尝试提取正文: {url}")
                content = self._extract_main_content(content)

            # 质量验证
            is_valid, reason = self._validate_article_quality(title, content, url)
            if not is_valid:
                logger.warning(f"内容质量不合格: {url} - {reason}")
                return None

            return {
                "title": title.strip(),
                "content": content,
                "url": url,
                "description": (metadata.get("description", "") if isinstance(metadata, dict) else metadata.description if hasattr(metadata, 'description') else "") or "",
            }

        except Exception as e:
            logger.error(f"抓取异常: {url} - {str(e)}")
            return None

    def crawl_website(self, start_url: str, limit: int = 20) -> list[dict]:
        """
        爬取整个网站，返回文章列表

        Args:
            start_url: 起始 URL
            limit: 最大爬取页面数（默认 20，控制 API 用量）

        Returns:
            [{
                "title": "文章标题",
                "content": "Markdown 格式内容",
                "url": "来源 URL",
                "source": "来源网站名",
                "crawled_at": "爬取时间",
            }, ...]
        """
        articles = []
        try:
            client = self._get_client()

            logger.info(f"开始爬取网站: {start_url} (限制 {limit} 页)")

            # 增强抓取参数
            from firecrawl.v2.types import ScrapeOptions
            scrape_options = ScrapeOptions(
                formats=['markdown'],
                only_main_content=True,
                wait_for=2000,  # 等待 2 秒渲染
            )

            crawl_result = client.crawl(
                start_url,
                limit=limit,
                scrape_options=scrape_options,
            )

            if not crawl_result:
                logger.warning(f"爬取失败: {start_url} - 返回空结果")
                return articles

            # 提取域名作为来源名
            parsed = urlparse(start_url)
            source_name = parsed.netloc.replace("www.", "")

            # v4.x 返回 CrawlJob 对象，需要访问 data 属性
            data = crawl_result.data if hasattr(crawl_result, 'data') else crawl_result.get('data', [])

            skipped_count = 0
            for page in data:
                # v4.x 的 page 是 Document 对象
                if hasattr(page, 'metadata'):
                    metadata = page.metadata if page.metadata else {}
                    title = metadata.title if hasattr(metadata, 'title') else ''
                    content = page.markdown if hasattr(page, 'markdown') else ''
                    page_url = metadata.source_url if hasattr(metadata, 'source_url') else ''
                else:
                    # 兼容 dict 格式
                    metadata = page.get('metadata', {})
                    title = metadata.get('title', '')
                    content = page.get('markdown', '')
                    page_url = metadata.get('sourceURL', page.get('url', ''))

                # URL 黑名单过滤
                if self._is_url_blacklisted(page_url):
                    skipped_count += 1
                    continue

                # 智能正文提取（如果检测到导航内容）
                if self._is_nav_content(content):
                    content = self._extract_main_content(content)

                # 质量验证
                is_valid, reason = self._validate_article_quality(title, content, page_url)
                if not is_valid:
                    skipped_count += 1
                    logger.debug(f"跳过页面: {page_url} - {reason}")
                    continue

                articles.append({
                    "title": title.strip(),
                    "content": content[:3000],  # 限制内容长度
                    "url": page_url,
                    "source": source_name,
                    "crawled_at": datetime.now().isoformat(),
                })

            logger.info(f"爬取完成: {start_url} - 获取 {len(articles)} 篇文章，跳过 {skipped_count} 篇")

        except Exception as e:
            logger.error(f"爬取异常: {start_url} - {str(e)}")
            # 如果 scrape_options 方式失败，尝试直接传递参数
            try:
                logger.info(f"尝试备选参数方式...")
                crawl_result = client.crawl(
                    start_url,
                    limit=limit,
                    formats=['markdown'],
                    only_main_content=True,
                )
                if crawl_result:
                    data = crawl_result.data if hasattr(crawl_result, 'data') else []
                    for page in data:
                        if hasattr(page, 'metadata') and hasattr(page, 'markdown'):
                            metadata = page.metadata
                            title = metadata.title if hasattr(metadata, 'title') else ''
                            content = page.markdown
                            page_url = metadata.source_url if hasattr(metadata, 'source_url') else ''

                            # 智能正文提取
                            if self._is_nav_content(content):
                                content = self._extract_main_content(content)

                            # 质量验证
                            is_valid, _ = self._validate_article_quality(title, content, page_url)
                            if is_valid:
                                articles.append({
                                    "title": title.strip(),
                                    "content": content[:3000],
                                    "url": page_url,
                                    "source": source_name,
                                    "crawled_at": datetime.now().isoformat(),
                                })
                    logger.info(f"备选方式爬取完成: {start_url} - 获取 {len(articles)} 篇文章")
            except Exception as e2:
                logger.error(f"备选方式也失败: {e2}")

        return articles

    def is_available(self) -> bool:
        """检查 Firecrawl 服务是否可用"""
        return bool(self.api_key)


# 全局单例
_firecrawl_service: Optional[FirecrawlService] = None


def get_firecrawl_service() -> FirecrawlService:
    """获取 Firecrawl 服务单例"""
    global _firecrawl_service
    if _firecrawl_service is None:
        _firecrawl_service = FirecrawlService()
    return _firecrawl_service
