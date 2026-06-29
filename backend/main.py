"""
FastAPI 主入口
启动命令: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import sys
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# 确保项目根目录在 sys.path 中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 加载 .env
load_dotenv(os.path.join(ROOT_DIR, ".env"))

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")


# ── 定时任务调度 ──────────────────────────────────────────────

def _setup_scheduler():
    """配置 APScheduler 定时任务"""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from backend.services.news_crawler import crawl_all

    scheduler = BackgroundScheduler()

    # 每天早上 8:00 自动抓取
    scheduler.add_job(
        crawl_all,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_crawl",
        name="每日新闻抓取",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("定时任务已启动: 每天 08:00 自动抓取新闻")
    return scheduler


def _startup_crawl():
    """启动时在后台线程立即执行一次抓取"""
    from backend.services.news_crawler import crawl_all

    def _crawl_task():
        try:
            logger.info("启动时自动抓取开始...")
            result = crawl_all()
            logger.info(f"启动时自动抓取完成: 新增 {result['total']} 篇文章")
        except Exception as e:
            logger.error(f"启动时自动抓取失败: {e}")

    thread = threading.Thread(target=_crawl_task, daemon=True)
    thread.start()


# ── 生命周期管理 ──────────────────────────────────────────────

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期：启动时初始化调度器并抓取，关闭时清理"""
    global _scheduler
    # 启动
    _scheduler = _setup_scheduler()
    _startup_crawl()
    yield
    # 关闭
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已关闭")


# ── 创建 FastAPI 应用 ────────────────────────────────────────

app = FastAPI(
    title="AI 市场调研报告生成系统",
    description="多智能体协作的市场调研报告自动生成平台",
    version="2.0.0",
    lifespan=lifespan,
)

# 挂载 API 路由
from backend.api.routes import router as api_router
app.include_router(api_router)

# 挂载前端静态文件
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")


@app.get("/")
async def serve_index():
    """返回前端主页面"""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI Market Research Agent"}
