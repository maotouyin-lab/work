# AI 职业规划与求职 Agent

<div align="center"><img src="qrcode.png" width="160" alt="GitHub 仓库二维码"></div>

基于双 LLM 架构的智能职业规划助手，提供职业咨询、情绪支持、技能迁移分析、简历优化、面试准备等服务。纯 Python 标准库 HTTP 服务，零前端依赖。

## 架构

```
用户 → HTTP Server (纯 Python stdlib) / 阿里云 FC
        ├── DeepSeek (deepseek-chat) — 职业咨询、简历优化、面试准备等全部 AI 分析
        └── 千问 (qwen-long) — PDF 文件上传解析（提取文本后仍由 DeepSeek 处理）
```

### Prompt 分层设计

| 层级 | 类型 | 说明 |
|------|------|------|
| Layer 1 | 安全护栏 | 代码强制执行，非建议性约束 |
| Layer 2 | 角色设定 | 10年+ 职业规划分析师 persona |
| Layer 3 | 功能指令 | 各场景专用 prompt（含反编造铁律、情绪支持等） |

### 安全机制：双重校验

| 层级 | 方式 | 做什么 |
|------|------|--------|
| 代码正则硬拦截 | `safety.py` `SafetyGuard` | 拦截「你应该辞职」「编造经历」等红线表述 |
| LLM 语义审查 | Step 5 | 检测代码正则漏掉的隐含风险并追加入 warnings |

## 功能模块

- **职业规划咨询** — 多轮对话，自动提取用户画像 → 意图识别 → 查市场数据 → 个性化分析
- **情绪支持** — 检测焦虑/迷茫状态自动切换共情模式，先接住情绪再轻量探索；前端快捷入口「聊聊情绪」
- **技能迁移分析** — 当前岗位 → 目标岗位的技能映射（可直接迁移 / 需转化 / 需新学）与缺口分析
- **简历优化** — 上传/粘贴简历 + JD，AI 逐条对照匹配，STAR 法则重写；内置反编造铁律（禁止虚构数字和经历）
- **面试准备** — 基于用户背景 + 目标 JD 生成个性化模拟题（背景深挖 / 能力验证 / 转行动机三类）
- **Offer 对比** — 多维度客观对比，不做推荐

## 快速启动

```bash
cd agent
pip install openai python-dotenv
cp .env.example .env   # 编辑填入 API Key
python server.py
```

访问 `http://localhost:5000`

## 环境变量

复制 `.env.example` 为 `.env`，填入 API Key：

```env
# DeepSeek（职业咨询、简历优化、面试准备等全部 AI 分析）
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 千问（PDF 文件上传解析，需 qwen-long 的文件上传能力）
QWEN_API_KEY=sk-xxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-long
```

## 项目结构

```
agent/
├── server.py          # HTTP 服务入口 (localhost:5000)
├── fc_handler.py      # 阿里云函数计算 FC HTTP 入口
├── api_core.py        # 共享业务逻辑（初始化 + API 函数，server/fc 共同引用）
├── orchestrator.py    # Agent 编排核心（多流程调度、5 步流水线）
├── prompts.py         # 分层 Prompt 系统（安全→角色→功能，含情绪支持/反编造）
├── llm.py             # 多 LLM 客户端（DeepSeek + 千问，OpenAI 兼容协议）
├── safety.py          # 安全护栏（代码层硬校验 + LLM 语义审查）
├── tools.py           # 工具函数（PDF/DOCX 解析、技能图谱查询、市场数据查询）
├── cost.py            # Token 成本追踪
├── evaluator.py       # Agent 输出质量评估（5 维度评分差异化样本）
├── demo_data.py       # 示例数据（24 技能、10 岗位、3 用户画像，均标 [示例]）
├── main.py            # CLI 交互入口
└── static/
    └── index.html     # 前端 UI（零依赖，纯 HTML/CSS/JS）
```

### 核心流程（以技能迁移为例）

```
用户输入 → Step 1: 意图识别(LLM)
         → Step 2: 技能图谱查询(非AI, 确定性图查询)
         → Step 3: 市场数据查询(非AI, 结构化API)
         → Step 4: AI综合分析(LLM, 3层Prompt组装)
         → Step 5: 安全检查(代码正则 + LLM双重校验)
         → 返回结构化结果
```

## 安全设计

安全护栏在 `safety.py` 的 `SafetyGuard` 类中做硬校验，即使模型输出违反规则也会被代码层拦截：

- 不替用户做人生决策（拦截「你应该辞职」「建议你选A公司」）
- 不协助简历造假（拦截编造经历、虚构项目、虚增数字）
- 市场数据标注来源和时效（所有数据源标 `[示例]`，区分 demo 和真实数据）
- 检测焦虑/抑郁情绪，共情优先于分析，必要时建议专业帮助
- 简历优化后自动追加提醒：「所有量化数字和具体成果请以原始简历为准」

## 设计决策（面试参考）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 技能图谱/市场数据 | 不走 LLM | 图查询和结构化 API 是确定性操作，LLM 可能编造数据 |
| 简历文本解析 | 纯 Python 标准库 | PDF 正则提取流、DOCX zipfile+XML，零依赖 |
| 安全检查 | 代码正则 + LLM 双重 | 代码拦截确定性红线，LLM 补语义漏网之鱼 |
| 分层 Prompt | Safety → Role → Task | 每层独立管理和调试，Safety 层不可被覆盖 |
| 双模型 | DeepSeek + 千问 | DeepSeek 高性价比分析，千问 qwen-long 文件上传能力强 |
| 前端 | 零依赖 HTML/CSS/JS | 减少构建步骤，部署简单，面试展示友好 |
| 问候快速通道 | 不调 LLM | 「你好」直接返回欢迎语，0 延迟 |

## 部署

支持多种部署方式：

- **本地开发** — `python server.py`，访问 `http://localhost:5000`
- **阿里云函数计算 FC** — `fc_handler.py` 作为 HTTP 函数入口，适配 FC 事件模型
- **Render** — 使用项目中的 `render.yaml` 一键部署
