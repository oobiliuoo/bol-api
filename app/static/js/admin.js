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

// ============ Toast 通知系统 ============
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    const icons = { success: '✓', error: '✗', warning: '⚠', info: '●' };
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || '●'}</span> ${message}`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease-in forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// ============ 确认对话框 ============
let confirmCallback = null;

function showConfirm(title, message, cb) {
    confirmCallback = cb;
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-msg').textContent = message;
    document.getElementById('confirm-overlay').classList.add('show');
}

function confirmCancel() {
    confirmCallback = null;
    document.getElementById('confirm-overlay').classList.remove('show');
}

function confirmOk() {
    document.getElementById('confirm-overlay').classList.remove('show');
    if (confirmCallback) {
        confirmCallback();
        confirmCallback = null;
    }
}

// 点击遮罩取消确认
document.getElementById('confirm-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) confirmCancel();
});

// ============ 加载状态管理 ============
function showTableLoading(tbody, columns) {
    const rows = Array.from({ length: 4 }, () => {
        const row = document.createElement('tr');
        row.className = 'skeleton-row';
        const td = document.createElement('td');
        td.colSpan = columns;
        row.appendChild(td);
        return row;
    });
    tbody.innerHTML = '';
    rows.forEach(r => tbody.appendChild(r));
    tbody.dataset.loading = 'true';
}

function hideTableLoading(tbody) {
    tbody.dataset.loading = '';
}

// ============ Escape 关闭模态框 ============
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.show').forEach(m => m.classList.remove('show'));
        document.getElementById('confirm-overlay').classList.remove('show');
    }
});

// Stats
async function loadStats() {
    try {
        const res = await fetchWithAuth('/stats/summary');
        if (!res.ok) { showToast('加载统计数据失败', 'error'); return; }
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
    } catch (e) {
        showToast('加载统计数据失败: ' + e.message, 'error');
    }
}

function formatNumber(n) {
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n/1000).toFixed(1) + 'K';
    return n;
}

function formatDate(s) {
    return new Date(s).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
}

function formatLatency(ms) {
    return (ms / 1000).toFixed(1) + 's';
}


// Keys
async function loadKeys() {
    const tbody = document.querySelector('#keys-table tbody');
    showTableLoading(tbody, 6);

    try {
        const res = await fetchWithAuth('/admin/keys');
        if (!res.ok) { showToast('加载密钥失败', 'error'); hideTableLoading(tbody); return; }
        const keys = await res.json();
        hideTableLoading(tbody);

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
                <td><span class="font-mono text-muted">#${k.id}</span></td>
                <td>${k.name || '<span class="text-muted">—</span>'}</td>
                <td>
                    <div class="key-actions">
                        <span class="font-mono-sm text-muted" id="key-display-${k.id}">${k.key_prefix || 'bol-xxx...'}</span>
                        <button class="btn btn-sm" onclick="toggleKeyVisibility(${k.id})" id="key-toggle-${k.id}">显示</button>
                        <button class="btn btn-sm" onclick="copyFullKey(${k.id})" id="key-copy-${k.id}">复制</button>
                    </div>
                </td>
                <td>
                    <span class="toggle-switch ${k.is_active ? 'active' : ''}" onclick="toggleKey(${k.id}, ${!k.is_active})">
                        <span class="toggle-track"><span class="toggle-thumb"></span></span>
                        <span class="toggle-label">${k.is_active ? '启用' : '禁用'}</span>
                    </span>
                </td>
                <td><span class="font-mono-sm text-muted">${formatDate(k.created_at)}</span></td>
                <td>
                    <div class="action-btns">
                        <button class="btn btn-danger" onclick="deleteKey(${k.id})">删除</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        hideTableLoading(tbody);
        showToast('加载密钥失败: ' + e.message, 'error');
    }
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
    const action = isActive ? '启用' : '禁用';
    showConfirm(`${action}密钥`, `确定${action}此 API 密钥？`, async () => {
        await fetchWithAuth(`/admin/keys/${id}?is_active=${isActive}`, {method: 'PATCH'});
        showToast(`密钥已${action}`, 'success');
        loadKeys();
    });
}

async function deleteKey(id) {
    showConfirm('删除 API 密钥', '确定删除此 API 密钥？此操作不可恢复。', async () => {
        await fetchWithAuth(`/admin/keys/${id}`, {method: 'DELETE'});
        showToast('密钥已删除', 'success');
        loadKeys();
    });
}

// Channels
async function loadChannels() {
    const tbody = document.querySelector('#channels-table tbody');
    showTableLoading(tbody, 7);

    try {
        const res = await fetchWithAuth('/admin/channels');
        if (!res.ok) { showToast('加载渠道失败', 'error'); hideTableLoading(tbody); return; }
        const channels = await res.json();
        hideTableLoading(tbody);

        if (channels.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7">
                        <div class="empty-state">
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
                <td><span class="font-mono text-muted">#${c.id}</span></td>
                <td>${c.name}</td>
                <td>
                    <span class="provider-badge provider-${c.api_protocol || 'openai'}">${c.api_protocol || 'openai'}</span>
                </td>
                <td>
                    <div class="model-tags">
                        ${c.models.length > 0
                            ? c.models.map(m => `<span class="model-tag">${m}</span>`).join('')
                            : '<span class="text-muted">全部</span>'
                        }
                    </div>
                </td>
                <td>
                    <span class="toggle-switch ${c.is_active ? 'active' : ''}" onclick="toggleChannel(${c.id}, ${!c.is_active})">
                        <span class="toggle-track"><span class="toggle-thumb"></span></span>
                        <span class="toggle-label">${c.is_active ? '启用' : '禁用'}</span>
                    </span>
                </td>
                <td id="latency-${c.id}">
                    <span class="font-mono-sm text-muted">—</span>
                </td>
                <td>
                    <div class="action-btns">
                        <button class="btn btn-sm btn-test" onclick="testChannel(${c.id})" id="test-btn-${c.id}">测试</button>
                        <button class="btn btn-sm btn-edit" onclick="editChannel(${c.id})">编辑</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteChannel(${c.id})">删除</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        hideTableLoading(tbody);
        showToast('加载渠道失败: ' + e.message, 'error');
    }
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
    document.getElementById('channel-type').value = 'openai';
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
    const saveBtn = document.querySelector('#channel-modal .btn-primary');
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中...';
    saveBtn.style.opacity = '0.6';

    try {
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
            showToast('请填写渠道名称和基础 URL', 'warning');
            saveBtn.disabled = false;
            saveBtn.textContent = '保存';
            saveBtn.style.opacity = '1';
            return;
        }

        if (editingChannelId && !data.api_key) {
            delete data.api_key;
        } else if (!editingChannelId && !data.api_key) {
            showToast('新渠道必须填写 API 密钥', 'warning');
            saveBtn.disabled = false;
            saveBtn.textContent = '保存';
            saveBtn.style.opacity = '1';
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
        showToast(editingChannelId ? '渠道已更新' : '渠道已创建', 'success');
        loadChannels();
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
        saveBtn.disabled = false;
        saveBtn.textContent = '保存';
        saveBtn.style.opacity = '1';
    }
}

async function toggleChannel(id, is_active) {
    const action = is_active ? '启用' : '禁用';
    showConfirm(`${action}渠道`, `确定${action}此渠道？`, async () => {
        await fetchWithAuth(`/admin/channels/${id}/toggle`, {
            method: 'POST',
            body: JSON.stringify({is_active})
        });
        showToast(`渠道已${action}`, 'success');
        loadChannels();
    });
}

async function deleteChannel(id) {
    showConfirm('删除渠道', '确定删除此渠道？此操作不可恢复。', async () => {
        await fetchWithAuth(`/admin/channels/${id}`, {method: 'DELETE'});
        showToast('渠道已删除', 'success');
        loadChannels();
    });
}

// Prices
let editingPriceId = null;

async function loadPrices() {
    const tbody = document.querySelector('#prices-table tbody');
    showTableLoading(tbody, 6);

    try {
        const res = await fetchWithAuth('/admin/prices');
        if (!res.ok) { showToast('加载价格数据失败', 'error'); hideTableLoading(tbody); return; }
        const prices = await res.json();
        hideTableLoading(tbody);

        if (prices.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6">
                        <div class="empty-state">
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
                <td><span class="font-mono text-muted">#${p.id}</span></td>
                <td class="font-mono">${p.model}</td>
                <td class="font-mono">$${p.input_price.toFixed(2)}/M</td>
                <td class="font-mono">$${p.output_price.toFixed(2)}/M</td>
                <td>
                    <span class="toggle-switch ${p.is_active ? 'active' : ''}" onclick="togglePrice(${p.id}, ${!p.is_active})">
                        <span class="toggle-track"><span class="toggle-thumb"></span></span>
                        <span class="toggle-label">${p.is_active ? '启用' : '禁用'}</span>
                    </span>
                </td>
                <td>
                    <div class="action-btns">
                        <button class="btn btn-sm btn-edit" onclick="editPrice(${p.id})">编辑</button>
                        <button class="btn btn-sm btn-danger" onclick="deletePrice(${p.id})">删除</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        hideTableLoading(tbody);
        showToast('加载价格数据失败: ' + e.message, 'error');
    }
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
    const saveBtn = document.querySelector('#price-modal .btn-primary');
    saveBtn.disabled = true;
    saveBtn.textContent = '保存中...';
    saveBtn.style.opacity = '0.6';

    try {
        const model = document.getElementById('price-model').value.trim();
        const inputPrice = parseFloat(document.getElementById('price-input').value) || 0;
        const outputPrice = parseFloat(document.getElementById('price-output').value) || 0;

        if (!model) {
            showToast('请填写模型名称', 'warning');
            saveBtn.disabled = false;
            saveBtn.textContent = '保存';
            saveBtn.style.opacity = '1';
            return;
        }

        const data = { model, input_price: inputPrice, output_price: outputPrice };

        if (editingPriceId) {
            await fetchWithAuth(`/admin/prices/${editingPriceId}`, {
                method: 'PATCH', body: JSON.stringify(data)
            });
        } else {
            await fetchWithAuth('/admin/prices', {
                method: 'POST', body: JSON.stringify(data)
            });
        }
        closePriceModal();
        showToast(editingPriceId ? '价格已更新' : '价格已创建', 'success');
        loadPrices();
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
        saveBtn.disabled = false;
        saveBtn.textContent = '保存';
        saveBtn.style.opacity = '1';
    }
}

async function togglePrice(id, is_active) {
    const action = is_active ? '启用' : '禁用';
    showConfirm(`${action}价格配置`, `确定${action}此价格配置？`, async () => {
        await fetchWithAuth(`/admin/prices/${id}/toggle`, {
            method: 'POST',
            body: JSON.stringify({is_active})
        });
        showToast(`价格配置已${action}`, 'success');
        loadPrices();
    });
}

async function deletePrice(id) {
    showConfirm('删除价格配置', '确定删除此价格配置？', async () => {
        await fetchWithAuth(`/admin/prices/${id}`, {method: 'DELETE'});
        showToast('价格配置已删除', 'success');
        loadPrices();
    });
}

// 日历周期映射
const PERIOD_MAP = {
    'today': { hours: 24, label: '本日', apiPeriod: 'today' },
    'week':  { hours: 168, label: '本周', apiPeriod: 'week' },
    'month': { hours: 720, label: '本月', apiPeriod: 'month' },
};

// Model Stats
let currentPeriod = '';  // 当前日历周期，同步给趋势图
let lastStatsPeriod = 'today';  // 最近选择的周期，自动刷新时沿用

async function loadModelStats(hours) {
    lastStatsPeriod = hours;  // 记录当前选择，供自动刷新使用
    const tabs = document.querySelectorAll('.period-tab-inline');
    tabs.forEach(tab => { tab.classList.remove('active'); });

    let periodParam = '';
    currentPeriod = '';
    if (typeof hours === 'string') {
        const p = PERIOD_MAP[hours];
        if (p) {
            document.getElementById('model-stats-period').textContent = p.label;
            periodParam = `&period=${p.apiPeriod}`;
            tabs.forEach(tab => { if (tab.textContent === p.label) tab.classList.add('active'); });
            currentPeriod = p.apiPeriod;
            hours = p.hours;
        }
    } else {
        document.getElementById('model-stats-period').textContent = hours < 24 ? `${hours}时` : `${hours / 24}天`;
        tabs.forEach(tab => {
            if (tab.textContent === '5时' && hours === 5) tab.classList.add('active');
        });
    }

    const container = document.getElementById('model-stats-container');

    let data;
    try {
        const res = await fetchWithAuth(`/stats/models?hours=${hours}${periodParam}`);
        if (!res.ok) { container.innerHTML = '<div class="error-banner show">加载模型统计数据失败</div>'; return; }
        data = await res.json();
    } catch (e) {
        container.innerHTML = `<div class="error-banner show">加载模型统计数据失败: ${e.message}</div>`;
        return;
    }

    const trendUrl = `/stats/trend?hours=${hours}${periodParam}`;
    renderStatsAndTrend(container, data);
    if (data.stats && data.stats.length > 0) {
        loadTrendData(hours, currentPeriod);
    }
}

async function loadModelStatsData(modelsUrl, trendUrl) {
    const container = document.getElementById('model-stats-container');
    let data;
    try {
        const res = await fetchWithAuth(modelsUrl);
        if (!res.ok) { container.innerHTML = '<div class="error-banner show">加载失败</div>'; return; }
        data = await res.json();
    } catch (e) {
        container.innerHTML = `<div class="error-banner show">加载失败: ${e.message}</div>`;
        return;
    }
    renderStatsAndTrend(container, data);
    if (data.stats && data.stats.length > 0 && trendUrl) {
        loadTrendData(trendUrl);
    }
}

async function renderStatsAndTrend(container, data) {
    const colors = [
        '#00d9ff', '#7b61ff', '#ff00aa', '#ff8c00', '#00ff88',
        '#ff3355', '#00aa88', '#aa00ff', '#88ff00', '#ff0088'
    ];
    const totalInputTokens = data.stats ? data.stats.reduce((sum, s) => sum + s.request_tokens, 0) : 0;
    const totalOutputTokens = data.stats ? data.stats.reduce((sum, s) => sum + s.response_tokens, 0) : 0;

    if (data.stats && data.stats.length > 0) {
        container.innerHTML = `
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
                <div class="model-summary-card">
                    <div class="summary-icon" style="color: var(--accent-primary);">⏱</div>
                    <div class="summary-content">
                        <div class="summary-value">${formatLatency(data.total_p50)}</div>
                        <div class="summary-label">P50 延迟</div>
                    </div>
                </div>
                <div class="model-summary-card">
                    <div class="summary-icon" style="color: var(--accent-error);">⚡</div>
                    <div class="summary-content">
                        <div class="summary-value">${formatLatency(data.total_peak)}</div>
                        <div class="summary-label">峰值延迟</div>
                    </div>
                </div>
                <div class="model-summary-card">
                    <div class="summary-icon" style="color: ${data.total_error_rate > 5 ? 'var(--accent-error)' : 'var(--accent-warning)'};">⚠</div>
                    <div class="summary-content">
                        <div class="summary-value">${data.total_error_rate}%</div>
                        <div class="summary-label">错误率 (${data.total_errors})</div>
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
                                    <div class="detail-stat">
                                        <span class="detail-stat-label">P50</span>
                                        <span class="detail-stat-value" style="color: var(--accent-primary);">${formatLatency(s.p50_latency)}</span>
                                    </div>
                                    <div class="detail-stat">
                                        <span class="detail-stat-label">峰值</span>
                                        <span class="detail-stat-value" style="color: var(--accent-secondary);">${formatLatency(s.peak_latency)}</span>
                                    </div>
                                    <div class="detail-stat">
                                        <span class="detail-stat-label">错误</span>
                                        <span class="detail-stat-value" style="color: ${s.error_rate > 5 ? 'var(--accent-error)' : 'var(--text-muted)'};">${s.error_rate}% (${s.error_count})</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
        // 趋势图由调用者通过 loadTrendData 加载
    } else {
        container.innerHTML = `
            <div class="model-empty-state">
                <div class="empty-icon">📭</div>
                <div class="empty-title">${data.period} 无请求记录</div>
                <div class="empty-desc">开始调用 API 后将显示统计数据</div>
            </div>
        `;
        // 清空趋势图
        const trendContainer = document.querySelector('.trend-chart-section');
        if (trendContainer) trendContainer.style.display = 'none';
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
    latencyCell.innerHTML = '<span class="font-mono-sm text-muted">...</span>';

    function resetBtn() {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.className = 'btn btn-sm btn-test';
    }

    try {
        const res = await fetchWithAuth(`/admin/channels/${id}/test`, {
            method: 'POST'
        });
        const data = await res.json();

        if (data.success) {
            latencyCell.innerHTML = `<span class="font-mono-sm text-success" style="font-weight:600;">${data.latency_ms}ms</span>`;
            btn.textContent = '✓';
            btn.className = 'btn btn-sm';
            btn.style.borderColor = 'rgba(34, 197, 94, 0.5)';
            btn.style.color = 'var(--accent-success)';
            btn.style.background = 'rgba(34, 197, 94, 0.1)';
        } else {
            latencyCell.innerHTML = '<span class="font-mono-sm text-error">错误</span>';
            btn.textContent = '✗';
            btn.className = 'btn btn-sm';
            btn.style.borderColor = 'rgba(239, 68, 68, 0.5)';
            btn.style.color = 'var(--accent-error)';
            btn.style.background = 'rgba(239, 68, 68, 0.1)';
        }

        setTimeout(resetBtn, 3000);
    } catch (e) {
        latencyCell.innerHTML = '<span class="font-mono-sm text-error">Error</span>';
        btn.textContent = '✗';
        btn.className = 'btn btn-sm';
        btn.style.borderColor = 'rgba(239, 68, 68, 0.5)';
        btn.style.color = 'var(--accent-error)';
        setTimeout(resetBtn, 3000);
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

// Logs
let logsPage = 1;
const logsPageSize = 50;

async function loadLogs(page = 1) {
    logsPage = page;
    const days = document.getElementById('logs-days').value;
    const model = document.getElementById('logs-model').value;
    const status = document.getElementById('logs-status').value;

    let url = `/stats/logs?days=${days}&page=${page}&page_size=${logsPageSize}`;
    if (model) url += `&model=${encodeURIComponent(model)}`;
    if (status) url += `&status=${status}`;

    try {
        const res = await fetchWithAuth(url);
        if (!res.ok) { showToast('加载日志失败', 'error'); return; }
        const data = await res.json();
        renderLogs(data.logs);
        renderLogsPagination(data.total, data.page, data.total_pages);
        renderLogsSummary(data.summary);
    } catch (e) {
        showToast('加载日志失败: ' + e.message, 'error');
    }
}

async function loadLogsModels() {
    const days = document.getElementById('logs-days').value;
    try {
        const res = await fetchWithAuth(`/stats/models/list?days=${days}`);
        if (!res.ok) return;
        const data = await res.json();
        const select = document.getElementById('logs-model');
        select.innerHTML = '<option value="">全部模型</option>';
        for (const m of data.models) {
            select.innerHTML += `<option value="${m}">${m}</option>`;
        }
    } catch (e) {}
}

function renderLogsSummary(summary) {
    const container = document.getElementById('logs-summary');
    if (!summary) {
        container.innerHTML = '';
        return;
    }
    const successRate = summary.total_requests > 0
        ? ((summary.success_count / summary.total_requests) * 100).toFixed(1)
        : 0;
    container.innerHTML = `
        <div class="logs-summary-grid">
            <div class="logs-summary-card">
                <div class="summary-value">${summary.total_requests}</div>
                <div class="summary-label">总请求</div>
            </div>
            <div class="logs-summary-card">
                <div class="summary-value">${formatNumber(summary.total_input)}</div>
                <div class="summary-label">输入 Tokens</div>
            </div>
            <div class="logs-summary-card">
                <div class="summary-value">${formatNumber(summary.total_output)}</div>
                <div class="summary-label">输出 Tokens</div>
            </div>
            <div class="logs-summary-card">
                <div class="summary-value">$${summary.total_cost.toFixed(4)}</div>
                <div class="summary-label">总费用</div>
            </div>
            <div class="logs-summary-card">
                <div class="summary-value">${summary.avg_latency}ms</div>
                <div class="summary-label">平均延迟</div>
            </div>
            <div class="logs-summary-card">
                <div class="summary-value" style="color: var(--accent-success);">${successRate}%</div>
                <div class="summary-label">成功率 (${summary.success_count}/${summary.total_requests})</div>
            </div>
        </div>
    `;
}

function renderLogs(logs) {
    const tbody = document.querySelector('#logs-table tbody');
    tbody.innerHTML = '';
    for (const log of logs) {
        const statusClass = log.status_code === 200 ? 'status-active' : 'status-inactive';
        const statusText = log.status_code === 200 ? '成功' : log.status_code === 499 ? '取消' : `失败(${log.status_code})`;
        // 转换 UTC 时间为本地时间
        const localTime = new Date(log.timestamp).toLocaleString('zh-CN', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false
        }).replace(/\//g, '-');
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${localTime}</td>
            <td>${log.model}</td>
            <td>${log.request_tokens.toLocaleString()}</td>
            <td>${log.response_tokens.toLocaleString()}</td>
            <td>$${log.cost.toFixed(4)}</td>
            <td>${log.latency_ms}ms</td>
            <td><span class="${statusClass}">${statusText}</span></td>
        `;
        tbody.appendChild(row);
    }
}

function renderLogsPagination(total, page, totalPages) {
    const container = document.getElementById('logs-pagination');
    if (totalPages <= 1) {
        container.innerHTML = `<span class="pagination-info">共 ${total} 条</span>`;
        return;
    }
    let html = `<span class="pagination-info">共 ${total} 条</span>`;
    html += `<button class="btn" ${page <= 1 ? 'disabled' : ''} onclick="loadLogs(${page - 1})">上一页</button>`;
    html += `<span class="pagination-page">${page} / ${totalPages}</span>`;
    html += `<button class="btn" ${page >= totalPages ? 'disabled' : ''} onclick="loadLogs(${page + 1})">下一页</button>`;
    container.innerHTML = html;
}

// Trend Chart
let trendData = null;
let currentTrendMetric = 'requests';
const trendColors = [
    '#00d9ff', '#7b61ff', '#ff00aa', '#ff8c00', '#00ff88',
    '#ff3355', '#00aa88', '#aa00ff', '#88ff00', '#ff0088'
];

async function loadTrendData(hours, period) {
    let url;
    if (typeof hours === 'string' && hours.startsWith('/')) {
        url = hours;  // 直接传入完整 URL
    } else {
        let periodParam = period ? `&period=${period}` : '';
        url = `/stats/trend?hours=${hours}${periodParam}`;
    }
    try {
        const res = await fetchWithAuth(url);
        if (!res.ok) return;
        trendData = await res.json();
        const trendContainer = document.querySelector('.trend-chart-section');
        if (trendContainer) trendContainer.style.display = '';
        renderTrendChart(currentTrendMetric);
    } catch (e) {
        console.warn('Failed to load trend data:', e);
    }
}

function computeTotalSeries(data) {
    const timeMap = {};
    for (const s of data.series) {
        if (s.model === '总请求') continue;
        for (const d of s.data) {
            if (!timeMap[d.time]) {
                timeMap[d.time] = { time: d.time, requests: 0, tokens: 0, cost: 0.0 };
            }
            timeMap[d.time].requests += d.requests || 0;
            timeMap[d.time].tokens += d.tokens || 0;
            timeMap[d.time].cost += (d.cost || 0);
        }
    }
    const sortedData = Object.values(timeMap).sort((a, b) => a.time.localeCompare(b.time));
    return { model: '总请求', data: sortedData };
}

function renderTrendChart(metric) {
    currentTrendMetric = metric;
    const canvas = document.getElementById('trend-canvas');
    const legendContainer = document.getElementById('trend-legend');
    if (!canvas || !trendData || !trendData.series || trendData.series.length === 0) {
        if (legendContainer) legendContainer.innerHTML = '';
        return;
    }

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

    if (!canvas._seriesHidden) {
        canvas._seriesHidden = {};
        trendData.series.forEach(s => { canvas._seriesHidden[s.model] = false; });
    }

    // 注入总请求线（如果不存在）
    const totalIdx = trendData.series.findIndex(s => s.model === '总请求');
    if (totalIdx === -1) {
        const totalSeries = computeTotalSeries(trendData);
        trendData.series.push(totalSeries);
        canvas._seriesHidden['总请求'] = false;
    }

    drawTrendChart(ctx, cssWidth, cssHeight, trendData, metric, canvas._seriesHidden);
    renderTrendLegend(legendContainer, trendData, canvas);
}

function drawTrendChart(ctx, width, height, data, metric, hiddenMap) {
    const padding = { top: 20, right: 20, bottom: 36, left: 56 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    let allValues = [];
    data.series.forEach(s => {
        if (hiddenMap[s.model]) return;
        s.data.forEach(d => allValues.push(d[metric]));
    });

    if (allValues.length === 0) {
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.font = '12px JetBrains Mono, monospace';
        ctx.textAlign = 'center';
        ctx.fillText('没有可见数据', width / 2, height / 2);
        return;
    }

    const maxVal = Math.max(...allValues);
    const roundedMax = roundUpNice(maxVal);

    const firstSeries = data.series.find(s => !hiddenMap[s.model]) || data.series[0];
    const times = firstSeries.data.map(d => new Date(d.time));
    const minTime = times[0];
    const maxTime = times[times.length - 1];
    const timeRange = maxTime - minTime || 1;

    ctx.clearRect(0, 0, width, height);

    // Grid lines
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

    // X-axis labels
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

    // Draw lines for each model
    data.series.forEach((s, idx) => {
        if (hiddenMap[s.model]) return;
        const isTotal = s.model === '总请求';
        const color = isTotal ? '#ffd700' : trendColors[idx % trendColors.length];
        const points = s.data.map(d => ({
            x: padding.left + ((new Date(d.time) - minTime) / timeRange) * chartW,
            y: padding.top + chartH - (d[metric] / roundedMax) * chartH,
        }));

        // Area fill (总请求线不填充区域)
        if (!isTotal) {
            ctx.beginPath();
            ctx.moveTo(points[0].x, padding.top + chartH);
            points.forEach(p => ctx.lineTo(p.x, p.y));
            ctx.lineTo(points[points.length - 1].x, padding.top + chartH);
            ctx.closePath();
            ctx.fillStyle = hexToRgba(color, 0.1);
            ctx.fill();
        }

        // Line
        ctx.beginPath();
        if (isTotal) {
            ctx.setLineDash([6, 4]);
        } else {
            ctx.setLineDash([]);
        }
        points.forEach((p, i) => {
            if (i === 0) ctx.moveTo(p.x, p.y);
            else ctx.lineTo(p.x, p.y);
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = isTotal ? 2.5 : 2;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.stroke();
        ctx.setLineDash([]);

        // Data dots
        const dotInterval = Math.max(1, Math.floor(points.length / 15));
        points.forEach((p, i) => {
            if (i % dotInterval === 0 || i === points.length - 1) {
                if (isTotal) {
                    // 菱形标记
                    ctx.beginPath();
                    ctx.moveTo(p.x, p.y - 4);
                    ctx.lineTo(p.x + 4, p.y);
                    ctx.lineTo(p.x, p.y + 4);
                    ctx.lineTo(p.x - 4, p.y);
                    ctx.closePath();
                    ctx.fillStyle = color;
                    ctx.fill();
                    ctx.strokeStyle = 'rgba(0,0,0,0.3)';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                } else {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
                    ctx.fillStyle = color;
                    ctx.fill();
                    ctx.strokeStyle = 'rgba(0,0,0,0.3)';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }
            }
        });
    });

    ctx.canvas._trendData = { data, metric, hiddenMap, padding, chartW, chartH, minTime, timeRange, roundedMax };
}

function renderTrendLegend(container, data, canvas) {
    if (!container) return;
    let html = '';
    data.series.forEach((s, idx) => {
        const isTotal = s.model === '总请求';
        const color = isTotal ? '#ffd700' : trendColors[idx % trendColors.length];
        const hidden = canvas._seriesHidden[s.model] ? ' hidden' : '';
        const dashClass = isTotal ? ' trend-legend-dash' : '';
        html += `
            <div class="trend-legend-item${hidden}${dashClass}" data-model="${s.model}">
                <span class="trend-legend-color" style="background: ${color};${isTotal ? ' border-style: dashed; border-width: 1px 0; height: 1px;' : ''}"></span>
                ${s.model}
            </div>
        `;
    });
    container.innerHTML = html;

    container.querySelectorAll('.trend-legend-item').forEach(el => {
        el.addEventListener('click', () => {
            const model = el.dataset.model;
            if (model === '总请求') {
                const allModels = trendData.series.map(s => s.model);
                const otherModels = allModels.filter(m => m !== '总请求');
                const othersAllHidden = otherModels.every(m => canvas._seriesHidden[m]);
                if (canvas._seriesHidden['总请求']) {
                    // 总请求被隐藏 → 显示总请求，隐藏其它
                    canvas._seriesHidden['总请求'] = false;
                    otherModels.forEach(m => { canvas._seriesHidden[m] = true; });
                } else if (othersAllHidden) {
                    // 只有总请求可见 → 恢复全部
                    allModels.forEach(m => { canvas._seriesHidden[m] = false; });
                } else {
                    // 总请求可见且其它也可见 → 隐藏其它
                    otherModels.forEach(m => { canvas._seriesHidden[m] = true; });
                }
            } else {
                canvas._seriesHidden[model] = !canvas._seriesHidden[model];
            }
            renderTrendChart(currentTrendMetric);
        });
    });
}

function switchTrendMetric(metric) {
    currentTrendMetric = metric;
    document.querySelectorAll('.trend-metric-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.metric === metric);
    });
    renderTrendChart(metric);
}

// Canvas mouse hover tooltip
(function() {
    const canvas = document.getElementById('trend-canvas');
    if (!canvas) return;
    const tooltip = document.createElement('div');
    tooltip.className = 'trend-tooltip';
    tooltip.id = 'trend-tooltip';
    document.body.appendChild(tooltip);

    canvas.addEventListener('mousemove', (e) => {
        const data = canvas._trendData;
        if (!data) { tooltip.style.display = 'none'; return; }

        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;

        const { data: trendResp, metric, hiddenMap, padding, chartW, chartH, minTime, timeRange, roundedMax } = data;
        const firstVisible = trendResp.series.find(s => !hiddenMap[s.model]);
        if (!firstVisible) { tooltip.style.display = 'none'; return; }

        const times = firstVisible.data.map(d => new Date(d.time));
        const relX = mouseX - padding.left;
        const pct = relX / chartW;
        const targetTime = minTime.getTime() + pct * timeRange;

        let nearestIdx = 0;
        let nearestDist = Infinity;
        times.forEach((t, i) => {
            const dist = Math.abs(t - targetTime);
            if (dist < nearestDist) { nearestDist = dist; nearestIdx = i; }
        });

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
        tooltip.style.display = 'block';

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
})();

// Tab switching
function switchTab(tabName) {
    // Update tab buttons
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(tab => tab.classList.remove('active'));
    document.querySelector(`.tab-btn[onclick="switchTab('${tabName}')"]`).classList.add('active');

    // Update tab content
    const contents = document.querySelectorAll('.tab-content');
    contents.forEach(content => content.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.add('active');

    // Load data for the tab if needed
    if (tabName === 'logs') {
        loadLogsModels();
        loadLogs();
    }
    if (tabName === 'keys') loadKeys();
    if (tabName === 'channels') loadChannels();
    if (tabName === 'prices') loadPrices();
}

// 自定义时间段
function toggleCustomPeriod() {
    const picker = document.getElementById('custom-period-picker');
    const tabs = document.querySelectorAll('.period-tab-inline');
    tabs.forEach(t => t.classList.remove('active'));

    if (picker.classList.contains('show')) {
        picker.classList.remove('show');
        // 恢复默认高亮
        tabs.forEach(t => { if (t.textContent === '本日') t.classList.add('active'); });
        loadModelStats('today');
        return;
    }

    // 设置默认值：近1小时
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 3600000);
    document.getElementById('custom-start').value = oneHourAgo.toISOString().slice(0, 16);
    document.getElementById('custom-end').value = now.toISOString().slice(0, 16);
    picker.classList.add('show');
    // 高亮"自定义"按钮
    tabs.forEach(t => { if (t.textContent === '自定义') t.classList.add('active'); });
}

function toUTCDate(localStr) {
    if (!localStr) return null;
    return new Date(localStr);
}

async function applyCustomPeriod() {
    const startStr = document.getElementById('custom-start').value;
    const endStr = document.getElementById('custom-end').value;
    if (!startStr || !endStr) {
        showToast('请选择起止时间', 'warning');
        return;
    }
    const start = toUTCDate(startStr);
    const end = toUTCDate(endStr);
    if (end <= start) {
        showToast('结束时间必须晚于开始时间', 'warning');
        return;
    }
    const spanHours = (end - start) / 3600000;
    const tabs = document.querySelectorAll('.period-tab-inline');
    tabs.forEach(t => t.classList.remove('active'));
    tabs.forEach(t => { if (t.textContent === '自定义') t.classList.add('active'); });
    document.getElementById('model-stats-period').textContent = '自定义';
    window._customRange = { start: start.toISOString(), end: end.toISOString() };
    currentPeriod = 'custom';
    lastStatsPeriod = 'custom';
    await loadModelStatsData(
        `/stats/models?hours=${Math.round(spanHours)}&start_time=${start.toISOString()}&end_time=${end.toISOString()}`,
        `/stats/trend?hours=${Math.round(spanHours)}&start_time=${start.toISOString()}&end_time=${end.toISOString()}`
    );
}

// Initialize
loadStats();
loadModelStats('today');
loadKeys();
loadChannels();
loadPrices();

// Refresh stats periodically（沿用当前周期选择，自定义时段不自动刷新）
setInterval(loadStats, 30000);
setInterval(() => { if (lastStatsPeriod !== 'custom') loadModelStats(lastStatsPeriod); }, 30000);

// Settings
async function showSettingsModal() {
    try {
        const res = await fetchWithAuth('/admin/settings');
        if (!res.ok) { showToast('加载设置失败', 'error'); return; }
        const data = await res.json();
        document.getElementById('setting-timeout').value = data.request_timeout || 300;
        document.getElementById('settings-modal').classList.add('show');
    } catch (e) {
        showToast('加载设置失败: ' + e.message, 'error');
    }
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.remove('show');
}

async function saveSettings() {
    const timeout = parseInt(document.getElementById('setting-timeout').value);
    if (!timeout || timeout < 30 || timeout > 3600) {
        showToast('超时时间需在 30-3600 秒之间', 'error');
        return;
    }
    try {
        const res = await fetchWithAuth('/admin/settings/request_timeout', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({key: 'request_timeout', value: String(timeout)})
        });
        if (!res.ok) { showToast('保存设置失败', 'error'); return; }
        showToast('设置已保存，超时已更新为 ' + timeout + ' 秒', 'success');
        closeSettingsModal();
    } catch (e) {
        showToast('保存设置失败: ' + e.message, 'error');
    }
}

// ---- 趋势图工具函数 ----
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