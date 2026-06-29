"""
标签提取服务 - 从爬取的文章内容中自动提取主题词作为标签
方案：jieba TF-IDF + 严格停用词 + 词性过滤 + 后处理
"""

import json
import os
import re
from pathlib import Path
from typing import List, Dict

import jieba
import jieba.analyse
from dotenv import load_dotenv

load_dotenv()

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CRAWL_DIR = os.path.join(ROOT_DIR, "crawled_data")


class TagExtractor:
    """从爬取数据中提取主题词作为标签（TF-IDF + 严格停用词 + 词性过滤）"""

    def __init__(self, top_k: int = 12):
        self.top_k = top_k

        # ===== 完整停用词表（覆盖财经/新闻高频噪音）=====
        self.stopwords = {
            # 常见虚词/助词
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
            '看', '好', '自己', '来', '与', '及', '更', '于', '其', '等', '但', '或', '并', '而', '所', '之', '则', '因', '此', '该', '各', '多', '每', '大', '小',
            '新', '老', '高', '低', '长', '短', '快', '慢', '正', '负', '方', '式', '方法',

            # 财经/数字类高频词
            '亿元', '万美元', '亿美元', '人民币', '美元', '欧元', '日元', '英镑', '港元', '澳门元', '新台币', '韩元',
            '同比增长', '环比增长', '增长', '下降', '上涨', '下跌', '涨幅', '跌幅', '同比', '环比', '截至', '累计', '合计',
            '显示', '表示', '据', '根据', '对于', '通过', '其中', '分别', '约为', '接近', '超过', '低于', '高于',
            '保持', '持续', '预计', '有望', '将', '已', '正在', '进行', '实现', '达到', '突破',

            # 新闻来源/固定前缀
            '氪获悉', '36氪', '新浪财经', '华尔街见闻', '同花顺', '东方财富', '澎湃新闻', '财联社', '界面', '界面新闻',
            '快讯', '独家', '首发', '深度', '解读', '分析', '报告', '研报', '调研',

            # 客套/无意义词
            '大家好', '欢迎', '关注', '分享', '评论', '点赞', '收藏', '转发', '声明', '免责', '版权', '请联系',
            '此外', '同时', '与此同时', '近日', '近期', '日前', '此前', '目前', '去年', '今年', '明年', '一季度', '上半年', '下半年',
            '年底', '年初', '月末', '周末', '工作日', '节假日', '今天', '明天', '昨天', '现在', '将来',

            # 其他常见干扰
            '用户', '消费者', '投资者', '分析师', '专家', '研究员', '作者', '编辑', '记者',
            '产品', '服务', '市场', '行业', '领域', '方向', '趋势', '机会', '挑战', '风险', '优势', '劣势',
            '我们', '他们', '大家', '各位', '各位朋友',
        }

    def _clean_text(self, text: str) -> str:
        """清洗文本：去除 URL、邮箱、数字、短英文"""
        # 去除 URL
        text = re.sub(r'http\S+', '', text)
        # 去除邮箱
        text = re.sub(r'\S+@\S+', '', text)
        # 去除数字（但保留中文数字）
        text = re.sub(r'\d+', '', text)
        # 去除单个或两个字母的英文（保留 AI、SaaS 等 3+ 字母词）
        text = re.sub(r'\b[a-zA-Z]{1,2}\b', '', text)
        # 去除多余空格
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def extract_from_text(self, text: str) -> List[str]:
        """从文本中提取关键词（使用 TF-IDF + 词性过滤）"""
        text = self._clean_text(text)
        if len(text) < 10:
            return []

        # 使用 jieba TF-IDF 提取关键词
        keywords = jieba.analyse.extract_tags(
            text,
            topK=self.top_k * 2,
            withWeight=False,
            allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'v', 'a'),
        )

        # 过滤停用词 + 长度过滤
        filtered = []
        for kw in keywords:
            if kw in self.stopwords:
                continue
            if len(kw) < 2:
                continue
            if re.match(r'^[0-9a-zA-Z]+$', kw):
                continue
            filtered.append(kw)

        # 去重（保留顺序）
        seen = set()
        result = []
        for kw in filtered:
            if kw not in seen:
                seen.add(kw)
                result.append(kw)

        # 如果结果太少，放宽词性限制
        if len(result) < 5:
            keywords2 = jieba.analyse.extract_tags(
                text,
                topK=self.top_k * 3,
                withWeight=False,
                allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'vn', 'v', 'a', 'an'),
            )
            for kw in keywords2:
                if kw in self.stopwords:
                    continue
                if len(kw) < 2:
                    continue
                if kw not in seen:
                    seen.add(kw)
                    result.append(kw)
                if len(result) >= self.top_k:
                    break

        return result[:self.top_k]

    def extract_from_articles(self, articles: List[Dict]) -> List[str]:
        """从文章列表中提取标签（拼接标题+摘要）"""
        if not articles:
            return []
        # 取前 30 篇文章（避免文本过长）
        texts = []
        for a in articles[:30]:
            title = a.get('title', '')
            summary = a.get('summary', '') or a.get('description', '')
            texts.append(title + " " + summary)
        combined = " ".join(texts)
        return self.extract_from_text(combined)

    def extract_from_crawled_data(self, days: int = 3) -> List[str]:
        """从最近 N 天的爬虫数据中提取标签，支持 LLM 精炼"""
        all_articles = self._load_articles(days)
        if not all_articles:
            return []
        tags = self.extract_from_articles(all_articles)
        # 少于 3 个标签视为无效，返回空
        if len(tags) < 3:
            return []

        # LLM 精炼
        if os.getenv("ENABLE_LLM_TAG_REFINE", "").lower() in ("true", "1", "yes"):
            print(f"[标签提取] 原始标签: {tags}")
            tags = self.refine_with_llm(tags)
            print(f"[标签提取] LLM精炼后: {tags}")

        return tags

    def count_articles_by_tags(self, tags: List[str], days: int = 3) -> int:
        """统计包含至少一个标签的文章数量"""
        if not tags:
            return 0

        all_articles = self._load_articles(days)
        count = 0
        tags_lower = [t.lower() for t in tags]

        for article in all_articles:
            text = (article.get('title', '') + " " + article.get('summary', '')).lower()
            if any(tag in text for tag in tags_lower):
                count += 1

        return count

    def filter_articles_by_tags(self, articles: List[Dict], tags: List[str]) -> List[Dict]:
        """根据标签过滤文章列表"""
        if not tags:
            return articles

        tags_lower = [t.lower() for t in tags]
        filtered = []

        for article in articles:
            text = (article.get('title', '') + " " + article.get('summary', '')).lower()
            if any(tag in text for tag in tags_lower):
                filtered.append(article)

        return filtered

    # 人物/活动类黑名单 —— 这些词不应出现在最终标签中
    TAG_BLACKLIST = {
        "圆桌", "创业者", "创始人", "嘉宾", "论坛", "峰会", "沙龙",
        "研讨", "交流", "分享", "对话", "访谈", "演讲", "发布会",
        "大会", "年会", "博览会", "展览会", "典礼", "仪式",
    }

    def refine_with_llm(self, candidate_tags: List[str]) -> List[str]:
        """使用 DeepSeek API 精炼标签：去噪、合并同类项、提升主题精度"""
        if not candidate_tags:
            return []
        if len(candidate_tags) < 3:
            return candidate_tags

        # 先用黑名单快速过滤
        candidate_tags = [t for t in candidate_tags if t not in self.TAG_BLACKLIST]
        if len(candidate_tags) < 3:
            return candidate_tags

        try:
            from agents.llm_client import LLMClient
            llm = LLMClient()

            prompt = f"""你是一个专业的标签精炼助手。请从以下候选标签中，筛选出 4-6 个最核心的主题标签。

【候选标签】
{', '.join(candidate_tags)}

【精炼规则（必须严格遵守）】
1. 将具体术语归类到更宏观的领域词：
   - "硅片"、"芯片"、"半导体" → 保留或归入 "半导体" / "芯片"
   - "脑机" → 归入 "脑机接口"
   - "加息"、"降息"、"利率" → 归入 "货币政策" / "宏观经济"
   - "黄仁勋"、"马斯克" → 保留知名人物名或标注其公司所属领域
   - "接口" → 如果是技术相关，归入具体技术领域词

2. 去掉过于宽泛的通用词：
   - "涨价"、"价格" → 去掉（太泛），保留具体商品名
   - "数据" → 除非是 "大数据" 等专有名词，否则去掉
   - "公司"、"企业"、"获悉" → 去掉（太泛）

3. 合并同类项：
   - "AI"、"人工智能"、"大模型" → 只保留一个（优先保留 "人工智能"）

4. 最终输出：
   - 只返回 4-6 个标签，用逗号分隔
   - 标签按重要性排列
   - 不要有任何额外文字、编号或解释

【示例】
输入：苹果、涨价、公司、价格、接口、硅片、脑机、加息、黄仁勋、数据、企业、获悉
输出：苹果、芯片、脑机接口、货币政策、半导体、人工智能

输入：新能源、电动车、电池、比亚迪、特斯拉、充电桩、续航、自动驾驶、AI
输出：新能源汽车、电池、比亚迪、特斯拉、自动驾驶、人工智能

输入：楼市、房价、成交量、开发商、土地、政策、限购、利率
输出：房地产、土地市场、楼市政策、货币政策

现在请处理：
{', '.join(candidate_tags)}"""

            response, error = llm.chat(prompt)
            if error:
                print(f"[标签精炼] LLM 调用失败: {error}")
                return candidate_tags[:self.top_k]
            refined = [t.strip() for t in response.split(',') if t.strip()]
            # 二次过滤黑名单
            refined = [t for t in refined if t not in self.TAG_BLACKLIST]
            return refined[:self.top_k] if refined else candidate_tags[:self.top_k]

        except Exception as e:
            print(f"[标签精炼] LLM 调用失败，使用原始标签: {e}")
            return candidate_tags[:self.top_k]

    def _load_articles(self, days: int) -> List[dict]:
        """加载最近 N 天的爬取文章"""
        from datetime import datetime, timedelta

        all_articles = []
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
