# bol-api

大语言模型 API 中转站 — 代理用户请求到多个上游 LLM 提供商，提供统一的 API Key 认证、渠道调度、用量追踪和 Web 管理界面。

## 功能特性

- **多服务商代理** — OpenAI、Anthropic、自定义渠道，统一入口
- **API Key 认证** — SHA256 哈希校验 + Fernet 加密存储，支持 Bearer / x-api-key
- **渠道调度** — 按模型匹配、协议筛选、优先级分组、加权随机选择
- **自动 Fallback** — 渠道失败时自动切换，最多 3 次尝试不同渠道
- **流式代理** — SSE 流式转发（OpenAI / Anthropic），asyncio.shield 保护后置记录
- **用量追踪** — Token 计量、费用估算、延迟监控、错误率统计
- **Web 管理面板** — 赛博朋克主题 UI，支持密钥/渠道/价格/统计管理
- **日历感知统计** — 本日/本周/本月按日历边界计算，支持自定义时间段

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
```

或直接创建 `.env` 文件：

```env
ADMIN_PASSWORD=admin123          # 管理界面密码（生产环境务必修改）
DATABASE_URL=sqlite+aiosqlite:///./data/bol_api.db
ENCRYPTION_KEY=your_32_byte_key  # Fernet 加密密钥（生产环境务必修改）
JWT_SECRET=your_jwt_secret       # JWT 签名密钥（生产环境务必修改）
JWT_EXPIRE_HOURS=24              # JWT 过期时间
HOST=0.0.0.0                     # 监听地址
PORT=8088                        # 监听端口
REQUEST_TIMEOUT=300               # 上游请求超时（秒）
```

### 启动服务

```bash
# 开发模式（自动重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8088

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8088
```

### 访问管理界面

浏览器打开 http://localhost:8088/admin ，使用 `ADMIN_PASSWORD` 登录。

## 项目架构

```
bol-api/
├── app/
│   ├── main.py              # FastAPI 入口，lifespan 管理
│   ├── config.py             # Pydantic Settings 环境变量配置
│   ├── auth/                 # 认证模块
│   │   ├── jwt.py            # JWT 创建/验证（HS256）
│   │   ├── middleware.py      # HTTP 中间件，API Key SHA256 校验
│   │   └── models.py         # Pydantic 模型
│   ├── channels/             # 渠道调度
│   │   ├── manager.py        # ChannelManager + 优先级分组 + 加权随机
│   │   └── models.py         # Pydantic 模型
│   ├── db/                   # 数据库层
│   │   ├── database.py       # SQLAlchemy async engine + session
│   │   ├── models.py         # ORM 模型
│   │   └── crud.py           # CRUD 操作
│   ├── providers/            # 上游 API 适配器
│   │   ├── base.py           # BaseProvider ABC
│   │   ├── openai.py         # OpenAI 格式适配
│   │   ├── anthropic.py      # Anthropic 格式适配
│   │   └── custom.py         # 自定义渠道（按 api_protocol 切换）
│   ├── routers/              # API 路由
│   │   ├── proxy.py          # 代理核心（chat_completions + messages）
│   │   ├── admin.py          # 管理界面路由
│   │   ├── keys.py           # API Key CRUD
│   │   ├── stats.py          # 统计接口
│   ├── stats/                # 统计模块
│   │   ├── models.py         # Pydantic 响应模型
│   │   └── recorder.py       # UsageRecorder（asyncio.Queue 后台写入）
│   ├── utils/                # 工具模块
│   │   ├── encryption.py     # Fernet 加密/解密
│   │   ├── http_client.py    # httpx.AsyncClient 单例
│   │   ├── logger.py         # 日志系统
│   │   ├── sanitize.py       # 请求参数清洗
│   │   └── tokenizer.py      # Token 估算
│   ├── static/               # 前端文件（赛博朋克主题管理面板）
│       ├── admin.html
│       ├── login.html
│       ├── css/admin.css
│       ├── js/admin.js
├── data/                     # SQLite 数据库 + 日志（运行时生成）
├── logs/                     # 应用/请求/错误日志（运行时生成）
├── requirements.txt
├── .env                      # 环境变量
└── README.md
```

### 请求处理流程

```
客户端请求 → AuthMiddleware (SHA256 校验)
    → ChannelManager (模型匹配 → 协议筛选 → 优先级分组 → 加权随机)
    → Provider (格式化请求 → 转发到上游)
    → UsageRecorder (异步记录 Token/费用/延迟)
    → 返回 JSONResponse / StreamingResponse
```

### 渠道调度策略

| 策略 | 说明 |
|------|------|
| 模型匹配 | 精确匹配 + 通配符前缀（`gpt-4*` 匹配 `gpt-4-turbo`） |
| 协议筛选 | 端点决定协议：`/v1/chat/completions` → `openai`，`/v1/messages` → `anthropic` |
| 优先级分组 | 高优先级渠道优先选择 |
| 加权随机 | 同优先级组内按权重随机分配 |
| Fallback | 失败时切换渠道，最多 3 次，5xx 重试、4xx 不重试 |
| 缓存 | ChannelCache 60s TTL，渠道变更时主动失效 |

### Provider 协议适配

```
BaseProvider ABC
  ├── OpenAIProvider    — /v1/chat/completions + Bearer auth
  ├── AnthropicProvider — /v1/messages + x-api-key
  └── CustomProvider    — 按 api_protocol 字段自动切换上述两种格式
```

CustomProvider 是核心适配器：当 `provider_type=custom` 时，根据 `api_protocol` 字段决定请求格式、端点、认证头和用量提取方式。这意味着任何兼容 OpenAI 或 Anthropic API 格式的服务商，只需设置对应的 `api_protocol` 即可接入。

## API 端点

### 代理接口（需要 API Key）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI 格式代理（Bearer token 或 x-api-key） |
| `/v1/messages` | POST | Anthropic 格式代理（Bearer token 或 x-api-key） |

请求格式与上游完全一致，只需将 `base_url` 指向 bol-api 即可：

```python
# OpenAI 格式示例
from openai import OpenAI

client = OpenAI(
    api_key="bol-your-api-key",
    base_url="http://localhost:8088/v1"
)
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)

# Anthropic 格式示例
import anthropic

client = anthropic.Anthropic(
    api_key="bol-your-api-key",
    base_url="http://localhost:8088"
)
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)
```

### 公开接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 服务状态 |
| `/health` | GET | 健康检查 |
| `/admin` | GET | 管理面板 |
| `/admin/login` | GET/POST | 登录页 / JWT 认证 |

### 管理接口（需要 JWT Token）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/admin/keys` | GET/POST | 密钥列表 / 创建 |
| `/admin/keys/{id}` | DELETE/PATCH | 删除 / 启禁密钥 |
| `/admin/keys/{id}/reveal` | GET | 显示完整密钥 |
| `/admin/channels` | GET/POST | 渠道列表 / 创建 |
| `/admin/channels/{id}` | PATCH/DELETE | 更新 / 删除渠道 |
| `/admin/channels/{id}/toggle` | POST | 启禁渠道 |
| `/admin/channels/{id}/test` | POST | 测试渠道连通性 |
| `/admin/channels/fetch-models` | POST | 拉取上游模型列表 |
| `/admin/prices` | GET/POST | 价格列表 / 创建 |
| `/admin/prices/{id}` | PATCH/DELETE | 更新 / 删除价格 |
| `/admin/prices/{id}/toggle` | POST | 启禁价格 |
| `/admin/settings` | GET | 系统设置 |
| `/admin/settings/{key}` | PUT | 更新设置 |

### 统计接口（需要 JWT Token）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/stats/summary` | GET | 全量汇总（请求数/Token/费用/RPM/TPM） |
| `/stats/logs` | GET | 分页日志 + 篩选 + 汇总 |
| `/stats/models` | GET | 模型统计（P50/峰值延迟/错误率） |
| `/stats/models/list` | GET | 模型列表 |
| `/stats/trend` | GET | 时间桶 + 模型趋势数据 |

## 认证体系

| 认证方式 | 适用场景 | 实现 |
|----------|----------|------|
| API Key | 代理接口（Bearer / x-api-key） | SHA256 哈希校验，Fernet 加密存储 |
| JWT Token | 管理接口（Authorization: Bearer） | HS256 签名，24h 过期 |
| Admin Password | 管理界面登录 | 密码验证后发放 JWT |

## 管理面板

基于纯 HTML/CSS/JS 的赛博朋克主题管理面板，5 个 Tab：

| Tab | 功能 |
|-----|------|
| 概览 | 统计卡片 + 模型用量 + 请求趋势图（Canvas 绘制） |
| 日志 | 分页日志表 + 天数/模型/状态筛选 |
| 密钥 | CRUD + 显示/隐藏/复制完整 Key |
| 渠道 | CRUD + 测试连通性 + 拉取模型 + provider_type/api_protocol 联动 |
| 价格 | CRUD + 启禁（$/M 定价） |

趋势图特性：
- 请求数/Token 数/费用三种指标切换
- 本日/本周/本月/自定义时间段
- 总请求聚合线（金色虚线，点击自动聚焦）
- Top 8 模型 + 其它聚合

## 用量追踪

- **非阻塞记录** — asyncio.Queue + 后台任务，请求处理不等待 DB 写入
- **自动重试** — 数据库锁定时最多 3 次重试，递增等待
- **自动清理** — 每小时清理 >90 天的日志
- **Token 估算** — 上游未返回 usage 时自动估算
- **费用计算** — 基于 ModelPrice 表（$/M），自动计算每次请求费用

## 数据模型

| 模型 | 核心字段 | 说明 |
|------|----------|------|
| APIKey | key_hash, encrypted_key, key_prefix, is_active | 用户密钥 |
| Channel | provider_type, api_protocol, base_url, api_key, models, priority, weight | 上游渠道 |
| ModelPrice | model, input_price, output_price, is_active | 模型定价 |
| UsageLog | model, request_tokens, response_tokens, cost, status_code, latency_ms | 用量记录 |
| SystemSetting | key, value | 系统配置 |

## 技术栈

- **后端**: Python 3 / FastAPI / SQLAlchemy (async + aiosqlite) / httpx / PyJWT / cryptography
- **前端**: 纯 HTML + CSS + JS（无框架），赛博朋克主题，Canvas 趋势图
- **数据库**: SQLite（WAL 模式，异步操作）