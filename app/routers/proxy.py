import time
import json
import asyncio
import httpx
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db, async_session
from app.channels.manager import ChannelManager, create_provider
from app.stats.recorder import UsageRecorder, calculate_cost
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.utils.logger import RequestLogger
from app.utils.tokenizer import count_tokens, count_message_tokens

router = APIRouter()
logger = logging.getLogger(__name__)
request_logger = RequestLogger()

# 最大重试次数（尝试不同渠道）
MAX_FALLBACK_ATTEMPTS = 3


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, db: AsyncSession = Depends(get_db)):
    """OpenAI兼容的聊天完成API"""
    body = await request.json()
    model = body.get("model")
    stream = body.get("stream", False)

    if not model:
        raise HTTPException(status_code=400, detail="Missing model parameter")

    api_key_id = getattr(request.state, "api_key_id", None)
    start_time = time.time()

    request_logger.log_request("/v1/chat/completions", body, api_key_id=api_key_id)

    # 获取所有支持该模型的渠道用于fallback
    all_channels = await ChannelManager.select_all_channels(db, model, protocol="openai")
    if not all_channels:
        request_logger.log_error(
            "/v1/chat/completions",
            channel_id=None,
            model=model,
            error="No available channel",
            error_type="NO_CHANNEL",
        )
        raise HTTPException(
            status_code=400, detail=f"No available channel for model: {model}"
        )

    # 尝试多个渠道
    failed_channels = []
    last_error = None

    for attempt in range(min(MAX_FALLBACK_ATTEMPTS, len(all_channels))):
        # 选择渠道（排除已失败的）
        channel = await ChannelManager.select_channel(
            db, model, exclude_ids=[c.id for c in failed_channels], protocol="openai"
        )
        if not channel:
            break

        request_logger.log_request(
            f"/v1/chat/completions [attempt {attempt + 1}]",
            body,
            api_key_id=api_key_id,
            extra={"channel_id": channel.id, "channel_name": channel.name},
        )
        provider = create_provider(channel)
        if not provider.supports_model(model):
            request_logger.log_fallback(
                "/v1/chat/completions",
                channel.id,
                model,
                reason=f"provider does not support model {model}",
            )
            failed_channels.append(channel)
            continue

        try:
            if stream:
                request_logger.log_stream_start(
                    "/v1/chat/completions", channel.id, model, api_key_id=api_key_id
                )
                return StreamingResponse(
                    stream_chat_response(
                        provider, body, channel, api_key_id, request, failed_channels
                    ),
                    media_type="text/event-stream",
                )
            else:
                response = await provider.chat_completion(body)
                latency_ms = int((time.time() - start_time) * 1000)

                # 提取用量
                usage = provider.extract_usage(response)

                request_logger.log_response(
                    "/v1/chat/completions",
                    channel.id,
                    model,
                    status_code=200,
                    latency_ms=latency_ms,
                    tokens=usage["total_tokens"],
                    body=response,
                )

                # 记录用量
                cost = await calculate_cost(
                    db, model, usage["request_tokens"], usage["response_tokens"]
                )
                await UsageRecorder.record(
                    api_key_id=api_key_id,
                    channel_id=channel.id,
                    provider=channel.provider_type,
                    model=model,
                    endpoint="/v1/chat/completions",
                    request_tokens=usage["request_tokens"],
                    response_tokens=usage["response_tokens"],
                    cost=cost,
                    latency_ms=latency_ms,
                )

                return JSONResponse(content=response)

        except httpx.TimeoutException as e:
            request_logger.log_error(
                "/v1/chat/completions",
                channel.id,
                model,
                error=str(e),
                error_type="TIMEOUT",
                latency_ms=int((time.time() - start_time) * 1000),
            )
            failed_channels.append(channel)
            last_error = e
            continue  # 尝试下一个渠道
        except httpx.ConnectError as e:
            request_logger.log_error(
                "/v1/chat/completions",
                channel.id,
                model,
                error=str(e),
                error_type="CONNECT_ERROR",
                latency_ms=int((time.time() - start_time) * 1000),
            )
            failed_channels.append(channel)
            last_error = e
            continue  # 尝试下一个渠道
        except asyncio.CancelledError:
            # 客户端断开连接，记录已发往上游的请求
            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_error(
                "/v1/chat/completions",
                channel.id,
                model,
                error="Client disconnected",
                error_type="CANCELLED",
                latency_ms=latency_ms,
            )
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                status_code=499,
                latency_ms=latency_ms,
            )
            raise
        except httpx.HTTPStatusError as e:
            # 上游返回4xx/5xx，提取响应体中的具体错误信息
            detail = e.response.text if e.response else str(e)
            status_code = e.response.status_code if e.response else 500
            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_error(
                "/v1/chat/completions",
                channel.id,
                model,
                error=f"HTTP {status_code}: {detail}",
                error_type="UPSTREAM_ERROR",
                latency_ms=latency_ms,
            )
            # 4xx错误不重试（请求本身有问题，换渠道也一样）
            if status_code >= 500:
                failed_channels.append(channel)
                last_error = e
                continue
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                status_code=status_code,
                latency_ms=latency_ms,
            )
            raise HTTPException(status_code=status_code, detail=detail)
        except Exception as e:
            request_logger.log_error(
                "/v1/chat/completions",
                channel.id,
                model,
                error=str(e),
                error_type="ERROR",
                latency_ms=int((time.time() - start_time) * 1000),
            )
            # 非网络错误，不重试
            latency_ms = int((time.time() - start_time) * 1000)
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                status_code=500,
                latency_ms=latency_ms,
            )
            raise HTTPException(status_code=500, detail=str(e))

    # 所有渠道都失败
    latency_ms = int((time.time() - start_time) * 1000)
    if failed_channels:
        # 记录最后一个失败渠道（使用 shield 防止 CancelledError 中断记录）
        last_channel = failed_channels[-1]
        try:
            await asyncio.shield(UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=last_channel.id,
                provider=last_channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                status_code=504 if isinstance(last_error, httpx.TimeoutException) else 502,
                latency_ms=latency_ms,
            ))
        except asyncio.CancelledError:
            pass

    if isinstance(last_error, httpx.TimeoutException):
        raise HTTPException(status_code=504, detail="All channels timed out")
    elif isinstance(last_error, httpx.ConnectError):
        raise HTTPException(
            status_code=502, detail=f"All channels failed to connect: {str(last_error)}"
        )
    else:
        raise HTTPException(
            status_code=503, detail="No available channel after fallback attempts"
        )


async def stream_chat_response(
    provider, body, channel, api_key_id, request, failed_channels=None
):
    """流式响应处理"""
    start_time = time.time()
    total_content = ""
    model = body.get("model")
    prompt_tokens = 0
    completion_tokens = 0

    try:
        async for line in provider.stream_chat_completion(body):
            # SSE格式：每个事件以\n\n结尾
            if line.strip():  # 非空行
                yield f"{line}\n\n"
            # 空行跳过，由上面的\n\n提供分隔
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    data = json.loads(line[6:])
                    if data.get("choices"):
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        total_content += content
                    # 检查是否有 usage 信息（OpenAI stream_options.include_usage）
                    if data.get("usage"):
                        usage = data["usage"]
                        prompt_tokens = usage.get("prompt_tokens", 0)
                        completion_tokens = usage.get("completion_tokens", 0)
                except json.JSONDecodeError:
                    pass  # JSON解析失败，跳过此行

        # 流式完成后记录用量
        latency_ms = int((time.time() - start_time) * 1000)

        # If upstream did not provide usage, estimate tokens accurately
        if prompt_tokens == 0:
            prompt_tokens = count_message_tokens(body.get("messages", []), model)
        if completion_tokens == 0:
            completion_tokens = count_tokens(total_content, model)

        request_logger.log_stream_end(
            "/v1/chat/completions",
            channel.id,
            model,
            latency_ms=latency_ms,
            tokens=prompt_tokens + completion_tokens,
        )

        # 在流结束后使用新的session记录用量
        async with async_session() as db:
            cost = await calculate_cost(db, model, prompt_tokens, completion_tokens)
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                request_tokens=prompt_tokens,
                response_tokens=completion_tokens,
                cost=cost,
                latency_ms=latency_ms,
            )

    except asyncio.CancelledError:
        # 客户端断开连接，记录已发往上游的请求
        latency_ms = int((time.time() - start_time) * 1000)
        request_logger.log_error(
            "/v1/chat/completions",
            channel.id,
            model,
            error="Client disconnected during stream",
            error_type="STREAM_CANCELLED",
            latency_ms=latency_ms,
        )
        try:
            await asyncio.shield(UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                status_code=499,
                latency_ms=latency_ms,
            ))
        except asyncio.CancelledError:
            pass
        raise

    except Exception as e:
        error_msg = str(e)
        latency_ms = int((time.time() - start_time) * 1000)

        request_logger.log_error(
            "/v1/chat/completions",
            channel.id,
            model,
            error=error_msg,
            error_type="STREAM_ERROR",
            latency_ms=latency_ms,
        )

        # 记录失败请求
        async with async_session() as db:
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/chat/completions",
                status_code=500,
                latency_ms=latency_ms,
            )

        # 发送标准OpenAI格式的错误事件
        error_data = {"error": {"message": error_msg, "type": "internal_error"}}
        yield f"data: {json.dumps(error_data)}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/v1/messages")
async def anthropic_messages(request: Request, db: AsyncSession = Depends(get_db)):
    """Anthropic兼容的消息API"""
    body = await request.json()
    model = body.get("model")
    stream = body.get("stream", False)

    if not model:
        raise HTTPException(status_code=400, detail="Missing model parameter")

    api_key_id = getattr(request.state, "api_key_id", None)
    start_time = time.time()

    request_logger.log_request("/v1/messages", body, api_key_id=api_key_id)

    # 获取所有支持该模型的渠道用于fallback
    all_channels = await ChannelManager.select_all_channels(db, model, protocol="anthropic")
    if not all_channels:
        request_logger.log_error(
            "/v1/messages",
            channel_id=None,
            model=model,
            error="No available channel",
            error_type="NO_CHANNEL",
        )
        raise HTTPException(
            status_code=400, detail=f"No available channel for model: {model}"
        )

    # 尝试多个渠道
    failed_channels = []
    last_error = None

    for attempt in range(min(MAX_FALLBACK_ATTEMPTS, len(all_channels))):
        # 选择渠道（排除已失败的）
        channel = await ChannelManager.select_channel(
            db, model, exclude_ids=[c.id for c in failed_channels], protocol="anthropic"
        )
        if not channel:
            break

        request_logger.log_request(
            f"/v1/messages [attempt {attempt + 1}]",
            body,
            api_key_id=api_key_id,
            extra={"channel_id": channel.id, "channel_name": channel.name},
        )
        provider = create_provider(channel)
        if not provider.supports_model(model):
            request_logger.log_fallback(
                "/v1/messages",
                channel.id,
                model,
                reason=f"provider does not support model {model}",
            )
            failed_channels.append(channel)
            continue

        try:
            if stream:
                request_logger.log_stream_start(
                    "/v1/messages", channel.id, model, api_key_id=api_key_id
                )
                return StreamingResponse(
                    stream_anthropic_response(
                        provider, body, channel, api_key_id, request
                    ),
                    media_type="text/event-stream",
                )
            else:
                response = await provider.chat_completion(body)
                latency_ms = int((time.time() - start_time) * 1000)

                usage = provider.extract_usage(response)

                request_logger.log_response(
                    "/v1/messages",
                    channel.id,
                    model,
                    status_code=200,
                    latency_ms=latency_ms,
                    tokens=usage["total_tokens"],
                    body=response,
                )

                cost = await calculate_cost(
                    db, model, usage["request_tokens"], usage["response_tokens"]
                )
                await UsageRecorder.record(
                    api_key_id=api_key_id,
                    channel_id=channel.id,
                    provider=channel.provider_type,
                    model=model,
                    endpoint="/v1/messages",
                    request_tokens=usage["request_tokens"],
                    response_tokens=usage["response_tokens"],
                    cost=cost,
                    latency_ms=latency_ms,
                )

                return JSONResponse(content=response)

        except httpx.TimeoutException as e:
            request_logger.log_error(
                "/v1/messages",
                channel.id,
                model,
                error=str(e),
                error_type="TIMEOUT",
                latency_ms=int((time.time() - start_time) * 1000),
            )
            failed_channels.append(channel)
            last_error = e
            continue  # 尝试下一个渠道
        except httpx.ConnectError as e:
            request_logger.log_error(
                "/v1/messages",
                channel.id,
                model,
                error=str(e),
                error_type="CONNECT_ERROR",
                latency_ms=int((time.time() - start_time) * 1000),
            )
            failed_channels.append(channel)
            last_error = e
            continue  # 尝试下一个渠道
        except asyncio.CancelledError:
            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_error(
                "/v1/messages",
                channel.id,
                model,
                error="Client disconnected",
                error_type="CANCELLED",
                latency_ms=latency_ms,
            )
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                status_code=499,
                latency_ms=latency_ms,
            )
            raise
        except httpx.HTTPStatusError as e:
            # 上游返回4xx/5xx，提取响应体中的具体错误信息
            detail = e.response.text if e.response else str(e)
            status_code = e.response.status_code if e.response else 500
            latency_ms = int((time.time() - start_time) * 1000)
            request_logger.log_error(
                "/v1/messages",
                channel.id,
                model,
                error=f"HTTP {status_code}: {detail}",
                error_type="UPSTREAM_ERROR",
                latency_ms=latency_ms,
            )
            # 4xx错误不重试（请求本身有问题，换渠道也一样）
            if status_code >= 500:
                failed_channels.append(channel)
                last_error = e
                continue
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                status_code=status_code,
                latency_ms=latency_ms,
            )
            raise HTTPException(status_code=status_code, detail=detail)
        except Exception as e:
            request_logger.log_error(
                "/v1/messages",
                channel.id,
                model,
                error=str(e),
                error_type="ERROR",
                latency_ms=int((time.time() - start_time) * 1000),
            )
            # 非网络错误，不重试
            latency_ms = int((time.time() - start_time) * 1000)
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                status_code=500,
                latency_ms=latency_ms,
            )
            raise HTTPException(status_code=500, detail=str(e))

    # 所有渠道都失败
    latency_ms = int((time.time() - start_time) * 1000)
    if failed_channels:
        # 记录最后一个失败渠道（使用 shield 防止 CancelledError 中断记录）
        last_channel = failed_channels[-1]
        try:
            await asyncio.shield(UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=last_channel.id,
                provider=last_channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                status_code=504 if isinstance(last_error, httpx.TimeoutException) else 502,
                latency_ms=latency_ms,
            ))
        except asyncio.CancelledError:
            pass

    if isinstance(last_error, httpx.TimeoutException):
        raise HTTPException(status_code=504, detail="All channels timed out")
    elif isinstance(last_error, httpx.ConnectError):
        raise HTTPException(
            status_code=502, detail=f"All channels failed to connect: {str(last_error)}"
        )
    else:
        raise HTTPException(
            status_code=503, detail="No available channel after fallback attempts"
        )


async def stream_anthropic_response(provider, body, channel, api_key_id, request):
    """Anthropic流式响应处理"""
    start_time = time.time()
    total_content = ""
    model = body.get("model")
    input_tokens = 0
    output_tokens = 0

    try:
        async for line in provider.stream_chat_completion(body):
            # SSE格式：每个事件以\n\n结尾
            if line.strip():  # 非空行
                yield f"{line}\n\n"
            # 兼容两种格式: "data: {...}" 和 "data:{...}"
            if line.startswith("data:"):
                try:
                    # 跳过"data:"或"data: "，添加长度检查防止越界
                    if len(line) > 5 and line[5] == "{":
                        json_str = line[5:]
                    elif len(line) > 6:
                        json_str = line[6:]
                    else:
                        continue  # 行太短，跳过
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
                except json.JSONDecodeError:
                    pass  # JSON解析失败，跳过此行

        latency_ms = int((time.time() - start_time) * 1000)
        # If upstream did not provide usage, estimate tokens accurately
        if input_tokens == 0:
            input_tokens = count_message_tokens(body.get("messages", []), model)
        if output_tokens == 0:
            output_tokens = count_tokens(total_content, model)

        request_logger.log_stream_end(
            "/v1/messages",
            channel.id,
            model,
            latency_ms=latency_ms,
            tokens=input_tokens + output_tokens,
        )

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
                latency_ms=latency_ms,
            )

    except asyncio.CancelledError:
        # 客户端断开连接，记录已发往上游的请求
        latency_ms = int((time.time() - start_time) * 1000)
        request_logger.log_error(
            "/v1/messages",
            channel.id,
            model,
            error="Client disconnected during stream",
            error_type="STREAM_CANCELLED",
            latency_ms=latency_ms,
        )
        try:
            await asyncio.shield(UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                status_code=499,
                latency_ms=latency_ms,
            ))
        except asyncio.CancelledError:
            pass
        raise

    except Exception as e:
        error_msg = str(e)
        latency_ms = int((time.time() - start_time) * 1000)

        request_logger.log_error(
            "/v1/messages",
            channel.id,
            model,
            error=error_msg,
            error_type="STREAM_ERROR",
            latency_ms=latency_ms,
        )

        # 记录失败请求
        async with async_session() as db:
            await UsageRecorder.record(
                api_key_id=api_key_id,
                channel_id=channel.id,
                provider=channel.provider_type,
                model=model,
                endpoint="/v1/messages",
                status_code=500,
                latency_ms=latency_ms,
            )

        # 发送标准Anthropic格式的错误事件
        error_data = {
            "type": "error",
            "error": {"type": "internal_error", "message": error_msg},
        }
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
        yield "data: [DONE]\n\n"
