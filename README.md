# AI 职业规划与求职 Agent

<div align="center"><img src="qrcode.png" width="160" alt="GitHub 仓库二维码"></div>

基于双 LLM 架构的智能职业规划助手，提供职业咨询、情绪支持、技能迁移分析、简历优化、面试准备等服务。纯 Python 标准库 HTTP 服务，零前端框架依赖。

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

### 安全机制：双重校验 + 输入预检

| 层级 | 方式 | 做什么 |
|------|------|--------|
| 输入预检（零成本） | 代码正则硬拦截 | Step 0 前拦截恶意请求，0 token 消耗，<1ms 响应 |
| 代码正则硬拦截 | `SafetyGuard.check()` | 输出层拦截「你应该辞职」「编造经历」等红线 |
| LLM 语义审查 | Step 5 | 检测代码正则漏掉的隐含风险并追加入 warnings |

## 功能模块

- **职业规划咨询** — 多轮对话，自动提取用户画像 → 意图识别 → 查市场数据 → 个性化分析
- **情绪支持** — 检测焦虑/迷茫状态自动切换共情模式，先接住情绪再轻量探索；前端快捷入口「聊聊情绪」
- **技能迁移分析** — 当前岗位 → 目标岗位的技能映射（可直接迁移 / 需转化 / 需新学）与缺口分析
- **简历优化** — 上传/粘贴简历 + JD，AI 逐条对照匹配，STAR 法则重写；内置反编造铁律（禁止虚构数字和经历）
- **面试准备** — 基于用户背景 + 目标 JD 生成个性化模拟题（背景深挖 / 能力验证 / 转行动机三类）
- **Badcase 追踪** — 自动检测编造数字、数据来源幻觉、安全 near-miss；前端面板支持筛选（Badcase/Goodcase/已修复/待处理）+ 标注修复

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
├── orchestrator.py    # Agent 编排核心（多流程调度、6 步流水线含输入预检）
├── prompts.py         # 分层 Prompt 系统（安全→角色→功能，含情绪支持/反编造）
├── llm.py             # 多 LLM 客户端（DeepSeek + 千问，OpenAI 兼容协议）
├── safety.py          # 安全护栏（上下文感知正则 + 双重校验）
├── badcase.py         # Badcase/Goodcase 追踪（自动检测 + 人工标注）
├── badcases.json      # Case 存储（人类可读 JSON）
├── tools.py           # 工具函数（PDF/DOCX 解析、技能图谱查询、市场数据查询）
├── cost.py            # Token 成本追踪（DeepSeek 定价）
├── evaluator.py       # Agent 输出质量评估（5 维度评分）
├── demo_data.py       # 示例数据（24 技能、10 岗位、3 用户画像，均标 [示例]）
├── main.py            # CLI 交互入口
└── static/
    └── index.html     # 前端 UI（零框架依赖，含 Badcase 管理面板）
```

### 核心流程

```
用户输入 → Step -1: 输入安全预检(代码正则，零成本)
         → Step 0: 提取用户画像(LLM)
         → Step 1: 意图识别(LLM)
         → Step 2: 技能图谱查询(非AI, 确定性图查询)
         → Step 3: 市场数据查询(非AI, 结构化API)
         → Step 4: AI综合分析(LLM, 3层Prompt组装)
                ├── 简历模式: 自动检测编造数字 → 写入 badcase
                └── 全模式: 检测数据来源未标注 → 写入 badcase
         → Step 5: 安全检查(代码正则 + LLM双重校验)
                ├── 拦截: 写入 badcase (safety_blocked)
                └── near-miss: 写入 badcase (safety_near_miss)
         → 返回结构化结果
```

## 安全设计

安全护栏在 `safety.py` 的 `SafetyGuard` 类中做硬校验，即使模型输出违反规则也会被代码层拦截：

- **输入预检**：LLM 调用前拦截恶意请求，0 token 消耗，避免 API TOS 风险和成本浪费
- 不替用户做人生决策（拦截「你应该辞职」「建议你选A公司」）
- 不协助简历造假（拦截编造经历、虚构项目、虚增数字；上下文感知，区分「包装经历」的真伪）
- 市场数据标注来源和时效（所有数据源标 `[示例]`，区分 demo 和真实数据）
- 检测焦虑/抑郁情绪，共情优先于分析，必要时建议专业帮助
- 简历优化后自动追加提醒：「所有量化数字和具体成果请以原始简历为准」

## Badcase 追踪系统

在 LLM 容易产生幻觉的关键节点做自动检测 + 人工标注，用于 Prompt 迭代和质量监控。

### 自动检测点

| 检测点 | 位置 | 规则 |
|--------|------|------|
| 简历数字编造 | Step 4 (resume_optimize) | 提取 LLM 输出中的数字，检查原文是否包含 |
| 数据来源幻觉 | Step 4 (全流程) | 检查输出是否引用了未标注 `[示例]` 的数据来源 |
| 安全 near-miss | Step 5 | LLM 安全审查发现代码正则漏掉的风险 |
| 代码层拦截 | Step 5 | 输出被安全护栏拦截 |

### 前端管理面板

- 双标签切换：运行追踪 / Badcase
- 统计卡片：Badcase / Goodcase / 已修复 / 待处理，点击筛选对应列表
- 标注修复：未修复 case 展开后输入说明 → 标注修复 → 自动归类到已修复
- 检测来源标签：自动检测（绿）/ 安全检查（红）/ 人工标注（紫）

## 设计决策（面试参考）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 技能图谱/市场数据 | 不走 LLM | 图查询和结构化 API 是确定性操作，LLM 可能编造数据 |
| 简历文本解析 | 纯 Python 标准库 | PDF 正则提取流、DOCX zipfile+XML，零依赖 |
| 安全检查 | 输入预检 + 代码正则 + LLM 三重 | 输入拦截省成本，代码拦截确定性红线，LLM 补语义漏网 |
| 分层 Prompt | Safety → Role → Task | 每层独立管理和调试，Safety 层不可被覆盖 |
| 双模型 | DeepSeek + 千问 | DeepSeek 高性价比分析，千问 qwen-long 文件上传能力强 |
| 前端 | 零框架 HTML/CSS/JS | 减少构建步骤，部署简单，面试展示友好 |
| 问候快速通道 | 不调 LLM | 「你好」「嘿」等 18 种问候直接返回欢迎语，0 延迟 |
| Badcase 追踪 | 自动检测 + 人工标注 | 幻觉高发区自动埋点，前端面板支持筛选/标注/统计 |
| 信息不足处理 | 标注不确定性 + 自然追问 | 不机械拒绝，体验优先；LLM 限定分析 + 明确标注缺口 |

## 部署

支持多种部署方式：

- **本地开发** — `python server.py`，访问 `http://localhost:5000`
- **阿里云函数计算 FC** — `fc_handler.py` 作为 HTTP 函数入口，适配 FC 事件模型
- **Render** — 使用项目中的 `render.yaml` 一键部署
