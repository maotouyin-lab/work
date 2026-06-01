# AI 职业规划与求职 Agent

<div align="center"><img src="qrcode.png" width="160" alt="GitHub 仓库二维码"></div>

基于双 LLM 架构的智能职业规划助手，提供职业咨询、技能迁移分析、简历优化、面试准备、Offer 对比等服务。

## 架构

```
用户 → HTTP Server (纯 Python stdlib)
        ├── DeepSeek (职业咨询、面试准备)
        └── 千问 qwen-turbo (简历优化) + qwen-long (PDF 解析)
```

### Prompt 分层设计

| 层级 | 类型 | 说明 |
|------|------|------|
| Layer 1 | 安全护栏 | 代码强制执行，非建议性约束 |
| Layer 2 | 角色设定 | 10年+ 职业规划分析师 persona |
| Layer 3 | 功能指令 | 各场景专用 prompt |

## 功能模块

- **职业规划咨询** — 多轮对话，自动提取用户画像，查市场数据，给个性化分析
- **技能迁移分析** — 当前岗位 → 目标岗位的技能映射与缺口分析
- **简历优化** — 上传/粘贴简历 + JD，AI 逐条对照匹配度，STAR 法则重写
- **面试准备** — 基于用户背景 + 目标 JD 生成个性化模拟题
- **Offer 对比** — 多维度客观对比，不做推荐

## 快速启动

```bash
cd agent
pip install openai python-dotenv
python server.py
```

访问 `http://localhost:5000`

## 环境变量

复制 `.env.example` 为 `.env`，填入 API Key：

```env
# DeepSeek（职业咨询、面试准备）
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 千问（简历优化 + PDF 解析）
QWEN_API_KEY=sk-xxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-turbo
```

## 项目结构

```
agent/
├── server.py          # HTTP 服务入口 (localhost:5000)
├── orchestrator.py    # Agent 编排核心
├── prompts.py         # 分层 Prompt 系统
├── llm.py             # 多 LLM 客户端（DeepSeek + 千问）
├── safety.py          # 安全护栏（代码层硬校验）
├── tools.py           # 工具函数（PDF/DOCX 解析等）
├── cost.py            # Token 成本追踪
├── evaluator.py       # 面试评估
├── demo_data.py       # 示例数据和用户画像
├── main.py            # CLI 交互入口
└── static/
    └── index.html     # 前端 UI（零依赖，纯 HTML/CSS/JS）
```

## 安全设计

安全护栏在 `orchestrator.py` 的 `SafetyGuard` 类中做硬校验，即使模型输出违反规则也会被代码层拦截：

- 不替用户做人生决策
- 不协助简历造假
- 市场数据标注来源和时效
- 检测焦虑/抑郁情绪并建议专业帮助
