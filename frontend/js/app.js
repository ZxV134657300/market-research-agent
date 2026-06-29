/**
 * app.js - SPA 路由切换、API 调用、轮询逻辑
 *
 * 核心改动：
 * - 仪表盘视图：不轮询，仅页面加载时调用 /api/stats + /api/trend 各一次
 * - 工作流视图：5 秒轮询 /api/status
 * - 离开仪表盘时调用 Dashboard.destroy() 释放 Chart 实例
 * - 进入仪表盘时调用 Dashboard.renderTrendChart() 初始化图表
 */

const API = '/api';

const App = {
  uploadedFileIds: [],
  currentReportId: null,
  _pollTimer: null,
  _dashboardLoaded: false,
  _currentPage: 'dashboard',
  _selectedTags: [],
  _availableTags: [],
  _countTimer: null,

  // ── 初始化 ──────────────────────────────────────────────
  init() {
    this.bindNav();
    this.bindUpload();
    this.bindCrawledToggle();
    this.bindSubPanelKeys();
    this._updateGenerateBtn();          // 立即根据开关状态启用/禁用按钮
    const hash = location.hash.replace('#', '') || 'dashboard';
    this.navigate(hash);
  },

  // ── SPA 路由 ────────────────────────────────────────────
  bindNav() {
    document.querySelectorAll('.nav-item').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault();
        this.navigate(el.dataset.page);
      });
    });
  },

  navigate(page) {
    const prevPage = this._currentPage;
    this._currentPage = page;

    // 切换 nav 高亮
    document.querySelectorAll('.nav-item').forEach(el =>
      el.classList.toggle('active', el.dataset.page === page));
    // 切换页面
    document.querySelectorAll('.page').forEach(el =>
      el.classList.toggle('active', el.id === `page-${page}`));
    location.hash = page;

    // ── 离开仪表盘：销毁 Chart，停止不必要的轮询 ──
    if (prevPage === 'dashboard' && page !== 'dashboard') {
      Dashboard.destroy();
    }

    // ── 进入仪表盘：加载静态数据 + 趋势图 ──
    if (page === 'dashboard') {
      this._loadDashboardOnce();
    }

    // ── 进入报告中心：加载列表，隐藏下载按钮 ──
    if (page === 'reports') {
      const dlBtn = document.getElementById('btn-download-report');
      if (dlBtn) dlBtn.style.display = 'none';
      this.currentReportId = null;
      this.refreshReports();
    }

    // ── 离开工作流：停止轮询（非工作流页面不需要状态轮询） ──
    if (page !== 'workflow' && this._pollTimer) {
      this.stopPolling();
    }

    // ── 进入报告生成：加载标签和采集数据状态 ──
    if (page === 'generate') {
      this.loadCrawledCount();
      this.loadSubCountHint();
      if (this._availableTags.length === 0) {
        this.loadTags();
      }
    }
  },

  // ── Dashboard ───────────────────────────────────────────

  /** 仪表盘只在首次进入时加载，后续进入除非显式刷新 */
  _loadDashboardOnce() {
    if (this._dashboardLoaded) return;
    this._dashboardLoaded = true;
    this._fetchDashboardData();
  },

  /** 手动刷新仪表盘（点击刷新按钮时调用） */
  refreshDashboard() {
    this._dashboardLoaded = false;
    this._loadDashboardOnce();
  },

  /** 并行拉取 stats + trend + reports，一次完成仪表盘渲染 */
  async _fetchDashboardData() {
    // 显示骨架屏
    Dashboard.showSkeletonStats();

    try {
      const [statsRes, trendRes, reportsRes] = await Promise.all([
        fetch(`${API}/stats`),
        fetch(`${API}/trend`),
        fetch(`${API}/reports`),
      ]);

      const stats   = await statsRes.json();
      const trend   = await trendRes.json();
      const reports = await reportsRes.json();

      // 顶部指标（带计数动画）
      Dashboard.updateStats(stats);

      // 趋势图
      Dashboard.renderTrendChart(trend);

      // 今日要闻（独立 API）+ 最新研报
      Dashboard.renderNewsList();
      Dashboard.renderRecentReports(reports);
    } catch (e) {
      console.error('加载仪表盘失败:', e);
      Dashboard.toast.error('仪表盘数据加载失败，请刷新重试');
    }
  },

  // ── 报告中心 ────────────────────────────────────────────
  async refreshReports() {
    try {
      const res = await fetch(`${API}/reports`);
      const list = await res.json();
      Dashboard.renderReportList(list, this.currentReportId);
    } catch (e) {
      console.error('刷新报告列表失败:', e);
      Dashboard.toast.error('刷新报告列表失败');
    }
  },

  async viewReport(id) {
    this.currentReportId = id;

    try {
      const res = await fetch(`${API}/report/${id}`);
      const data = await res.json();
      document.getElementById('preview-title').textContent = data.title;
      document.getElementById('report-content').innerHTML = marked.parse(data.markdown);

      // 显示下载按钮
      const dlBtn = document.getElementById('btn-download-report');
      if (dlBtn) dlBtn.style.display = '';

      const traceSection = document.getElementById('trace-section');
      const traceContent = document.getElementById('trace-content');
      if (data.trace) {
        traceSection.style.display = 'block';
        traceContent.style.display = 'none';
        traceContent.innerHTML = marked.parse(data.trace);
      } else {
        traceSection.style.display = 'none';
      }

      this.refreshReports();
    } catch (e) {
      console.error('加载报告失败:', e);
    }
  },

  // ── 下载报告 ────────────────────────────────────────────
  downloadReport() {
    if (!this.currentReportId) return;
    window.open(`${API}/report/${this.currentReportId}/download`, '_blank');
  },

  toggleTrace() {
    const el = document.getElementById('trace-content');
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
  },

  // ── 文件上传 ────────────────────────────────────────────
  bindUpload() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    ['dragenter', 'dragover'].forEach(evt =>
      dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.add('drag-over'); }));
    ['dragleave', 'drop'].forEach(evt =>
      dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.remove('drag-over'); }));

    dropZone.addEventListener('drop', e => this.handleFiles(e.dataTransfer.files));
    fileInput.addEventListener('change', e => this.handleFiles(e.target.files));
  },

  async handleFiles(fileList) {
    for (const file of fileList) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch(`${API}/upload`, { method: 'POST', body: formData });
        const data = await res.json();
        this.uploadedFileIds.push(data.file_id);
        this.addUploadItem(file.name, data.file_id, data.size);
        Dashboard.toast.success(`"${file.name}" 上传成功`);
      } catch (e) {
        console.error('上传失败:', e);
        Dashboard.toast.error(`"${file.name}" 上传失败`);
      }
    }
    this._updateGenerateBtn();
  },

  // ── 自动采集数据开关 ────────────────────────────────────
  bindCrawledToggle() {
    const cb = document.getElementById('cfg-use-crawled');
    if (cb) cb.addEventListener('change', () => this._updateGenerateBtn());
  },

  /** 加载订阅源数量提示（页面进入时调用） */
  async loadSubCountHint() {
    const hint = document.getElementById('sub-count-hint');
    if (!hint) return;
    try {
      const res = await fetch(`${API}/subscriptions`);
      if (!res.ok) return;
      const subs = await res.json();
      const enabled = subs.filter(s => s.enabled !== false).length;
      hint.textContent = subs.length > 0 ? `${enabled} 个源已启用` : '';
    } catch (e) {
      // 静默失败
    }
  },

  /** 拉取今日爬取文章数，更新开关旁边的提示（不影响按钮状态） */
  async loadCrawledCount() {
    const hint = document.getElementById('crawled-count-hint');
    try {
      const res = await fetch(`${API}/crawl/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const count = data.new_articles || data.total_articles || 0;
      if (count > 0) {
        hint.textContent = `已有 ${count} 篇可用`;
        hint.classList.add('active');
      } else {
        hint.textContent = '暂无采集数据';
        hint.classList.remove('active');
      }
    } catch (e) {
      console.error('获取爬取状态失败:', e);
      hint.textContent = '暂无采集数据';
      hint.classList.remove('active');
    }
  },

  // ── 标签选择 ──────────────────────────────────────────────

  /** 从后端加载可用标签列表 */
  async loadTags() {
    const tagList = document.getElementById('tag-list');
    try {
      const res = await fetch(`${API}/tags`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this._availableTags = data.tags || [];

      if (this._availableTags.length === 0) {
        tagList.innerHTML = '<div class="tag-empty">暂无可用标签，请等待数据采集</div>';
        return;
      }

      tagList.innerHTML = this._availableTags.map(tag =>
        `<button class="tag-btn" data-tag="${this._escapeHtml(tag)}" onclick="App.toggleTag('${this._escapeHtml(tag)}')">${this._escapeHtml(tag)}</button>`
      ).join('');
    } catch (e) {
      console.error('加载标签失败:', e);
      tagList.innerHTML = '<div class="tag-empty">暂无可用标签，请等待数据采集</div>';
    }
  },

  /** 切换标签选中状态 */
  toggleTag(tag) {
    const idx = this._selectedTags.indexOf(tag);
    if (idx >= 0) {
      this._selectedTags.splice(idx, 1);
    } else {
      this._selectedTags.push(tag);
    }

    // 更新按钮样式
    document.querySelectorAll('.tag-btn').forEach(btn => {
      const btnTag = btn.dataset.tag;
      btn.classList.toggle('active', this._selectedTags.includes(btnTag));
    });

    // 更新已选标签信息
    this._updateTagInfo();
    this._updateGenerateBtn();

    // 防抖：延迟请求文章数量
    if (this._countTimer) clearTimeout(this._countTimer);
    this._countTimer = setTimeout(() => this._countArticlesByTags(), 300);
  },

  /** 更新已选标签信息显示 */
  _updateTagInfo() {
    const infoEl = document.getElementById('tag-info');
    const selectedEl = document.getElementById('tag-selected');
    const countEl = document.getElementById('tag-article-count');

    if (this._selectedTags.length === 0) {
      infoEl.style.display = 'none';
      return;
    }

    infoEl.style.display = 'flex';
    selectedEl.textContent = '已选择：' + this._selectedTags.join('、');
    countEl.textContent = '查询中…';
  },

  /** 根据选中标签统计匹配文章数量 */
  async _countArticlesByTags() {
    const countEl = document.getElementById('tag-article-count');

    if (this._selectedTags.length === 0) {
      countEl.textContent = '';
      return;
    }

    try {
      const tagsParam = encodeURIComponent(this._selectedTags.join(','));
      const res = await fetch(`${API}/articles/count?tags=${tagsParam}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      countEl.textContent = `当前标签下可用文章：${data.count} 篇`;
    } catch (e) {
      console.error('统计文章数量失败:', e);
      countEl.textContent = '';
    }
  },

  /** HTML 转义 */
  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  /** 根据「有无上传文件」+「开关状态」决定按钮是否可用 */
  _updateGenerateBtn() {
    const btn = document.getElementById('btn-generate');
    const useCrawled = document.getElementById('cfg-use-crawled')?.checked;
    const hasFiles = this.uploadedFileIds.length > 0;
    btn.disabled = !(hasFiles || useCrawled);

    // 更新按钮文案
    if (this._selectedTags.length > 0) {
      const tagLabel = this._selectedTags.slice(0, 2).join(' + ');
      const suffix = this._selectedTags.length > 2 ? '…' : '';
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        开始生成报告（${tagLabel}${suffix}）
      `;
    } else {
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        开始生成报告
      `;
    }
  },

  addUploadItem(name, id, size) {
    const list = document.getElementById('upload-list');
    const li = document.createElement('li');
    li.innerHTML = `
      <span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6B7280" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:4px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        ${name} <span style="color:#94A3B8;font-size:11px">(${(size / 1024).toFixed(1)} KB)</span>
      </span>
      <button class="remove-btn" onclick="App.removeUpload('${id}', this)" aria-label="移除文件">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    `;
    list.appendChild(li);
  },

  removeUpload(id, btn) {
    this.uploadedFileIds = this.uploadedFileIds.filter(fid => fid !== id);
    btn.closest('li').remove();
    this._updateGenerateBtn();
  },

  // ── 报告生成 + 轮询 ─────────────────────────────────────
  async startGenerate() {
    const useCrawled = document.getElementById('cfg-use-crawled')?.checked;
    const hasFiles = this.uploadedFileIds.length > 0;

    // 既没上传文件，也没开爬取数据
    if (!hasFiles && !useCrawled) return;

    // ── 清空日志容器 ──
    const logBox = document.getElementById('log-box');
    if (logBox) logBox.innerHTML = '';

    // ── 重置进度条 ──
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    if (progressBar) progressBar.style.width = '0%';
    if (progressText) progressText.textContent = '0%';

    // ── 重置所有步骤状态 ──
    const names = ['collector', 'analyst', 'writer', 'reviewer'];
    names.forEach(name => {
      const stepEl = document.getElementById(`step-${name}`);
      const msgEl = document.getElementById(`step-msg-${name}`);
      if (stepEl) stepEl.className = 'step pending';
      if (msgEl) msgEl.textContent = '等待中';
    });

    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
      生成中…
    `;

    try {
      const res = await fetch(`${API}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: this.uploadedFileIds,
          use_crawled_data: useCrawled,
          tags: this._selectedTags.join(','),
        }),
      });
      const data = await res.json();

      Dashboard.toast.info('报告生成已启动，请等待完成…');

      // 离开仪表盘时销毁图表
      Dashboard.destroy();
      this._dashboardLoaded = false;

      this.navigate('workflow');
      this.startPolling();
    } catch (e) {
      console.error('触发生成失败:', e);
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        开始生成报告
      `;
      Dashboard.toast.error('触发报告生成失败，请重试');
      this._updateGenerateBtn();  // 恢复按钮文案
    }
  },

  startPolling() {
    if (this._pollTimer) clearInterval(this._pollTimer);
    this._pollTimer = setInterval(() => this.pollStatus(), 5000);
    this.pollStatus();
  },

  stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  },

  async pollStatus() {
    try {
      const res = await fetch(`${API}/status`);
      const state = await res.json();

      // 只更新工作流页面的 DOM
      const names = ['collector', 'analyst', 'writer', 'reviewer'];
      names.forEach(name => {
        const agent = state.agents.find(a => a.name === name);
        const stepEl = document.getElementById(`step-${name}`);
        const msgEl  = document.getElementById(`step-msg-${name}`);
        if (!agent || !stepEl) return;

        stepEl.className = 'step ' + agent.status;
        msgEl.textContent = agent.message || this.statusLabel(agent.status);
      });

      document.getElementById('progress-bar').style.width = state.progress + '%';
      document.getElementById('progress-text').textContent = state.progress + '%';

      // 日志增量追加
      const logBox = document.getElementById('log-box');
      const currentCount = logBox.children.length;
      if (state.logs.length > currentCount) {
        const newLines = state.logs.slice(currentCount);
        newLines.forEach(line => {
          const humanized = this._humanizeLog(line); // [幽默日志] 转换为口语化文案
          const div = document.createElement('div');
          div.className = 'log-line';
          if (humanized.includes('✅') || humanized.includes('🎉')) div.className += ' success';
          else if (humanized.includes('❌')) div.className += ' error';
          else if (humanized.includes('🚀') || humanized.includes('🕵️') || humanized.includes('☕') || humanized.includes('🔬') || humanized.includes('📦') || humanized.includes('🔍') || humanized.includes('📈') || humanized.includes('😎') || humanized.includes('📄')) div.className += ' info';
          div.textContent = humanized;
          logBox.appendChild(div);
        });
        logBox.scrollTop = logBox.scrollHeight;
      }

      if (state.phase === 'done' || state.phase === 'error') {
        this.stopPolling();
        this._updateGenerateBtn();  // 恢复按钮文案（含标签信息）

        if (state.phase === 'done') {
          Dashboard.toast.success('报告生成完成！');
          // 标记仪表盘需要刷新
          this._dashboardLoaded = false;
          setTimeout(() => {
            this.navigate('reports');
            this.refreshReports();
            if (state.report_id) this.viewReport(state.report_id);
          }, 1000);
        } else {
          Dashboard.toast.error('报告生成失败，请检查日志');
        }
      }
    } catch (e) {
      console.error('轮询状态失败:', e);
    }
  },

  statusLabel(status) {
    return { pending: '等待中', running: '执行中…', done: '已完成', error: '出错' }[status] || status;
  },

  // [幽默日志] 将后端日志转换为带人设的口语化文案
  _humanizeLog(line) {
    // 提取时间戳前缀（如有），替换后保留
    const tsMatch = line.match(/^(\[\d{2}:\d{2}:\d{2}\]\s*)/);
    const ts = tsMatch ? tsMatch[1] : '';
    const body = tsMatch ? line.slice(tsMatch[0].length) : line;

    // 匹配并替换
    // "等待流水线启动..."
    if (body.includes('等待流水线启动')) {
      return ts + '😎 准备就绪，随时开干！';
    }
    // "标签过滤后保留 X 篇文章"
    let m = body.match(/标签过滤后保留\s*(\d+)\s*篇文章/);
    if (m) {
      return ts + `🔍 筛掉一堆废话，留下 ${m[1]} 篇真货`;
    }
    // "智能体A: 信息采集官 开始工作" (📥)
    if (body.includes('智能体A') && body.includes('信息采集官') && body.includes('开始工作')) {
      return ts + '🚀 派遣特工"信息采集官"潜入互联网...';
    }
    // "采集完成: X 个文档片段"
    m = body.match(/采集完成[：:]\s*(\d+)\s*个文档片段/);
    if (m) {
      return ts + `📦 捡了 ${m[1]} 篇宝藏文章，准备开搞~`;
    }
    // "智能体B: 竞品情报官 开始工作" (🔍)
    if (body.includes('智能体B') && body.includes('竞品情报官') && body.includes('开始工作')) {
      return ts + '🕵️ 情报官上线，正在翻对手的老底...';
    }
    // "情报分析完成: 趋势数据已生成"
    if (body.includes('情报分析完成') && body.includes('趋势数据已生成')) {
      return ts + '📈 发现趋势！这个赛道有搞头（或没救了）';
    }
    // "智能体C: 报告写手官 开始工作" (✍️)
    if (body.includes('智能体C') && body.includes('报告写手官') && body.includes('开始工作')) {
      return ts + '☕ 写手官喝了口咖啡，开始编报告...';
    }
    // "报告初稿生成完成"
    if (body.includes('报告初稿生成完成')) {
      return ts + '📄 第一版报告出炉，感觉能拿去卖了';
    }
    // "智能体D: 质检验收官 开始工作" (🔎)
    if (body.includes('智能体D') && body.includes('质检验收官') && body.includes('开始工作')) {
      return ts + '🔬 质检官拿着放大镜找茬中...';
    }
    // "质检完成: 通过率 X%"
    m = body.match(/质检完成[：:]\s*通过率\s*([\d.]+)%/);
    if (m) {
      return ts + `✅ 质检过啦！通过率 ${m[1]}%，算你厉害`;
    }
    // "报告生成完毕！"
    if (body.includes('报告生成完毕')) {
      return ts + '🎉 恭喜老板！报告新鲜出炉！';
    }
    // 未匹配的原样返回
    return line;
  },

  // ── 订阅源管理 ────────────────────────────────────────────

  /** 打开订阅源管理面板 */
  openSubPanel() {
    const overlay = document.getElementById('subOverlay');
    overlay.style.display = 'flex';
    this.loadSubscriptions();
  },

  /** 关闭订阅源管理面板 */
  closeSubPanel() {
    const overlay = document.getElementById('subOverlay');
    overlay.style.display = 'none';
  },

  /** 绑定 ESC 键关闭面板 */
  bindSubPanelKeys() {
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') this.closeSubPanel();
    });
  },

  /** 加载订阅源列表并渲染 */
  async loadSubscriptions() {
    const listEl = document.getElementById('subList');
    listEl.innerHTML = '<div class="sub-loading">加载中…</div>';

    try {
      const res = await fetch(`${API}/subscriptions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const subs = await res.json();

      // 更新订阅源数量提示
      this._updateSubCountHint(subs.length);

      if (subs.length === 0) {
        listEl.innerHTML = '<div class="sub-empty">暂无订阅源，请添加 RSS 地址</div>';
        return;
      }

      listEl.innerHTML = subs.map(sub => this._renderSubItem(sub)).join('');
    } catch (e) {
      console.error('加载订阅源失败:', e);
      listEl.innerHTML = '<div class="sub-empty">加载失败，请重试</div>';
    }
  },

  /** 渲染单个订阅源项 */
  _renderSubItem(sub) {
    const enabled = sub.enabled !== false;
    const subType = sub.type || 'rss';
    const typeLabel = subType === 'firecrawl'
      ? '<span class="sub-type-badge firecrawl">AI爬虫</span>'
      : '<span class="sub-type-badge rss">RSS</span>';

    return `
      <div class="sub-item ${enabled ? '' : 'disabled'}" data-id="${sub.id}">
        <div class="sub-item-info">
          <div class="sub-item-name">${this._escapeHtml(sub.name)} ${typeLabel}</div>
          <div class="sub-item-url">${this._escapeHtml(sub.url)}</div>
          ${sub.category ? `<span class="sub-item-tag">${this._escapeHtml(sub.category)}</span>` : ''}
        </div>
        <div class="sub-item-actions">
          <button class="sub-toggle-btn ${enabled ? 'active' : ''}"
                  onclick="App.toggleSubscription('${sub.id}')"
                  title="${enabled ? '点击禁用' : '点击启用'}">
            ${enabled ? '已启用' : '已禁用'}
          </button>
          <button class="sub-delete-btn" onclick="App.deleteSubscription('${sub.id}')" title="删除">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
      </div>
    `;
  },

  /** [Firecrawl] 切换订阅源类型时更新 placeholder */
  onSubTypeChange() {
    const typeEl = document.getElementById('subType');
    const urlEl = document.getElementById('subUrl');
    if (typeEl.value === 'firecrawl') {
      urlEl.placeholder = '新闻列表页 URL（如：https://finance.sina.com.cn/roll/）';
    } else {
      urlEl.placeholder = 'RSSHub 地址（如：http://localhost:1200/...）';
    }
  },

  /** 更新订阅源数量提示 */
  _updateSubCountHint(count) {
    const hint = document.getElementById('sub-count-hint');
    if (hint) {
      hint.textContent = count > 0 ? `共 ${count} 个订阅源` : '';
    }
  },

  /** 添加订阅源 */
  async addSubscription() {
    const nameEl = document.getElementById('subName');
    const urlEl = document.getElementById('subUrl');
    const categoryEl = document.getElementById('subCategory');
    const typeEl = document.getElementById('subType');  // [Firecrawl] 新增

    const name = nameEl.value.trim();
    const url = urlEl.value.trim();
    const category = categoryEl.value.trim() || '自定义';
    const sourceType = typeEl ? typeEl.value : 'rss';  // [Firecrawl] 新增

    if (!name) {
      Dashboard.toast.warning('请输入订阅源名称');
      nameEl.focus();
      return;
    }
    if (!url) {
      Dashboard.toast.warning('请输入订阅源地址');
      urlEl.focus();
      return;
    }

    const btn = document.getElementById('addSubBtn');
    btn.disabled = true;
    btn.textContent = '添加中…';

    try {
      const res = await fetch(`${API}/subscriptions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, url, category, type: sourceType }),  // [Firecrawl] 新增 type
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || '添加失败');
      }

      const typeLabel = sourceType === 'firecrawl' ? 'AI爬虫' : 'RSS';
      Dashboard.toast.success(`已添加${typeLabel}订阅源: ${name}`);
      nameEl.value = '';
      urlEl.value = '';
      categoryEl.value = '';
      this.loadSubscriptions();
    } catch (e) {
      console.error('添加订阅源失败:', e);
      Dashboard.toast.error(e.message || '添加失败');
    } finally {
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        添加
      `;
    }
  },

  /** 删除订阅源 */
  async deleteSubscription(id) {
    try {
      const res = await fetch(`${API}/subscriptions/${id}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '删除失败');
      }
      Dashboard.toast.success('已删除订阅源');
      this.loadSubscriptions();
    } catch (e) {
      console.error('删除订阅源失败:', e);
      Dashboard.toast.error(e.message || '删除失败');
    }
  },

  /** 切换订阅源启用/禁用 */
  async toggleSubscription(id) {
    try {
      const res = await fetch(`${API}/subscriptions/${id}/toggle`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '操作失败');
      }
      const data = await res.json();
      Dashboard.toast.success(data.message);
      this.loadSubscriptions();
    } catch (e) {
      console.error('切换订阅源状态失败:', e);
      Dashboard.toast.error(e.message || '操作失败');
    }
  },

  // ── 系统配置 ────────────────────────────────────────────
  toggleApiKey() {
    const input = document.getElementById('cfg-apikey');
    const btn = input.nextElementSibling;
    if (input.type === 'password') {
      input.type = 'text';
      btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
    } else {
      input.type = 'password';
      btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    }
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
