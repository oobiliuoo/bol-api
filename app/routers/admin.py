from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session
from app.db.crud import (
    create_channel, get_all_channels, update_channel, delete_channel, toggle_channel,
    create_model_price, get_all_model_prices, update_model_price, delete_model_price,
    toggle_model_price, get_model_price_by_id
)
from app.channels.models import ChannelCreate, ChannelUpdate, ChannelResponse
from app.config import settings
import os

router = APIRouter(tags=["Admin"])


async def get_db():
    async with async_session() as session:
        yield session


def verify_admin(request: Request):
    """验证管理员密码"""
    password = request.query_params.get("password") or request.headers.get("X-Admin-Password")
    if password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return True


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(password: str = None):
    """管理界面首页"""
    if password != settings.admin_password:
        return HTMLResponse(content=get_login_page())
    return HTMLResponse(content=get_admin_html())


@router.post("/admin/login")
async def admin_login(request: Request):
    """管理员登录"""
    body = await request.json()
    password = body.get("password")
    if password == settings.admin_password:
        return {"success": True}
    raise HTTPException(status_code=401, detail="Invalid password")


# 渠道管理
@router.post("/admin/channels", response_model=ChannelResponse)
async def create_channel_route(
    data: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """创建新渠道"""
    channel = await create_channel(
        db,
        name=data.name,
        provider_type=data.provider_type,
        api_protocol=data.api_protocol,
        base_url=data.base_url,
        api_key=data.api_key,
        models=data.models,
        priority=data.priority,
        weight=data.weight
    )
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        provider_type=channel.provider_type,
        api_protocol=channel.api_protocol,
        base_url=channel.base_url,
        models=channel.models,
        is_active=channel.is_active,
        priority=channel.priority,
        weight=channel.weight
    )


@router.get("/admin/channels", response_model=list[ChannelResponse])
async def list_channels(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """列出所有渠道"""
    channels = await get_all_channels(db)
    return [
        ChannelResponse(
            id=c.id,
            name=c.name,
            provider_type=c.provider_type,
            api_protocol=c.api_protocol or "openai",
            base_url=c.base_url,
            models=c.models,
            is_active=c.is_active,
            priority=c.priority,
            weight=c.weight
        )
        for c in channels
    ]


@router.patch("/admin/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel_route(
    channel_id: int,
    data: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """更新渠道"""
    channel = await update_channel(db, channel_id, **data.dict(exclude_unset=True))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        provider_type=channel.provider_type,
        api_protocol=channel.api_protocol or "openai",
        base_url=channel.base_url,
        models=channel.models,
        is_active=channel.is_active,
        priority=channel.priority,
        weight=channel.weight
    )


@router.delete("/admin/channels/{channel_id}")
async def delete_channel_route(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """删除渠道"""
    success = await delete_channel(db, channel_id)
    if not success:
        raise HTTPException(status_code=404, detail="Channel not found")
    return {"message": "Channel deleted"}


@router.post("/admin/channels/{channel_id}/toggle")
async def toggle_channel_route(
    channel_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """切换渠道启用/禁用状态"""
    body = await request.json()
    is_active = body.get("is_active", True)
    channel = await toggle_channel(db, channel_id, is_active)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        provider_type=channel.provider_type,
        api_protocol=channel.api_protocol or "openai",
        base_url=channel.base_url,
        models=channel.models,
        is_active=channel.is_active,
        priority=channel.priority,
        weight=channel.weight
    )


@router.post("/admin/channels/fetch-models")
async def fetch_models_route(
    request: Request,
    _: bool = Depends(verify_admin)
):
    """从上游渠道获取支持的模型列表"""
    from app.utils.http_client import AsyncHttpClient

    body = await request.json()
    base_url = body.get("base_url", "").rstrip("/")
    api_key = body.get("api_key", "")
    api_protocol = body.get("api_protocol", "openai")

    if not base_url or not api_key:
        raise HTTPException(status_code=400, detail="Missing base_url or api_key")

    try:
        # 构建请求头
        if api_protocol == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            # Anthropic没有models端点，返回空列表提示用户手动配置
            return {"models": [], "message": "Anthropic API does not support models listing. Please configure manually."}
        else:
            # OpenAI格式
            headers = {
                "Authorization": f"Bearer {api_key}",
            }
            url = f"{base_url}/v1/models"

            client = await AsyncHttpClient.get_client()
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            models = []
            if "data" in data:
                # OpenAI格式响应
                models = [m["id"] for m in data["data"]]
            elif isinstance(data, list):
                # 某些自定义格式直接返回列表
                models = [m.get("id", m.get("name", "")) for m in data if m.get("id") or m.get("name")]

            return {"models": models, "count": len(models)}

    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg:
            error_msg = "Invalid API key"
        elif "404" in error_msg:
            error_msg = "Models endpoint not found"
        elif "timeout" in error_msg.lower():
            error_msg = "Connection timeout"
        raise HTTPException(status_code=400, detail=error_msg)


@router.post("/admin/channels/{channel_id}/test")
async def test_channel_route(
    channel_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """测试渠道连接"""
    from app.db.crud import get_channel_by_id
    from app.channels.manager import create_provider
    import time

    channel = await get_channel_by_id(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    provider = create_provider(channel)
    api_protocol = channel.api_protocol or "openai"

    # 根据API协议类型发送测试请求
    start_time = time.time()

    try:
        if api_protocol == "anthropic":
            # Anthropic格式请求
            test_request = {
                "model": channel.models[0] if channel.models else "claude-3-haiku-20240307",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Hi"}]
            }
        else:
            # OpenAI格式请求
            test_request = {
                "model": channel.models[0] if channel.models else "gpt-3.5-turbo",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Hi"}]
            }

        response = await provider.chat_completion(test_request)
        latency_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "latency_ms": latency_ms,
            "model": test_request["model"],
            "protocol": api_protocol,
            "message": "Connection successful"
        }

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)

        # 解析常见错误
        if "401" in error_msg or "Unauthorized" in error_msg:
            error_msg = "Invalid API key"
        elif "404" in error_msg:
            error_msg = "Model not found or endpoint invalid"
        elif "timeout" in error_msg.lower():
            error_msg = "Connection timeout"

        return {
            "success": False,
            "latency_ms": latency_ms,
            "error": error_msg
        }


# 模型价格管理
@router.get("/admin/prices")
async def list_prices(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """列出所有模型价格配置"""
    prices = await get_all_model_prices(db)
    return [
        {
            "id": p.id,
            "model": p.model,
            "input_price": p.input_price,
            "output_price": p.output_price,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None
        }
        for p in prices
    ]


@router.post("/admin/prices")
async def create_price_route(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """创建模型价格配置"""
    body = await request.json()
    model = body.get("model")
    input_price = body.get("input_price", 0.0)
    output_price = body.get("output_price", 0.0)

    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    price = await create_model_price(db, model, input_price, output_price)
    return {
        "id": price.id,
        "model": price.model,
        "input_price": price.input_price,
        "output_price": price.output_price,
        "is_active": price.is_active
    }


@router.patch("/admin/prices/{price_id}")
async def update_price_route(
    price_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """更新模型价格配置"""
    body = await request.json()
    price = await update_model_price(db, price_id, **body)
    if not price:
        raise HTTPException(status_code=404, detail="Price config not found")
    return {
        "id": price.id,
        "model": price.model,
        "input_price": price.input_price,
        "output_price": price.output_price,
        "is_active": price.is_active
    }


@router.post("/admin/prices/{price_id}/toggle")
async def toggle_price_route(
    price_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """切换模型价格启用/禁用状态"""
    body = await request.json()
    is_active = body.get("is_active", True)
    price = await toggle_model_price(db, price_id, is_active)
    if not price:
        raise HTTPException(status_code=404, detail="Price config not found")
    return {
        "id": price.id,
        "model": price.model,
        "input_price": price.input_price,
        "output_price": price.output_price,
        "is_active": price.is_active
    }


@router.delete("/admin/prices/{price_id}")
async def delete_price_route(
    price_id: int,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin)
):
    """删除模型价格配置"""
    success = await delete_model_price(db, price_id)
    if not success:
        raise HTTPException(status_code=404, detail="Price config not found")
    return {"message": "Price config deleted"}


def get_login_page() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bol-api // Login</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #0a0e14;
            --bg-surface: #131820;
            --bg-elevated: #1a222d;
            --border: #2a3544;
            --text: #c5d1de;
            --text-muted: #6b7d8f;
            --accent: #00d9ff;
            --accent-glow: rgba(0, 217, 255, 0.15);
            --error: #ff5f5f;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-deep);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
        }

        /* Animated grid background */
        body::before {
            content: '';
            position: absolute;
            inset: 0;
            background:
                linear-gradient(90deg, var(--border) 1px, transparent 1px),
                linear-gradient(var(--border) 1px, transparent 1px);
            background-size: 60px 60px;
            opacity: 0.3;
            animation: gridMove 20s linear infinite;
        }

        @keyframes gridMove {
            0% { transform: translate(0, 0); }
            100% { transform: translate(60px, 60px); }
        }

        /* Glow orbs */
        .glow-orb {
            position: absolute;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.4;
            animation: float 8s ease-in-out infinite;
        }

        .glow-orb-1 {
            width: 300px; height: 300px;
            background: var(--accent);
            top: -100px; left: -100px;
        }

        .glow-orb-2 {
            width: 200px; height: 200px;
            background: #7b61ff;
            bottom: -50px; right: -50px;
            animation-delay: -4s;
        }

        @keyframes float {
            0%, 100% { transform: translate(0, 0) scale(1); }
            50% { transform: translate(20px, -20px) scale(1.1); }
        }

        .login-container {
            position: relative;
            z-index: 10;
            animation: fadeInUp 0.6s ease-out;
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .login-box {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 40px 48px;
            width: 380px;
            box-shadow:
                0 0 0 1px var(--bg-elevated),
                0 20px 50px -10px rgba(0, 0, 0, 0.5),
                inset 0 1px 0 rgba(255,255,255,0.05);
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 32px;
        }

        .logo-icon {
            width: 48px; height: 48px;
            background: linear-gradient(135deg, var(--accent), #7b61ff);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            font-size: 20px;
            color: var(--bg-deep);
        }

        .logo-text {
            font-family: 'JetBrains Mono', monospace;
            font-size: 24px;
            font-weight: 500;
            color: var(--text);
        }

        .logo-text span {
            color: var(--accent);
        }

        h2 {
            font-size: 14px;
            font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 24px;
        }

        .input-group {
            position: relative;
            margin-bottom: 20px;
        }

        .input-group label {
            display: block;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 8px;
            font-weight: 500;
        }

        .input-group input {
            width: 100%;
            padding: 14px 16px;
            background: var(--bg-elevated);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            transition: all 0.2s ease;
            outline: none;
        }

        .input-group input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .input-group input::placeholder {
            color: var(--text-muted);
            opacity: 0.5;
        }

        .btn {
            width: 100%;
            padding: 14px 24px;
            background: linear-gradient(135deg, var(--accent), #7b61ff);
            border: none;
            border-radius: 8px;
            color: var(--bg-deep);
            font-family: 'Outfit', sans-serif;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px -4px rgba(0, 217, 255, 0.4);
        }

        .btn:active {
            transform: translateY(0);
        }

        .error-msg {
            color: var(--error);
            font-size: 12px;
            margin-top: 16px;
            text-align: center;
            opacity: 0;
            transition: opacity 0.2s;
        }

        .error-msg.show {
            opacity: 1;
        }
    </style>
</head>
<body>
    <div class="glow-orb glow-orb-1"></div>
    <div class="glow-orb glow-orb-2"></div>

    <div class="login-container">
        <div class="login-box">
            <div class="logo">
                <div class="logo-icon">B</div>
                <div class="logo-text">bol<span>-api</span></div>
            </div>

            <h2>Admin Access</h2>

            <div class="input-group">
                <label>Password</label>
                <input type="password" id="password" placeholder="Enter admin password" autofocus>
            </div>

            <button class="btn" onclick="login()">Authenticate</button>

            <div class="error-msg" id="error">Invalid credentials</div>
        </div>
    </div>

    <script>
        document.getElementById('password').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') login();
        });

        async function login() {
            const password = document.getElementById('password').value;
            const errorMsg = document.getElementById('error');

            const res = await fetch('/admin/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password})
            });

            if (res.ok) {
                localStorage.setItem('admin_password', password);
                window.location.href = '/admin?password=' + password;
            } else {
                errorMsg.classList.add('show');
                setTimeout(() => errorMsg.classList.remove('show'), 2000);
            }
        }
    </script>
</body>
</html>
"""


def get_admin_html() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bol-api // 控制面板</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-deep: #0a0e14;
            --bg-surface: #131820;
            --bg-elevated: #1a222d;
            --bg-card: #1e2733;
            --border: #2a3544;
            --border-light: #3a4555;
            --text: #c5d1de;
            --text-muted: #6b7d8f;
            --text-bright: #e8f0f8;
            --accent: #00d9ff;
            --accent-secondary: #7b61ff;
            --accent-glow: rgba(0, 217, 255, 0.15);
            --success: #22c55e;
            --warning: #f59e0b;
            --error: #ef4444;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg-deep);
            color: var(--text);
            min-height: 100vh;
            line-height: 1.6;
        }

        /* Header */
        .header {
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border);
            padding: 16px 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-icon {
            width: 40px; height: 40px;
            background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            font-size: 18px;
            color: var(--bg-deep);
        }

        .logo-text {
            font-family: 'JetBrains Mono', monospace;
            font-size: 20px;
            font-weight: 500;
        }

        .logo-text span { color: var(--accent); }

        .header-status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: var(--text-muted);
        }

        .status-dot {
            width: 8px; height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* Main container */
        .main {
            padding: 32px;
            max-width: 1400px;
            margin: 0 auto;
        }

        /* Page title */
        .page-title {
            font-size: 32px;
            font-weight: 700;
            color: var(--text-bright);
            margin-bottom: 32px;
            animation: fadeIn 0.4s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 32px;
            animation: fadeInUp 0.5s ease-out;
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .stat-card {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px 24px;
            position: relative;
            overflow: hidden;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .stat-card:hover {
            border-color: var(--border-light);
            transform: translateY(-2px);
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--accent), var(--accent-secondary));
            opacity: 0.6;
        }

        .stat-icon {
            width: 48px; height: 48px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }

        .stat-card:nth-child(1) .stat-icon { background: rgba(0, 217, 255, 0.15); color: var(--accent); }
        .stat-card:nth-child(2) .stat-icon { background: rgba(123, 97, 255, 0.15); color: var(--accent-secondary); }
        .stat-card:nth-child(3) .stat-icon { background: rgba(34, 197, 94, 0.15); color: var(--success); }
        .stat-card:nth-child(4) .stat-icon { background: rgba(245, 158, 11, 0.15); color: var(--warning); }

        .stat-content {
            flex: 1;
        }

        .stat-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 32px;
            font-weight: 700;
            color: var(--text-bright);
            line-height: 1.2;
        }

        .stat-label {
            font-size: 13px;
            color: var(--text-muted);
            font-weight: 500;
            margin-top: 4px;
        }

        .stat-detail {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 2px;
        }

        /* Mini chart bars */
        .stat-mini-chart {
            display: flex;
            align-items: end;
            gap: 3px;
            height: 32px;
        }

        .mini-bar {
            width: 6px;
            background: var(--accent);
            border-radius: 2px 2px 0 0;
            opacity: 0.6;
            transition: opacity 0.2s;
        }

        .mini-bar:hover {
            opacity: 1;
        }

        /* Model stats enhanced */
        .model-row {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            transition: background 0.15s;
        }

        .model-row:hover {
            background: rgba(255,255,255,0.02);
        }

        .model-name {
            flex: 0 0 180px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            background: var(--bg-elevated);
            padding: 4px 10px;
            border-radius: 4px;
        }

        .model-stats {
            flex: 1;
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .model-stat-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .model-stat-label {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
        }

        .model-stat-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            color: var(--text-bright);
        }

        .model-progress {
            flex: 1;
            height: 8px;
            background: var(--bg-elevated);
            border-radius: 4px;
            overflow: hidden;
            min-width: 100px;
        }

        .model-progress-bar {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }

        .model-rank {
            flex: 0 0 32px;
            text-align: center;
        }

        .rank-badge {
            width: 24px; height: 24px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }

        .rank-1 { background: linear-gradient(135deg, #ffd700, #ffaa00); color: #000; }
        .rank-2 { background: linear-gradient(135deg, #c0c0c0, #a0a0a0); color: #000; }
        .rank-3 { background: linear-gradient(135deg, #cd7f32, #b5651d); color: #fff; }
        .rank-other { background: var(--bg-elevated); color: var(--text-muted); }

        /* Period tabs inline */
        .period-tabs-inline {
            display: flex;
            gap: 8px;
        }

        .period-tab-inline {
            padding: 6px 12px;
            background: var(--bg-elevated);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text-muted);
            font-size: 12px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .period-tab-inline:hover {
            border-color: var(--border-light);
        }

        .period-tab-inline.active {
            background: var(--accent);
            border-color: var(--accent);
            color: var(--bg-deep);
            font-weight: 600;
        }

        /* Section */
        .section {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            margin-bottom: 24px;
            animation: fadeInUp 0.5s ease-out;
            animation-fill-mode: both;
        }

        .section:nth-child(3) { animation-delay: 0.1s; }
        .section:nth-child(4) { animation-delay: 0.2s; }

        .section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
        }

        .section-title {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-bright);
        }

        .section-title-code {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: var(--text-muted);
            margin-left: 8px;
        }

        /* Buttons */
        .btn {
            padding: 10px 16px;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--bg-elevated);
            color: var(--text);
        }

        .btn:hover {
            background: var(--bg-card);
            border-color: var(--border-light);
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent), var(--accent-secondary));
            border: none;
            color: var(--bg-deep);
            font-weight: 600;
        }

        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px -2px rgba(0, 217, 255, 0.3);
        }

        .btn-danger {
            border-color: rgba(239, 68, 68, 0.3);
            color: var(--error);
        }

        .btn-danger:hover {
            background: rgba(239, 68, 68, 0.1);
            border-color: var(--error);
        }

        .btn-success {
            border-color: rgba(34, 197, 94, 0.3);
            color: var(--success);
        }

        .btn-success:hover {
            background: rgba(34, 197, 94, 0.1);
            border-color: var(--success);
        }

        /* Table */
        .table-container {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th, td {
            padding: 14px 24px;
            text-align: left;
        }

        th {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 1px solid var(--border);
            background: var(--bg-elevated);
        }

        td {
            font-size: 14px;
            border-bottom: 1px solid var(--border);
        }

        tr:hover td {
            background: rgba(255,255,255,0.02);
        }

        /* Keys table column widths */
        #keys-table th:nth-child(1), #keys-table td:nth-child(1) { width: 60px; }
        #keys-table th:nth-child(2), #keys-table td:nth-child(2) { width: 150px; }
        #keys-table th:nth-child(3), #keys-table td:nth-child(3) { width: 200px; }
        #keys-table th:nth-child(4), #keys-table td:nth-child(4) { width: 80px; }
        #keys-table th:nth-child(5), #keys-table td:nth-child(5) { width: 140px; }
        #keys-table th:nth-child(6), #keys-table td:nth-child(6) { width: 120px; text-align: right; }

        /* Channels table column widths */
        #channels-table th:nth-child(1), #channels-table td:nth-child(1) { width: 60px; }
        #channels-table th:nth-child(2), #channels-table td:nth-child(2) { width: 140px; }
        #channels-table th:nth-child(3), #channels-table td:nth-child(3) { width: 100px; }
        #channels-table th:nth-child(4), #channels-table td:nth-child(4) { width: 80px; }
        #channels-table th:nth-child(5), #channels-table td:nth-child(5) { width: auto; min-width: 200px; }
        #channels-table th:nth-child(6), #channels-table td:nth-child(6) { width: 80px; }
        #channels-table th:nth-child(7), #channels-table td:nth-child(7) { width: 80px; }
        #channels-table th:nth-child(8), #channels-table td:nth-child(8) { width: 180px; text-align: right; }

        /* Prices table column widths */
        #prices-table th:nth-child(1), #prices-table td:nth-child(1) { width: 60px; }
        #prices-table th:nth-child(2), #prices-table td:nth-child(2) { width: 180px; }
        #prices-table th:nth-child(3), #prices-table td:nth-child(3) { width: 120px; }
        #prices-table th:nth-child(4), #prices-table td:nth-child(4) { width: 120px; }
        #prices-table th:nth-child(5), #prices-table td:nth-child(5) { width: 80px; }
        #prices-table th:nth-child(6), #prices-table td:nth-child(6) { width: 180px; text-align: right; }

        /* Action buttons container */
        .action-btns {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
        }
        .action-btns .btn {
            padding: 4px 12px;
            font-size: 12px;
        }

        .empty-state {
            text-align: center;
            padding: 40px 24px;
            color: var(--text-muted);
        }

        .empty-state-icon {
            font-size: 48px;
            opacity: 0.3;
            margin-bottom: 16px;
        }

        /* Status badges */
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            font-family: 'JetBrains Mono', monospace;
        }

        .badge-active {
            background: rgba(34, 197, 94, 0.15);
            color: var(--success);
            border: 1px solid rgba(34, 197, 94, 0.3);
        }

        .badge-disabled {
            background: rgba(239, 68, 68, 0.15);
            color: var(--error);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .badge-dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: currentColor;
        }

        /* Provider badge */
        .provider-badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .provider-openai { background: rgba(16, 163, 127, 0.15); color: #10a37f; border: 1px solid rgba(16, 163, 127, 0.3); }
        .provider-anthropic { background: rgba(204, 133, 50, 0.15); color: #cc8532; border: 1px solid rgba(204, 133, 50, 0.3); }
        .provider-custom { background: rgba(123, 97, 255, 0.15); color: var(--accent-secondary); border: 1px solid rgba(123, 97, 255, 0.3); }

        /* Modal */
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(10, 14, 20, 0.8);
            backdrop-filter: blur(8px);
            z-index: 200;
            display: none;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.2s ease;
        }

        .modal-overlay.show {
            display: flex;
        }

        .modal {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            width: 480px;
            max-width: 90vw;
            box-shadow: 0 20px 60px -10px rgba(0, 0, 0, 0.5);
            animation: modalIn 0.3s ease-out;
        }

        @keyframes modalIn {
            from { opacity: 0; transform: translateY(20px) scale(0.95); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }

        .modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
        }

        .modal-title {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-bright);
        }

        .modal-close {
            width: 32px; height: 32px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: var(--text-muted);
            background: var(--bg-elevated);
            border: 1px solid var(--border);
            transition: all 0.15s;
        }

        .modal-close:hover {
            background: rgba(239, 68, 68, 0.1);
            border-color: var(--error);
            color: var(--error);
        }

        .modal-body {
            padding: 24px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            font-size: 12px;
            font-weight: 500;
            color: var(--text-muted);
            margin-bottom: 8px;
        }

        .form-group input,
        .form-group select {
            width: 100%;
            padding: 12px 14px;
            background: var(--bg-elevated);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-size: 14px;
            transition: all 0.15s;
            outline: none;
        }

        .form-group input:focus,
        .form-group select:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .form-group input::placeholder {
            color: var(--text-muted);
            opacity: 0.5;
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }

        .modal-footer {
            display: flex;
            gap: 12px;
            padding: 20px 24px;
            border-top: 1px solid var(--border);
            justify-content: flex-end;
        }

        /* Key modal */
        .key-display {
            background: var(--bg-elevated);
            border: 1px solid var(--accent);
            border-radius: 8px;
            padding: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--accent);
            word-break: break-all;
            position: relative;
        }

        .key-copy-btn {
            position: absolute;
            top: 8px; right: 8px;
            padding: 6px 10px;
            font-size: 11px;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            .main { padding: 16px; }
            .header { padding: 12px 16px; }
            th, td { padding: 12px 16px; }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="logo">
            <div class="logo-icon">B</div>
            <div class="logo-text">bol<span>-api</span></div>
        </div>
        <div class="header-status">
            <div class="status-dot"></div>
            <span>System Online</span>
        </div>
    </header>

    <main class="main">
        <h1 class="page-title">控制面板</h1>

        <!-- Stats -->
        <div class="stats-grid" id="stats"></div>

        <!-- Model Usage Section -->
        <div class="section" id="model-stats-section">
            <div class="section-header">
                <div>
                    <span class="section-title">模型用量统计</span>
                    <span class="section-title-code" id="model-stats-period">7天</span>
                </div>
                <div class="period-tabs-inline">
                    <button class="period-tab-inline active" onclick="loadModelStats(5)">5时</button>
                    <button class="period-tab-inline" onclick="loadModelStats(24)">日</button>
                    <button class="period-tab-inline" onclick="loadModelStats(168)">周</button>
                    <button class="period-tab-inline" onclick="loadModelStats(720)">月</button>
                </div>
            </div>
            <div id="model-stats-container"></div>
        </div>

        <!-- API Keys Section -->
        <div class="section">
            <div class="section-header">
                <div>
                    <span class="section-title">API 密钥</span>
                    <span class="section-title-code">/admin/keys</span>
                </div>
                <button class="btn btn-primary" onclick="showKeyModal()">
                    <span>+ 新建密钥</span>
                </button>
            </div>
            <div class="table-container">
                <table id="keys-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>名称</th>
                            <th>密钥</th>
                            <th>状态</th>
                            <th>创建时间</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>

        <!-- Channels Section -->
        <div class="section">
            <div class="section-header">
                <div>
                    <span class="section-title">渠道管理</span>
                    <span class="section-title-code">/admin/channels</span>
                </div>
                <button class="btn btn-primary" onclick="showChannelModal()">
                    <span>+ Add Channel</span>
                </button>
            </div>
            <div class="table-container">
                <table id="channels-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>名称</th>
                            <th>提供商</th>
                            <th>协议</th>
                            <th>模型</th>
                            <th>状态</th>
                            <th>延迟</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>

        <!-- Prices Section -->
        <div class="section">
            <div class="section-header">
                <div>
                    <span class="section-title">模型价格</span>
                    <span class="section-title-code">$/M (每百万token)</span>
                </div>
                <button class="btn btn-primary" onclick="showPriceModal()">
                    <span>+ Add Price</span>
                </button>
            </div>
            <div class="table-container">
                <table id="prices-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>模型名称</th>
                            <th>输入价格</th>
                            <th>输出价格</th>
                            <th>状态</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </main>

    <!-- Key Modal -->
    <div class="modal-overlay" id="key-modal">
        <div class="modal">
            <div class="modal-header">
                <span class="modal-title">创建 API 密钥</span>
                <div class="modal-close" onclick="closeKeyModal()">✕</div>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label>密钥名称（可选）</label>
                    <input type="text" id="key-name" placeholder="例如：生产环境应用">
                </div>
                <div id="key-result" style="display:none;">
                    <div class="form-group">
                        <label>新 API 密钥（请保存，仅显示一次）</label>
                        <div class="key-display">
                            <span id="key-value"></span>
                            <button class="btn key-copy-btn" onclick="copyKey()">复制</button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn" onclick="closeKeyModal()">取消</button>
                <button class="btn btn-primary" id="key-create-btn" onclick="createKey()">创建</button>
            </div>
        </div>
    </div>

    <!-- Channel Modal -->
    <div class="modal-overlay" id="channel-modal">
        <div class="modal">
            <div class="modal-header">
                <span class="modal-title" id="modal-title">添加渠道</span>
                <div class="modal-close" onclick="closeChannelModal()">✕</div>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label>渠道名称</label>
                    <input type="text" id="channel-name" placeholder="例如：OpenAI 生产环境">
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>提供商类型</label>
                        <select id="channel-type">
                            <option value="openai">OpenAI</option>
                            <option value="anthropic">Anthropic</option>
                            <option value="custom">自定义</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>API 协议</label>
                        <select id="channel-protocol">
                            <option value="openai">OpenAI 格式</option>
                            <option value="anthropic">Anthropic 格式</option>
                        </select>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>优先级</label>
                        <input type="number" id="channel-priority" value="1" min="1" max="100">
                    </div>
                </div>
                <div class="form-group">
                    <label>基础 URL</label>
                    <input type="text" id="channel-url" placeholder="https://api.openai.com">
                </div>
                <div class="form-group">
                    <label>API 密钥</label>
                    <div style="display: flex; gap: 8px; align-items: stretch;">
                        <input type="text" id="channel-apikey" placeholder="sk-..." style="flex: 1;">
                        <span id="key-status" style="display: none; padding: 0 10px; background: rgba(34, 197, 94, 0.15); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 6px; color: var(--success); font-size: 12px; font-weight: 500; align-self: center;">✓ 已设置</span>
                    </div>
                </div>
                <div class="form-group">
                    <label>模型（逗号分隔，留空表示全部）</label>
                    <div style="display: flex; gap: 8px; align-items: stretch;">
                        <input type="text" id="channel-models" placeholder="gpt-4, gpt-3.5-turbo" style="flex: 1;">
                        <button class="btn" id="fetch-models-btn" onclick="fetchModels()" style="white-space: nowrap;">
                            <span>↻ 拉取</span>
                        </button>
                    </div>
                    <div id="fetch-models-status" style="margin-top: 8px; font-size: 12px; color: var(--text-muted); display: none;"></div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn" onclick="closeChannelModal()">取消</button>
                <button class="btn btn-primary" onclick="saveChannel()">保存</button>
            </div>
        </div>
    </div>

    <!-- Price Modal -->
    <div class="modal-overlay" id="price-modal">
        <div class="modal">
            <div class="modal-header">
                <span class="modal-title" id="price-modal-title">添加模型价格</span>
                <div class="modal-close" onclick="closePriceModal()">✕</div>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label>模型名称</label>
                    <input type="text" id="price-model" placeholder="例如：gpt-4-turbo">
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>输入价格 ($/M)</label>
                        <input type="number" id="price-input" value="0" min="0" step="0.01" placeholder="输入token价格">
                    </div>
                    <div class="form-group">
                        <label>输出价格 ($/M)</label>
                        <input type="number" id="price-output" value="0" min="0" step="0.01" placeholder="输出token价格">
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn" onclick="closePriceModal()">取消</button>
                <button class="btn btn-primary" onclick="savePrice()">保存</button>
            </div>
        </div>
    </div>

    <script>
        const password = localStorage.getItem('admin_password') || new URLSearchParams(window.location.search).get('password');
        const headers = {'X-Admin-Password': password, 'Content-Type': 'application/json'};

        // Stats
        async function loadStats() {
            const res = await fetch('/stats/summary', {headers});
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

        // Keys
        async function loadKeys() {
            const res = await fetch('/admin/keys', {headers});
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
                // 显示完整key
                const res = await fetch(`/admin/keys/${id}/reveal`, {headers});
                const data = await res.json();
                if (data.key) {
                    displayEl.textContent = data.key;
                    displayEl.style.color = 'var(--accent)';
                    toggleBtn.textContent = '隐藏';
                }
            } else {
                // 隐藏key
                const res = await fetch('/admin/keys', {headers});
                const keys = await res.json();
                const k = keys.find(k => k.id === id);
                displayEl.textContent = k.key_prefix || 'bol-xxx...';
                displayEl.style.color = 'var(--text-muted)';
                toggleBtn.textContent = '显示';
            }
        }

        async function copyFullKey(id) {
            const res = await fetch(`/admin/keys/${id}/reveal`, {headers});
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

        function formatDate(s) {
            return new Date(s).toLocaleDateString('zh-CN', {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
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
            const res = await fetch('/admin/keys', {method: 'POST', headers, body: JSON.stringify({name})});
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
            await fetch(`/admin/keys/${id}?is_active=${isActive}`, {method: 'PATCH', headers});
            loadKeys();
        }

        async function deleteKey(id) {
            if (confirm('确定删除此 API 密钥？此操作不可恢复。')) {
                await fetch(`/admin/keys/${id}`, {method: 'DELETE', headers});
                loadKeys();
            }
        }

        // Channels
        async function loadChannels() {
            const res = await fetch('/admin/channels', {headers});
            const channels = await res.json();
            const tbody = document.querySelector('#channels-table tbody');

            if (channels.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8">
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
                        <span class="provider-badge provider-${c.provider_type}">${c.provider_type}</span>
                    </td>
                    <td>
                        <span class="provider-badge provider-${c.api_protocol || 'openai'}">${c.api_protocol || 'openai'}</span>
                    </td>
                    <td>
                        ${c.models.length > 0
                            ? c.models.map(m => `<span style="font-family: 'JetBrains Mono'; font-size: 11px; background: var(--bg-elevated); padding: 2px 6px; border-radius: 3px; margin-right: 4px;">${m}</span>`).join('')
                            : '<span style="color: var(--text-muted);">全部</span>'
                        }
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
            document.getElementById('channel-protocol').value = 'openai';
            document.getElementById('channel-type').value = 'custom';
            document.getElementById('fetch-models-status').style.display = 'none';
        }

        async function editChannel(id) {
            editingChannelId = id;
            document.getElementById('channel-modal').classList.add('show');
            document.getElementById('modal-title').textContent = '编辑渠道';

            // 获取渠道详情
            const res = await fetch('/admin/channels', {headers});
            const channels = await res.json();
            const c = channels.find(c => c.id === id);

            if (c) {
                document.getElementById('channel-name').value = c.name;

                // 正确设置Provider Type
                const typeSelect = document.getElementById('channel-type');
                const typeValue = c.provider_type || 'custom';
                for (let opt of typeSelect.options) {
                    opt.selected = opt.value === typeValue;
                }

                // 正确设置协议值
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

            // 显示加载状态
            btn.disabled = true;
            btn.innerHTML = '<span>↻ 加载中...</span>';
            btn.style.opacity = '0.6';
            statusDiv.style.display = 'block';
            statusDiv.style.color = 'var(--text-muted)';
            statusDiv.textContent = '正在拉取模型列表...';

            try {
                const res = await fetch('/admin/channels/fetch-models', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        base_url: baseUrl,
                        api_key: apiKey,
                        api_protocol: apiProtocol
                    })
                });

                const data = await res.json();

                if (res.ok) {
                    if (data.models && data.models.length > 0) {
                        // 填充models输入框
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

            // 恢复按钮状态
            btn.disabled = false;
            btn.innerHTML = '<span>↻ 拉取</span>';
            btn.style.opacity = '1';

            // 3秒后隐藏状态提示
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

            // 编辑模式下如果没有输入新key，不发送api_key字段
            if (editingChannelId && !data.api_key) {
                delete data.api_key;
            } else if (!editingChannelId && !data.api_key) {
                alert('新渠道必须填写 API 密钥');
                return;
            }

            if (editingChannelId) {
                await fetch(`/admin/channels/${editingChannelId}`, {
                    method: 'PATCH',
                    headers,
                    body: JSON.stringify(data)
                });
            } else {
                await fetch('/admin/channels', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify(data)
                });
            }
            closeChannelModal();
            loadChannels();
        }

        async function toggleChannel(id, is_active) {
            await fetch(`/admin/channels/${id}/toggle`, {
                method: 'POST',
                headers,
                body: JSON.stringify({is_active})
            });
            loadChannels();
        }

        async function deleteChannel(id) {
            if (confirm('确定删除此渠道？')) {
                await fetch(`/admin/channels/${id}`, {method: 'DELETE', headers});
                loadChannels();
            }
        }

        // 模型价格管理
        let editingPriceId = null;

        async function loadPrices() {
            const res = await fetch('/admin/prices', {headers});
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

            const res = await fetch('/admin/prices', {headers});
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
                await fetch(`/admin/prices/${editingPriceId}`, {
                    method: 'PATCH',
                    headers,
                    body: JSON.stringify(data)
                });
            } else {
                await fetch('/admin/prices', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify(data)
                });
            }
            closePriceModal();
            loadPrices();
        }

        async function togglePrice(id, is_active) {
            await fetch(`/admin/prices/${id}/toggle`, {
                method: 'POST',
                headers,
                body: JSON.stringify({is_active})
            });
            loadPrices();
        }

        async function deletePrice(id) {
            if (confirm('确定删除此价格配置？')) {
                await fetch(`/admin/prices/${id}`, {method: 'DELETE', headers});
                loadPrices();
            }
        }

        // Model Stats (inline)
        async function loadModelStats(hours) {
            // 更新tab状态
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

            // 更新period显示
            document.getElementById('model-stats-period').textContent = hours < 24 ? `${hours}时` : `${hours / 24}天`;

            // 获取数据
            const res = await fetch(`/stats/models?hours=${hours}`);
            const data = await res.json();

            const container = document.getElementById('model-stats-container');
            const maxRequests = data.stats && data.stats.length > 0 ? data.stats[0].requests : 1;

            // 计算总tokens
            const totalInputTokens = data.stats ? data.stats.reduce((sum, s) => sum + s.request_tokens, 0) : 0;
            const totalOutputTokens = data.stats ? data.stats.reduce((sum, s) => sum + s.response_tokens, 0) : 0;

            if (data.stats && data.stats.length > 0) {
                container.innerHTML = `
                    <div style="padding: 16px 24px; border-bottom: 1px solid var(--border); background: var(--bg-elevated);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; gap: 20px;">
                                <div>
                                    <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">总请求</span>
                                    <span style="font-family: 'JetBrains Mono'; font-size: 18px; font-weight: 600; color: var(--text-bright); margin-left: 8px;">${data.total_requests}</span>
                                </div>
                                <div>
                                    <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">输入Tokens</span>
                                    <span style="font-family: 'JetBrains Mono'; font-size: 18px; font-weight: 600; color: var(--accent); margin-left: 8px;">${formatNumber(totalInputTokens)}</span>
                                </div>
                                <div>
                                    <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">输出Tokens</span>
                                    <span style="font-family: 'JetBrains Mono'; font-size: 18px; font-weight: 600; color: var(--accent-secondary); margin-left: 8px;">${formatNumber(totalOutputTokens)}</span>
                                </div>
                            </div>
                            <div>
                                <span style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">总费用</span>
                                <span style="font-family: 'JetBrains Mono'; font-size: 18px; font-weight: 600; color: var(--success); margin-left: 8px;">$${data.total_cost.toFixed(4)}</span>
                            </div>
                        </div>
                    </div>
                    ${data.stats.map((s, i) => {
                        const percentage = Math.round((s.requests / maxRequests) * 100);
                        const inputPct = s.request_tokens + s.response_tokens > 0 ? Math.round((s.request_tokens / (s.request_tokens + s.response_tokens)) * 100) : 0;
                        const rankClass = i === 0 ? 'rank-1' : i === 1 ? 'rank-2' : i === 2 ? 'rank-3' : 'rank-other';
                        return `
                            <div class="model-row">
                                <div class="model-rank">
                                    <span class="rank-badge ${rankClass}">${i + 1}</span>
                                </div>
                                <div class="model-name">${s.model}</div>
                                <div class="model-stats">
                                    <div class="model-stat-item">
                                        <span class="model-stat-label">请求</span>
                                        <span class="model-stat-value">${s.requests}</span>
                                    </div>
                                    <div class="model-progress">
                                        <div class="model-progress-bar" style="width: ${percentage}%; background: linear-gradient(90deg, var(--accent), var(--accent-secondary));"></div>
                                    </div>
                                    <div class="model-stat-item">
                                        <span class="model-stat-label">输入</span>
                                        <span class="model-stat-value" style="color: var(--accent);">${formatNumber(s.request_tokens)}</span>
                                    </div>
                                    <div class="model-stat-item">
                                        <span class="model-stat-label">输出</span>
                                        <span class="model-stat-value" style="color: var(--accent-secondary);">${formatNumber(s.response_tokens)}</span>
                                    </div>
                                    <div class="model-stat-item">
                                        <span class="model-stat-label">费用</span>
                                        <span class="model-stat-value" style="color: var(--success);">$${s.cost.toFixed(4)}</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                `;
            } else {
                container.innerHTML = `
                    <div style="text-align: center; color: var(--text-muted); padding: 60px 24px;">
                        <div style="font-size: 48px; opacity: 0.3; margin-bottom: 16px;">📭</div>
                        <div style="font-size: 14px;">近 ${data.period} 无请求记录</div>
                        <div style="font-size: 12px; margin-top: 8px; opacity: 0.6;">开始调用 API 后将显示统计数据</div>
                    </div>
                `;
            }
        }

        async function testChannel(id) {
            const btn = document.getElementById(`test-btn-${id}`);
            const latencyCell = document.getElementById(`latency-${id}`);
            const originalText = btn.textContent;

            // 显示测试中状态
            btn.textContent = '测试中...';
            btn.disabled = true;
            btn.style.opacity = '0.6';
            latencyCell.innerHTML = '<span style="color: var(--text-muted); font-family: JetBrains Mono; font-size: 12px;">...</span>';

            try {
                const res = await fetch(`/admin/channels/${id}/test`, {
                    method: 'POST',
                    headers: headers
                });
                const data = await res.json();

                if (data.success) {
                    // 更新延迟显示
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

                // 3秒后恢复按钮，但保留延迟显示
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

        // Close modal on overlay click
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
        loadModelStats(168);  // 默认显示周统计

        // Refresh stats periodically
        setInterval(loadStats, 30000);
        setInterval(() => loadModelStats(168), 30000);
    </script>
</body>
</html>
"""