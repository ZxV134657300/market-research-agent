/**
 * dashboard.js v3.0 - 仪表盘图表 + 面板渲染 + 微交互
 *
 * 新增功能：
 * - 数字滚动计数动画（从 0 到目标值）
 * - 骨架屏加载状态
 * - 趋势指示器渲染
 * - 研报卡片化（首字母彩色图标）
 * - Toast 通知系统
 * - 空状态引导
 */

const Dashboard = {
  chart: null,
  _initialized: false,

  // ── Toast 通知系统 ─────────────────────────────────────
  toast: {
    container: null,

    init() {
      this.container = document.getElementById('toast-container');
    },

    show(message, type = 'info', duration = 3000) {
      if (!this.container) this.init();

      const toast = document.createElement('div');
      toast.className = `toast ${type}`;

      const icons = {
        success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22C55E" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4A6CF7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
      };

      toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span>${message}</span>
      `;

      this.container.appendChild(toast);

      setTimeout(() => {
        toast.classList.add('leaving');
        setTimeout(() => toast.remove(), 300);
      }, duration);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 5000); },
    info(msg) { this.show(msg, 'info'); },
    warning(msg) { this.show(msg, 'warning', 4000); },
  },

  // ── 数字滚动动画 ──────────────────────────────────────
  animateCounter(element, target, duration = 800, suffix = '') {
    if (!element) return;

    const start = 0;
    const startTime = performance.now();

    const step = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // easeOutExpo 缓动函数
      const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      const current = Math.floor(start + (target - start) * eased);

      element.textContent = current.toLocaleString() + suffix;

      if (progress < 1) {
        requestAnimationFrame(step);
      }
    };

    requestAnimationFrame(step);
  },

  // ── 骨架屏 ────────────────────────────────────────────
  showSkeletonStats() {
    const ids = ['stat-files', 'stat-reports', 'stat-qc', 'stat-chunks'];
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.innerHTML = '<div class="skeleton skeleton-number"></div>';
      }
    });
  },

  // ── 趋势指示器 ────────────────────────────────────────
  updateTrend(elementId, value, label) {
    const el = document.getElementById(elementId);
    if (!el) return;

    if (value === null || value === undefined) {
      el.className = 'stat-trend neutral';
      el.textContent = '--';
      return;
    }

    if (value > 0) {
      el.className = 'stat-trend up';
      el.textContent = `+${value}% ${label}`;
    } else if (value < 0) {
      el.className = 'stat-trend down';
      el.textContent = `${value}% ${label}`;
    } else {
      el.className = 'stat-trend neutral';
      el.textContent = `持平 ${label}`;
    }
  },

  // ── 趋势图 ────────────────────────────────────────────
  renderTrendChart(data) {
    const canvas = document.getElementById('chart-trend');
    if (!canvas) return;

    // 已初始化 → 只更新数据
    if (this._initialized && this.chart) {
      this.chart.data.labels = data.dates;
      this.chart.data.datasets[0].data = data.collection;
      this.chart.data.datasets[1].data = data.output;
      this.chart.update('none');
      return;
    }

    // 防御：如果标记丢失但实例存在，先销毁
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }

    this.chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: data.dates,
        datasets: [
          {
            label: '采集量',
            data: data.collection,
            borderColor: '#6366F1',
            backgroundColor: 'rgba(99, 102, 241, 0.06)',
            fill: true,
            tension: 0.4,
            pointBackgroundColor: '#6366F1',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            borderWidth: 2.5,
          },
          {
            label: '研报产出',
            data: data.output,
            borderColor: '#8B5CF6',
            backgroundColor: 'rgba(139, 92, 246, 0.06)',
            fill: true,
            tension: 0.4,
            pointBackgroundColor: '#8B5CF6',
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
            borderWidth: 2.5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: 'easeOutQuart' },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1E293B',
            titleColor: '#F1F5F9',
            bodyColor: '#CBD5E1',
            cornerRadius: 8,
            padding: 12,
            titleFont: { size: 13, weight: '600' },
            bodyFont: { size: 12 },
            boxPadding: 4,
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94A3B8', font: { size: 12 } },
            border: { display: false },
          },
          y: {
            beginAtZero: true,
            grid: { color: '#F1F5F9' },
            ticks: {
              color: '#94A3B8',
              font: { size: 12 },
              stepSize: 1,
              precision: 0,
            },
            border: { display: false },
          },
        },
      },
    });

    this._initialized = true;
  },

  // ── 更新统计卡片（带计数动画） ─────────────────────────
  updateStats(data) {
    // 文件数
    const filesEl = document.getElementById('stat-files');
    if (filesEl) {
      const target = parseInt(data.file_count) || 0;
      this.animateCounter(filesEl, target, 800);
    }

    // 报告数
    const reportsEl = document.getElementById('stat-reports');
    if (reportsEl) {
      const target = parseInt(data.report_count) || 0;
      this.animateCounter(reportsEl, target, 800);
    }

    // 质检通过率
    const qcEl = document.getElementById('stat-qc');
    if (qcEl) {
      const target = parseFloat(data.qc_pass_rate) || 0;
      this.animateCounter(qcEl, target, 1000, '%');
    }

    // 处理片段数
    const chunksEl = document.getElementById('stat-chunks');
    if (chunksEl) {
      const target = parseInt(data.chunk_count) || 0;
      this.animateCounter(chunksEl, target, 1200);
    }

    // 趋势指示器（模拟数据 - 基于实际数据计算）
    this.updateTrend('stat-files-trend', data.file_trend || null, '较昨日');
    this.updateTrend('stat-reports-trend', data.report_trend || null, '较上周');
    this.updateTrend('stat-qc-trend', data.qc_trend || null, '较上次');
    this.updateTrend('stat-chunks-trend', data.chunk_trend || null, '较昨日');
  },

  // ── 渲染今日要闻 ──────────────────────────────────────
  async renderNewsList() {
    const container = document.getElementById('news-list');
    if (!container) return;

    try {
      const res = await fetch('/api/news/top5');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (!data.news || data.news.length === 0) {
        container.innerHTML = `
          <div class="news-item placeholder">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#CBD5E1" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right:8px"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>
            暂无今日要闻
          </div>
        `;
        return;
      }

      container.innerHTML = data.news.map((item, i) => `
        <div class="news-item">
          <span class="news-rank rank-${i + 1}">${i + 1}</span>
          <div class="news-body">
            <a href="${item.link}" target="_blank" rel="noopener" class="news-title">${item.title}</a>
            <div class="news-meta">
              <span class="news-source">${item.source}</span>
              <span class="news-time">${item.published}</span>
            </div>
          </div>
        </div>
      `).join('');
    } catch (e) {
      console.error('加载今日要闻失败:', e);
      container.innerHTML = `
        <div class="news-item placeholder">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#CBD5E1" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right:8px"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          加载失败，请稍后重试
        </div>
      `;
    }
  },

  // ── 渲染最新研报（卡片化） ────────────────────────────
  renderRecentReports(reports) {
    const container = document.getElementById('recent-reports');
    if (!container) return;

    if (!reports || reports.length === 0) {
      container.innerHTML = `
        <div class="empty-state" id="empty-reports">
          <div class="empty-state-icon">
            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          </div>
          <div class="empty-state-title">还没有生成报告</div>
          <div class="empty-state-desc">前往「系统配置」上传数据或开启自动采集，一键生成专业调研报告</div>
          <button class="empty-state-btn" onclick="App.navigate('config')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            去生成
          </button>
        </div>
      `;
      return;
    }

    const gradients = ['gradient-blue', 'gradient-green', 'gradient-purple', 'gradient-orange', 'gradient-rose'];
    const latest = reports.slice(0, 5);

    container.innerHTML = latest.map((r, i) => {
      const time = r.created_at.replace('T', ' ').slice(0, 16);
      const statusLabel = r.status === 'done' ? '已发布' : r.status;
      const firstChar = (r.title || 'R')[0].toUpperCase();
      const gradientClass = gradients[i % gradients.length];

      return `
        <div class="recent-item" onclick="App.navigate('reports'); App.viewReport('${r.id}')">
          <div class="recent-icon ${gradientClass}">${firstChar}</div>
          <div class="recent-body">
            <div class="recent-title">${r.title}</div>
            <div class="recent-meta">
              <span class="recent-time">${time}</span>
              <span class="recent-status">${statusLabel}</span>
            </div>
          </div>
        </div>
      `;
    }).join('');
  },

  // ── 渲染报告列表（卡片化） ────────────────────────────
  renderReportList(list, currentReportId) {
    const container = document.getElementById('report-list');
    if (!container) return;

    if (!list || list.length === 0) {
      container.innerHTML = `
        <div class="empty-state" id="empty-report-list">
          <div class="empty-state-icon">
            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          </div>
          <div class="empty-state-title">还没有生成报告</div>
          <div class="empty-state-desc">前往「系统配置」上传数据或开启自动采集，一键生成专业调研报告</div>
          <button class="empty-state-btn" onclick="App.navigate('config')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            去生成
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = list.map(r => `
      <div class="report-item ${r.id === currentReportId ? 'active' : ''}"
           onclick="App.viewReport('${r.id}')">
        <div class="ri-title">${r.title}</div>
        <div class="ri-time">${r.created_at.replace('T', ' ').slice(0, 19)}</div>
      </div>
    `).join('');
  },

  // ── 销毁图表实例 ──────────────────────────────────────
  destroy() {
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    this._initialized = false;
  },

  reset() {
    this.destroy();
  },
};
