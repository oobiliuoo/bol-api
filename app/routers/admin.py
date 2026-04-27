from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.db.crud import (
    create_channel, get_all_channels, update_channel, delete_channel, toggle_channel,
    create_model_price, get_all_model_prices, update_model_price, delete_model_price,
    toggle_model_price, get_model_price_by_id
)
from app.channels.models import ChannelCreate, ChannelUpdate, ChannelResponse
from app.config import settings
from app.auth.jwt import create_token, verify_token
import os

router = APIRouter(tags=["Admin"])


def get_admin_verifier():
    """返回管理员验证依赖函数"""
    def verify_admin(request: Request):
        """验证管理员身份（支持 JWT token 或密码）"""
        # 优先检查 JWT token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if verify_token(token):
                return True

        # 兼容旧的密码验证方式
        password = request.headers.get("X-Admin-Password")
        if password and password == settings.admin_password:
            return True

        raise HTTPException(status_code=401, detail="Invalid or expired authentication")
    return verify_admin


verify_admin = get_admin_verifier()


@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """管理界面首页（登录后由前端验证）"""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    return FileResponse(os.path.join(static_dir, "admin.html"))


@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    """管理界面登录页"""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    return FileResponse(os.path.join(static_dir, "login.html"))


@router.post("/admin/login")
async def admin_login(request: Request):
    """管理员登录，返回 JWT token"""
    body = await request.json()
    password = body.get("password")
    if password == settings.admin_password:
        token = create_token("admin")
        return {"success": True, "token": token}
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
        if api_protocol == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            return {"models": [], "message": "Anthropic API does not support models listing. Please configure manually."}
        else:
            headers = {"Authorization": f"Bearer {api_key}"}
            url = f"{base_url}/v1/models"

            client = await AsyncHttpClient.get_client()
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            models = []
            if "data" in data:
                models = [m["id"] for m in data["data"]]
            elif isinstance(data, list):
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
    start_time = time.time()

    try:
        if api_protocol == "anthropic":
            test_request = {
                "model": channel.models[0] if channel.models else "claude-3-haiku-20240307",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "Hi"}]
            }
        else:
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