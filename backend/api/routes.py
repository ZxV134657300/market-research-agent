"""API 路由定义 - 所有 RESTful 端点"""

import os
import uuid
import json
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from backend.api.models import (
    UploadResponse, GenerateRequest, GenerateResponse,
    PipelineStatus, ReportSummary, ReportDetail, StatsResponse,
    CrawlStatusResponse, CrawlTriggerResponse,
    TagsResponse, ArticleCountResponse,
)
from backend.services import agent_service
from backend.services import report_storage
from backend.services.news_crawler import crawl_all, get_crawl_status
from backend.services.tag_extractor import TagExtractor
from backend.services.subscription_service import SubscriptionService

# 订阅源服务实例
sub_service = SubscriptionService()

router = APIRouter(prefix="/api")

# 上传文件保存目录
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 已上传文件索引  {file_id: {path, filename, size}}
_uploaded_files: dict[str, dict] = {}


# ── 文件上传 ────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """上传单个文件（TXT / PDF），返回 file_id"""
    file_id = uuid.uuid4().hex[:10]
    save_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    _uploaded_files[file_id] = {
        "path": save_path,
        "filename": file.filename,
        "size": len(content),
    }
    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        size=len(content),
        message="上传成功",
    )


# ── 触发报告生成 ────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate_report(req: GenerateRequest):
    """触发多智能体流水线生成报告"""
    file_paths = []
    for fid in req.file_ids:
        info = _uploaded_files.get(fid)
        if not info:
            raise HTTPException(status_code=404, detail=f"文件 {fid} 不存在，请先上传")
        file_paths.append(info["path"])

    # 检查：既没有上传文件，也没有开启爬取数据
    if not file_paths and not req.use_crawled_data:
        raise HTTPException(
            status_code=400,
            detail="请上传文件或开启「使用自动采集数据」选项",
        )

    report_id = agent_service.start_pipeline(
        file_paths, title=req.title, use_crawled_data=req.use_crawled_data,
        tags=req.tags or "",
    )
    return GenerateResponse(report_id=report_id, message="流水线已启动，请轮询 /api/status 查看进度")


# ── 流水线状态 ──────────────────────────────────────────────

@router.get("/status", response_model=PipelineStatus)
async def get_status():
    """获取当前智能体流水线执行状态（前端每 2 秒轮询）"""
    state = agent_service.get_pipeline_status()
    return PipelineStatus(
        report_id=state.get("report_id"),
        phase=state["phase"],
        agents=state["agents"],
        logs=state["logs"],
        progress=state["progress"],
    )


# ── 报告列表 ────────────────────────────────────────────────

@router.get("/reports", response_model=list[ReportSummary])
async def list_reports():
    """获取所有已生成报告的摘要列表"""
    return agent_service.get_all_reports()


# ── 报告详情 ────────────────────────────────────────────────

@router.get("/report/{report_id}", response_model=ReportDetail)
async def get_report(report_id: str):
    """根据 ID 获取完整报告（Markdown 格式）"""
    report = agent_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return ReportDetail(
        id=report_id,
        title=report["title"],
        created_at=report["created_at"],
        markdown=report["markdown"],
        trace=report["trace"],
        stats=report["stats"],
    )


@router.get("/report/{report_id}/download")
async def download_report(report_id: str):
    """下载报告的 .md 文件"""
    report = agent_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")

    file_path = report_storage.REPORTS_DIR / f"{report_id}.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")

    # 生成下载文件名：标题_日期.md
    title = report["title"]
    date_part = report_id.split("_")[0]  # YYYYMMDD
    safe_title = title.replace("/", "_").replace("\\", "_").replace(":", "_")
    download_name = f"{safe_title}_{date_part}.md"

    return FileResponse(
        path=str(file_path),
        filename=download_name,
        media_type="text/markdown; charset=utf-8",
    )


# ── 标签服务 ────────────────────────────────────────────────

@router.get("/tags", response_model=TagsResponse)
async def get_tags():
    """获取当前可用标签列表（从最近 3 天爬取数据中提取）"""
    extractor = TagExtractor(top_k=12)
    tags = extractor.extract_from_crawled_data(days=3)
    # 可选：通过环境变量 ENABLE_LLM_TAG_REFINE=1 开启 LLM 精炼
    if tags and os.environ.get("ENABLE_LLM_TAG_REFINE", "").strip() in ("1", "true", "yes"):
        tags = extractor.refine_with_llm(tags)
    return TagsResponse(tags=tags)


@router.get("/articles/count", response_model=ArticleCountResponse)
async def get_articles_count(tags: str = ""):
    """根据标签统计匹配的文章数量"""
    if not tags.strip():
        return ArticleCountResponse(count=0)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    extractor = TagExtractor()
    count = extractor.count_articles_by_tags(tag_list, days=3)
    return ArticleCountResponse(count=count)


# ── 数据溯源 ────────────────────────────────────────────────

@router.get("/trace/{report_id}")
async def get_trace(report_id: str):
    """获取报告的数据溯源附录"""
    report = agent_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"report_id": report_id, "trace": report["trace"]}


# ── 仪表盘统计 ──────────────────────────────────────────────

@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """获取仪表盘统计数据（仅页面加载时调用一次）"""
    return agent_service.get_stats()


@router.get("/trend")
async def get_trend():
    """获取近 7 日采集量与研报产出趋势数据"""
    return agent_service.get_trend_data()


# ── 新闻爬取 ────────────────────────────────────────────────

@router.post("/crawl", response_model=CrawlTriggerResponse)
async def trigger_crawl():
    """手动触发一次新闻爬取（后台执行）"""
    status = get_crawl_status()
    if status["running"]:
        return CrawlTriggerResponse(message="爬取任务正在执行中，请稍后再试")

    def _run():
        crawl_all()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return CrawlTriggerResponse(message="爬取任务已启动，可通过 /api/crawl/status 查看进度")


@router.get("/crawl/status", response_model=CrawlStatusResponse)
async def crawl_status():
    """获取最近一次爬取的状态"""
    status = get_crawl_status()
    return CrawlStatusResponse(**status)


# ── 订阅源管理 ──────────────────────────────────────────────

@router.get("/subscriptions")
async def get_subscriptions():
    """获取所有订阅源列表"""
    return sub_service.get_all()


@router.post("/subscriptions")
async def add_subscription(body: dict):
    """添加新订阅源"""
    name = body.get("name", "").strip()
    url = body.get("url", "").strip()
    category = body.get("category", "自定义").strip()
    source_type = body.get("type", "rss").strip()  # [Firecrawl] 新增类型字段

    if not name:
        raise HTTPException(status_code=400, detail="订阅源名称不能为空")
    if not url:
        raise HTTPException(status_code=400, detail="订阅源地址不能为空")

    # 验证类型
    if source_type not in ("rss", "firecrawl"):
        raise HTTPException(status_code=400, detail="类型必须为 'rss' 或 'firecrawl'")

    try:
        new_sub = sub_service.add(name, url, category, source_type)
        return {"message": "添加成功", "subscription": new_sub}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/subscriptions/{sub_id}")
async def delete_subscription(sub_id: str):
    """删除订阅源"""
    success = sub_service.delete(sub_id)
    if not success:
        raise HTTPException(status_code=404, detail="订阅源不存在")
    return {"message": "删除成功"}


@router.post("/subscriptions/{sub_id}/toggle")
async def toggle_subscription(sub_id: str):
    """切换订阅源启用/禁用状态"""
    result = sub_service.toggle(sub_id)
    if not result:
        raise HTTPException(status_code=404, detail="订阅源不存在")
    state = "已启用" if result["enabled"] else "已禁用"
    return {"message": state, "subscription": result}


# ── 今日要闻 ────────────────────────────────────────────────

def _format_published(raw: str) -> str:
    """将发布时间格式化为友好格式（如 '10:30' 或 '今天 10:30'）"""
    if not raw:
        return ""
    # 尝试常见格式
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            dt = datetime.strptime(raw[:len(fmt)+2].strip(), fmt)
            today = datetime.now().date()
            if dt.date() == today:
                return f"今天 {dt.strftime('%H:%M')}"
            return dt.strftime("%m-%d %H:%M")
        except ValueError:
            continue
    # 兜底：截取时间部分
    if " " in raw:
        return raw.split(" ")[1][:5]
    return raw[:16]


@router.get("/news/top5")
async def get_top5_news():
    """获取今日要闻 TOP5（从 crawled_data 读取最新文章）"""
    data_dir = Path(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "crawled_data",
    ))

    # 找最新的 JSON 文件
    json_files = sorted(data_dir.glob("*.json"), reverse=True)
    # 排除 seen_hashes.json
    json_files = [f for f in json_files if f.name != "seen_hashes.json"]

    if not json_files:
        return {"news": [], "total": 0}

    try:
        with open(json_files[0], "r", encoding="utf-8") as f:
            articles = json.load(f)
    except (json.JSONDecodeError, Exception):
        return {"news": [], "total": 0}

    total = len(articles)
    top5 = articles[:5]

    news = []
    for a in top5:
        news.append({
            "title": a.get("title", ""),
            "link": a.get("link", ""),
            "source": a.get("source", ""),
            "published": _format_published(a.get("published", "")),
            "summary": a.get("summary", "")[:200],
        })

    return {"news": news, "total": total}
