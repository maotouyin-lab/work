"""
Token cost tracking for AI Career Agent.

⚠️ 面试核心亮点: Agent产品必须主动追踪每一步的Token消耗。
简单问答只看总成本，Agent需要看步骤级成本分布——才能优化瓶颈环节。
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CostTier(Enum):
    """Pricing tiers matching Claude Sonnet 4 (2026)"""
    INPUT_TOKEN = 3.0      # $3 per 1M input tokens
    OUTPUT_TOKEN = 15.0    # $15 per 1M output tokens
    EMBEDDING = 0.1        # $0.1 per 1M tokens


@dataclass
class StepCost:
    """单个步骤的Token消耗记录"""
    step_name: str
    input_tokens: int
    output_tokens: int
    # 标注该步骤用的是AI还是传统API
    uses_ai: bool  # True = LLM调用(贵), False = 结构化API(便宜)
    duration_ms: float = 0.0


@dataclass
class SessionCost:
    """一次完整Agent会话的成本汇总"""
    session_id: str
    steps: list[StepCost] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.steps)

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.steps)

    @property
    def total_cost_usd(self) -> float:
        """Calculate total cost in USD"""
        input_cost = (self.total_input_tokens / 1_000_000) * CostTier.INPUT_TOKEN.value
        output_cost = (self.total_output_tokens / 1_000_000) * CostTier.OUTPUT_TOKEN.value
        return round(input_cost + output_cost, 6)

    @property
    def total_cost_rmb(self) -> float:
        """Convert to RMB (≈7.2 rate)"""
        return round(self.total_cost_usd * 7.2, 4)

    @property
    def ai_step_count(self) -> int:
        return sum(1 for s in self.steps if s.uses_ai)

    @property
    def non_ai_step_count(self) -> int:
        return sum(1 for s in self.steps if not s.uses_ai)


class CostTracker:
    """
    面试话术: "Agent每个步骤我都记录了是否走AI。
    数据查询类步骤（技能图谱、薪资数据）不走AI，token消耗为零——这就是在架构层面控制成本。"
    """

    def __init__(self):
        self.current_session: SessionCost = None
        self.all_sessions: list[SessionCost] = []

    def start_session(self, session_id: str):
        self.current_session = SessionCost(session_id=session_id)

    def record_step(self, step_name: str, input_tokens: int, output_tokens: int,
                    uses_ai: bool, duration_ms: float = 0.0):
        """记录一个步骤的成本"""
        if self.current_session is None:
            self.start_session(f"auto_{datetime.now().strftime('%H%M%S')}")

        step = StepCost(
            step_name=step_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            uses_ai=uses_ai,
            duration_ms=duration_ms
        )
        self.current_session.steps.append(step)

    def get_session_summary(self) -> str:
        """生成可展示的成本摘要——面试时可以直接展示这个输出"""
        if self.current_session is None:
            return "No active session"

        s = self.current_session
        lines = [
            "=" * 50,
            f"  Session: {s.session_id}  |  Steps: {len(s.steps)}",
            f"  AI调用步骤: {s.ai_step_count}  |  非AI步骤: {s.non_ai_step_count}",
            "-" * 50,
        ]

        for step in s.steps:
            tag = "🤖 AI" if step.uses_ai else "📡 API"
            cost = ((step.input_tokens / 1e6) * CostTier.INPUT_TOKEN.value +
                    (step.output_tokens / 1e6) * CostTier.OUTPUT_TOKEN.value)
            lines.append(
                f"  {tag} | {step.step_name:30s} | "
                f"in:{step.input_tokens:>6d} out:{step.output_tokens:>5d} | "
                f"${cost:.6f} | {step.duration_ms:.0f}ms"
            )

        lines.extend([
            "-" * 50,
            f"  Total Input:  {s.total_input_tokens:>8d} tokens",
            f"  Total Output: {s.total_output_tokens:>8d} tokens",
            f"  Cost:         ${s.total_cost_usd:.6f} USD  (¥{s.total_cost_rmb:.4f} RMB)",
            "=" * 50,
        ])
        return '\n'.join(lines)


def estimate_tokens(text: str) -> int:
    """简易Token估算（实际应用中用tiktoken等库精确计算）"""
    # 粗略估算: 中文 ≈ 1.5 chars/token, 英文 ≈ 4 chars/token
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)
