# 请求趋势图实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在管理后台概览页"模型用量统计"下方增加 Canvas 折线趋势图，按模型分色展示请求数/Tokens/费用随时间变化趋势。

**方案：** 后端新增 `/stats/trend` 端点，按时间桶 + 模型分组聚合；前端用原生 Canvas 绘制多折线图，含图例切换和指标切换。

**涉及文件：**
- `app/stats/models.py` — 新增 TrendDataPoint, TrendSeries, TrendResponse
- `app/db/crud.py` — 新增 `get_trend_data()`
- `app/routers/stats.py` — 新增 `GET /stats/trend` 端点
- `app/static/admin.html` — 新增趋势图容器
- `app/static/js/admin.js` — 新增趋势图逻辑 (Canvas 绘制)
- `app/static/css/admin.css` — 新增趋势图样式

---

### Task 1: Pydantic 模型 (models.py)

**文件：** `app/stats/models.py`

- [ ] **Step 1: 在 `ModelStatsResponse` 下方添加趋势图模型**

在 `app/stats/models.py` 末尾新增：

```python
class TrendDataPoint(BaseModel):
    """单个时间桶的数据"""
    time: str  # ISO 8601, e.g. "2026-05-12T14:00:00Z"
    requests: int
    tokens: int
    cost: float


class TrendSeries(BaseModel):
    """一个模型的时间序列"""
    model: str
    data: List[TrendDataPoint]


class TrendResponse(BaseModel):
    """趋势图响应"""
    granularity: str  # "hour" | "day"
    hours: int
    series: List[TrendSeries]
```

- [ ] **Step 2: 校验**

Run: `python -c "import ast; ast.parse(open('app/stats/models.py').read()); print('OK')"`

- [ ] **Step 3: 提交**

```bash
git add app/stats/models.py
git commit -m "feat(stats): 添加趋势图 Pydantic 模型"
```

---

### Task 2: CRUD 函数 (crud.py)

**文件：** `app/db/crud.py`

在 `get_model_stats` 函数（第 450 行）之后、文件末尾添加新函数。

- [ ] **Step 1: 在 `get_model_stats` 之后添加 `get_trend_data()`**

```python
async def get_trend_data(session: AsyncSession, hours: int = 168) -> dict:
    """获取按时间桶 + 模型分组的趋势数据

    颗粒度规则：
    - hours <= 24: 按小时桶
    - hours >= 168: 按天桶
    """
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    # 按颗粒度选择时间格式化
    if hours <= 24:
        time_format = "%Y-%m-%dT%H:00:00"
        granularity = "hour"
    else:
        time_format = "%Y-%m-%dT00:00:00"
        granularity = "day"

    # 按时间桶 + 模型分组聚合
    query = (
        select(
            func.strftime(time_format, UsageLog.timestamp).label("time_bucket"),
            UsageLog.model,
            func.count().label("requests"),
            func.sum(UsageLog.request_tokens + UsageLog.response_tokens).label("tokens"),
            func.sum(UsageLog.cost).label("cost"),
        )
        .where(UsageLog.timestamp >= start_time)
        .group_by("time_bucket", UsageLog.model)
        .order_by("time_bucket")
    )

    result = await session.execute(query)
    rows = result.all()

    # 将扁平结果重构为按 model 分组的 series
    model_data = {}  # model -> list of data points
    for row in rows:
        if row.model not in model_data:
            model_data[row.model] = []
        model_data[row.model].append({
            "time": row.time_bucket + "Z",
            "requests": row.requests or 0,
            "tokens": row.tokens or 0,
            "cost": round(row.cost or 0.0, 6),
        })

    # 按总请求数排序，取 Top 8
    model_totals = [(m, sum(d["requests"] for d in data)) for m, data in model_data.items()]
    model_totals.sort(key=lambda x: x[1], reverse=True)
    top_models = [m for m, _ in model_totals[:8]]

    # 构建 series：Top 8 单独，其余合并为"其他"
    series = []
    for model in top_models:
        series.append({
            "model": model,
            "data": model_data[model],
        })

    # 合并其他模型
    other_data = {}
    for model, data in model_data.items():
        if model not in top_models:
            for dp in data:
                t = dp["time"]
                if t not in other_data:
                    other_data[t] = {"time": t, "requests": 0, "tokens": 0, "cost": 0.0}
                other_data[t]["requests"] += dp["requests"]
                other_data[t]["tokens"] += dp["tokens"]
                other_data[t]["cost"] += dp["cost"]

    if other_data:
        other_list = sorted(other_data.values(), key=lambda x: x["time"])
        series.append({"model": "其他", "data": other_list})

    return {
        "granularity": granularity,
        "hours": hours,
        "series": series,
    }
```

- [ ] **Step 2: 校验语法**

```bash
python -c "import ast; ast.parse(open('app/db/crud.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add app/db/crud.py
git commit -m "feat(stats): 添加趋势图 CRUD 查询函数"
```

---

### Task 3: API 端点 (stats.py)

**文件：** `app/routers/stats.py`

- [ ] **Step 1: 更新导入**

在文件顶部，将 `from app.db.crud import get_usage_logs, get_usage_summary, get_model_stats` 改为：
```python
from app.db.crud import get_usage_logs, get_usage_summary, get_model_stats, get_trend_data
```

在 `from app.stats.models import UsageLogResponse, UsageSummaryResponse, ModelStatsResponse` 行添加 TrendResponse：
```python
from app.stats.models import UsageLogResponse, UsageSummaryResponse, ModelStatsResponse, TrendResponse
```

- [ ] **Step 2: 在 `/stats/models/list` 端点之后、文件末尾添加 `/stats/trend` 端点**

```python
@router.get("/trend", response_model=TrendResponse)
async def get_trend(
    hours: int = Query(168, description="统计时长（小时）"),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """获取按时间桶 + 模型分组的趋势数据"""
    data = await get_trend_data(db, hours)
    return TrendResponse(**data)
```

- [ ] **Step 3: 校验**

```bash
python -c "
import ast
ast.parse(open('app/routers/stats.py').read())
print('OK')
from app.routers.stats import router
print('Import OK')
"
```

Expected: `OK`, `Import OK`

- [ ] **Step 4: 提交**

```bash
git add app/routers/stats.py
git commit -m "feat(stats): 添加趋势图 API 端点 /stats/trend"
```

---

### Task 4: HTML 容器 (admin.html)

**文件：** `app/static/admin.html`

- [ ] **Step 1: 在 `#model-stats-container` 后、`</div>` 关闭前添加趋势图区域**

找到 `#model-stats-section` 中 `id="model-stats-container"` 所在行后的 `</div>`（即第 59-60 行），在两者之间插入：

```html
                <!-- 请求趋势图 -->
                <div class="trend-chart-section">
                    <div class="trend-header">
                        <span class="trend-title">请求趋势</span>
                        <div class="trend-metrics" id="trend-metrics">
                            <button class="trend-metric-btn active" data-metric="requests" onclick="switchTrendMetric('requests')">请求数</button>
                            <button class="trend-metric-btn" data-metric="tokens" onclick="switchTrendMetric('tokens')">Token 数</button>
                            <button class="trend-metric-btn" data-metric="cost" onclick="switchTrendMetric('cost')">费 用</button>
                        </div>
                    </div>
                    <div class="trend-canvas-wrapper">
                        <canvas id="trend-canvas"></canvas>
                    </div>
                    <div class="trend-legend" id="trend-legend"></div>
                </div>
```

修改后该区域应为：
```html
                <div id="model-stats-container"></div>
                <!-- 请求趋势图 -->
                <div class="trend-chart-section">
                    ...
                </div>
            </div>
        </div>
```

- [ ] **Step 2: 校验 HTML 结构无误（无需要语法检查的工具，目测即可）**

- [ ] **Step 3: 提交**

```bash
git add app/static/admin.html
git commit -m "feat(admin): 添加请求趋势图 HTML 容器"
```

---

### Task 5: CSS 样式 (admin.css)

**文件：** `app/static/css/admin.css`

- [ ] **Step 1: 在文件末尾追加趋势图样式**

```css
/* Trend Chart */
.trend-chart-section {
    border-top: 1px solid var(--border);
    padding: 20px 24px;
}

.trend-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
}

.trend-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 12px;
    font-weight: 700;
    color: var(--accent-primary);
    letter-spacing: 1px;
    text-transform: uppercase;
}

.trend-metrics {
    display: flex;
    gap: 6px;
}

.trend-metric-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 4px 12px;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
}

.trend-metric-btn:hover {
    color: var(--text);
    border-color: var(--accent-primary);
}

.trend-metric-btn.active {
    background: var(--accent-primary);
    color: #000;
    border-color: var(--accent-primary);
    font-weight: 600;
}

.trend-canvas-wrapper {
    width: 100%;
    background: var(--bg-tertiary);
    border-radius: 8px;
    position: relative;
}

#trend-canvas {
    width: 100%;
    height: 220px;
    display: block;
}

.trend-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 12px;
    justify-content: center;
}

.trend-legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-muted);
    user-select: none;
}

.trend-legend-item:hover {
    background: rgba(255, 255, 255, 0.05);
}

.trend-legend-item.hidden {
    opacity: 0.4;
    text-decoration: line-through;
}

.trend-legend-color {
    width: 14px;
    height: 3px;
    border-radius: 2px;
    flex-shrink: 0;
}

.trend-tooltip {
    display: none;
    position: fixed;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text);
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    white-space: nowrap;
}

.trend-tooltip .tooltip-time {
    font-size: 10px;
    color: var(--text-muted);
    margin-bottom: 4px;
}

.trend-tooltip .tooltip-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 0;
}

.trend-tooltip .tooltip-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
```

- [ ] **Step 2: 校验**

Run: 目测确认 CSS 语法无误（括号匹配、分号完整）

- [ ] **Step 3: 提交**

```bash
git add app/static/css/admin.css
git commit -m "feat(admin): 添加趋势图 CSS 样式"
```

---

### Task 6: JavaScript 趋势图逻辑 (admin.js)

**文件：** `app/static/js/admin.js`

这是最核心的 task。需要在 `loadModelStats` 函数（约第 931 行）之后、`switchTab` 函数（约第 1111 行）之前添加新的函数。

- [ ] **Step 1: 在 `loadModelStats` 末尾添加趋势图数据加载调用**

在 `loadModelStats` 函数的大括号 `}` 结束之前（约第 929 行 empty state 渲染之后），添加：

```javascript
        // 同时加载趋势图数据
        loadTrendData(hours);
    } else {
        container.innerHTML = `
            <div class="model-empty-state">
                <div class="empty-icon">📭</div>
                <div class="empty-title">近 ${data.period} 无请求记录</div>
                <div class="empty-desc">开始调用 API 后将显示统计数据</div>
            </div>
        `;
        // 清空趋势图
        const trendContainer = document.querySelector('.trend-chart-section');
        if (trendContainer) trendContainer.style.display = 'none';
    }
```

注意修改 `loadModelStats` 最后的 else 分支，在 empty state 渲染后添加隐藏趋势图的逻辑。

- [ ] **Step 2: 在 `loadModelStats` 和 `switchTab` 之间添加趋势图函数**

```javascript
// Trend Chart
let trendData = null;
let currentTrendMetric = 'requests';
const trendColors = [
    '#00d9ff', '#7b61ff', '#ff00aa', '#ff8c00', '#00ff88',
    '#ff3355', '#00aa88', '#aa00ff', '#88ff00', '#ff0088'
];

async function loadTrendData(hours) {
    try {
        const res = await fetchWithAuth(`/stats/trend?hours=${hours}`);
        if (!res.ok) return;
        trendData = await res.json();
        const trendContainer = document.querySelector('.trend-chart-section');
        if (trendContainer) trendContainer.style.display = '';
        renderTrendChart(currentTrendMetric);
    } catch (e) {
        // 静默失败，不干扰主流程
        console.warn('Failed to load trend data:', e);
    }
}

function renderTrendChart(metric) {
    currentTrendMetric = metric;
    const canvas = document.getElementById('trend-canvas');
    const legendContainer = document.getElementById('trend-legend');
    if (!canvas || !trendData || !trendData.series || trendData.series.length === 0) {
        if (legendContainer) legendContainer.innerHTML = '';
        return;
    }

    // 获取高 DPI 适配
    const wrapper = canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;
    const rect = wrapper.getBoundingClientRect();
    const cssWidth = rect.width || wrapper.clientWidth;
    const cssHeight = 220;

    canvas.width = cssWidth * dpr;
    canvas.height = cssHeight * dpr;
    canvas.style.width = cssWidth + 'px';
    canvas.style.height = cssHeight + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // 初始化隐藏状态（如果是首次渲染）
    if (!canvas._seriesHidden) {
        canvas._seriesHidden = {};
        trendData.series.forEach(s => { canvas._seriesHidden[s.model] = false; });
    }

    // 绘制图表
    drawTrendChart(ctx, cssWidth, cssHeight, trendData, metric, canvas._seriesHidden);

    // 渲染图例
    renderTrendLegend(legendContainer, trendData, canvas);
}

function drawTrendChart(ctx, width, height, data, metric, hiddenMap) {
    const padding = { top: 20, right: 20, bottom: 36, left: 56 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    // 收集所有可见系列的数据值用于 Y 轴范围
    let allValues = [];
    data.series.forEach(s => {
        if (hiddenMap[s.model]) return;
        s.data.forEach(d => allValues.push(d[metric]));
    });

    if (allValues.length === 0) {
        // 没有可见数据，清空画布并显示提示
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.font = '12px JetBrains Mono, monospace';
        ctx.textAlign = 'center';
        ctx.fillText('没有可见数据', width / 2, height / 2);
        return;
    }

    const maxVal = Math.max(...allValues);
    const roundedMax = roundUpNice(maxVal);

    // 时间和 X 轴映射
    const firstSeries = data.series.find(s => !hiddenMap[s.model]) || data.series[0];
    const times = firstSeries.data.map(d => new Date(d.time));
    const minTime = times[0];
    const maxTime = times[times.length - 1];
    const timeRange = maxTime - minTime || 1;

    // ---- 清空 ----
    ctx.clearRect(0, 0, width, height);

    // ---- 绘制网格线 ----
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.textAlign = 'right';

    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
        const y = padding.top + (chartH / gridLines) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();

        const val = Math.round(roundedMax - (roundedMax / gridLines) * i);
        ctx.fillText(formatTrendValue(val, metric), padding.left - 8, y + 4);
    }

    // ---- 绘制 X 轴标签 ----
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.font = '10px JetBrains Mono, monospace';

    const labelCount = Math.min(times.length, data.granularity === 'hour' ? 6 : 5);
    const step = Math.max(1, Math.floor((times.length - 1) / (labelCount - 1)));

    for (let i = 0; i < times.length; i += step) {
        const x = padding.left + ((times[i] - minTime) / timeRange) * chartW;
        const label = formatTrendTime(times[i], data.granularity);
        ctx.fillText(label, x, height - padding.bottom + 16);
    }

    // ---- 绘制每个模型的折线 ----
    data.series.forEach((s, idx) => {
        if (hiddenMap[s.model]) return;
        const color = trendColors[idx % trendColors.length];
        const points = s.data.map(d => ({
            x: padding.left + ((new Date(d.time) - minTime) / timeRange) * chartW,
            y: padding.top + chartH - (d[metric] / roundedMax) * chartH,
        }));

        // 面积填充
        ctx.beginPath();
        ctx.moveTo(points[0].x, padding.top + chartH);
        points.forEach(p => ctx.lineTo(p.x, p.y));
        ctx.lineTo(points[points.length - 1].x, padding.top + chartH);
        ctx.closePath();
        ctx.fillStyle = hexToRgba(color, 0.1);
        ctx.fill();

        // 折线
        ctx.beginPath();
        points.forEach((p, i) => {
            if (i === 0) ctx.moveTo(p.x, p.y);
            else ctx.lineTo(p.x, p.y);
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.stroke();

        // 数据点圆点
        const dotInterval = Math.max(1, Math.floor(points.length / 15));
        points.forEach((p, i) => {
            if (i % dotInterval === 0 || i === points.length - 1) {
                ctx.beginPath();
                ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
                ctx.fillStyle = color;
                ctx.fill();
                ctx.strokeStyle = 'rgba(0,0,0,0.3)';
                ctx.lineWidth = 1;
                ctx.stroke();
            }
        });
    });

    // ---- 保存鼠标交互所需的数据 ----
    canvas._trendData = { data, metric, hiddenMap, padding, chartW, chartH, minTime, timeRange, roundedMax };
}

function renderTrendLegend(container, data, canvas) {
    if (!container) return;
    let html = '';
    data.series.forEach((s, idx) => {
        const color = trendColors[idx % trendColors.length];
        const hidden = canvas._seriesHidden[s.model] ? ' hidden' : '';
        html += `
            <div class="trend-legend-item${hidden}" data-model="${s.model}">
                <span class="trend-legend-color" style="background: ${color};"></span>
                ${s.model}
            </div>
        `;
    });
    container.innerHTML = html;

    // 点击图例切换可见性
    container.querySelectorAll('.trend-legend-item').forEach(el => {
        el.addEventListener('click', () => {
            const model = el.dataset.model;
            canvas._seriesHidden[model] = !canvas._seriesHidden[model];
            renderTrendChart(currentTrendMetric);
        });
    });
}

// Trend chart metric switch
function switchTrendMetric(metric) {
    currentTrendMetric = metric;
    // 更新按钮状态
    document.querySelectorAll('.trend-metric-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.metric === metric);
    });
    renderTrendChart(metric);
}

// ---- Canvas 鼠标 hover tooltip ----
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('trend-canvas');
    const tooltip = document.createElement('div');
    tooltip.className = 'trend-tooltip';
    tooltip.id = 'trend-tooltip';
    document.body.appendChild(tooltip);

    canvas.addEventListener('mousemove', (e) => {
        const data = canvas._trendData;
        if (!data) { tooltip.style.display = 'none'; return; }

        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;

        // 找到最近的 X 轴数据点
        const { data: trendResp, metric, hiddenMap, padding, chartW, chartH, minTime, timeRange, roundedMax } = data;
        const firstVisible = trendResp.series.find(s => !hiddenMap[s.model]);
        if (!firstVisible) { tooltip.style.display = 'none'; return; }

        const times = firstVisible.data.map(d => new Date(d.time));
        const relX = mouseX - padding.left;
        const pct = relX / chartW;
        const targetTime = minTime + pct * timeRange;

        // 找到最近的数据点索引
        let nearestIdx = 0;
        let nearestDist = Infinity;
        times.forEach((t, i) => {
            const dist = Math.abs(t - targetTime);
            if (dist < nearestDist) {
                nearestDist = dist;
                nearestIdx = i;
            }
        });

        // 构建 tooltip 内容
        const timeLabel = firstVisible.data[nearestIdx].time;
        let tipHtml = `<div class="tooltip-time">${timeLabel}</div>`;
        trendResp.series.forEach((s, idx) => {
            if (hiddenMap[s.model]) return;
            const dp = s.data[nearestIdx];
            if (!dp) return;
            const color = trendColors[idx % trendColors.length];
            const val = formatTrendValue(dp[metric], metric);
            tipHtml += `
                <div class="tooltip-row">
                    <span class="tooltip-dot" style="background: ${color};"></span>
                    <span>${s.model}: ${val}</span>
                </div>
            `;
        });

        tooltip.innerHTML = tipHtml;
        tooltip.style.display = '';

        // 定位 tooltip
        let tx = e.clientX + 12;
        let ty = e.clientY - 10;
        if (tx + 200 > window.innerWidth) tx = e.clientX - 200;
        if (ty < 0) ty = e.clientY + 20;
        tooltip.style.left = tx + 'px';
        tooltip.style.top = ty + 'px';
    });

    canvas.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
    });
});

// ---- 工具函数 ----
function roundUpNice(val) {
    if (val <= 0) return 10;
    const magnitude = Math.pow(10, Math.floor(Math.log10(val)));
    const normalized = val / magnitude;
    if (normalized <= 1) return magnitude;
    if (normalized <= 2) return 2 * magnitude;
    if (normalized <= 5) return 5 * magnitude;
    return 10 * magnitude;
}

function formatTrendValue(val, metric) {
    if (metric === 'cost') return '$' + val.toFixed(4);
    if (val >= 1000000) return (val / 1000000).toFixed(1) + 'M';
    if (val >= 1000) return (val / 1000).toFixed(1) + 'K';
    return val.toString();
}

function formatTrendTime(date, granularity) {
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    if (granularity === 'day') return `${month}/${day}`;
    const hour = String(date.getHours()).padStart(2, '0');
    return `${month}/${day} ${hour}:00`;
}

function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}
```

- [ ] **Step 3: 更新初始化代码和自动刷新**

在现有初始化代码中（约第 1135 行 `loadModelStats(168);`），无需额外修改，因为 `loadModelStats` 内部会调用 `loadTrendData(hours)`。

但需要确保趋势图初始显示。`loadModelStats(168)` 调用后，`loadTrendData(168)` 会被自动调用。

- [ ] **Step 4: 校验语法**

```bash
python -c "exec(compile(open('app/static/js/admin.js', 'rb').read(), 'admin.js', 'exec')); print('JS syntax OK')" 2>&1 || node -c "app/static/js/admin.js" 2>&1 || echo "Node or Python check not available - manual verification"
```

如果 `node` 可用：
```bash
node -c "app/static/js/admin.js"
```

- [ ] **Step 5: 提交**

```bash
git add app/static/js/admin.js
git commit -m "feat(admin): 添加请求趋势图 Canvas 绘制逻辑"
```

---

### Task 7: 集成验证

- [ ] **Step 1: 启动服务器**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 打开管理后台并验证**

1. 打开 `http://localhost:8000/admin`，进入概览页
2. 确认"模型用量统计"下方出现"请求趋势"区域
3. 确认默认显示请求数折线图，多条模型彩色线条
4. 点击 "Token 数" / "费 用" 按钮，图形正确切换
5. 点击 "5时/日/周/月" 时间按钮，趋势图同步更新（5时/日 → 小时桶，周/月 → 天桶）
6. 点击图例项，对应线条显示/隐藏
7. 鼠标悬停图表区，显示 tooltip 各模型数值

- [ ] **Step 3: 修复发现的问题**

如果发现问题，逐个修复并重新验证。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit -m "feat(admin): 完成请求趋势图功能"
```
