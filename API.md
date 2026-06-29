# AI 市场调研报告系统 - API 文档

**Base URL**: `http://localhost:8000`

## 端点列表

### 1. 上传文件

```
POST /api/upload
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | TXT 或 PDF 文件 |

**响应** `200 OK`
```json
{
  "file_id": "a1b2c3d4e5",
  "filename": "2024_smartphone_market.txt",
  "size": 3842,
  "message": "上传成功"
}
```

---

### 2. 触发报告生成

```
POST /api/generate
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_ids | string[] | 是 | 已上传文件的 ID 列表 |
| title | string | 否 | 报告标题，默认自动生成 |

**响应** `200 OK`
```json
{
  "report_id": "f6g7h8i9j0",
  "message": "流水线已启动，请轮询 /api/status 查看进度"
}
```

---

### 3. 查询流水线状态

```
GET /api/status
```

**响应** `200 OK`
```json
{
  "report_id": "f6g7h8i9j0",
  "phase": "running",
  "progress": 50,
  "agents": [
    {"name": "collector", "label": "信息采集官", "status": "done",    "message": "完成 — 3 个文件，12 个片段"},
    {"name": "analyst",   "label": "竞品情报官", "status": "running", "message": "正在检索长期记忆…"},
    {"name": "writer",    "label": "报告写手官", "status": "pending", "message": ""},
    {"name": "reviewer",  "label": "质检验收官", "status": "pending", "message": ""}
  ],
  "logs": ["[14:32:01] 📥 智能体A 开始工作", "[14:32:05] ✅ 采集完成"]
}
```

| phase 值 | 说明 |
|----------|------|
| idle | 空闲，未启动 |
| running | 正在执行 |
| done | 已完成 |
| error | 出错 |

| agent.status 值 | 说明 |
|-----------------|------|
| pending | 等待中 |
| running | 执行中 |
| done | 已完成 |
| error | 出错 |

---

### 4. 获取报告列表

```
GET /api/reports
```

**响应** `200 OK`
```json
[
  {
    "id": "f6g7h8i9j0",
    "title": "市场调研报告 2026-06-20 14:30",
    "created_at": "2026-06-20T14:32:15.123456",
    "agent_count": 4,
    "status": "done"
  }
]
```

---

### 5. 获取报告详情

```
GET /api/report/{report_id}
```

**响应** `200 OK`
```json
{
  "id": "f6g7h8i9j0",
  "title": "市场调研报告 2026-06-20 14:30",
  "created_at": "2026-06-20T14:32:15.123456",
  "markdown": "# 市场调研报告\n\n## 市场概况\n\n...",
  "trace": "## 数据溯源附录\n\n...",
  "stats": {
    "total_chunks": 12,
    "total_numbers": 45,
    "verified_count": 42,
    "missing_count": 3,
    "revision_count": 1
  }
}
```

---

### 6. 获取数据溯源

```
GET /api/trace/{report_id}
```

**响应** `200 OK`
```json
{
  "report_id": "f6g7h8i9j0",
  "trace": "## 数据溯源附录\n\n### 📄 2024_smartphone_market.txt\n..."
}
```

---

### 7. 仪表盘统计

```
GET /api/stats
```

**响应** `200 OK`
```json
{
  "file_count": 3,
  "chunk_count": 12,
  "qc_pass_rate": 93.3,
  "report_count": 2,
  "weekly_data": [
    {"date": "06-14", "count": 1},
    {"date": "06-15", "count": 0},
    {"date": "06-16", "count": 2},
    {"date": "06-17", "count": 1},
    {"date": "06-18", "count": 3},
    {"date": "06-19", "count": 0},
    {"date": "06-20", "count": 2}
  ]
}
```

---

## 前端页面路由（SPA Hash）

| 路由 | 页面 | 说明 |
|------|------|------|
| `#dashboard` | 工作台 | 统计卡片 + 趋势图表 |
| `#reports` | 报告中心 | 报告列表 + Markdown 预览 + 溯源 |
| `#workflow` | 工作流 | 4 个智能体管道进度 + 实时日志 |
| `#config` | 系统配置 | API Key + 文件上传 |

## 典型调用流程

```
1. POST /api/upload        × N（逐个上传文件）
2. POST /api/generate       （触发流水线）
3. GET  /api/status         × 每2秒轮询，直到 phase=done
4. GET  /api/report/{id}    （获取完整报告）
5. GET  /api/trace/{id}     （获取溯源附录）
```
