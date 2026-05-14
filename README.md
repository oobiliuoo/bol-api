# bol-api

大模型API中转站 - 统一代理多个大模型服务商的API请求

## 功能
- API Key认证管理
- 多服务商代理(OpenAI、Anthropic、自定义渠道)
- 用量统计
- Web管理界面

## 快速开始

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 设置管理员密码和加密密钥
```

3. 启动服务
```bash
uvicorn app.main:app --reload
```

4. 访问管理界面
打开 http://localhost:8088/admin

## API端点
- `/v1/chat/completions` - OpenAI兼容聊天API
- `/v1/messages` - Anthropic兼容消息API