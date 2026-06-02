# AI 职业规划与求职 Agent

基于双 LLM 架构的智能职业规划助手，提供职业咨询、情绪支持、技能迁移分析、简历优化、面试准备等服务。纯 Python 标准库 HTTP 服务，零前端框架依赖。

## 架构

```
用户 → HTTP Server (纯 Python stdlib) / 阿里云 FC
        ├── DeepSeek (deepseek-chat) — 职业咨询、面试准备等核心分析
        ├── 千问 (qwen-turbo) — 简历优化（中文理解更优）
        └── 千问 (qwen-long) — PDF 文件上传解析
        └── 阿里云 OSS — Badcase 数据持久化（FC 环境）/ NAS / 本地文件
```

### Prompt 分层设计

| 层级 | 类型 | 说明 |
|------|------|------|
| Layer 1 | 安全护栏 | 代码强制执行，非建议性约束 |
| Layer 2 | 角色设定 | 10年+ 职业规划分析师 persona |
| Layer 3 | 功能指令 | 各场景专用 prompt（含反编造铁律、情绪支持等） |

### 安全机制：三重校验

| 层级 | 方式 | 做什么 |
|------|------|--------|
| 输入预检（零成本） | 代码正则硬拦截 | Step 0 前拦截恶意请求，0 token 消耗，<1ms 响应 |
| 代码正则硬拦截 | `SafetyGuard.check()` | 输出层拦截「你应该辞职」「编造经历」等红线，上下文感知区分「包装」和「造假」 |
| LLM 语义审查 | Step 5 | 检测代码正则漏掉的隐含风险并追加入 warnings |

## 功能模块

- **职业规划咨询** — 多轮对话，自动提取用户画像 → 意图识别 → 查市场数据 → 个性化分析
- **情绪支持** — 检测焦虑/迷茫状态自动切换共情模式，先接住情绪再轻量探索；前端快捷入口「聊聊情绪」
- **技能迁移分析** — 当前岗位 → 目标岗位的技能映射（可直接迁移 / 需转化 / 需新学）与缺口分析
- **简历优化** — 上传/粘贴简历 + JD，AI 逐条对照匹配，STAR 法则重写；内置反编造铁律（禁止虚构数字和经历）
- **面试准备** — 基于用户背景 + 目标 JD 生成个性化模拟题（背景深挖 / 能力验证 / 转行动机三类）
- **Badcase 追踪** — 自动检测编造数字、数据来源幻觉、安全 near-miss；前端面板支持筛选 + 标注修复
- **Badcase 持久化存储** — FC 环境自动对接阿里云 OSS；也支持 NAS 挂载路径和本地文件

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
# DeepSeek（职业咨询、面试准备等核心分析）
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 千问（简历优化 + PDF 文件解析）
QWEN_API_KEY=sk-xxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-turbo
```

### Badcase 持久化存储（FC 部署必配）

| 变量名 | 用途 | 示例 |
|--------|------|------|
| `OSS_BUCKET` | OSS Bucket 名称（设置后自动启用 OSS 存储） | `career-agent-data` |
| `OSS_ENDPOINT` | OSS 地域 Endpoint | `oss-cn-hongkong.aliyuncs.com` |
| `OSS_ACCESS_KEY_ID` | AccessKey ID（可选，FC RAM 角色可替代） | — |
| `OSS_ACCESS_KEY_SECRET` | AccessKey Secret（可选，FC RAM 角色可替代） | — |
| `BADCASE_STORAGE_PATH` | 自定义文件路径（NAS 挂载场景，OSS 未设置时生效） | `/mnt/nas/badcases.json` |

存储优先级：`OSS_BUCKET` → `BADCASE_STORAGE_PATH` → 本地文件（代码目录可写）→ `/tmp/badcases.json`（FC 只读环境）

FC 运行时若绑定了 RAM 角色（有 OSS 权限），无需手动设置 AccessKey，代码自动复用 `ALIBABA_CLOUD_ACCESS_KEY_ID` 等 FC 注入的 STS 凭证。

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
├── badcase.py         # Badcase/Goodcase 追踪（自动检测 + 三级存储后端：OSS/NAS/本地）
├── badcases.json      # Case 存储（人类可读 JSON，含种子数据）
├── tools.py           # 工具函数（PDF/DOCX 解析纯标准库、技能图谱查询、市场数据查询）
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
         → 返回结构化结果（含步骤级 token 消耗明细）
```

## 安全设计

安全护栏在 `safety.py` 的 `SafetyGuard` 类中做硬校验，即使模型输出违反规则也会被代码层拦截：

- **输入预检**：LLM 调用前拦截恶意请求，0 token 消耗，避免 API TOS 风险和成本浪费
- **上下文感知拦截**：区分「包装经历」（合法的简历优化用语）和「编造经历」（造假请求），通过 ±80 字符窗口检测语境信号。合法信号优先于欺诈信号——宁可漏过不能误杀
- 不替用户做人生决策（拦截「你应该辞职」「建议你选A公司」，但放行条件句式「如果你选A，可能会...」）
- 不协助简历造假（拦截编造经历、虚构项目、虚增数字）
- 市场数据标注来源和时效（所有数据源标 `[示例]`，区分 demo 和真实数据）
- 检测焦虑/抑郁情绪，共情优先于分析，必要时建议专业帮助
- 简历优化后自动追加提醒：「所有量化数字和具体成果请以原始简历为准」

## Badcase 追踪系统

在 LLM 容易产生幻觉的关键节点做自动检测 + 人工标注，用于 Prompt 迭代和质量监控。

### 存储架构

```
FC 环境 OSS（持久化，跨实例共享）
       ↑ 冷启动无数据 → 内嵌种子数据自动导入
NAS 挂载路径（持久化，单实例）
       ↑ BADCASE_STORAGE_PATH 指定路径
本地文件（开发环境）
       ↑ 代码目录可写时使用
/tmp（FC 兜底，实例回收丢失）
```

### 自动检测点

| 检测点 | 位置 | 规则 |
|--------|------|------|
| 简历数字编造 | Step 4 (resume_optimize) | 提取 LLM 输出中的数字，检查简历原文是否包含 |
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
| 简历文本解析 | 纯 Python 标准库 | PDF 正则提取流（多编码自适应评分）、DOCX zipfile+XML，零依赖 |
| 安全检查 | 输入预检 + 代码正则 + LLM 三重 | 输入拦截省成本，代码拦截确定性红线，LLM 补语义漏网 |
| 分层 Prompt | Safety → Role → Task | 每层独立管理和调试，Safety 层不可被覆盖 |
| 双模型 | DeepSeek + 千问 | DeepSeek 高性价比分析，千问中文简历优化更强、qwen-long 文件上传 |
| Badcase 存储 | OSS V1 签名（纯标准库） | 零 SDK 依赖，hmac+hashlib+urllib 实现，自动复用 FC 运行时 STS 凭证 |
| 前端 | 零框架 HTML/CSS/JS | 减少构建步骤，部署简单，面试展示友好 |
| 问候快速通道 | 不调 LLM | 「你好」「嘿」等 18 种问候直接返回欢迎语，0 延迟 |
| 信息不足处理 | 标注不确定性 + 自然追问 | 不机械拒绝，体验优先；LLM 限定分析 + 明确标注缺口 |

## 部署

### 本地开发

```bash
cd agent
pip install openai python-dotenv
python server.py
# → http://localhost:5000
```

### 阿里云函数计算 FC

1. 运行 `python deploy.py` 打包 `fc_deploy.zip`
2. FC 控制台上传 zip，运行时选 Python 3.x，入口函数 `fc_handler.handler`
3. 配置环境变量（API Key + OSS 信息）
4. 授权 FC 函数角色访问 OSS（`AliyunOSSFullAccess` 或最小权限策略）

### OSS 持久化配置

```bash
# 环境变量
OSS_BUCKET=career-agent-data
OSS_ENDPOINT=oss-cn-hongkong.aliyuncs.com
# AccessKey 可选 — FC RAM 角色有 OSS 权限时自动复用运行时 STS 凭证
```

### Render

使用项目根目录的 `render.yaml` 一键部署。
