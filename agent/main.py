"""
AI职业规划与求职Agent — 入口演示

面试时直接跑: python main.py
会输出完整的多步骤Agent执行过程 + 成本分析 + Eval评估
"""
import sys
import io
# Fix Windows GBK encoding for emoji output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from demo_data import USER_XIAOMING, USER_AQIANG
from orchestrator import CareerAgent
from evaluator import CareerAgentEvaluator, EVAL_CASES


def demo_skill_transfer():
    """演示1: 技能迁移分析（核心功能）"""
    print("\n" + "█" * 60)
    print("█  演示1: 技能迁移分析 — Agent多步编排")
    print("█  用户: 小明 | 运营专员 → 产品经理")
    print("█" * 60)

    agent = CareerAgent(verbose=True)
    result = agent.run(USER_XIAOMING, flow="skill_transfer")

    print("\n" + "─" * 60)
    print("  📋 最终输出:")
    print("─" * 60)
    print(result.final_output)

    print("\n" + result.session_summary)

    return result


def demo_safety_guard():
    """演示2: 安全护栏——代码拦截违规输出"""
    print("\n" + "█" * 60)
    print("█  演示2: 安全护栏拦截测试")
    print("█" * 60)

    from safety import SafetyGuard

    guard = SafetyGuard()

    # 测试1: 违规输出
    dangerous_output = "根据你的情况分析，你应该立刻辞职，然后去A公司做产品经理。"
    result1 = guard.check(dangerous_output)
    print(f"\n  测试1: '{dangerous_output}'")
    print(f"  → 拦截: {result1.level.value}")
    if result1.violations:
        for v in result1.violations:
            print(f"    ⛔ {v}")

    # 测试2: 安全输出
    safe_output = """
根据市场数据分析，产品经理岗位当前需求增长23%（数据来源：Boss直聘2026Q1报告）。
以下是你的技能迁移分析...如果选择转产品，可能面临的挑战是...
建议你在未来1-2个月内先尝试内部转岗积累经验。最终决策请结合个人情况。
    """
    result2 = guard.check(safe_output)
    print(f"\n  测试2: [安全输出]")
    print(f"  → 结果: {result2.level.value}")

    return guard


def demo_eval_framework():
    """演示3: 五维质量评估"""
    print("\n" + "█" * 60)
    print("█  演示3: Eval Set 五维质量评估")
    print("█" * 60)

    evaluator = CareerAgentEvaluator()

    # 模拟Agent输出（Case 001）
    sample_output = """
## 技能迁移分析
用户小明，当前运营专员，目标产品经理。

| 你的技能 | 可迁移性 | 对产品经理的价值 |
| 数据分析(SQL) | 高(0.85) | 核心迁移技能 |
| 用户运营 | 高(0.80) | 核心迁移技能 |

来源: Skill Graph DB v2.3

### 3个月行动计划
- 第1个月: 完成产品入门课程，产出原型作品
- 第2个月: 在工作中实践需求文档撰写
- 第3个月: 投递15-20家目标公司
"""

    for case in EVAL_CASES[:2]:  # 跑前2个用例
        result = evaluator.evaluate(case, sample_output if case.case_id == "eval_001_normal_transfer" else "我很理解你现在的迷茫，让我帮你分析一下你的优势和可能的方向...（部分输出）")
        print(f"\n  Case {case.case_id}: 总分 {result.total_score:.2f} | {'✅ PASS' if result.passed else '❌ FAIL'}")

    print(evaluator.print_report())
    return evaluator


def demo_cost_breakdown():
    """演示4: 成本分步追踪"""
    print("\n" + "█" * 60)
    print("█  演示4: 步骤级成本追踪")
    print("█" * 60)

    from cost import CostTracker

    tracker = CostTracker()
    tracker.start_session("demo_cost_analysis")

    # 模拟一次完整的Agent调用
    steps = [
        ("01_意图识别", 200, 100, True, 300),
        ("02_技能图谱查询", 0, 0, False, 45),     # ⭐ 不走AI
        ("03_市场数据查询", 0, 0, False, 120),    # ⭐ 不走AI
        ("04_综合分析生成", 3500, 2000, True, 2500),
        ("05_安全检查", 2000, 100, True, 150),
        ("06_输出格式化", 500, 300, True, 200),
    ]

    for name, inp, out, ai, dur in steps:
        tracker.record_step(name, inp, out, ai, dur)

    summary = tracker.get_session_summary()

    # 额外分析
    ai_cost = sum(
        (s.input_tokens / 1e6) * 3.0 + (s.output_tokens / 1e6) * 15.0
        for s in tracker.current_session.steps if s.uses_ai
    )
    non_ai_steps = len([s for s in tracker.current_session.steps if not s.uses_ai])

    print(summary)
    print(f"\n  📊 成本分析:")
    print(f"     AI步骤成本:   ${ai_cost:.6f}")
    print(f"     非AI步骤成本: $0.000000 (纯结构化API调用)")
    print(f"     非AI步骤数:   {non_ai_steps}/6 — 节省了{non_ai_steps}次LLM调用")
    print(f"     ⭐ 面试重点: 33%的步骤不走AI，成本降低且数据更准确")

    return tracker


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║       AI职业规划与求职Agent — 面试演示系统              ║
║                                                          ║
║  核心展示:                                                ║
║  1. Agent多步编排（非单次AI对话）                        ║
║  2. AI/非AI步骤的清晰边界（哪些用API，哪些用LLM）       ║
║  3. 代码级安全护栏（非prompt建议）                       ║
║  4. 五维质量评估体系（非对错二分法）                    ║
║  5. 步骤级成本追踪                                      ║
╚══════════════════════════════════════════════════════════╝
    """)

    # 依次运行4个演示
    demo_skill_transfer()
    demo_safety_guard()
    demo_cost_breakdown()
    demo_eval_framework()

    print("\n" + "=" * 60)
    print("  所有演示完成。以上输出展示了Agent的5个核心设计决策。")
    print("  面试时可选择性地运行单个演示来深入说明。")
    print("=" * 60)
