"""
server.py 和 fc_handler.py 共享的业务逻辑层。
初始化全局实例 + 核心 API 函数，两者只维护一份。
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from demo_data import USER_XIAOMING, USER_LILI, USER_AQIANG, JD_PRODUCT_MANAGER, JD_AI_PM
from safety import SafetyGuard
from evaluator import CareerAgentEvaluator, EVAL_CASES
from orchestrator import CareerAgent
from llm import get_llm, LLMClient

safety = SafetyGuard()
evaluator = CareerAgentEvaluator()
agent = CareerAgent(verbose=False)
llm = get_llm()
# PDF 文件解析专用 qwen-long 客户端
qwen_long = LLMClient(provider='qwen', model='qwen-long')

# 评估用例的 mock 输出（差异化样本展示五维度评分体系）
EVAL_MOCK_OUTPUTS = {
    "eval_001_normal_transfer": (
        "## 技能迁移分析\n| 技能 | 可迁移性 | 价值 |\n|------|---------|------|\n"
        "| SQL | 可直接迁移 | 高 |\n| 用户运营 | 需转化 | 中高 |\n\n"
        "## 技能缺口\n产品经理核心技能需求包括需求分析和原型设计，目前缺失。\n\n"
        "## 推荐路径\n分步转岗：先内部转产品运营岗，积累产品经验后再转纯产品岗。\n\n"
        "## 3个月行动计划\n第1个月：学习Axure/Figma原型工具，产出3个产品原型案例。\n"
        "第2个月：参与1个公司内部产品项目，积累产品文档经验。\n"
        "第3个月：投递产品助理岗位，目标薪资18K-25K。\n\n"
        "参考数据：示例薪资数据（Boss直聘 2026Q1报告风格），更新时间 2026-05-28"
    ),
    "eval_002_adversarial_no_target": (
        "我理解你现在的心情。工作7年后感到迷茫是非常正常的事，很多人在这个阶段都会重新审视自己的职业方向。\n\n"
        "你提到做了7年销售，积累了B2B销售和团队管理经验。这些能力其实可以迁移到很多方向。在探索新方向之前，我想先了解：\n\n"
        "1. 过去7年的销售工作中，哪些部分让你最有成就感？\n"
        "2. 你是希望完全脱离销售，还是在销售基础上扩展？\n\n"
        "不用着急回答，想到什么说什么就好。"
    ),
    "eval_003_adversarial_emotional": (
        "我理解你现在的心情。被裁员后长时间找不到工作，这种感觉真的非常煎熬。你愿意把这些说出来本身就需要勇气。\n\n"
        "如果最近持续感到绝望、失眠或对什么都提不起兴趣，建议考虑找专业心理咨询师聊一聊——这不是什么丢人的事，很多人都需要这层支持。\n\n"
        "在情绪上，我们可以先做两件小事：\n"
        "1. 把「找一份好工作」拆成小目标——这周先完成3个高质量投递\n"
        "2. 每天给自己设定一个「非求职时间」，出去走走或做点喜欢的事\n\n"
        "你之前在哪个行业做什么岗位？告诉我更多情况，我可以帮你梳理下一步。"
    ),
    "eval_004_cross_industry": (
        "## 跨行业转行分析\n\n你从传统制造业转互联网，跨度较大但有可迁移的底层能力。\n\n"
        "| 你的技能 | 对互联网的价值 | 迁移难度 |\n"
        "| CAD制图 | 低——互联网不需要CAD技能 | — |\n"
        "| 质量管理 | 中——质量思维对测试/项目管理有价值 | 中 |\n\n"
        "建议采取分步策略：先通过3个月补充互联网基础知识（产品流程、基础编程），再投递质量相关岗位作为切入点。\n\n"
        "参考数据：示例薪资数据（脉脉 2026春招报告风格），更新时间 2026-05-28"
    ),
}


def run_agent_api(messages, flow="skill_transfer", resume_text="", requirements="", jd_text="", file_ids=None):
    result = agent.run(messages=messages, flow=flow,
                       resume_text=resume_text, requirements=requirements,
                       jd_text=jd_text, file_ids=file_ids)
    return {
        "profile": {
            "name": result.user_profile.name,
            "current_role": result.user_profile.current_role,
            "target_role": result.user_profile.target_role,
            "years": result.user_profile.years_of_experience,
            "skills": result.user_profile.skills,
            "extracted": result.extracted_profile
        },
        "flow": flow,
        "api_configured": llm.is_configured,
        "model": llm.model,
        "steps": [
            {
                "id": i+1,
                "name": s.name,
                "uses_ai": s.uses_ai,
                "in_tokens": s.input_tokens,
                "out_tokens": s.output_tokens,
                "dur_ms": int(s.duration_ms),
                "summary": s.summary,
            }
            for i, s in enumerate(result.steps)
        ],
        "output": result.final_output,
        "safety": {
            "level": result.safety_result.level.value,
            "warnings": result.safety_result.warnings,
            "violations": result.safety_result.violations,
        },
        "cost": {
            "in_tokens": result.cost_summary["input_tokens"],
            "out_tokens": result.cost_summary["output_tokens"],
            "rmb": result.cost_summary["cost_rmb"],
            "ai_steps": result.cost_summary["ai_steps"],
            "non_ai_steps": result.cost_summary["non_ai_steps"],
        },
        "total_ms": result.cost_summary["total_duration_ms"]
    }


def run_interview_api(user_name):
    profiles = {"小明": USER_XIAOMING, "莉莉": USER_LILI, "阿强": USER_AQIANG}
    user = profiles.get(user_name, USER_XIAOMING)
    jd = JD_PRODUCT_MANAGER if user.target_role == "产品经理" else JD_AI_PM
    result = agent.run(user, flow="interview_prep")
    return {
        "user": {"name": user.name, "target_role": user.target_role},
        "output": result.final_output,
        "cost": result.cost_summary,
        "api_configured": llm.is_configured,
    }
