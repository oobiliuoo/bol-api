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

    const container = document.getElementById('model-stats-container');

    let data;
    try {
        const res = await fetchWithAuth(`/stats/models?hours=${hours}`);
        if (!res.ok) { container.innerHTML = '<div class="error-banner show">加载模型统计数据失败</div>'; return; }
        data = await res.json();
    } catch (e) {
        container.innerHTML = `<div class="error-banner show">加载模型统计数据失败: ${e.message}</div>`;
        return;
    }

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

// Initialize
loadStats();
loadKeys();
loadChannels();
loadPrices();
loadModelStats(168);

// Refresh stats periodically
setInterval(loadStats, 30000);
setInterval(() => loadModelStats(168), 30000);