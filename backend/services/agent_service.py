"""
智能体调度服务 - 在后台线程中运行 4 个智能体流水线，并通过全局状态供前端轮询。
"""

import os
import sys
import time
import uuid
import threading
from datetime import datetime

# 确保项目根目录在 Python 路径中
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from agents.collector import CollectorAgent
from agents.analyst import AnalystAgent
from agents.writer import WriterAgent
from agents.reviewer import ReviewerAgent
from backend.services.memory_service import store_report_memory
from backend.services.news_crawler import (
    load_crawled_data, get_today_article_count, get_daily_article_counts,
)
from backend.services.data_bridge import get_crawled_data_as_file_paths, get_latest_crawled_data
from backend.services.tag_extractor import TagExtractor
from backend.services import report_storage

# ── 全局状态 ────────────────────────────────────────────────
_lock = threading.Lock()

_pipeline_state: dict = {
    "report_id": None,
    "phase": "idle",           # idle | running | done | error
    "agents": [
        {"name": "collector", "label": "信息采集官", "status": "pending", "message": ""},
        {"name": "analyst",   "label": "竞品情报官", "status": "pending", "message": ""},
        {"name": "writer",    "label": "报告写手官", "status": "pending", "message": ""},
        {"name": "reviewer",  "label": "质检验收官", "status": "pending", "message": ""},
    ],
    "logs": [],
    "progress": 0,
}


def get_pipeline_status() -> dict:
    """返回当前流水线状态的快照"""
    with _lock:
        import copy
        return copy.deepcopy(_pipeline_state)


def get_report(report_id: str) -> dict | None:
    """根据 ID 获取报告（从 Markdown 文件读取）"""
    return report_storage.get_report(report_id)


def get_all_reports() -> list[dict]:
    """获取所有报告的摘要列表（从文件系统扫描）"""
    return report_storage.get_all_reports()


def get_stats() -> dict:
    """获取仪表盘统计数据（从文件系统实时查询）"""
    # 1. 今日采集文章数 — 从 crawled_data 实时读取
    file_count = get_today_article_count()

    # 2. 从报告文件中批量读取统计（仅解析 frontmatter，高效）
    aggregated = report_storage.get_all_stats()
    total_chunks = aggregated["total_chunks"]
    total_numbers = aggregated["total_numbers"]
    total_verified = aggregated["verified_count"]
    report_count = report_storage.get_report_count()

    # 3. 最近一次报告的质检通过率
    latest_qc = 100.0
    ls = aggregated.get("latest_stats", {})
    ln = ls.get("total_numbers", 0)
    if ln > 0:
        latest_qc = round(ls.get("verified_count", 0) / ln * 100, 1)

    return {
        "file_count": file_count,
        "chunk_count": total_chunks,
        "qc_pass_rate": latest_qc,
        "report_count": report_count,
    }


def get_trend_data() -> dict:
    """
    获取近 7 日的采集量与研报产出趋势数据。
    - 采集量：从 crawled_data/*.json 按日期统计每天爬取的文章数
    - 产出量：从 reports/*.md 文件名提取日期，按天统计
    """
    from datetime import timedelta

    today = datetime.now()
    dates = []
    collection = []
    output = []

    # 1. 获取近 7 天每天的爬取文章数
    daily_counts = get_daily_article_counts(days=7)

    # 2. 直接扫描 reports/ 目录，从文件名提取日期统计
    #    文件名格式：YYYYMMDD_HHMMSS.md → 前 8 位为日期
    report_date_counts: dict[str, int] = {}
    for md_file in report_storage.REPORTS_DIR.glob("*.md"):
        stem = md_file.stem  # e.g. "20260622_202057"
        if len(stem) >= 8:
            date_str = stem[:8]  # "20260622"
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                day_key = dt.strftime("%Y-%m-%d")
                report_date_counts[day_key] = report_date_counts.get(day_key, 0) + 1
            except ValueError:
                continue

    # 3. 组装近 7 天数据
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_str = d.strftime("%Y-%m-%d")
        dates.append(d.strftime("%m-%d"))
        collection.append(daily_counts.get(day_str, 0))
        output.append(report_date_counts.get(day_str, 0))

    return {
        "dates": dates,
        "collection": collection,
        "output": output,
    }


# ── 后台流水线 ──────────────────────────────────────────────

def _set_agent_status(index: int, status: str, message: str = ""):
    with _lock:
        _pipeline_state["agents"][index]["status"] = status
        _pipeline_state["agents"][index]["message"] = message


def _append_log(msg: str):
    with _lock:
        ts = datetime.now().strftime("%H:%M:%S")
        _pipeline_state["logs"].append(f"[{ts}] {msg}")


def _set_progress(val: int):
    with _lock:
        _pipeline_state["progress"] = val


def _run_pipeline(file_paths: list[str], title: str, report_id: str,
                   use_crawled_data: bool = True, tags: str = ""):
    """在后台线程中依次运行 4 个智能体"""
    try:
        with _lock:
            _pipeline_state["phase"] = "running"
            _pipeline_state["report_id"] = report_id
            for a in _pipeline_state["agents"]:
                a["status"] = "pending"
                a["message"] = ""
            _pipeline_state["logs"] = []
            _pipeline_state["progress"] = 0

        # ── 标签过滤：如果用户选择了标签，先过滤爬取数据 ──
        tag_list = []
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                _append_log(f"🏷️ 已选择标签：{'、'.join(tag_list)}，将只处理相关领域数据")

        # ── 合并爬取数据 ──
        all_file_paths = list(file_paths)
        if use_crawled_data:
            if tag_list:
                # 有标签时：加载原始文章，按标签过滤后重新生成 txt
                from backend.services.data_bridge import save_crawled_as_txt
                extractor = TagExtractor()
                all_articles = get_latest_crawled_data(days=3)
                filtered_articles = extractor.filter_articles_by_tags(all_articles, tag_list)

                if len(filtered_articles) < 3:
                    _append_log(f"❌ 标签「{tags}」下数据不足（仅 {len(filtered_articles)} 篇），请调整标签选择")
                    with _lock:
                        _pipeline_state["phase"] = "error"
                    return

                # 将过滤后的文章保存为临时 txt 文件
                filtered_txt = save_crawled_as_txt(filtered_articles)
                all_file_paths.append(filtered_txt)
                _append_log(f"📰 标签过滤后保留 {len(filtered_articles)} 篇文章")
            else:
                crawled_txt_paths = get_crawled_data_as_file_paths(days=3)
                if crawled_txt_paths:
                    all_file_paths.extend(crawled_txt_paths)
                    _append_log(f"📰 加载 {len(crawled_txt_paths)} 个爬取数据文件，合并到数据源")

        if not all_file_paths:
            _append_log("❌ 没有可用数据源（未上传文件且无爬取数据）")
            with _lock:
                _pipeline_state["phase"] = "error"
            return

        # ── A: 采集官 ──
        _set_agent_status(0, "running", "正在解析文档、提取实体…")
        _append_log("📥 智能体A: 信息采集官 开始工作")
        t0 = time.time()

        collector = CollectorAgent()
        collector_output = collector.run(all_file_paths)

        elapsed = round(time.time() - t0, 1)
        chunk_count = len(collector_output["raw_chunks"])
        _set_agent_status(0, "done", f"完成 — 处理 {len(collector_output['file_names'])} 个文件，{chunk_count} 个片段（{elapsed}s）")
        _append_log(f"✅ 采集完成: {chunk_count} 个文档片段")
        _set_progress(25)

        # ── B: 情报官 ──
        _set_agent_status(1, "running", "正在检索长期记忆、分析趋势…")
        _append_log("🔍 智能体B: 竞品情报官 开始工作")
        t0 = time.time()

        analyst = AnalystAgent()
        analyst_output = analyst.run(collector_output)

        elapsed = round(time.time() - t0, 1)
        mem_count = len(analyst_output.get("memory_references", []))
        _set_agent_status(1, "done", f"完成 — 检索到 {mem_count} 条历史记忆（{elapsed}s）")
        _append_log(f"✅ 情报分析完成: 趋势数据已生成")
        _set_progress(50)

        # ── C: 写手官 ──
        _set_agent_status(2, "running", "正在撰写报告初稿…")
        _append_log("✍️ 智能体C: 报告写手官 开始工作")
        t0 = time.time()

        writer = WriterAgent()
        writer_output = writer.run(collector_output, analyst_output)

        elapsed = round(time.time() - t0, 1)
        _set_agent_status(2, "done", f"完成 — 报告初稿已生成（{elapsed}s）")
        _append_log("✅ 报告初稿生成完成")
        _set_progress(75)

        # ── D: 质检官 ──
        _set_agent_status(3, "running", "正在核查数据准确性…")
        _append_log("🔎 智能体D: 质检验收官 开始工作")
        t0 = time.time()

        reviewer = ReviewerAgent()
        reviewer_output = reviewer.run(writer_output, collector_output)

        elapsed = round(time.time() - t0, 1)
        vr = reviewer_output["verification_report"]
        _set_agent_status(3, "done",
                          f"完成 — {vr['total_numbers']} 条数据，{vr['verified_count']} 条已验证（{elapsed}s）")
        _append_log(f"✅ 质检完成: 通过率 {round(vr['verified_count'] / max(vr['total_numbers'], 1) * 100, 1)}%")
        _set_progress(100)

        # ── 持久化存储报告（Markdown 文件） ──
        report_stats = {
            "total_chunks": chunk_count,
            "total_numbers": vr["total_numbers"],
            "verified_count": vr["verified_count"],
            "missing_count": vr["missing_count"],
            "revision_count": reviewer_output["revision_count"],
        }
        saved_id = report_storage.save_report(
            markdown_content=reviewer_output["final_report"],
            title=title,
            trace=reviewer_output["sourcing_appendix"],
            stats=report_stats,
        )
        # 用实际保存的 ID 更新流水线状态（可能因同秒冲突而不同）
        with _lock:
            _pipeline_state["report_id"] = saved_id

        # 存入长期记忆
        try:
            store_report_memory(title, reviewer_output["final_report"],
                                collector_output["entities"],
                                reviewer_output["sourcing_appendix"])
        except Exception:
            pass

        with _lock:
            _pipeline_state["phase"] = "done"
        _append_log("🎉 报告生成完毕！")

    except Exception as e:
        with _lock:
            _pipeline_state["phase"] = "error"
        _append_log(f"❌ 流水线异常: {e}")
        # 标记当前 running 的 agent 为 error
        with _lock:
            for a in _pipeline_state["agents"]:
                if a["status"] == "running":
                    a["status"] = "error"
                    a["message"] = str(e)


def start_pipeline(file_paths: list[str], title: str | None = None,
                   use_crawled_data: bool = True, tags: str = "") -> str:
    """启动后台流水线，返回 report_id"""
    report_id = uuid.uuid4().hex[:12]

    # 如果用户选择了标签，自动在标题前加上标签前缀
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if not title:
        if tag_list:
            tag_prefix = "、".join(tag_list[:3])
            title = f"{tag_prefix}领域市场调研分析报告 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        else:
            title = f"市场调研报告 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    thread = threading.Thread(
        target=_run_pipeline,
        args=(file_paths, title, report_id, use_crawled_data, tags),
        daemon=True,
    )
    thread.start()
    return report_id
