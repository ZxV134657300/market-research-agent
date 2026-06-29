"""
订阅源管理服务 - 支持用户自定义 RSS 订阅源和 Firecrawl AI 爬虫源
数据存储在 subscriptions.json 文件中，支持增删改查
"""

import json
import os
import sys
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

SUBSCRIPTION_FILE = Path(ROOT_DIR) / "subscriptions.json"

logger = logging.getLogger("subscription_service")

# ── 默认预设订阅源（首次启动时自动添加） ─────────────────────
DEFAULT_SUBSCRIPTIONS = [
    {
        "name": "36氪",
        "url": "https://36kr.com/feed",
        "category": "科技创投",
        "type": "rss",
    },
    {
        "name": "华尔街见闻",
        "url": "https://rsshub.rssforever.com/wallstreetcn/news/global",
        "category": "财经要闻",
        "type": "rss",
    },
    {
        "name": "同花顺",
        "url": "https://rsshub.rssforever.com/10jqka/realtimenews",
        "category": "实时行情",
        "type": "rss",
    },
]


class SubscriptionService:
    """RSS 订阅源管理服务"""

    def __init__(self):
        self._ensure_file()

    def _ensure_file(self):
        """确保订阅源文件存在，不存在则创建并写入默认源"""
        if not SUBSCRIPTION_FILE.exists():
            # 首次创建，写入默认订阅源
            defaults = []
            for item in DEFAULT_SUBSCRIPTIONS:
                defaults.append({
                    "id": str(uuid.uuid4().hex[:8]),
                    "name": item["name"],
                    "url": item["url"],
                    "category": item.get("category", "未分类"),
                    "type": item.get("type", "rss"),  # [Firecrawl] 新增类型字段
                    "enabled": True,
                    "added_at": datetime.now().isoformat(),
                })
            with open(SUBSCRIPTION_FILE, "w", encoding="utf-8") as f:
                json.dump(defaults, f, ensure_ascii=False, indent=2)
            logger.info(f"已创建订阅源配置文件，预设 {len(defaults)} 个默认源")
        else:
            # [Firecrawl] 兼容旧数据：自动补充 type 字段
            self._migrate_old_data()

    def _migrate_old_data(self):
        """迁移旧数据：为缺少 type 字段的订阅源自动补充 'rss'"""
        try:
            subs = self.get_all()
            modified = False
            for s in subs:
                if "type" not in s:
                    s["type"] = "rss"
                    modified = True
            if modified:
                with open(SUBSCRIPTION_FILE, "w", encoding="utf-8") as f:
                    json.dump(subs, f, ensure_ascii=False, indent=2)
                logger.info("已自动迁移旧订阅源数据，补充 type 字段")
        except Exception as e:
            logger.error(f"迁移旧数据失败: {e}")

    def get_all(self) -> List[Dict]:
        """获取所有订阅源"""
        with open(SUBSCRIPTION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_enabled(self) -> List[Dict]:
        """获取所有已启用的订阅源"""
        return [s for s in self.get_all() if s.get("enabled", True)]

    def add(self, name: str, url: str, category: str = "自定义",
            source_type: str = "rss") -> Dict:
        """
        添加新订阅源

        Args:
            name: 源名称
            url: RSS 地址或目标网站 URL
            category: 分类标签
            source_type: 来源类型 ('rss' 或 'firecrawl')

        Returns:
            新添加的订阅源对象

        Raises:
            ValueError: URL 已存在时抛出
        """
        subs = self.get_all()

        # 检查是否已存在相同 URL
        for s in subs:
            if s["url"] == url:
                raise ValueError("该订阅源已存在")

        new_sub = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "url": url,
            "category": category,
            "type": source_type,  # [Firecrawl] 新增类型字段
            "enabled": True,
            "added_at": datetime.now().isoformat(),
        }
        subs.append(new_sub)

        with open(SUBSCRIPTION_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)

        logger.info(f"已添加订阅源: {name} ({url}) [类型: {source_type}]")
        return new_sub

    def delete(self, sub_id: str) -> bool:
        """
        删除订阅源

        Args:
            sub_id: 订阅源 ID

        Returns:
            是否删除成功
        """
        subs = self.get_all()
        new_subs = [s for s in subs if s["id"] != sub_id]

        if len(new_subs) == len(subs):
            return False

        with open(SUBSCRIPTION_FILE, "w", encoding="utf-8") as f:
            json.dump(new_subs, f, ensure_ascii=False, indent=2)

        logger.info(f"已删除订阅源: {sub_id}")
        return True

    def toggle(self, sub_id: str) -> Optional[Dict]:
        """
        切换订阅源启用/禁用状态

        Args:
            sub_id: 订阅源 ID

        Returns:
            切换后的订阅源对象，未找到返回 None
        """
        subs = self.get_all()
        for s in subs:
            if s["id"] == sub_id:
                s["enabled"] = not s.get("enabled", True)
                with open(SUBSCRIPTION_FILE, "w", encoding="utf-8") as f:
                    json.dump(subs, f, ensure_ascii=False, indent=2)
                state = "启用" if s["enabled"] else "禁用"
                logger.info(f"已{state}订阅源: {s['name']}")
                return s
        return None

    def update(self, sub_id: str, name: str = None, url: str = None, category: str = None) -> Optional[Dict]:
        """
        更新订阅源信息

        Args:
            sub_id: 订阅源 ID
            name: 新名称（可选）
            url: 新地址（可选）
            category: 新分类（可选）

        Returns:
            更新后的订阅源对象，未找到返回 None
        """
        subs = self.get_all()
        for s in subs:
            if s["id"] == sub_id:
                if name is not None:
                    s["name"] = name
                if url is not None:
                    s["url"] = url
                if category is not None:
                    s["category"] = category
                with open(SUBSCRIPTION_FILE, "w", encoding="utf-8") as f:
                    json.dump(subs, f, ensure_ascii=False, indent=2)
                logger.info(f"已更新订阅源: {s['name']}")
                return s
        return None
