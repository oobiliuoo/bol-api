# bol-api 项目架构分析报告

> 生成日期: 2026-05-15

## 1. 项目概览

**bol-api** 是一个大语言模型 API 中转站（LLM API Relay），代理用户请求到多个上游 LLM 提供商（OpenAI、Anthropic、自定义端点），提供统一的 API Key 认证、渠道调度、用量追踪和 Web 管理界面。

- **技术栈**: Python 3 / FastAPI / SQLAlchemy (async + aiosqlite) / SQLite / httpx / PyJWT / cryptography
- **代码规模**: 8,427 行（Python 3,740 行，前端 4,588 行，配置 10 行）
- **数据库**: SQLite（WAL 模式，异步操作）
- **运行方式**: `uvicorn app.main:app --host 0.0.0.0 --port 8088`

## 2. 目录结构

```
bol-api/
├── app/
│   ├── main.py              # FastAPI 入口，lifespan 管理，路由注册
│   ├── config.py             # Pydantic Settings，环境变量配置
│   ├── auth/                 # 认证模块
│   │   ├── jwt.py            # JWT 创建/验证（HS256）
│   │   ├── middleware.py      # Starlette HTTP 中间件，API Key SHA256 校验
│   │   └── models.py         # Pydantic 模型（KeyCreate/Response/List/Reveal）
│   ├── channels/             # 渠道调度模块
│   │   ├── manager.py        # ChannelManager + ChannelCache + create_provider
│   │   └── models.py         # Pydantic 模型（ChannelCreate/Update/Response）
│   ├── db/                   # 数据库层
│   │   ├── database.py       # SQLAlchemy async engine + session + init_db
│   │   ├── models.py         # ORM 模型（APIKey, Channel, ModelPrice, UsageLog, SystemSetting）
│   │   └── crud.py           # 全部 CRUD 操作（737 行，最重文件）
│   ├── providers/            # 上游 API 适配器
│   │   ├── base.py           # BaseProvider ABC（chat_completion, stream, extract_usage）
│   │   ├── openai.py         # OpenAI 格式适配
│   │   ├── anthropic.py      # Anthropic 格式适配
│   │   └── custom.py         # 自定义渠道（按 api_protocol 切换 OpenAI/Anthropic）
│   ├── routers/              # API 路由
│   │   ├── proxy.py          # /v1/chat/completions + /v1/messages（786 行，核心代理）
│   │   ├── admin.py          # 管理界面路由（渠道/价格/设置 CRUD）
│   │   ├── keys.py           # API Key CRUD
│   │   ├── stats.py          # 统计接口（日志/摘要/模型统计/趋势）
│   ├── stats/                # 统计模块
│   │   ├── models.py         # Pydantic 响应模型
│   │   └── recorder.py       # UsageRecorder（asyncio.Queue + 后台任务）
│   ├── utils/                # 工具模块
│   │   ├── encryption.py     # Fernet 加密/解密 API Key
│   │   ├── http_client.py    # AsyncHttpClient 单例（httpx.AsyncClient + 超时缓存）
│   │   ├── logger.py         # 日志系统（RotatingFileHandler + RequestLogger）
│   │   ├── sanitize.py       # 请求参数清洗（effort 映射）
│   │   ├── tokenizer.py      # Token 估算（tiktoken 简化版）
│   ├── static/               # 前端文件
│   │   ├── admin.html        # 管理面板 HTML（388 行）
│   │   ├── login.html        # 登录页（463 行）
│   │   ├── css/admin.css     # 赛博朋克主题 CSS（2,126 行）
│   │   ├── js/admin.js       # 管理面板 JS（1,574 行）
├── requirements.txt          # 依赖列表
├── .env                      # 环境变量
├── CLAUDE.md                 # Claude Code 指令
└── README.md                 # 项目文档
```

## 3. 核心架构

### 3.1 请求处理流程

```
客户端请求
    │
    ▼
AuthMiddleware (Starlette HTTP Middleware)
    │  校验 Bearer token / x-api-key
    │  SHA256 哈希比对 → 注入 request.state.api_key_id
    │
    ▼
Proxy Router (/v1/chat/completions 或 /v1/messages)
    │  解析 model + stream 参数
    │  ChannelManager.select_all_channels(db, model, protocol)
    │  → 按协议筛选渠道列表
    │
    ▼
ChannelManager.select_channel(db, model, exclude_ids, protocol)
    │  优先级分组 → 最高优先级组 → 加权随机选择
    │  ChannelCache 缓存（60s TTL）
    │
    ▼
create_provider(channel) → OpenAI/Anthropic/CustomProvider
    │  provider.chat_completion(body) 或 provider.stream_chat_completion(body)
    │  AsyncHttpClient.post / post_stream（单例 httpx.AsyncClient）
    │
    ▼
provider.extract_usage(response) → {request_tokens, response_tokens, total_tokens}
    │  calculate_cost(db, model, tokens) → 查 ModelPrice 表
    │  UsageRecorder.record(...) → asyncio.Queue → 后台任务写入 UsageLog
    │
    ▼
返回 JSONResponse 或 StreamingResponse
```

### 3.2 渠道调度策略

| 策略 | 实现 |
|------|------|
| 模型匹配 | 精确匹配 + 通配符前缀（`gpt-4*` 匹配 `gpt-4-turbo`） |
| 协议筛选 | 按请求端点固定协议（`/v1/chat/completions` → `openai`，`/v1/messages` → `anthropic`） |
| 优先级分组 | 高优先级渠道优先，同组内加权随机 |
| Fallback | 最多 3 次尝试不同渠道，排除已失败渠道 |
| 缓存 | ChannelCache（60s TTL），渠道变更时 invalidate |

### 3.3 认证体系

| 认证方式 | 适用场景 |
|----------|----------|
| API Key (Bearer/x-api-key) | 用户请求代理接口，SHA256 哈希校验 |
| JWT Token (HS256) | 管理界面 API，24h 过期 |
| Admin Password | 管理界面登录 + 兼容旧接口 |

公开路径（无需认证）: `/admin`, `/stats`, `/static`, `/docs`, `/health`, `/`

### 3.4 数据模型

| 模型 | 表名 | 核心字段 | 说明 |
|------|------|----------|------|
| APIKey | api_keys | key_hash(SHA256), encrypted_key(Fernet), key_prefix, is_active | 用户密钥 |
| Channel | channels | provider_type, api_protocol, base_url, api_key, models(JSON), priority, weight | 上游渠道 |
| ModelPrice | model_prices | model(unique), input_price, output_price, is_active | 模型定价（$/M） |
| UsageLog | usage_logs | model, request_tokens, response_tokens, cost, status_code, latency_ms, timestamp | 用量记录 |
| SystemSetting | system_settings | key(unique), value | 系统配置键值对 |

### 3.5 Provider 协议适配

```
                    ┌─ OpenAIProvider ─── /v1/chat/completions ─── Bearer auth ─── prompt/completion_tokens
BaseProvider ABC ──┤
                    ├─ AnthropicProvider ─ /v1/messages ─────────── x-api-key ────── input/output_tokens
                    │
                    └─ CustomProvider ──── 按 api_protocol 切换上述两种格式
```

CustomProvider 是核心适配器：`provider_type=custom` 时根据 `api_protocol` 字段决定请求格式、端点、认证头和用量提取方式。

### 3.6 流式响应处理

**OpenAI 流式** (`stream_chat_response`):
- 直接转发 SSE 行，解析 `choices[0].delta.content` 累积文本
- `delta.get("content") or ""` 处理 JSON null 值
- 流结束后 `asyncio.shield(_record_stream_usage())` 防止 Starlette CancelledError

**Anthropic 流式** (`stream_anthropic_response`):
- SSE 事件缓冲（event + data 行，空行 flush）
- 解析 `content_block_delta` 累积文本，`message_start/message_delta` 提取用量
- 同样使用 `asyncio.shield` 保护后置记录

### 3.7 用量记录机制

```
UsageRecorder.record(...) → asyncio.Queue.put(data)
                                    │
                                    ▼
                            process_queue() 后台任务
                                    │
                                    ▼
                            create_usage_log(session, **data)
                            → OperationalError 重试 3 次
                            → 数据库锁定时递增等待
```

- 非阻塞：请求处理不等待 DB 写入完成
- 重试：数据库锁定时最多 3 次重试
- 清理：每小时清理 >90 天的日志
- 关闭：`drain(timeout=5.0)` 等待队列清空

### 3.8 统计系统

| API 端点 | 功能 | 时间维度 |
|----------|------|----------|
| `/stats/summary` | 全量汇总（请求数/Token/费用/RPM/TPM/天数） | 全量（天数从数据实际跨度计算） |
| `/stats/models` | 按模型分组统计（P50/峰值延迟/错误率） | hours / period(today/week/month) / 自定义 |
| `/stats/trend` | 时间桶 + 模型趋势数据（Top 8 + 其他） | 同上，自动选择小时/天颗粒度 |
| `/stats/logs` | 分页日志 + 筛选 + 汇总 | days / model / status |

日历感知计算：`_calc_start_time()` 将 `today/week/month` 映射到 UTC 00:00 起始时间。

## 4. 前端架构

### 4.1 技术栈

- 纯 HTML + CSS + JS（无框架）
- 赛博朋克主题（Orbitron/JetBrains Mono/Outfit 字体）
- Canvas 手绘趋势图（无第三方图表库）

### 4.2 页面结构

| 页面 | 文件 | 功能 |
|------|------|------|
| 管理面板 | admin.html + admin.js + admin.css | 5 个 Tab：概览/日志/密钥/渠道/价格 |
| 登录页 | login.html | JWT 登录 |

### 4.3 管理面板 Tab

| Tab | 功能 | 关键交互 |
|-----|------|----------|
| 概览 | 统计卡片 + 模型用量 + 趋势图 | 5时/本日/本周/本月/自定义周期切换 |
| 日志 | 分页日志表 + 筛选 + 汇总 | 天数/模型/状态筛选 |
| 密钥 | CRUD + 显示/隐藏/复制 | Fernet 解密显示完整 Key |
| 渠道 | CRUD + 测试 + 拉取模型 | provider_type/api_protocol 联动 |
| 价格 | CRUD + 启用/禁用 | $/M 定价 |

### 4.4 自动刷新

- 统计摘要：30s 间隔
- 模型统计：30s 间隔，沿用当前周期选择（自定义时段不自动刷新）

## 5. 关键设计决策

### 5.1 优点

1. **异步全链路**: FastAPI async + SQLAlchemy async + httpx async + asyncio.Queue，无阻塞点
2. **Fallback 机制**: 最多 3 次尝试不同渠道，5xx 重试、4xx 不重试
3. **shield 保护**: `asyncio.shield()` 防止流完成后 Starlette 取消后置 DB 操作
4. **渠道缓存**: 60s TTL 缓存避免每次请求查 DB，变更时主动 invalidate
5. **模型自动同步**: 创建/更新渠道时自动将新模型同步到价格列表
6. **日历感知统计**: 本日/本周/本月按日历边界计算而非固定小时数
7. **单例 HTTP 客户端**: 共享 httpx.AsyncClient，连接池复用，DB 可配置超时
8. **Fernet 加密**: API Key 加密存储，SHA256 哈希校验，仅管理员可解密查看

### 5.2 已识别的局限

1. **无跨协议 Fallback**: `/v1/chat/completions` 只找 `openai` 协议渠道，`/v1/messages` 只找 `anthropic` 协议渠道。若模型只在另一协议渠道上，返回 "No available channel"。已设计转换方案但暂未实施。

2. **verify_admin 重复**: `admin.py`、`keys.py`、`stats.py` 各自定义了 `verify_admin()` 函数，逻辑完全相同（JWT + 密码双认证）。应提取为共享依赖。

3. **SQLite 单写限制**: WAL 模式允许读写并发，但写操作仍串行。高并发写入场景可能遇到锁等待。

4. **Token 估算精度**: `tokenizer.py` 使用简化估算而非 tiktoken 精确计算，上游未返回 usage 时估算可能偏差。

5. **无速率限制**: APIKey 有 `rate_limit` 字段但未实现限流逻辑。

6. **前端无框架**: 纯 JS 1,574 行，DOM 操作为主，复杂交互维护成本较高。

7. **渠道 API Key 未加密存储**: Channel 的 `api_key` 字段直接存储原始值，未像 APIKey 的 `encrypted_key` 一样加密。

## 6. 依赖关系图

```
main.py
  ├── config.py (Settings)
  ├── db/database.py (init_db, get_db)
  ├── auth/middleware.py (setup_auth_middleware)
  │     └── db/crud.py (get_api_key_by_hash)
  │     └── db/database.py (async_session)
  ├── stats/recorder.py (UsageRecorder.init, process_queue, start_cleanup_task)
  ├── routers/proxy.py
  │     ├── channels/manager.py (ChannelManager, create_provider)
  │     │     └── db/crud.py (get_active_channels, get_channel_by_id)
  │     │     └── providers/* (OpenAI/Anthropic/CustomProvider)
  │     ├── stats/recorder.py (UsageRecorder.record, calculate_cost)
  │     ├── utils/http_client.py (AsyncHttpClient)
  │     ├── utils/logger.py (RequestLogger)
  │     ├── utils/tokenizer.py (count_tokens, count_message_tokens)
  ├── routers/admin.py
  │     ├── db/crud.py (channel/price/setting CRUD)
  │     ├── channels/models.py (Pydantic models)
  │     ├── auth/jwt.py (create_token, verify_token)
  │     ├── utils/http_client.py (AsyncHttpClient, refresh_timeout_cache)
  ├── routers/keys.py
  │     ├── db/crud.py (api_key CRUD)
  │     ├── auth/jwt.py (verify_token)
  │     ├── utils/encryption.py (decrypt_key, is_encrypted)
  ├── routers/stats.py
  │     ├── db/crud.py (usage logs/summary/model_stats/trend)
  │     ├── stats/models.py (Pydantic response models)
  │     ├── auth/jwt.py (verify_token)
```

## 7. API 端点清单

| 端点 | 方法 | 认证 | 功能 |
|------|------|------|------|
| `/` | GET | 公开 | 服务状态 |
| `/health` | GET | 公开 | 健康检查 |
| `/v1/chat/completions` | POST | API Key | OpenAI 格式代理 |
| `/v1/messages` | POST | API Key | Anthropic 格式代理 |
| `/admin` | GET | 公开 | 管理面板 HTML |
| `/admin/login` | GET | 公开 | 登录页 HTML |
| `/admin/login` | POST | 公开 | 登录获取 JWT |
| `/admin/keys` | GET/POST | Admin | 密钥列表/创建 |
| `/admin/keys/{id}` | DELETE/PATCH | Admin | 删除/启禁密钥 |
| `/admin/keys/{id}/reveal` | GET | Admin | 显示完整密钥 |
| `/admin/channels` | GET/POST | Admin | 渠道列表/创建 |
| `/admin/channels/{id}` | PATCH/DELETE | Admin | 更新/删除渠道 |
| `/admin/channels/{id}/toggle` | POST | Admin | 启禁渠道 |
| `/admin/channels/{id}/test` | POST | Admin | 测试渠道 |
| `/admin/channels/fetch-models` | POST | Admin | 拉取上游模型 |
| `/admin/prices` | GET/POST | Admin | 价格列表/创建 |
| `/admin/prices/{id}` | PATCH/DELETE | Admin | 更新/删除价格 |
| `/admin/prices/{id}/toggle` | POST | Admin | 启禁价格 |
| `/admin/settings` | GET | Admin | 系统设置 |
| `/admin/settings/{key}` | PUT | Admin | 更新设置 |
| `/stats/summary` | GET | Admin | 用量摘要 |
| `/stats/logs` | GET | Admin | 用量日志 |
| `/stats/models` | GET | Admin | 模型统计 |
| `/stats/models/list` | GET | Admin | 模型列表 |
| `/stats/trend` | GET | Admin | 趋势数据 |

## 8. 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | admin123 | 管理界面密码 |
| `DATABASE_URL` | sqlite+aiosqlite:///./data/bol_api.db | 数据库路径 |
| `ENCRYPTION_KEY` | default_encryption_key_32_bytes! | Fernet 加密密钥 |
| `JWT_SECRET` | default_jwt_secret_change_in_production! | JWT 签名密钥 |
| `JWT_EXPIRE_HOURS` | 24 | JWT 过期时间 |
| `HOST` | 0.0.0.0 | 监听地址 |
| `PORT` | 8088 | 监听端口 |
| `REQUEST_TIMEOUT` | 300 | 上游请求超时（秒） |

## 9. 代码量分布

| 文件 | 行数 | 占比 | 角色 |
|------|------|------|------|
| admin.css | 2,126 | 25.3% | 前端样式 |
| admin.js | 1,574 | 18.7% | 前端逻辑 |
| proxy.py | 786 | 9.3% | 核心代理路由 |
| crud.py | 737 | 8.7% | 数据库操作 |
| admin.py | 430 | 5.1% | 管理路由 |
| logger.py | 277 | 3.3% | 日志系统 |
| admin.html | 388 | 4.6% | 管理面板 HTML |
| login.html | 463 | 5.5% | 登录页 |
| manager.py | 229 | 2.7% | 渠道调度 |
| 其他 | 617 | 7.3% | 配置/模型/工具等 |

**后端 3,740 行 (44.4%) / 前端 4,588 行 (54.5%) / 配置 10 行 (0.1%)**

## 10. 改进建议

1. **提取共享 verify_admin**: 将 `admin.py`、`keys.py`、`stats.py` 中重复的 `verify_admin()` 提取到 `app/auth/dependencies.py`，作为 FastAPI `Depends` 共享依赖。

2. **加密渠道 API Key**: Channel 的 `api_key` 应像 APIKey 的 `encrypted_key` 一样使用 Fernet 加密存储，仅在发送上游请求时解密。

3. **实现速率限制**: APIKey 模型已有 `rate_limit` 字段，可在 AuthMiddleware 中实现基于滑动窗口的 RPM 限流。

4. **跨协议 Fallback**（已设计未实施）: 当同协议无可用渠道时，自动 fallback 到另一协议渠道，转换请求/响应格式。方案详见 `docs/superpowers/plans/` 中的计划文档。

5. **前端组件化**: 1,574 行纯 JS 维护成本高，可考虑引入轻量框架（如 Alpine.js）或至少将 JS 模块化拆分。

6. **数据库迁移**: 当前使用 `Base.metadata.create_all` 直接建表，无迁移工具。建议引入 Alembic 管理 schema 变更。