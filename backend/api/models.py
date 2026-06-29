"""Pydantic 数据模型 - 定义 API 请求/响应结构"""

from pydantic import BaseModel
from typing import Optional


class UploadResponse(BaseModel):
    """文件上传响应"""
    file_id: str
    filename: str
    size: int
    message: str


class GenerateRequest(BaseModel):
    """触发报告生成请求"""
    file_ids: list[str] = []
    title: Optional[str] = None
    use_crawled_data: bool = True
    tags: Optional[str] = ""


class GenerateResponse(BaseModel):
    """触发报告生成响应"""
    report_id: str
    message: str


class AgentStatus(BaseModel):
    """单个智能体状态"""
    name: str
    label: str
    status: str          # pending | running | done | error
    message: str = ""


class PipelineStatus(BaseModel):
    """流水线整体状态"""
    report_id: Optional[str] = None
    phase: str           # idle | running | done | error
    agents: list[AgentStatus]
    logs: list[str]
    progress: int        # 0-100


class ReportSummary(BaseModel):
    """报告摘要（列表用）"""
    id: str
    title: str
    created_at: str
    agent_count: int
    status: str


class ReportDetail(BaseModel):
    """报告详情"""
    id: str
    title: str
    created_at: str
    markdown: str
    trace: str
    stats: dict


class StatsResponse(BaseModel):
    """仪表盘统计数据（静态指标，仅页面加载时获取一次）"""
    file_count: int
    chunk_count: int
    qc_pass_rate: float
    report_count: int


class CrawlSourceStatus(BaseModel):
    """单个 RSS 源的爬取状态"""
    name: str
    count: int
    skipped: int
    error: Optional[str] = None


class CrawlStatusResponse(BaseModel):
    """爬取状态响应"""
    last_run: Optional[str] = None
    last_duration: float = 0
    total_articles: int = 0
    new_articles: int = 0
    sources_status: list[CrawlSourceStatus] = []
    running: bool = False


class CrawlTriggerResponse(BaseModel):
    """手动触发爬取的响应"""
    message: str
    result: Optional[dict] = None


class TagsResponse(BaseModel):
    """标签列表响应"""
    tags: list[str]


class ArticleCountResponse(BaseModel):
    """标签匹配文章数量响应"""
    count: int
