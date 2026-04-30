// bol-api Admin Interface JavaScript

const token = localStorage.getItem('admin_token');
if (!token) {
    window.location.href = '/admin/login';
}
const headers = {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'};

// 登出功能
function logout() {
    localStorage.removeItem('admin_token');
    window.location.href = '/admin/login';
}

// 处理 401 响应 - token 过期自动跳转登录
async function fetchWithAuth(url, options = {}) {
    const res = await fetch(url, {...options, headers: {...headers, ...options.headers}});
    if (res.status === 401) {
        localStorage.removeItem('admin_token');
        window.location.href = '/admin/login';
    }
    return res;
}

// 检查 token 是否有效
async function checkAuth() {
    try {
        const res = await fetchWithAuth('/admin/channels');
        if (res.status === 401) {
            return false;
        }
        return true;
    } catch (e) {
        console.error('Auth check failed:', e);
        return false;
    }
}

// 页面加载时检查认证
checkAuth();

// Stats
async function loadStats() {
    const res = await fetchWithAuth('/stats/summary');
    const data = await res.json();

    const avgTokens = data.total_requests > 0 ? Math.round(data.total_tokens / data.total_requests) : 0;
    const avgCost = data.total_requests > 0 ? (data.total_cost / data.total_requests).toFixed(4) : '0.0000';

    document.getElementById('stats').innerHTML = `
        <div class="stat-card">
            <div class="stat-icon">📊</div>
            <div class="stat-content">
                <div class="stat-value">${data.total_requests}</div>
                <div class="stat-label">总请求次数</div>
                <div class="stat-detail">已追踪 ${data.days} 天</div>
            </div>
            <div class="stat-mini-chart">
                <div class="mini-bar" style="height: ${Math.random() * 30 + 2}px;"></div>
                <div class="mini-bar" style="height: ${Math.random() * 30 + 2}px;"></div>
                <div class="mini-bar" style="height: ${Math.random() * 30 + 2}px;"></div>
                <div class="mini-bar" style="height: ${Math.random() * 30 + 2}px;"></div>
                <div class="mini-bar" style="height: ${Math.random() * 30 + 2}px;"></div>
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">🔢</div>
            <div class="stat-content">
                <div class="stat-value">${formatNumber(data.total_tokens)}</div>
                <div class="stat-label">Tokens 消耗</div>
                <div class="stat-detail">平均 ${avgTokens} tokens/请求</div>
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">💰</div>
            <div class="stat-content">
                <div class="stat-value">$${data.total_cost.toFixed(4)}</div>
                <div class="stat-label">预估费用</div>
                <div class="stat-detail">平均 $${avgCost}/请求</div>
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">⚡</div>
            <div class="stat-content">
                <div class="stat-value">${data.rpm}</div>
                <div class="stat-label">RPM</div>
                <div class="stat-detail">每分钟请求数</div>
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">📝</div>
            <div class="stat-content">
                <div class="stat-value">${formatNumber(data.tpm)}</div>
                <div class="stat-label">TPM</div>
                <div class="stat-detail">每分钟 Token 数</div>
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">📈</div>
            <div class="stat-content">
                <div class="stat-value">${data.days}</div>
                <div class="stat-label">追踪天数</div>
                <div class="stat-detail">日均 ${Math.round(data.total_requests / data.days)} 次请求</div>
            </div>
        </div>
    `;
}

function formatNumber(n) {
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n/1000).toFixed(1) + 'K';
    return n;
}

function formatDate(s) {
    return new Date(s).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
}

// Keys
async function loadKeys() {
    const res = await fetchWithAuth('/admin/keys');
    const keys = await res.json();
    const tbody = document.querySelector('#keys-table tbody');

    if (keys.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    <div class="empty-state">
                        <div class="empty-state-icon">🔑</div>
                        <div>暂无 API 密钥，请创建一个开始使用</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = keys.map(k => `
        <tr>
            <td><span style="font-family: 'JetBrains Mono'; color: var(--text-muted);">#${k.id}</span></td>
            <td>${k.name || '<span style="color: var(--text-muted)">—</span>'}</td>
            <td>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-family: 'JetBrains Mono'; font-size: 12px; color: var(--text-muted);" id="key-display-${k.id}">${k.key_prefix || 'bol-xxx...'}</span>
                    <button class="btn" style="padding: 4px 8px; font-size: 11px; border-color: var(--border);" onclick="toggleKeyVisibility(${k.id})" id="key-toggle-${k.id}">显示</button>
                    <button class="btn" style="padding: 4px 8px; font-size: 11px; border-color: var(--border);" onclick="copyFullKey(${k.id})" id="key-copy-${k.id}">复制</button>
                </div>
            </td>
            <td>
                <span class="badge ${k.is_active ? 'badge-active' : 'badge-disabled'}">
                    <span class="badge-dot"></span>
                    ${k.is_active ? '启用' : '禁用'}
                </span>
            </td>
            <td><span style="font-family: 'JetBrains Mono'; font-size: 12px; color: var(--text-muted);">${formatDate(k.created_at)}</span></td>
            <td>
                <div class="action-btns">
                    <button class="btn ${k.is_active ? '' : 'btn-primary'}" style="${k.is_active ? 'border-color: var(--border); color: var(--text-muted);' : ''}" onclick="toggleKey(${k.id}, ${!k.is_active})">${k.is_active ? '禁用' : '启用'}</button>
                    <button class="btn btn-danger" onclick="deleteKey(${k.id})">删除</button>
                </div>
            </td>
        </tr>
    `).join('');
}

async function toggleKeyVisibility(id) {
    const displayEl = document.getElementById(`key-display-${id}`);
    const toggleBtn = document.getElementById(`key-toggle-${id}`);
    const currentText = displayEl.textContent;

    if (currentText.includes('...')) {
        const res = await fetchWithAuth(`/admin/keys/${id}/reveal`);
        const data = await res.json();
        if (data.key) {
            displayEl.textContent = data.key;
            displayEl.style.color = 'var(--accent)';
            toggleBtn.textContent = '隐藏';
        }
    } else {
        const res = await fetchWithAuth('/admin/keys');
        const keys = await res.json();
        const k = keys.find(k => k.id === id);
        displayEl.textContent = k.key_prefix || 'bol-xxx...';
        displayEl.style.color = 'var(--text-muted)';
        toggleBtn.textContent = '显示';
    }
}

async function copyFullKey(id) {
    const res = await fetchWithAuth(`/admin/keys/${id}/reveal`);
    const data = await res.json();
    if (data.key) {
        navigator.clipboard.writeText(data.key);
        const copyBtn = document.getElementById(`key-copy-${id}`);
        copyBtn.textContent = '已复制!';
        copyBtn.style.borderColor = 'var(--success)';
        copyBtn.style.color = 'var(--success)';
        setTimeout(() => {
            copyBtn.textContent = '复制';
            copyBtn.style.borderColor = 'var(--border)';
            copyBtn.style.color = '';
        }, 2000);
    }
}

function showKeyModal() {
    document.getElementById('key-modal').classList.add('show');
    document.getElementById('key-name').value = '';
    document.getElementById('key-result').style.display = 'none';
    document.getElementById('key-create-btn').style.display = 'inline-flex';
}

function closeKeyModal() {
    document.getElementById('key-modal').classList.remove('show');
}

async function createKey() {
    const name = document.getElementById('key-name').value;
    const res = await fetchWithAuth('/admin/keys', {method: 'POST', body: JSON.stringify({name})});
    const data = await res.json();

    document.getElementById('key-value').textContent = data.key;
    document.getElementById('key-result').style.display = 'block';
    document.getElementById('key-create-btn').style.display = 'none';

    loadKeys();
}

function copyKey() {
    const key = document.getElementById('key-value').textContent;
    navigator.clipboard.writeText(key);
}

async function toggleKey(id, isActive) {
    await fetchWithAuth(`/admin/keys/${id}?is_active=${isActive}`, {method: 'PATCH'});
    loadKeys();
}

async function deleteKey(id) {
    if (confirm('确定删除此 API 密钥？此操作不可恢复。')) {
        await fetchWithAuth(`/admin/keys/${id}`, {method: 'DELETE'});
        loadKeys();
    }
}

// Channels
async function loadChannels() {
    const res = await fetchWithAuth('/admin/channels');
    const channels = await res.json();
    const tbody = document.querySelector('#channels-table tbody');

    if (channels.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7">
                        <div class="empty-state-icon">📡</div>
                        <div>暂无渠道配置，请添加一个以启用 API 代理</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = channels.map(c => `
        <tr>
            <td><span style="font-family: 'JetBrains Mono'; color: var(--text-muted);">#${c.id}</span></td>
            <td>${c.name}</td>
            <td>
                <span class="provider-badge provider-${c.api_protocol || 'openai'}">${c.api_protocol || 'openai'}</span>
            </td>
            <td>
                <div class="model-tags">
                    ${c.models.length > 0
                        ? c.models.map(m => `<span class="model-tag">${m}</span>`).join('')
                        : '<span style="color: var(--text-muted);">全部</span>'
                    }
                </div>
            </td>
            <td>
                <span class="badge ${c.is_active ? 'badge-active' : 'badge-disabled'}">
                    <span class="badge-dot"></span>
                    ${c.is_active ? '启用' : '禁用'}
                </span>
            </td>
            <td id="latency-${c.id}">
                <span style="color: var(--text-muted); font-family: 'JetBrains Mono'; font-size: 12px;">—</span>
            </td>
            <td>
                <div class="action-btns">
                    <button class="btn ${c.is_active ? '' : 'btn-primary'}" style="${c.is_active ? 'border-color: var(--border); color: var(--text-muted);' : ''}" onclick="toggleChannel(${c.id}, ${!c.is_active})">${c.is_active ? '禁用' : '启用'}</button>
                    <button class="btn" style="border-color: rgba(0, 217, 255, 0.3); color: var(--accent);" onclick="testChannel(${c.id})" id="test-btn-${c.id}">测试</button>
                    <button class="btn" style="border-color: var(--border);" onclick="editChannel(${c.id})">编辑</button>
                    <button class="btn btn-danger" onclick="deleteChannel(${c.id})">删除</button>
                </div>
            </td>
        </tr>
    `).join('');
}

let editingChannelId = null;

function showChannelModal() {
    editingChannelId = null;
    document.getElementById('channel-modal').classList.add('show');
    document.getElementById('modal-title').textContent = '添加渠道';
    document.getElementById('channel-name').value = '';
    document.getElementById('channel-url').value = '';
    document.getElementById('channel-apikey').value = '';
    document.getElementById('channel-apikey').placeholder = 'sk-...';
    document.getElementById('key-status').style.display = 'none';
    document.getElementById('channel-models').value = '';
    document.getElementById('channel-priority').value = '1';
    document.getElementById('channel-type').value = 'custom';
    document.getElementById('channel-protocol').value = 'openai';
    document.getElementById('fetch-models-status').style.display = 'none';
    onChannelTypeChange();
}

function onChannelTypeChange() {
    const type = document.getElementById('channel-type').value;
    const protocolGroup = document.getElementById('protocol-group');
    const protocolSelect = document.getElementById('channel-protocol');
    if (type === 'custom') {
        protocolGroup.style.display = '';
    } else {
        protocolGroup.style.display = 'none';
        protocolSelect.value = type;
    }
}

async function editChannel(id) {
    editingChannelId = id;
    document.getElementById('channel-modal').classList.add('show');
    document.getElementById('modal-title').textContent = '编辑渠道';

    const res = await fetchWithAuth('/admin/channels');
    const channels = await res.json();
    const c = channels.find(c => c.id === id);

    if (c) {
        document.getElementById('channel-name').value = c.name;

        const typeSelect = document.getElementById('channel-type');
        const typeValue = c.provider_type || 'custom';
        for (let opt of typeSelect.options) {
            opt.selected = opt.value === typeValue;
        }

        const protocolSelect = document.getElementById('channel-protocol');
        const protocolValue = c.api_protocol || 'openai';
        for (let opt of protocolSelect.options) {
            opt.selected = opt.value === protocolValue;
        }

        document.getElementById('channel-url').value = c.base_url;
        document.getElementById('channel-apikey').value = '';
        document.getElementById('channel-apikey').placeholder = '留空保持原值';
        document.getElementById('key-status').style.display = 'inline-flex';
        document.getElementById('channel-models').value = c.models.join(', ');
        document.getElementById('channel-priority').value = c.priority;
        document.getElementById('fetch-models-status').style.display = 'none';
        onChannelTypeChange();
    }
}

async function fetchModels() {
    const btn = document.getElementById('fetch-models-btn');
    const statusDiv = document.getElementById('fetch-models-status');
    const baseUrl = document.getElementById('channel-url').value.trim();
    const apiKey = document.getElementById('channel-apikey').value.trim();
    const apiProtocol = document.getElementById('channel-protocol').value;

    if (!baseUrl) {
        statusDiv.style.display = 'block';
        statusDiv.style.color = 'var(--error)';
        statusDiv.textContent = '请先输入基础 URL';
        return;
    }

    if (!apiKey && !editingChannelId) {
        statusDiv.style.display = 'block';
        statusDiv.style.color = 'var(--error)';
        statusDiv.textContent = '请先输入 API 密钥';
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span>↻ 加载中...</span>';
    btn.style.opacity = '0.6';
    statusDiv.style.display = 'block';
    statusDiv.style.color = 'var(--text-muted)';
    statusDiv.textContent = '正在拉取模型列表...';

    try {
        const res = await fetchWithAuth('/admin/channels/fetch-models', {
            method: 'POST',
            body: JSON.stringify({
                base_url: baseUrl,
                api_key: apiKey,
                api_protocol: apiProtocol
            })
        });

        const data = await res.json();

        if (res.ok) {
            if (data.models && data.models.length > 0) {
                document.getElementById('channel-models').value = data.models.join(', ');
                statusDiv.style.color = 'var(--success)';
                statusDiv.textContent = `已找到 ${data.count} 个模型`;
            } else {
                statusDiv.style.color = 'var(--warning)';
                statusDiv.textContent = data.message || '未找到模型，请手动配置';
            }
        } else {
            statusDiv.style.color = 'var(--error)';
            statusDiv.textContent = data.detail || '拉取模型失败';
        }
    } catch (e) {
        statusDiv.style.color = 'var(--error)';
        statusDiv.textContent = '错误: ' + e.message;
    }

    btn.disabled = false;
    btn.innerHTML = '<span>↻ 拉取</span>';
    btn.style.opacity = '1';

    setTimeout(() => {
        statusDiv.style.display = 'none';
    }, 3000);
}

function closeChannelModal() {
    editingChannelId = null;
    document.getElementById('channel-modal').classList.remove('show');
}

async function saveChannel() {
    const models = document.getElementById('channel-models').value.split(',').map(m => m.trim()).filter(m => m);
    const data = {
        name: document.getElementById('channel-name').value,
        provider_type: document.getElementById('channel-type').value,
        api_protocol: document.getElementById('channel-protocol').value,
        base_url: document.getElementById('channel-url').value,
        api_key: document.getElementById('channel-apikey').value,
        models: models,
        priority: parseInt(document.getElementById('channel-priority').value) || 1
    };

    if (!data.name || !data.base_url) {
        alert('请填写必填字段');
        return;
    }

    if (editingChannelId && !data.api_key) {
        delete data.api_key;
    } else if (!editingChannelId && !data.api_key) {
        alert('新渠道必须填写 API 密钥');
        return;
    }

    if (editingChannelId) {
        await fetchWithAuth(`/admin/channels/${editingChannelId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    } else {
        await fetchWithAuth('/admin/channels', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    closeChannelModal();
    loadChannels();
}

async function toggleChannel(id, is_active) {
    await fetchWithAuth(`/admin/channels/${id}/toggle`, {
        method: 'POST',
        body: JSON.stringify({is_active})
    });
    loadChannels();
}

async function deleteChannel(id) {
    if (confirm('确定删除此渠道？')) {
        await fetchWithAuth(`/admin/channels/${id}`, {method: 'DELETE'});
        loadChannels();
    }
}

// Prices
let editingPriceId = null;

async function loadPrices() {
    const res = await fetchWithAuth('/admin/prices');
    const prices = await res.json();
    const tbody = document.querySelector('#prices-table tbody');

    if (prices.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6">
                    <div style="text-align: center; padding: 40px; color: var(--text-muted);">
                        <div class="empty-state-icon">💰</div>
                        <div>暂无价格配置，请添加模型价格以计算费用</div>
                    </div>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = prices.map(p => `
        <tr>
            <td><span style="font-family: 'JetBrains Mono'; color: var(--text-muted);">#${p.id}</span></td>
            <td style="font-family: 'JetBrains Mono';">${p.model}</td>
            <td style="font-family: 'JetBrains Mono';">$${p.input_price.toFixed(2)}/M</td>
            <td style="font-family: 'JetBrains Mono';">$${p.output_price.toFixed(2)}/M</td>
            <td>
                <span class="badge ${p.is_active ? 'badge-active' : 'badge-disabled'}">
                    <span class="badge-dot"></span>
                    ${p.is_active ? '启用' : '禁用'}
                </span>
            </td>
            <td>
                <div class="action-btns">
                    <button class="btn ${p.is_active ? '' : 'btn-primary'}" style="${p.is_active ? 'border-color: var(--border); color: var(--text-muted);' : ''}" onclick="togglePrice(${p.id}, ${!p.is_active})">${p.is_active ? '禁用' : '启用'}</button>
                    <button class="btn" style="border-color: var(--border);" onclick="editPrice(${p.id})">编辑</button>
                    <button class="btn btn-danger" onclick="deletePrice(${p.id})">删除</button>
                </div>
            </td>
        </tr>
    `).join('');
}

function showPriceModal() {
    editingPriceId = null;
    document.getElementById('price-modal').classList.add('show');
    document.getElementById('price-modal-title').textContent = '添加模型价格';
    document.getElementById('price-model').value = '';
    document.getElementById('price-input').value = '0';
    document.getElementById('price-output').value = '0';
}

async function editPrice(id) {
    editingPriceId = id;
    document.getElementById('price-modal').classList.add('show');
    document.getElementById('price-modal-title').textContent = '编辑模型价格';

    const res = await fetchWithAuth('/admin/prices');
    const prices = await res.json();
    const p = prices.find(p => p.id === id);

    if (p) {
        document.getElementById('price-model').value = p.model;
        document.getElementById('price-input').value = p.input_price;
        document.getElementById('price-output').value = p.output_price;
    }
}

function closePriceModal() {
    editingPriceId = null;
    document.getElementById('price-modal').classList.remove('show');
}

async function savePrice() {
    const model = document.getElementById('price-model').value.trim();
    const inputPrice = parseFloat(document.getElementById('price-input').value) || 0;
    const outputPrice = parseFloat(document.getElementById('price-output').value) || 0;

    if (!model) {
        alert('请填写模型名称');
        return;
    }

    const data = {
        model,
        input_price: inputPrice,
        output_price: outputPrice
    };

    if (editingPriceId) {
        await fetchWithAuth(`/admin/prices/${editingPriceId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    } else {
        await fetchWithAuth('/admin/prices', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    closePriceModal();
    loadPrices();
}

async function togglePrice(id, is_active) {
    await fetchWithAuth(`/admin/prices/${id}/toggle`, {
        method: 'POST',
        body: JSON.stringify({is_active})
    });
    loadPrices();
}

async function deletePrice(id) {
    if (confirm('确定删除此价格配置？')) {
        await fetchWithAuth(`/admin/prices/${id}`, {method: 'DELETE'});
        loadPrices();
    }
}

// Model Stats
async function loadModelStats(hours) {
    const tabs = document.querySelectorAll('.period-tab-inline');
    tabs.forEach(tab => {
        tab.classList.remove('active');
        if (tab.textContent === '5时' && hours === 5) {
            tab.classList.add('active');
        } else if (tab.textContent === '日' && hours === 24) {
            tab.classList.add('active');
        } else if (tab.textContent === '周' && hours === 168) {
            tab.classList.add('active');
        } else if (tab.textContent === '月' && hours === 720) {
            tab.classList.add('active');
        }
    });

    document.getElementById('model-stats-period').textContent = hours < 24 ? `${hours}时` : `${hours / 24}天`;

    const res = await fetchWithAuth(`/stats/models?hours=${hours}`);
    const data = await res.json();

    const container = document.getElementById('model-stats-container');
    const maxRequests = data.stats && data.stats.length > 0 ? data.stats[0].requests : 1;

    const totalInputTokens = data.stats ? data.stats.reduce((sum, s) => sum + s.request_tokens, 0) : 0;
    const totalOutputTokens = data.stats ? data.stats.reduce((sum, s) => sum + s.response_tokens, 0) : 0;

    if (data.stats && data.stats.length > 0) {
        // 颜色数组用于图表
        const colors = [
            '#00d9ff', '#7b61ff', '#ff00aa', '#ff8c00', '#00ff88',
            '#ff3355', '#00aa88', '#aa00ff', '#88ff00', '#ff0088'
        ];

        container.innerHTML = `
            <!-- 汇总统计卡片 -->
            <div class="model-summary-grid">
                <div class="model-summary-card">
                    <div class="summary-icon">📊</div>
                    <div class="summary-content">
                        <div class="summary-value">${data.total_requests}</div>
                        <div class="summary-label">总请求</div>
                    </div>
                </div>
                <div class="model-summary-card">
                    <div class="summary-icon" style="color: var(--accent-primary);">↓</div>
                    <div class="summary-content">
                        <div class="summary-value">${formatNumber(totalInputTokens)}</div>
                        <div class="summary-label">输入 Tokens</div>
                    </div>
                </div>
                <div class="model-summary-card">
                    <div class="summary-icon" style="color: var(--accent-secondary);">↑</div>
                    <div class="summary-content">
                        <div class="summary-value">${formatNumber(totalOutputTokens)}</div>
                        <div class="summary-label">输出 Tokens</div>
                    </div>
                </div>
                <div class="model-summary-card">
                    <div class="summary-icon" style="color: var(--accent-success);">$</div>
                    <div class="summary-content">
                        <div class="summary-value">${data.total_cost.toFixed(4)}</div>
                        <div class="summary-label">总费用</div>
                    </div>
                </div>
            </div>

            <!-- 可视化图表 -->
            <div class="model-chart-section">
                <div class="chart-title">请求分布</div>
                <div class="model-bar-chart">
                    ${data.stats.slice(0, 10).map((s, i) => {
                        const percentage = Math.round((s.requests / data.total_requests) * 100);
                        const width = Math.max(percentage, 3);
                        const color = colors[i % colors.length];
                        return `
                            <div class="chart-row">
                                <div class="chart-label">${s.model}</div>
                                <div class="chart-bar-wrapper">
                                    <div class="chart-bar" style="width: ${width}%; background: ${color};">
                                        <span class="chart-bar-value">${percentage}%</span>
                                    </div>
                                </div>
                                <div class="chart-count">${s.requests}</div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>

            <!-- 详细数据表格 -->
            <div class="model-detail-section">
                <div class="detail-title">详细数据</div>
                <div class="model-detail-grid">
                    ${data.stats.map((s, i) => {
                        const rankClass = i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : 'rank-default';
                        const color = colors[i % colors.length];
                        const percentage = Math.round((s.requests / data.total_requests) * 100);
                        return `
                            <div class="model-detail-card">
                                <div class="detail-header">
                                    <span class="detail-rank ${rankClass}">#${i + 1}</span>
                                    <span class="detail-model">${s.model}</span>
                                </div>
                                <div class="detail-usage-bar" style="background: ${color}; width: ${percentage}%;"></div>
                                <div class="detail-stats">
                                    <div class="detail-stat">
                                        <span class="detail-stat-label">请求</span>
                                        <span class="detail-stat-value">${s.requests}</span>
                                    </div>
                                    <div class="detail-stat">
                                        <span class="detail-stat-label">输入</span>
                                        <span class="detail-stat-value" style="color: var(--accent-primary);">${formatNumber(s.request_tokens)}</span>
                                    </div>
                                    <div class="detail-stat">
                                        <span class="detail-stat-label">输出</span>
                                        <span class="detail-stat-value" style="color: var(--accent-secondary);">${formatNumber(s.response_tokens)}</span>
                                    </div>
                                    <div class="detail-stat">
                                        <span class="detail-stat-label">费用</span>
                                        <span class="detail-stat-value" style="color: var(--accent-success);">$${s.cost.toFixed(4)}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="model-empty-state">
                <div class="empty-icon">📭</div>
                <div class="empty-title">近 ${data.period} 无请求记录</div>
                <div class="empty-desc">开始调用 API 后将显示统计数据</div>
            </div>
        `;
    }
}

// Test Channel
async function testChannel(id) {
    const btn = document.getElementById(`test-btn-${id}`);
    const latencyCell = document.getElementById(`latency-${id}`);
    const originalText = btn.textContent;

    btn.textContent = '测试中...';
    btn.disabled = true;
    btn.style.opacity = '0.6';
    latencyCell.innerHTML = '<span style="color: var(--text-muted); font-family: JetBrains Mono; font-size: 12px;">...</span>';

    try {
        const res = await fetchWithAuth(`/admin/channels/${id}/test`, {
            method: 'POST'
        });
        const data = await res.json();

        if (data.success) {
            latencyCell.innerHTML = `<span style="color: var(--success); font-family: JetBrains Mono; font-size: 12px; font-weight: 600;">${data.latency_ms}ms</span>`;
            btn.textContent = '✓';
            btn.style.borderColor = 'rgba(34, 197, 94, 0.5)';
            btn.style.color = 'var(--success)';
            btn.style.background = 'rgba(34, 197, 94, 0.1)';
        } else {
            latencyCell.innerHTML = `<span style="color: var(--error); font-family: JetBrains Mono; font-size: 12px;">错误</span>`;
            btn.textContent = '✗';
            btn.style.borderColor = 'rgba(239, 68, 68, 0.5)';
            btn.style.color = 'var(--error)';
            btn.style.background = 'rgba(239, 68, 68, 0.1)';
            console.error('Test failed:', data.error);
        }

        setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.borderColor = 'rgba(0, 217, 255, 0.3)';
            btn.style.color = 'var(--accent)';
            btn.style.background = '';
        }, 3000);

    } catch (e) {
        latencyCell.innerHTML = `<span style="color: var(--error); font-family: JetBrains Mono; font-size: 12px;">Error</span>`;
        btn.textContent = '✗';
        btn.style.borderColor = 'rgba(239, 68, 68, 0.5)';
        btn.style.color = 'var(--error)';
        console.error('Test error:', e);

        setTimeout(() => {
            btn.textContent = originalText;
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.borderColor = 'rgba(0, 217, 255, 0.3)';
            btn.style.color = 'var(--accent)';
            btn.style.background = '';
        }, 3000);
    }
}

// Modal close on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.classList.remove('show');
        }
    });
});

// Initialize
loadStats();
loadKeys();
loadChannels();
loadPrices();
loadModelStats(168);

// Refresh stats periodically
setInterval(loadStats, 30000);
setInterval(() => loadModelStats(168), 30000);