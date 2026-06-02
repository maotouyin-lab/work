"""
LLM Client — DeepSeek API integration (OpenAI-compatible).

面试重点: 这个模块的设计体现了几个关键决策:
1. 模型可切换（不绑定单一厂商）
2. 成本追踪内置到每次调用
3. 分层Prompt在客户端层面组装
"""
import os, sys, time, json
from dataclasses import dataclass, field

# 优先使用 vendored 依赖（FC 函数计算环境无需 pip install）
_deps_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deps')
if os.path.isdir(_deps_dir):
    sys.path.insert(0, _deps_dir)

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))


@dataclass
class LLMResponse:
    """统一的LLM响应格式"""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: float
    finish_reason: str = "stop"


@dataclass
class LLMCall:
    """单次调用的完整记录"""
    purpose: str           # 调用目的（意图识别/综合分析/安全检查等）
    system_prompt: str
    user_prompt: str
    response: LLMResponse = None
    error: str = None
    timestamp: float = field(default_factory=time.time)


class LLMClient:
    """
    多模型客户端，支持 DeepSeek / Qwen(千问) 等 OpenAI 兼容 API。

    使用方式:
        client = LLMClient()                           # 默认 DeepSeek
        client = LLMClient(provider='qwen')            # 千问
        client = LLMClient(api_key='...', base_url='...', model='...')  # 自定义
    """

    PROVIDER_CONFIGS = {
        'deepseek': {
            'api_key_env': 'DEEPSEEK_API_KEY',
            'base_url_env': 'DEEPSEEK_BASE_URL',
            'model_env': 'DEEPSEEK_MODEL',
            'default_base_url': 'https://api.deepseek.com',
            'default_model': 'deepseek-chat',
        },
        'qwen': {
            'api_key_env': 'QWEN_API_KEY',
            'base_url_env': 'QWEN_BASE_URL',
            'model_env': 'QWEN_MODEL',
            'default_base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'default_model': 'qwen-long',
        },
    }

    def __init__(self, provider: str = 'deepseek',
                 api_key: str = None, base_url: str = None, model: str = None):
        cfg = self.PROVIDER_CONFIGS.get(provider, self.PROVIDER_CONFIGS['deepseek'])
        self.provider = provider
        self.api_key = (api_key or os.getenv(cfg['api_key_env'], ''))
        self.base_url = (base_url or os.getenv(cfg['base_url_env'], cfg['default_base_url']))
        self.model = (model or os.getenv(cfg['model_env'], cfg['default_model']))
        self.is_configured = bool(self.api_key and len(self.api_key) > 10)

        if self.is_configured:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.client = None

        self.call_history: list[LLMCall] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def chat(self, user_message: str, system: str = "",
             temperature: float = 0.3, max_tokens: int = 4096,
             purpose: str = "general", file_ids: list[str] = None) -> LLMResponse:
        """
        发送对话请求。

        Args:
            user_message: 用户消息
            system: 系统提示词
            temperature: 温度（职业规划场景用低温度保证稳定性）
            max_tokens: 最大输出token
            purpose: 调用目的（用于日志和成本分析）

        Returns:
            LLMResponse with content + token usage
        """
        call = LLMCall(purpose=purpose, system_prompt=system, user_prompt=user_message)
        t0 = time.time()

        # 未配置API Key时返回提示
        if not self.is_configured:
            resp = LLMResponse(
                content=self._fallback_response(purpose, user_message),
                model="fallback-mock",
                input_tokens=len(user_message) // 2,
                output_tokens=200,
                duration_ms=0
            )
            call.response = resp
            self.call_history.append(call)
            return resp

        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            # Inject file references as separate system messages (qwen-long format)
            if file_ids:
                for fid in file_ids:
                    messages.append({"role": "system", "content": f"fileid://{fid}"})
            messages.append({"role": "user", "content": user_message})

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body={"chat_template_kwargs": {"thinking": False}}
            )

            usage = completion.usage
            choice = completion.choices[0]
            duration = (time.time() - t0) * 1000

            resp = LLMResponse(
                content=choice.message.content,
                model=self.model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                duration_ms=duration,
                finish_reason=choice.finish_reason or "stop"
            )

            self.total_input_tokens += usage.prompt_tokens
            self.total_output_tokens += usage.completion_tokens

        except Exception as e:
            resp = LLMResponse(
                content=f"[API调用失败: {str(e)}]",
                model=self.model,
                input_tokens=0,
                output_tokens=0,
                duration_ms=(time.time() - t0) * 1000,
                finish_reason="error"
            )
            call.error = str(e)

        call.response = resp
        self.call_history.append(call)
        return resp

    def chat_with_layered_prompts(self, user_message: str,
                                   safety_prompt: str,
                                   role_prompt: str,
                                   task_prompt: str,
                                   purpose: str = "agent_task",
                                   file_ids: list[str] = None) -> LLMResponse:
        """
        使用分层Prompt系统调用。

        Prompt组装顺序: Safety(最高优先) → Role → Task → User Message
        """
        full_system = f"""{safety_prompt}

---

{role_prompt}

---

{task_prompt}"""
        return self.chat(user_message, system=full_system, purpose=purpose,
                         file_ids=file_ids)

    def upload_file(self, file_bytes: bytes, filename: str) -> dict:
        """上传文件到模型服务（DashScope qwen-long），返回 file_id。

        调用方式:
            result = client.upload_file(pdf_bytes, 'resume.pdf')
            file_id = result['file_id']
        """
        import io

        if not self.is_configured:
            return {"error": "API未配置，无法上传文件", "file_id": None}

        try:
            file_obj = io.BytesIO(file_bytes)
            file_obj.name = filename

            response = self.client.files.create(
                file=file_obj,
                purpose="file-extract"
            )
            return {
                "file_id": response.id,
                "filename": filename,
                "bytes": getattr(response, 'bytes', len(file_bytes)),
                "status": getattr(response, 'status', 'unknown'),
                "error": None
            }
        except Exception as e:
            return {"error": str(e), "file_id": None}

    def _fallback_response(self, purpose: str, user_message: str) -> str:
        """未配置API Key时的降级响应（模拟输出，保证系统可运行）"""
        if purpose == "intent_recognition":
            return '{"primary": "skill_analysis", "intents": ["career_planning"], "urgency": "medium"}'

        if purpose == "skill_transfer":
            return f"""[模拟模式] 基于DeepSeek API的技能迁移分析会在这里显示。

请将DeepSeek API Key填入 .env 文件后重启服务，即可获得真实AI分析。

你当前输入: "{user_message[:50]}..."

真实API调用后会返回:
- 个性化技能迁移分析
- 基于真实数据的市场趋势解读
- 可执行的3个月行动计划
- 带引用来源的分析报告"""

        if purpose == "interview_prep":
            return f"""[模拟模式] 基于你背景的个性化面试题会在这里生成。

请配置DeepSeek API Key后重试。"""

        return f"[模拟模式] 请配置API Key: 编辑 .env 文件，填入 DEEPSEEK_API_KEY"

    def get_cost_summary(self) -> dict:
        """获取累计成本摘要"""
        # DeepSeek pricing (2026): input ~¥1/1M tokens, output ~¥2/1M tokens
        input_cost = self.total_input_tokens / 1_000_000 * 1.0
        output_cost = self.total_output_tokens / 1_000_000 * 2.0
        return {
            "total_calls": len(self.call_history),
            "successful_calls": sum(1 for c in self.call_history if c.response and c.response.finish_reason != "error"),
            "failed_calls": sum(1 for c in self.call_history if c.error),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_rmb": round(input_cost + output_cost, 4),
            "model": self.model,
            "is_configured": self.is_configured
        }


# ── 全局单例 ──
_llm_client: LLMClient = None
_qwen_client: LLMClient = None


def get_llm() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(provider='deepseek')
    return _llm_client


def get_qwen_llm() -> LLMClient:
    global _qwen_client
    if _qwen_client is None:
        _qwen_client = LLMClient(provider='qwen')
    return _qwen_client
