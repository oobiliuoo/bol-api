import time
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session
from app.channels.manager import ChannelManager, create_provider
from app.stats.recorder import UsageRecorder, calculate_cost
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider

router = APIRouter()


async def get_db():
    async with async_session() as session:
        yield session


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, db: AsyncSession = Depends(get_db)):
    """OpenAI兼容的聊天完成API"""
    body = await request.json()
    model = body.get("model")
    stream = body.get("stream", False)

    if not model:
        raise HTTPException(status_code=400, detail="Missing model parameter")

    # 获取渠道和Provider
    channel = await ChannelManager.select_channel(db, model)
    if not channel:
        raise HTTPException(status_code=400, detail=f"No available channel for model: {model}")

    provider = create_provider(channel)
    if not provider.supports_model(model):
        raise HTTPException(status_code=400, detail=f"Channel does not support model: {model}")

    api_key_id = getattr(request.state, "api_key_id", None)
    start_time = time.time()

    try:
        if stream:
            return StreamingResponse(
                stream_chat_response(provider, body, channel, api_key_id, request),
                media_type="text/event-stream"
            )
        else:
            response = await provider.chat_completion(body)
            latency_ms = int((time.time() - start_time) * 1000)

            # 提取用量
            usage = provider.extract_usage(response)

            # 记录用量
            cost = await calculate_cost(db, model, usage["request_tokens"], usage["response_tokens"])
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                request_tokens=usage["request_tokens"],
                response_tokens=usage["response_tokens"],
                cost=cost,
                latency_ms=latency_ms
            )

            return JSONResponse(content=response)

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        await UsageRecorder.record(
            api_key_id=api_key_id,
            channel_id=channel.id,
            provider=channel.provider_type,
            model=model,
            endpoint="/v1/chat/completions",
            status_code=500,
            latency_ms=latency_ms
        )
        raise HTTPException(status_code=500, detail=str(e))


async def stream_chat_response(provider, body, channel, api_key_id, request):
    """流式响应处理"""
    start_time = time.time()
    total_content = ""
    model = body.get("model")

    try:
        async for line in provider.stream_chat_completion(body):
            yield f"{line}\n"
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    data = json.loads(line[6:])
                    if data.get("choices"):
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        total_content += content
                except:
                    pass

        # 流式完成后记录用量（估算）
        latency_ms = int((time.time() - start_time) * 1000)
        # 流式响应没有准确的token计数，用内容长度估算
        estimated_tokens = len(total_content) // 4

        # 在流结束后使用新的session记录用量
        async with async_session() as db:
            cost = await calculate_cost(db, model, 0, estimated_tokens)
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                response_tokens=estimated_tokens,
                cost=cost,
                latency_ms=latency_ms
            )

    except Exception as e:
        yield f"data: {{'error': '{str(e)}'}}\n"


@router.post("/v1/messages")
async def anthropic_messages(request: Request, db: AsyncSession = Depends(get_db)):
    """Anthropic兼容的消息API"""
    body = await request.json()
    model = body.get("model")
    stream = body.get("stream", False)

    if not model:
        raise HTTPException(status_code=400, detail="Missing model parameter")

    # 获取渠道和Provider
    channel = await ChannelManager.select_channel(db, model)
    if not channel:
        raise HTTPException(status_code=400, detail=f"No available channel for model: {model}")

    provider = create_provider(channel)
    if not provider.supports_model(model):
        raise HTTPException(status_code=400, detail=f"Channel does not support model: {model}")

    api_key_id = getattr(request.state, "api_key_id", None)
    start_time = time.time()

    try:
        if stream:
            return StreamingResponse(
                stream_anthropic_response(provider, body, channel, api_key_id, request),
                media_type="text/event-stream"
            )
        else:
            response = await provider.chat_completion(body)
            latency_ms = int((time.time() - start_time) * 1000)

            usage = provider.extract_usage(response)
            cost = await calculate_cost(db, model, usage["request_tokens"], usage["response_tokens"])
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                request_tokens=usage["request_tokens"],
                response_tokens=usage["response_tokens"],
                cost=cost,
                latency_ms=latency_ms
            )

            return JSONResponse(content=response)

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        await UsageRecorder.record(
            api_key_id=api_key_id,
            channel_id=channel.id,
            provider=channel.provider_type,
            model=model,
            endpoint="/v1/messages",
            status_code=500,
            latency_ms=latency_ms
        )
        raise HTTPException(status_code=500, detail=str(e))


async def stream_anthropic_response(provider, body, channel, api_key_id, request):
    """Anthropic流式响应处理"""
    start_time = time.time()
    total_content = ""
    model = body.get("model")
    input_tokens = 0
    output_tokens = 0

    try:
        async for line in provider.stream_chat_completion(body):
            yield f"{line}\n"
            # 兼容两种格式: "data: {...}" 和 "data:{...}"
            if line.startswith("data:"):
                try:
                    # 跳过"data:"或"data: "
                    json_str = line[5:] if line[5] == '{' else line[6:]
                    data = json.loads(json_str)
                    if data.get("type") == "content_block_delta":
                        delta = data.get("delta", {})
                        text = delta.get("text", "")
                        total_content += text
                    elif data.get("type") == "message_start":
                        usage = data.get("message", {}).get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)
                    elif data.get("type") == "message_delta":
                        # message_delta可能包含完整的usage信息（某些上游服务商）
                        usage = data.get("usage", {})
                        if usage:
                            input_tokens = usage.get("input_tokens", input_tokens)
                            output_tokens = usage.get("output_tokens", 0)
                        # 也尝试从delta中获取（标准Anthropic格式）
                        delta_usage = data.get("delta", {}).get("usage", {})
                        if delta_usage:
                            output_tokens = delta_usage.get("output_tokens", 0)
                except:
                    pass

        latency_ms = int((time.time() - start_time) * 1000)
        if output_tokens == 0:
            output_tokens = len(total_content) // 4

        # 在流结束后使用新的session记录用量
        async with async_session() as db:
            cost = await calculate_cost(db, model, input_tokens, output_tokens)
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                request_tokens=input_tokens,
                response_tokens=output_tokens,
                cost=cost,
                latency_ms=latency_ms
            )

    except Exception as e:
        yield f"event: error\ndata: {{'error': '{str(e)}'}}\n"