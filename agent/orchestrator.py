"""
Agent Orchestrator — 多步编排核心，接入真实DeepSeek API。

面试重点:
  1. 数据查询类步骤（技能图谱/市场数据）不走LLM → 结构化API
  2. 推理类步骤（意图识别/综合分析/安全检查）走LLM → DeepSeek
  3. 每个步骤独立记录成本（来自API返回的真实token数）
  4. 分层Prompt: Safety(硬约束) → Role(角色) → Task(任务)
"""
import time, json
from dataclasses import dataclass, field
from typing import Optional

from demo_data import (
    UserProfile, USER_XIAOMING, USER_LILI, USER_AQIANG,
    JOB_MARKET_DATA, SKILL_TRANSFER_MAP,
    JD_PRODUCT_MANAGER, JD_AI_PM
)
from safety import SafetyGuard, SafetyLevel
from cost import CostTracker, estimate_tokens
from tools import TOOL_REGISTRY
from llm import get_llm, get_qwen_llm, LLMResponse, LLMClient
from prompts import (
    SAFETY_SYSTEM_PROMPT, ROLE_PROMPT,
    get_profile_extraction_prompt, get_intent_recognition_prompt,
    get_skill_transfer_prompt, get_interview_prep_prompt,
    get_3month_plan_prompt, get_resume_optimize_prompt,
    get_emotional_support_prompt
)


@dataclass
class AgentStep:
    name: str
    uses_ai: bool
    input_tokens: int
    output_tokens: int
    duration_ms: float
    summary: str
    detail: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class AgentResult:
    user_profile: UserProfile
    steps: list[AgentStep]
    final_output: str
    safety_result: SafetyLevel
    cost_summary: dict
    extracted_profile: dict = field(default_factory=dict)  # 从对话中提取的用户画像


class CareerAgent:
    """
    AI职业规划与求职Agent（真实API版本）。

    使用:
        agent = CareerAgent()
        result = agent.run(USER_XIAOMING, flow="skill_transfer")
    """

    def __init__(self, verbose: bool = True):
        self.safety = SafetyGuard()
        self.cost = CostTracker()
        self.llm: LLMClient = get_llm()
        self.verbose = verbose

    def run(self, user: UserProfile = None, flow: str = "skill_transfer",
            message: str = "", messages: list = None,
            resume_text: str = "", requirements: str = "",
            jd_text: str = "", file_ids: list[str] = None) -> AgentResult:
        """
        执行Agent主流程。

        flow options:
          - "skill_transfer": 技能迁移分析
          - "interview_prep": 面试模拟准备
          - "resume_optimize": 简历优化
          - "full_planning": 完整职业规划

        messages: 对话历史 [{"role":"user"|"assistant","content":"..."}]，支持多轮上下文
        message: 单轮消息（兼容旧调用）
        resume_text: 简历原文（resume_optimize 流程使用）
        requirements: 优化要求（resume_optimize 流程使用）
        user: 预设UserProfile
        """
        self.cost.start_session(f"{user.name if user else 'chat'}_{flow}")
        steps = []
        t_start = time.time()
        extracted_profile = {}

        # 从 messages 数组中提取当前用户消息和历史
        if messages:
            history_text = "\n".join(
                f"{'用户' if m['role']=='user' else 'AI'}: {m['content']}"
                for m in messages
            )
            # 最后一条用户消息作为当前输入
            current_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), messages[-1]['content'])
            has_history = len([m for m in messages if m['role'] == 'user']) > 1
        else:
            history_text = message or ""
            current_msg = message or ""
            has_history = False

        # 简短招呼检测：纯打招呼/问好消息跳过完整流程，返回温暖简短回应
        greeting_patterns = ['你好', 'hi', 'hello', '嗨', '在吗', '在么', '您好', 'hey', '早上好', '下午好', '晚上好']
        if current_msg and not has_history and flow == "skill_transfer":
            msg_clean = current_msg.strip().lower()
            if any(msg_clean == g or msg_clean.startswith(g) for g in greeting_patterns):
                greeting_output = (
                    "你好！我是你的AI职业规划助手。\n\n"
                    "随便聊聊就行——告诉我你目前在做什么工作、会哪些技能、想往哪个方向发展，或者直接说「我很迷茫」，我都会帮你分析。\n\n"
                    "不用一次性说全，想到什么说什么就好。"
                )
                s = self.cost.current_session
                return AgentResult(
                    user_profile=UserProfile(name="用户", current_role="", years_of_experience=0,
                        industry="", skills=[], education="", salary_range="", target_role=None),
                    steps=[AgentStep(name="招呼识别", uses_ai=False, input_tokens=0, output_tokens=0,
                        duration_ms=0, summary="识别为简短招呼，返回欢迎语")],
                    final_output=greeting_output,
                    safety_result=SafetyLevel.PASS,
                    cost_summary={"total_steps": 1, "ai_steps": 0, "non_ai_steps": 1,
                        "input_tokens": 0, "output_tokens": 0, "cost_rmb": 0.0,
                        "api_configured": self.llm.is_configured, "model": self.llm.model,
                        "total_duration_ms": int((time.time() - t_start) * 1000)},
                    extracted_profile={}
                )

        if self.verbose:
            print(f"\n{'='*50}")
            print(f"  Agent启动 | 用户: {user.name if user else '对话提取'} | 模式: {flow}")
            print(f"  历史轮次: {'多轮' if has_history else '单轮'} | API: {'DeepSeek' if self.llm.is_configured else '模拟'}")
            print(f"{'='*50}\n")

        # ═══════════════════════════════════════
        # Step 0: 从对话历史提取用户画像
        # 简历优化模式跳过——简历原文已含所有信息，不需要从对话提取
        # ═══════════════════════════════════════
        if flow == "resume_optimize" and not user:
            user = UserProfile(name="用户", current_role="", years_of_experience=0,
                               industry="", skills=[], education="", salary_range="",
                               target_role="")
        elif current_msg and not user:
            t0 = time.time()
            # 多轮对话：把完整历史给 LLM 提取更精准的画像
            extract_input = history_text if has_history else current_msg
            profile_prompt = get_profile_extraction_prompt(extract_input)
            resp0 = self.llm.chat(profile_prompt, purpose="profile_extraction")
            extracted = self._parse_json_safe(resp0.content)
            extracted_profile = extracted

            user = UserProfile(
                name=extracted.get("name") or "用户",
                current_role=extracted.get("current_role") or "",
                years_of_experience=extracted.get("years_of_experience") or 0,
                industry=extracted.get("industry") or "",
                skills=extracted.get("skills") or [],
                education=extracted.get("education") or "",
                salary_range="",
                target_role=extracted.get("target_role") or None,
                priorities=extracted.get("priorities") or [],
                emotional_state=extracted.get("emotional_state") or "neutral"
            )

            step0 = AgentStep(
                name="提取用户画像", uses_ai=True,
                input_tokens=resp0.input_tokens, output_tokens=resp0.output_tokens,
                duration_ms=resp0.duration_ms,
                summary=f"从{'多轮' if has_history else '单轮'}对话中识别：{user.current_role}，{user.years_of_experience}年经验，目标{user.target_role or '待探索'}",
                detail={"输入": extract_input[:80]+"...", "提取字段": f"岗位={user.current_role}, 年限={user.years_of_experience}年, 技能={user.skills}, 目标={user.target_role or '未明确'}"}
            )
            steps.append(step0)
            self.cost.record_step(step0.name, resp0.input_tokens, resp0.output_tokens, True, resp0.duration_ms)

            if self.verbose:
                print(f"  [Step 0] 用户画像提取 → {user.current_role} → {user.target_role or '待探索'} "
                      f"({resp0.input_tokens}+{resp0.output_tokens} tokens, {resp0.duration_ms:.0f}ms)")

        # ═══════════════════════════════════════
        # Step 1: 意图识别（走LLM — 需要语义理解）
        # 简历优化跳过——flow 已明确，不需要识别意图
        # ═══════════════════════════════════════
        if flow == "resume_optimize":
            intent = {"primary": "resume_optimize", "sub_intents": [], "urgency": "medium"}
            primary = "resume_optimize"
            step1 = AgentStep(
                name="意图识别", uses_ai=False, input_tokens=0, output_tokens=0, duration_ms=0,
                summary="简历优化模式", detail={"意图": "resume_optimize"}
            )
            steps.append(step1)
            self.cost.record_step(step1.name, 0, 0, False, 0)
        else:
            t0 = time.time()
            user_context = f"对话历史：\n{history_text[:1000]}" if has_history else (message or "")
            intent_prompt = get_intent_recognition_prompt(user_context)
            resp = self.llm.chat(intent_prompt, purpose="intent_recognition")
            intent = self._parse_intent(resp.content)

            primary = intent.get("primary", intent.get("primary_intent", flow))
            if not user.target_role and primary not in ("interview_prep", "emotional_support"):
                primary = "career_planning"

            intent_label = {"career_planning":"职业规划分析", "skill_analysis":"技能迁移分析", "job_search":"求职市场查询", "emotional_support":"情绪疏导+方向探索", "interview_prep":"面试准备"}
            step1 = AgentStep(
                name="意图识别", uses_ai=True,
                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                duration_ms=resp.duration_ms,
                summary=f"判断用户需求：{intent_label.get(primary, primary)}",
                detail={"原始意图": primary, "子意图": str(intent.get('intents', intent.get('sub_intents', []))), "紧迫度": intent.get('urgency', '-')}
            )
            steps.append(step1)
            self.cost.record_step(step1.name, resp.input_tokens, resp.output_tokens, True, resp.duration_ms)

            if self.verbose:
                print(f"  [Step 1] 意图识别 → {primary} "
                      f"({resp.input_tokens}+{resp.output_tokens} tokens, {resp.duration_ms:.0f}ms)")

        # ═══════════════════════════════════════
        # 信息充分度检查：仅标记，不拦截。
        # 让 LLM 基于已有信息做限定分析 + 标注不确定性 + 自然追问。
        # — 面试展示重点：体验优先，不机械拒绝用户 —
        # ═══════════════════════════════════════
        profile_incomplete = current_msg and self._profile_insufficient(user) and flow != "resume_optimize"
        if profile_incomplete:
            user_insufficient_marker = f"\n\n[提示：用户画像不完整，缺少关键信息。请基于已有信息做限定分析，明确标注不确定项，并在分析末尾自然追问缺失信息。]"
        else:
            user_insufficient_marker = ""

        # ═══════════════════════════════════════
        # Step 2 & 3: 数据查询（不走LLM！并行执行）
        # 简历优化、情绪支持不需要技能/市场数据，跳过
        # ═══════════════════════════════════════
        is_emotional = (flow == "emotional_support" or
                        user.emotional_state in ("anxious", "confused"))
        if flow != "resume_optimize" and not is_emotional:
            t2 = time.time()
            target_for_search = user.target_role or "产品经理"
            skill_data = TOOL_REGISTRY["query_skill_graph"]["function"](
                user.skills, target_for_search
            )
            skill_names = ', '.join(user.skills)
            step2 = AgentStep(
                name="技能匹配查询", uses_ai=False,
                input_tokens=0, output_tokens=0,
                duration_ms=(time.time() - t2) * 1000,
                summary=f"查询「{skill_names}」→「{target_for_search}」的可迁移性",
                detail={"查询技能": skill_names, "目标岗位": target_for_search, "匹配结果": str(skill_data.get('matched', skill_data.get('data', {})))[:200], "数据来源": "技能图谱数据库（结构化API）"}
            )
            steps.append(step2)
            self.cost.record_step(step2.name, 0, 0, False, step2.duration_ms)

            t3 = time.time()
            market_data = TOOL_REGISTRY["query_job_market"]["function"](target_for_search)
            step3 = AgentStep(
                name="市场薪资查询", uses_ai=False,
                input_tokens=0, output_tokens=0,
                duration_ms=(time.time() - t3) * 1000,
                summary=f"查询「{target_for_search}」市场数据：{market_data['data'].get('avg_salary', 'N/A')}，需求{market_data['data'].get('demand_trend', 'N/A')}",
                detail={"岗位": target_for_search, "平均薪资": market_data['data'].get('avg_salary', '-'), "需求趋势": market_data['data'].get('demand_trend', '-'), "数据来源": market_data['data'].get('data_source', '-'), "更新时间": market_data['data'].get('data_updated', '-'), "来源类型": "市场数据API（非LLM生成）"}
            )
            steps.append(step3)
            self.cost.record_step(step3.name, 0, 0, False, step3.duration_ms)

            if self.verbose:
                print(f"  [Step 2] 技能图谱查询 → {len(user.skills)}项技能 (非AI, {step2.duration_ms:.0f}ms)")
                print(f"  [Step 3] 市场数据查询 → {market_data['data'].get('avg_salary', 'N/A')} (非AI, {step3.duration_ms:.0f}ms)")
        else:
            skill_data, market_data = {}, {}

        # ═══════════════════════════════════════
        # Step 4: AI综合分析（走LLM — 核心推理）
        # ═══════════════════════════════════════
        t4 = time.time()

        # 情绪支持模式：用户焦虑/迷茫/情绪化 → 先接住情绪，再做轻量探索
        if is_emotional:
            task_prompt = get_emotional_support_prompt(user, history_text)
            resp4 = self.llm.chat_with_layered_prompts(
                user_message=f"对话历史：\n{history_text}\n\n用户{user.name}情绪状态需要关注，请先共情再分析",
                safety_prompt=SAFETY_SYSTEM_PROMPT,
                role_prompt=ROLE_PROMPT,
                task_prompt=task_prompt,
                purpose="emotional_support"
            )
        elif flow == "interview_prep":
            task_prompt = get_interview_prep_prompt(
                user,
                JD_PRODUCT_MANAGER if user.target_role == "产品经理" else JD_AI_PM
            )
            resp4 = self.llm.chat_with_layered_prompts(
                user_message=f"为{user.name}生成面试题",
                safety_prompt=SAFETY_SYSTEM_PROMPT,
                role_prompt=ROLE_PROMPT,
                task_prompt=task_prompt,
                purpose="interview_prep"
            )
        elif flow == "resume_optimize":
            # 简历优化使用千问 API（千问在中文理解和内容生成上更优）
            actual_resume = resume_text or current_msg
            actual_reqs = requirements or ""
            task_prompt = get_resume_optimize_prompt(
                resume_text=actual_resume,
                target_role=user.target_role or "",
                user_skills=user.skills,
                requirements=actual_reqs,
                chat_context=history_text,
                jd_text=jd_text
            )
            # 使用分层 prompt，但替换 ROLE_PROMPT 的「信息不足只追问」铁律
            # 为「简历优化模式下直接输出」，避免矛盾。
            RESUME_ROLE_PROMPT = """你是资深简历优化专家，专注帮求职者优化简历表达。

【你的工作方式】
- 用户已提供简历原文和目标信息，直接开始优化，不需要追问。
- 用STAR法则重写经历，强动词开头，量化成果。
- 数据 > 观点，所有优化基于原文真实经历。
- 帮用户更好地展示自己 > 替用户编造经历。
"""
            resume_llm = get_qwen_llm()
            resp4 = resume_llm.chat_with_layered_prompts(
                user_message=f"请立即输出 {user.name}（{user.current_role}→{user.target_role or '目标岗位'}）的优化后简历，不要打招呼，不要问问题。",
                safety_prompt=SAFETY_SYSTEM_PROMPT,
                role_prompt=RESUME_ROLE_PROMPT,
                task_prompt=task_prompt,
                purpose="resume_optimize",
                file_ids=file_ids
            )
        else:
            task_prompt = get_skill_transfer_prompt(user, skill_data, market_data)
            resp4 = self.llm.chat_with_layered_prompts(
                user_message=f"对话历史：\n{history_text}\n\n请基于以上对话历史，为{user.name}（{user.current_role}，想转{user.target_role or '探索新方向'}）做分析{user_insufficient_marker}",
                safety_prompt=SAFETY_SYSTEM_PROMPT,
                role_prompt=ROLE_PROMPT,
                task_prompt=task_prompt,
                purpose="skill_transfer"
            )

        synthesis = resp4.content
        step4 = AgentStep(
            name="AI综合分析", uses_ai=True,
            input_tokens=resp4.input_tokens, output_tokens=resp4.output_tokens,
            duration_ms=resp4.duration_ms,
            summary=f"LLM生成个性化分析：{resp4.output_tokens}tokens（含技能迁移/缺口/路径/3月计划）",
            detail={"输入": f"用户画像 + 技能匹配数据 + 市场数据", "输出": f"{resp4.output_tokens}tokens 结构化报告（技能迁移表/缺口分析/推荐路径/行动计划）", "模型": self.llm.model, "Prompt层数": "3层（Safety → Role → Task）"}
        )
        steps.append(step4)
        self.cost.record_step(step4.name, resp4.input_tokens, resp4.output_tokens, True, resp4.duration_ms)

        if self.verbose:
            print(f"  [Step 4] AI综合分析 → {resp4.output_tokens}tokens "
                  f"({resp4.input_tokens}+{resp4.output_tokens}, {resp4.duration_ms:.0f}ms, "
                  f"¥{self._calc_cost(resp4.input_tokens, resp4.output_tokens):.4f})")

        # ═══════════════════════════════════════
        # Step 5: 安全检查（走LLM + 代码双重校验）
        # ═══════════════════════════════════════
        t5 = time.time()

        safety_result = self.safety.check(synthesis, {"user": user.name, "flow": flow})

        if safety_result.level != SafetyLevel.BLOCK:
            safety_check_prompt = f"""请检查以下AI生成的职业规划建议是否存在安全风险。
重点关注: 是否替用户做了决策、是否包含危险建议、是否引用了编造的数据。

【待检查内容】
{synthesis[:3000]}

【输出格式】
{{"safe": true/false, "risks": ["风险项1", "风险项2"], "suggestion": "修改建议"}}
"""
            resp5 = self.llm.chat(safety_check_prompt, purpose="safety_check")
            llm_safety = self._parse_json_safe(resp5.content)
            if not llm_safety.get("safe", True):
                for risk in llm_safety.get("risks", []):
                    if risk not in safety_result.warnings:
                        safety_result.warnings.append(f"[LLM安全审查] {risk}")

        # 简历优化模式：追加 AI 生成内容提醒
        if flow == "resume_optimize":
            safety_result.warnings.append("简历经AI优化，所有量化数字和具体成果请以原始简历为准，建议发送前逐条核对")
        else:
            resp5 = LLMResponse(content="blocked", model="local", input_tokens=0, output_tokens=0, duration_ms=0)

        step5 = AgentStep(
            name="内容安全检查", uses_ai=(safety_result.level != SafetyLevel.BLOCK),
            input_tokens=resp5.input_tokens if hasattr(resp5, 'input_tokens') else 0,
            output_tokens=resp5.output_tokens if hasattr(resp5, 'output_tokens') else 0,
            duration_ms=(time.time() - t5) * 1000,
            summary=f"代码正则 + LLM双重校验：{'✅ 通过' if safety_result.level.value == 'pass' else '⚠️ 警告' if safety_result.level.value == 'warn' else '🚫 拦截'}",
            detail={
                "检查方式": "代码正则硬拦截（决策类/造假类/数据引用类）+ LLM语义审查",
                "违规项": safety_result.violations if safety_result.violations else "无",
                "警告": safety_result.warnings if safety_result.warnings else "无",
                "结果": safety_result.level.value,
            }
        )
        steps.append(step5)
        if safety_result.level != SafetyLevel.BLOCK:
            self.cost.record_step(step5.name, step5.input_tokens, step5.output_tokens, True, step5.duration_ms)

        if self.verbose:
            status = "PASS" if safety_result.level == SafetyLevel.PASS else \
                     "WARN" if safety_result.level == SafetyLevel.WARN else "BLOCK"
            print(f"  [Step 5] 安全检查 → {status} (违规{len(safety_result.violations)}项, 警告{len(safety_result.warnings)}项)")

        # ═══════════════════════════════════════
        # Step 6: 输出包装
        # ═══════════════════════════════════════
        final_output = self.safety.wrap_output(synthesis, safety_result)

        s = self.cost.current_session
        cost_summary = {
            "total_steps": len(s.steps),
            "ai_steps": s.ai_step_count,
            "non_ai_steps": s.non_ai_step_count,
            "input_tokens": s.total_input_tokens,
            "output_tokens": s.total_output_tokens,
            "cost_rmb": s.total_cost_rmb,
            "api_configured": self.llm.is_configured,
            "model": self.llm.model,
            "total_duration_ms": int((time.time() - t_start) * 1000)
        }

        if self.verbose:
            print(f"\n  Total: {cost_summary['total_steps']}步, "
                  f"AI步{cost_summary['ai_steps']}/非AI步{cost_summary['non_ai_steps']}, "
                  f"¥{cost_summary['cost_rmb']:.4f}, "
                  f"{cost_summary['total_duration_ms']}ms\n")

        return AgentResult(
            user_profile=user,
            steps=steps,
            final_output=final_output,
            safety_result=safety_result.level,
            cost_summary=cost_summary,
            extracted_profile=extracted_profile
        )

    def _profile_insufficient(self, user: UserProfile) -> bool:
        """检查用户画像是否过于模糊，无法进行有意义的分析。
        通过标准：有岗位 + 有年限 + (有技能 或 有目标方向)。
        任一项不满足就追问，不做硬分析。"""
        has_role = bool(user.current_role and user.current_role.strip())
        has_skills = bool(user.skills and any(s.strip() for s in user.skills))
        has_target = bool(user.target_role and str(user.target_role).strip())
        has_years = True  # years=0 is valid (fresh grad); info comes from role + skills
        # 方向来自具体的目标岗位（不含"未知"等占位符），而非模糊的优先级
        has_direction = has_target or (
            user.priorities and any(
                p.strip() in ("成长空间", "薪资", "稳定性", "WLB", "技术深度", "管理路线")
                for p in user.priorities
            )
        )
        if not has_role:
            return True
        if not has_years:
            return True
        if not has_skills and not has_direction:
            return True
        return False

    def _parse_intent(self, content: str) -> dict:
        """解析意图识别的JSON输出"""
        return self._parse_json_safe(content)

    def _parse_json_safe(self, text: str) -> dict:
        """安全解析JSON"""
        try:
            # 提取第一个JSON对象
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        """DeepSeek 2026 定价: input ¥1/1M, output ¥2/1M"""
        return (input_tokens / 1_000_000) * 1.0 + (output_tokens / 1_000_000) * 2.0
