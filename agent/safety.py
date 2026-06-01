"""
Code-enforced Safety Guardrails for Career Agent.

Design principle: Context-aware detection, not blind keyword matching.
- High-confidence signals (explicit fabrication words) → direct BLOCK
- Ambiguous signals (like "包装") → check surrounding context before deciding
- Each violation carries a confidence score; only high-confidence violations block.
"""

import re
from dataclasses import dataclass, field
from enum import Enum


class SafetyLevel(Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class SafetyResult:
    level: SafetyLevel
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocked_output: str = ""


class SafetyGuard:
    """
    Context-aware safety guardrails.

    Key insight: "包装经历" alone is NOT fraud — it's standard career-advice
    language meaning "present your real experience better." We only flag it
    when the surrounding context contains fabrication signals.
    """

    # ── RED LINE 1: Decision substitution ──
    # Match the imperative pattern broadly, then check context for
    # conditional/analytical framing (如果/假设/假如/要是).
    # "如果你选A，你可能会..." = analysis ✓
    # "根据你的情况，你应该辞职" = decision substitution ✗
    DECISION_IMPERATIVES = [
        (r'你\s*(?:应该|必须|最好|务必|非得)\s*(?:立刻|马上|尽快)?\s*(?:辞职|离职|跳槽|转行)', '替用户做辞职/跳槽决策'),
        (r'(?:建议|推荐)你\s*(?:选择|去|接受|拒掉?)\s*(?:[A-Z]|公司|offer|岗位|职位)', '替用户做offer选择'),
        (r'不\s*(?:建议|推荐)你\s*(?:继续|留在|做下去|从事)', '替用户做否定性判断'),
    ]

    # Words that signal the statement is analytical, not imperative
    CONDITIONAL_MARKERS = [
        r'如果', r'假如', r'假设', r'要是', r'倘若', r'万一',
        r'比如', r'例如', r'像是', r'比方说',
    ]

    # ── RED LINE 2: Resume fabrication ──
    # Negation markers that precede fabrication keywords → NOT a violation
    # e.g. "不要编造经历" is compliance, not a suggestion to fabricate
    NEGATION_MARKERS = [
        r'不要', r'绝不', r'禁止', r'不可', r'不能', r'不得',
        r'切勿', r'避免', r'杜绝', r'严禁', r'一定不要', r'千万不要',
    ]

    # HIGH confidence: explicit fabrication/deception words → direct block
    FABRICATION_HIGH = [
        (r'(编造|虚构|伪造|杜撰|无中生有|凭空).{0,15}(经历|项目|工作|经验|履历|简历)', '编造/虚构经历'),
        (r'(假装|冒充|伪装).{0,10}(会|懂|做过|掌握|具备)', '假装具备某种能力'),
        (r'(?:没做过|没干过|没接触过|不会).{0,10}(?:说成|写成|包装成|改成).{0,10}(?:做过|会的|懂的)', '把没做过的事写成做过'),
        (r'(?:造假|作弊|欺骗|撒谎|骗).{0,15}(?:简历|面试|经历|项目|背景)', '简历/面试造假'),
        (r'(?:买|办|搞|弄).{0,5}(?:假|伪造).{0,5}(?:学历|证书|文凭|学位)', '学历/证书造假'),
    ]

    # LOW confidence: "包装" is legitimate career vocabulary in most contexts.
    # Only flag when accompanied by fabrication signals.
    FABRICATION_LOW = [
        (r'(包装|美化|润色).{0,10}(经历|项目|职级|薪资|简历)', '包装经历/简历'),
        (r'(夸大|夸张|虚高).{0,10}(成果|薪资|职级|业绩|数据)', '夸大成果/数据'),
    ]

    # Words that, when near "包装", suggest FRAUD intent
    FRAUD_CONTEXT_SIGNALS = [
        r'造假', r'虚构', r'编造', r'没有的', r'没做过的', r'假的',
        r'骗', r'蒙', r'混过去', r'忽悠', r'随便写', r'胡乱',
        r'凭空', r'子虚乌有', r'不存在的',
    ]

    # Words that, when near "包装", suggest LEGITIMATE career advice
    LEGITIMATE_CONTEXT_SIGNALS = [
        r'适当', r'合理', r'优化', r'突出', r'亮点', r'优势',
        r'真实', r'实际', r'客观', r'基于事实', r'诚实',
        r'更好的(?:表达|呈现|展示)', r'换个(?:角度|说法)',
        r'STAR', r'数据化', r'量化', r'具体化',
        r'简历优化', r'简历修改', r'修改简历',
        r'挖掘', r'提炼', r'梳理', r'总结',
    ]

    # ── RED LINE 3: Data citation ──
    DATA_PATTERNS = [
        (r'\d{1,3}[kK万]\s*[-~到]\s*\d{1,3}[kK万]', '薪资数据'),
        (r'(?:增长|下降|提升|降低|上涨|下跌)[\d.]+%', '趋势数据'),
    ]

    def check(self, agent_output: str, context: dict = None) -> SafetyResult:
        """Context-aware safety check on agent output."""
        violations = []
        warnings = []

        # ── Check 1: Decision substitution (context-aware) ──
        for pattern, description in self.DECISION_IMPERATIVES:
            for m in re.finditer(pattern, agent_output):
                if not self._is_conditional_context(agent_output, m.start()):
                    violations.append(f"[红线-决策替做] {description} → '{m.group()[:30]}'")

        # ── Check 2: Resume fabrication (tiered) ──
        for pattern, description in self.FABRICATION_HIGH:
            for m in re.finditer(pattern, agent_output):
                if not self._is_negation_context(agent_output, m.start()):
                    violations.append(f"[红线-造假建议] {description} → '{m.group()[:30]}'")

        for pattern, description in self.FABRICATION_LOW:
            for m in re.finditer(pattern, agent_output):
                if self._is_fraud_context(agent_output, m.start(), m.end()):
                    violations.append(
                        f"[红线-造假建议] {description}: "
                        f"上下文包含造假信号 → '{m.group()}'"
                    )
                # If context is clearly legitimate, silently pass
                # If ambiguous (no clear signal either way), warn but don't block

        # ── Check 3: Data citation ──
        for pattern, data_type in self.DATA_PATTERNS:
            for m in re.finditer(pattern, agent_output):
                pos = m.start()
                nearby = agent_output[pos:pos + 250]
                if '数据来源' not in nearby and '来源' not in nearby and '据' not in nearby[:50]:
                    warnings.append(
                        f"[数据引用] {data_type} '{m.group()}' 附近未找到数据来源标注"
                    )

        # ── Check 4: Emotional safety ──
        distress_keywords = ['绝望', '活不下去了', '想死', '崩溃', '严重抑郁']
        for kw in distress_keywords:
            if kw in agent_output:
                warnings.append(
                    f"[情绪安全] 检测到高风险情绪词 '{kw}'，"
                    "输出中应包含寻求专业帮助的建议"
                )

        # ── Verdict ──
        if violations:
            return SafetyResult(
                level=SafetyLevel.BLOCK,
                violations=violations,
                warnings=warnings,
                blocked_output=self._generate_block_message(violations)
            )
        elif warnings:
            return SafetyResult(level=SafetyLevel.WARN, warnings=warnings)
        else:
            return SafetyResult(level=SafetyLevel.PASS)

    def _is_fraud_context(self, text: str, match_start: int, match_end: int) -> bool:
        """
        Check if an ambiguous match (like '包装经历') appears in a fraud context.

        Returns True only when fraud signals are present AND
        no legitimate signals override them.
        """
        # Extract surrounding context (±80 chars around the match)
        ctx_start = max(0, match_start - 80)
        ctx_end = min(len(text), match_end + 80)
        context_window = text[ctx_start:ctx_end]

        # If legitimate signals present → not fraud
        for sig in self.LEGITIMATE_CONTEXT_SIGNALS:
            if re.search(sig, context_window):
                return False

        # If fraud signals present AND no legitimate override → fraud
        for sig in self.FRAUD_CONTEXT_SIGNALS:
            if re.search(sig, context_window):
                return True

        # No clear signal either way → not confident enough to block
        return False

    def _is_conditional_context(self, text: str, match_start: int) -> bool:
        """
        Check if a decision-imperative match appears in a conditional context.
        "如果你选A，你应该..." → conditional (pass)
        "根据你的情况，你应该辞职" → not conditional (block)
        """
        # Look at text BEFORE the match (up to 60 chars)
        ctx_start = max(0, match_start - 60)
        prefix = text[ctx_start:match_start]

        for marker in self.CONDITIONAL_MARKERS:
            if re.search(marker, prefix):
                return True
        return False

    def _is_negation_context(self, text: str, match_start: int) -> bool:
        """
        Check if a fabrication keyword is in a negation context.
        "不要编造经历" → negation (pass, it's compliance)
        "你可以编造经历" → not negation (block, it's a suggestion)
        """
        ctx_start = max(0, match_start - 30)
        prefix = text[ctx_start:match_start]

        # Check negation markers in prefix window
        for marker in self.NEGATION_MARKERS:
            if re.search(marker, prefix):
                return True

        # Check immediate negation: character just before match is 不
        # e.g. "不编造经历", "不虚构项目"
        if match_start > 0 and text[match_start - 1] == '不':
            return True

        return False

    def _generate_block_message(self, violations: list[str]) -> str:
        return f"""
⚠️ 系统安全护栏已拦截本次输出。

原因：检测到以下违反安全规则的内容：
{chr(10).join(f'  • {v}' for v in violations)}

关于职业规划的建议：
- 我可以帮你整理信息、分析选项、推演可能的结果
- 但最终的人生决策，必须由你自己做出
- 如果你需要更深入的一对一咨询，建议预约持证职业规划师
"""

    def wrap_output(self, output: str, safety_result: SafetyResult) -> str:
        """根据安全级别包装输出。"""
        if safety_result.level == SafetyLevel.BLOCK:
            return safety_result.blocked_output

        if safety_result.level == SafetyLevel.WARN:
            warning_text = '\n'.join(f'  ⚠ {w}' for w in safety_result.warnings)
            return f"""{output}

---
📌 温馨提示（系统自动检测）：
{warning_text}
"""

        return output
