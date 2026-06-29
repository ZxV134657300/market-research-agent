"""
================================================================================
AI 市场调研报告生成系统 (Multi-Agent AI Market Research Report System)
================================================================================

【系统架构设计思路】

本系统采用"流水线 + 质检闭环"的多智能体协作架构，由4个专职智能体组成：
  智能体A (信息采集官) → 智能体B (竞品情报官) → 智能体C (报告写手官) → 智能体D (质检验收官)
                                                                                  ↓
                                                                            修正循环 ←─┘

【数据流图】

  用户上传文件 (PDF/TXT)
        │
        ▼
  ┌─────────────────┐
  │  智能体A: 采集官  │  解析文档 → 提取实体 → 结构化JSON
  │  CollectorAgent   │  工具: parse_document(), extract_key_entities()
  └────────┬────────┘
           │ { entities, raw_chunks }
           ▼
  ┌─────────────────┐
  │  智能体B: 情报官  │  检索ChromaDB → 对比历史 → 计算趋势
  │  AnalystAgent     │  工具: search_vector_memory(), calculate_trend()
  └────────┬────────┘
           │ { trends, historical_context }
           ▼
  ┌─────────────────┐
  │  智能体C: 写手官  │  5章节结构 → 生成Markdown初稿
  │  WriterAgent      │  工具: generate_section(), render_markdown()
  └────────┬────────┘
           │ draft (Markdown字符串)
           ▼
  ┌─────────────────┐     ┌──────────────────┐
  │  智能体D: 质检官  │────▶│ 数字校验工具       │
  │  ReviewerAgent    │◀────│ validation_tools  │
  └────────┬────────┘     └──────────────────┘
           │ (若发现幻觉 → 返回写手官修正，最多2轮)
           ▼
     终版报告 + 数据溯源附录
           │
           ▼
     Streamlit 页面渲染展示

【关键设计原则】
1. 工具函数全部为纯Python本地函数，不依赖LLM
2. 智能体间通过TypedDict结构化数据传递，便于解耦测试
3. ChromaDB提供跨会话的长期记忆能力
4. 质检闭环确保报告零幻觉
================================================================================
"""

import os
import tempfile
import streamlit as st
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# 导入智能体
from agents.collector import CollectorAgent
from agents.analyst import AnalystAgent
from agents.writer import WriterAgent
from agents.reviewer import ReviewerAgent
from tools.memory_tools import add_to_memory


def save_uploaded_files(uploaded_files) -> list[str]:
    """将上传的文件保存到临时目录，返回文件路径列表"""
    temp_dir = tempfile.mkdtemp()
    file_paths = []
    for uploaded_file in uploaded_files:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        file_paths.append(file_path)
    return file_paths


def store_report_to_memory(report: str, entities: dict):
    """将报告关键信息存入 ChromaDB 长期记忆"""
    # 压缩关键信息为记忆片段
    brands = entities.get("brands", [])
    findings = entities.get("key_findings", [])

    memory_content = f"""市场调研报告摘要:
涉及品牌: {', '.join(brands[:5]) if brands else '未识别'}
关键发现: {'; '.join(findings[:3]) if findings else '未提取'}
报告前500字: {report[:500]}"""

    metadata = {
        "type": "market_research_report",
        "brands": ", ".join(brands[:5]) if brands else "unknown",
        "timestamp": str(os.environ.get("TIMESTAMP", "unknown")),
    }

    try:
        add_to_memory(memory_content, metadata)
    except Exception as e:
        st.warning(f"存储记忆失败（不影响报告生成）: {e}")


def main():
    st.set_page_config(
        page_title="AI 市场调研报告生成系统",
        page_icon="📊",
        layout="wide",
    )

    st.title("📊 AI 市场调研报告生成系统")
    st.markdown(
        "**基于多智能体协作的市场调研报告自动生成系统**\n\n"
        "上传市场资料（PDF/TXT），系统将通过4个智能体协作生成专业报告。"
    )

    # ========== 左侧边栏：文件上传 ==========
    with st.sidebar:
        st.header("📁 文件上传")
        uploaded_files = st.file_uploader(
            "选择市场资料文件",
            type=["txt", "pdf"],
            accept_multiple_files=True,
            help="支持 TXT 和 PDF 格式，可同时上传多个文件",
        )

        if uploaded_files:
            st.success(f"已上传 {len(uploaded_files)} 个文件：")
            for f in uploaded_files:
                st.write(f"  📄 {f.name} ({f.size / 1024:.1f} KB)")

        st.divider()
        st.header("ℹ️ 使用说明")
        st.markdown(
            "1. 上传市场资料文件\n"
            "2. 点击「开始生成报告」\n"
            "3. 等待4个智能体依次处理\n"
            "4. 查看生成的报告和数据溯源"
        )

        st.divider()
        st.header("⚙️ 系统配置")
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if api_key and api_key != "sk-your-api-key-here":
            st.success("✅ API Key 已配置")
        else:
            st.warning("⚠️ 请在 .env 文件中配置 DEEPSEEK_API_KEY")

    # ========== 主体区域 ==========
    if not uploaded_files:
        st.info("👈 请在左侧边栏上传市场资料文件后，点击下方按钮开始生成报告。")

        # 展示示例数据
        st.subheader("📋 演示数据说明")
        st.markdown(
            "本系统附带 3 个模拟数据文件，位于 `mock_data/` 目录：\n\n"
            "| 文件 | 内容 |\n"
            "|------|------|\n"
            "| `2024_smartphone_market.txt` | 2024年全球智能手机市场分析 |\n"
            "| `2025_ev_trends.txt` | 2025年新能源汽车趋势分析 |\n"
            "| `brand_feedback.txt` | 某品牌用户评论反馈汇总 |\n\n"
            "您可以上传这些文件来体验系统功能。"
        )
        return

    # ========== 报告生成按钮 ==========
    if st.button("🚀 开始生成报告", type="primary", use_container_width=True):
        file_paths = save_uploaded_files(uploaded_files)

        # 使用 st.status 显示4个智能体的执行状态
        with st.status("🤖 多智能体协作处理中...", expanded=True) as status:
            # ---- 智能体A：信息采集官 ----
            st.write("📥 **智能体A：信息采集官** 正在解析文档、提取实体...")
            collector = CollectorAgent()
            collector_output = collector.run(file_paths)
            st.write(
                f"  ✅ 已处理 {len(collector_output['file_names'])} 个文件，"
                f"提取到 {len(collector_output['raw_chunks'])} 个文档片段"
            )

            # ---- 智能体B：竞品情报官 ----
            st.write("🔍 **智能体B：竞品情报官** 正在检索长期记忆、分析趋势...")
            analyst = AnalystAgent()
            analyst_output = analyst.run(collector_output)
            mem_count = len(analyst_output.get("memory_references", []))
            st.write(f"  ✅ 趋势分析完成，检索到 {mem_count} 条历史记忆")

            # ---- 智能体C：报告写手官 ----
            st.write("✍️ **智能体C：报告写手官** 正在撰写报告初稿...")
            writer = WriterAgent()
            writer_output = writer.run(collector_output, analyst_output)
            st.write("  ✅ 报告初稿生成完成")

            # ---- 智能体D：质检验收官 ----
            st.write("🔎 **智能体D：质检验收官** 正在核查数据准确性...")
            reviewer = ReviewerAgent()
            reviewer_output = reviewer.run(writer_output, collector_output)
            vr = reviewer_output["verification_report"]
            st.write(
                f"  ✅ 质检完成：共 {vr['total_numbers']} 个数据引用，"
                f"{vr['verified_count']} 个已验证，"
                f"{vr['missing_count']} 个未找到来源，"
                f"修订 {reviewer_output['revision_count']} 次"
            )

            status.update(label="✅ 报告生成完成！", state="complete", expanded=False)

        # 存入长期记忆
        store_report_to_memory(
            reviewer_output["final_report"],
            collector_output["entities"],
        )

        # ========== 展示结果（报告正文 + 下载 + 溯源） ==========
        st.divider()
        st.markdown("## 📊 生成的调研报告")

        # 质检摘要指标
        col1, col2, col3 = st.columns(3)
        col1.metric("数据引用总数", vr["total_numbers"])
        col2.metric("已验证", vr["verified_count"])
        col3.metric("未找到来源", vr["missing_count"])

        # 报告正文（用 container 包裹，确保在主界面可视区域直接展示）
        with st.container():
            st.markdown(reviewer_output["final_report"], unsafe_allow_html=True)

        # 并排下载按钮：左边下载报告，右边下载溯源附录
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                label="📥 下载报告 (Markdown)",
                data=reviewer_output["final_report"],
                file_name="market_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with dl_col2:
            st.download_button(
                label="📎 下载溯源附录",
                data=reviewer_output["sourcing_appendix"],
                file_name="trace_appendix.txt",
                mime="text/plain",
                use_container_width=True,
            )

        # 数据溯源折叠面板（放在最底部，避免主报告过长）
        st.divider()
        with st.expander("📌 点击展开：数据溯源详情", expanded=False):
            st.markdown(reviewer_output["sourcing_appendix"])
            if vr["results"]:
                st.markdown("---")
                st.markdown("### 逐条验证详情")
                import pandas as pd
                df_data = []
                for r in vr["results"]:
                    df_data.append({
                        "数字": r["number"],
                        "验证状态": "✅ 已验证" if r["found"] else "❌ 未找到",
                        "匹配类型": r["match_type"],
                        "来源文件": r["source_file"] or "-",
                    })
                df = pd.DataFrame(df_data)
                st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    main()
