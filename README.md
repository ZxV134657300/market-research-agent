# 📊 AI 市场调研报告生成系统

> **Multi-Agent Market Research Report Generator**
>
> 基于多智能体协作的自动化市场调研报告生成系统

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Database-purple?logo=chromadb&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Completed-brightgreen)

---

## 📖 项目��

�系统通过 **4 � AI 智能�** 协同工作，结� **RSS 新闻�动采�** � **ChromaDB 长期记忆**，实现从数据采集到报告生成的全自动化流程。用户只�上传资料或开��动采集，系统即可产出带数��源�经过幻觉�测的专业市场分析报告�

**核心理念：流水线 + 质���**

```
用户上传文件 / RSS �动采�
        �
        �
  ┌─�������������
  � A · 信息采集� �  解析文档 � 提取实体 � 结构� JSON
  └─�������������
         �
  ┌─�������������
  � B · 竞品情报� �  �� ChromaDB � 对比历史 � 计算趋势
  └─�������������
         �
  ┌─�������������
  � C · 报告写手� �  5 章节结构 � 生成 Markdown 初�
  └─�������������
         �
  ┌─�������������     ┌─��������������
  � D · 质�验收� │─���▶│ 数字校验工具   �
  └─�������������     └─��������������
         � (幻� � 返回写手官修正，�� 2 �)
         �
   终版报告 + 数据�源附�
```

---

## � 核心功能

| 功能 | 说明 |
|------|------|
| 📡 **多源 RSS �动采�** | 定时抓取 36�、华尔��闻、同花顺� RSS 源，�动去重，按日存储 |
| � **4 智能体流水线** | 采集� � 情报� � 写手� � 质�验收官，全链��动化 |
| � **ChromaDB 长期记忆** | 跨会话存储历史报告，向量�索�强分析深度 |
| 🔍 **幻��测与��** | 质�验收官自动校验报告中每个数字，标记未找到来源的数� |
| 📊 **�视化�表盘** | 今日要闻 TOP5�7 日采集趋势图、质�通过率等指标卡片 |
| 📁 **报告��** | 历史报告列表、Markdown 实时预��数��源折叠面� |
| � **定时任务调度** | APScheduler 每天 08:00 �动抓取，�动时立即执�一� |
| 🔄 **熔断机制** | RSS 源连�失败 3 次自动跳过，避免阻�整�流程 |

---

## 🏗� 系统架构

```mermaid
graph TB
    subgraph 数据�
        RSS1[36氪]
        RSS2[华尔街�闻]
        RSS3[同花顺]
        UP[用户上传 PDF/TXT]
    end

    subgraph 后�服务
        CRAWLER[news_crawler.py<br/>RSS �� + 去重]
        BRIDGE[data_bridge.py<br/>数据格式桥接]
        API[FastAPI �由层]
        SVC[agent_service.py<br/>流水线调�]
    end

    subgraph 智能体流水线
        A[📥 信息采集�<br/>CollectorAgent]
        B[🔍 竞品情报�<br/>AnalystAgent]
        C[✍️ 报告写手�<br/>WriterAgent]
        D[🔎 质�验收�<br/>ReviewerAgent]
    end

    subgraph 存储
        CD[(crawled_data/)]
        DB[(ChromaDB)]
        FS[(uploads/)]
    end

    subgraph 前�
        FE[SPA �表盘<br/>HTML + CSS + JS]
    end

    RSS1 & RSS2 & RSS3 --> CRAWLER
    CRAWLER -->|JSON| CD
    CD -->|txt| BRIDGE
    UP --> FS
    BRIDGE & FS --> API
    API --> SVC
    SVC --> A --> B --> C --> D
    D -->|幻�修�| C
    D -->|终版报告| FE
    B <-->|向量��| DB
    D -->|存储记忆| DB
```

---

## 🛠� ���

| 层级 | �� | 用� |
|------|------|------|
| **后�框架** | FastAPI + Uvicorn | REST API 服务 |
| **AI 模型** | DeepSeek API（兼� OpenAI SDK� | 实体提取、趋势分析�报告生� |
| **向量数据�** | ChromaDB + onnxruntime | 长期记忆、�义�� |
| **RSS ��** | feedparser | 新闻/研报�动采� |
| **定时调度** | APScheduler | 每日定时抓取任务 |
| **PDF 解析** | pypdf | 上传文件文本提取 |
| **前�** | HTML + CSS + JavaScript | 原生 SPA，无框架依赖 |
| **图表** | Chart.js | 趋势折线� |
| **Markdown** | marked.js | 报告实时渲染 |

---

## 🚀 �速启�

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd market_research_agent
```

### 2. 安�依�

```bash
pip install -r requirements.txt
```

### 3. 配置�境变�

在项�根目录创� `.env` 文件�

```env
DEEPSEEK_API_KEY=sk-your-api-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### 4. �动服�

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 访问系统

打开浏�器访问�**http://localhost:8000**

> 💡 �动后系统会自动执行一� RSS 新闻抓取，并注册每天 08:00 的定时任务�

---

## 📂 项目结构

```
market_research_agent/
�
├─� backend/                        # 后�服务
�   ├─� main.py                     # FastAPI 入口 + 生命周期管理
�   ├─� api/
�   �   ├─� routes.py               # RESTful �由定�
�   �   └─� models.py               # Pydantic 数据模型
�   └─� services/
�       ├─� agent_service.py        # 智能体流水线调度
�       ├─� memory_service.py       # ChromaDB 记忆服务
�       ├─� news_crawler.py         # RSS ��（去� + 熔断�
�       └─� data_bridge.py          # ��数据 � 智能体格式桥�
�
├─� frontend/                       # 前� SPA
�   ├─� index.html                  # 主页�（含内联 SVG favicon�
�   ├─� css/
�   �   └─� style.css               # 全局样式（主色调 #4A6CF7�
�   └─� js/
�       ├─� app.js                  # �由切� + API 调用 + ��
�       └─� dashboard.js            # �表盘图表 + 面板渲染
�
├─� agents/                         # 智能体实�
�   ├─� collector.py                # 信息采集�
�   ├─� analyst.py                  # 竞品情报�
�   ├─� writer.py                   # 报告写手�
�   ├─� reviewer.py                 # 质�验收�
�   └─� llm_client.py              # LLM API 调用封�
�
├─� tools/                          # 工具函数
�   ├─� file_parser.py              # PDF/TXT 文档解析
�   ├─� memory_tools.py             # ChromaDB 存取工具
�   └─� validation_tools.py         # 数字校验工具
�
├─� crawled_data/                   # ��数据（自动生成）
�   ├─� YYYY-MM-DD.json             # 当日原�文�
�   ├─� YYYY-MM-DD.txt              # �换后的智能体�用格�
�   └─� seen_hashes.json            # 去重哈希记录
�
├─� memory_db/                      # ChromaDB 持久化目�
├─� uploads/                        # 用户上传文件
├─� mock_data/                      # 演示用数�
�   ├─� 2024_smartphone_market.txt
�   ├─� 2025_ev_trends.txt
�   └─� brand_feedback.txt
�
├─� app.py                          # Streamlit 旧版入口（保留）
├─� API.md                          # API 接口文档
├─� requirements.txt                # Python 依赖清单
├─� .env                            # �境变量（不提交到 Git�
└─� README.md                       # �文件
```

---

## 📡 API ��

### 文件与报�

| 方法 | �� | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传文件（TXT/PDF），返回 `file_id` |
| `POST` | `/api/generate` | 触发报告生成（支� `use_crawled_data` 参数� |
| `GET` | `/api/status` | 查�流水线执�状态（前�� 5 秒轮�� |
| `GET` | `/api/reports` | 获取�有报告摘要列� |
| `GET` | `/api/report/{id}` | 获取报告详情（Markdown + �源） |
| `GET` | `/api/trace/{id}` | 获取数据�源附� |

### �表盘

| 方法 | �� | 说明 |
|------|------|------|
| `GET` | `/api/stats` | 统�指标（今日采集、报告数、质�率等� |
| `GET` | `/api/trend` | � 7 日采集量与研报产出趋� |
| `GET` | `/api/news/top5` | 今日要闻 TOP5（从�取数�读取� |

### ��

| 方法 | �� | 说明 |
|------|------|------|
| `POST` | `/api/crawl` | 手动触发�次新闻爬� |
| `GET` | `/api/crawl/status` | 查�最近一次爬取状� |

### 其他

| 方法 | �� | 说明 |
|------|------|------|
| `GET` | `/` | 前� SPA 主页� |
| `GET` | `/health` | 健康�� |

---

## 🖥� 效果预�

### 工作台仪表盘

```
┌─���������������������������������������������������������
�  📥 今日采集   📄 �计报�   � 质�通过�   ⚙️ 处理片�  �
�     98 �         3 �         93.3%          156       �
├─���������������������������������������������������������
�  📈 � 7 日采集与产出趋势                                 �
�  ����������������������������������������               �
�  �  ╱╲    采集� ���  研报产出 ���       �               �
�  � �  �        ╱╲                        �               �
�  │╱    ╲─������  ╲─�����                 �               �
�  ╰─��������������������������������������               �
├─���������������������������������������������������������
� 📰 今日要闻 TOP5       � 📊 �新研�                    �
� �1 标�...    36�     � 📊 市场调研报告 2026-06-21      �
� �2 标�...    华尔�   �   已发�                        �
� �3 标�...    同花�   � 📊 智能手机分析 2026-06-20      �
� �4 标�...    36�     �   已发�                        �
� �5 标�...    华尔�   �                                �
└─�����������������������┴─��������������������������������
```

### 工作流�道

```
   ┌─���      ┌─���      ┌─���      ┌─���
   � A � ���� � B � ���� � C � ���� � D �
   └─���      └─���      └─���      └─���
  采集�     情报�      写手�     质��
   � done    � done    � done    � done

  ████████████████████████████████████ 100%

  [10:42:11] 📥 智能体A: 信息采集� �始工�
  [10:42:15] � 采集完成: 156 �文档片�
  [10:42:20] 🔍 智能体B: 竞品情报� �始工�
  [10:42:25] � 情报分析完成: 趋势数据已生�
  [10:43:01] ✍️ 智能体C: 报告写手� �始工�
  [10:43:30] � 报告初�生成完�
  [10:43:35] 🔎 智能体D: 质�验收� �始工�
  [10:43:45] � 质�完成: 通过� 93.3%
  [10:43:46] 🎉 报告生成完毕�
```

---

## 🔧 配置说明

### RSS 源配�

� `backend/services/news_crawler.py` ��� `RSS_SOURCES` 列表�

```python
RSS_SOURCES = [
    {"name": "36�",     "url": "https://36kr.com/feed", "category": "科技创投"},
    {"name": "华尔街�闻", "url": "https://rsshub.rssforever.com/wallstreetcn/news/global", "category": "财经要闻"},
    {"name": "同花�",    "url": "https://rsshub.rssforever.com/10jqka/realtimenews", "category": "实时行情"},
]
```

> 💡 部分源�过 [RSSHub](https://github.com/DIYgod/RSSHub) 代理，可�行搭建�有实例以提高稳定��

### 定时任务

� `backend/main.py` ��改抓取时间：

```python
# 每天早上 8:00 �动抓�
scheduler.add_job(crawl_all, trigger=CronTrigger(hour=8, minute=0), ...)
```

### 智能体提示词

各智能体的系统提示词位于 `agents/` �录下对应� `.py` 文件�� `SYSTEM_PROMPT` 常量�

---

## 🗺� 后续规划

- [ ] 报告导出� PDF 格式
- [ ] 用户认证与��户��
- [ ] 更� RSS 源接入（财新、东方财富等�
- [ ] 报告模板�定义（�业模板库）
- [ ] Docker 容器化部�
- [ ] 实时 WebSocket 推�（替代���
- [ ] 多���持（英文报告生成�

---

## 📄 许可�

�项目基于 [MIT License](LICENSE) �源�

---

<p align="center">
  Built with ❤️ by Multi-Agent Team
</p>
