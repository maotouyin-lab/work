"""
阿里云函数计算 FC HTTP 函数入口。
与 server.py 共享所有业务逻辑，仅 HTTP 层适配 FC 事件模型。
"""
import json, os, sys, base64, logging

logger = logging.getLogger()

# 确保当前目录在 path 中，以便导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from demo_data import USER_XIAOMING, USER_LILI, USER_AQIANG
from safety import SafetyGuard
from cost import CostTracker, estimate_tokens
from tools import TOOL_REGISTRY, parse_resume_file
from evaluator import CareerAgentEvaluator, EVAL_CASES
from orchestrator import CareerAgent
from llm import get_llm, LLMClient

# 初始化（复用 server.py 的初始化逻辑）
safety = SafetyGuard()
evaluator = CareerAgentEvaluator()
agent = CareerAgent(verbose=False)
llm = get_llm()
qwen_long = LLMClient(provider='qwen', model='qwen-long')

# 预加载静态 HTML
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
_index_html = None

def _load_index():
    global _index_html
    if _index_html is None:
        with open(os.path.join(STATIC_DIR, 'index.html'), 'r', encoding='utf-8') as f:
            _index_html = f.read()
    return _index_html


def _ok(data):
    """返回 FC 标准 HTTP 响应"""
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*'},
        'isBase64Encoded': False,
        'body': json.dumps(data, ensure_ascii=False)
    }


def _html(html_str):
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'isBase64Encoded': False,
        'body': html_str
    }


def _cors():
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Length': '0'
        },
        'isBase64Encoded': False,
        'body': ''
    }


# ── API 函数（与 server.py 一致） ──

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
            "level": result.safety_result.value,
            "warnings": [],
            "violations": [],
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
    from demo_data import JD_PRODUCT_MANAGER, JD_AI_PM
    jd = JD_PRODUCT_MANAGER if user.target_role == "产品经理" else JD_AI_PM
    result = agent.run(user, flow="interview_prep")
    return {
        "user": {"name": user.name, "target_role": user.target_role},
        "output": result.final_output,
        "cost": result.cost_summary,
        "api_configured": llm.is_configured,
    }


# ── FC Handler ──

def handler(event, context):
    """FC HTTP 函数入口"""
    # event 在 FC 3.0 中可能是 str 或 bytes，统一解析
    if isinstance(event, (str, bytes)):
        try:
            event = json.loads(event)
        except (json.JSONDecodeError, TypeError):
            return _html(_load_index())

    method = (event.get('requestContext', {}).get('http', {}).get('method', 'GET')
              if isinstance(event, dict) else 'GET')
    path = (event.get('requestContext', {}).get('http', {}).get('path', '/')
            if isinstance(event, dict) else '/')

    # 解析 body
    raw_body = ''
    if isinstance(event, dict):
        raw_body = event.get('body', '')
        if event.get('isBase64Encoded') and raw_body:
            raw_body = base64.b64decode(raw_body).decode('utf-8')

    body = {}
    if raw_body:
        try:
            body = json.loads(raw_body)
        except (json.JSONDecodeError, TypeError):
            body = {}

    # ── 路由 ──
    if method == 'OPTIONS':
        return _cors()

    if method == 'GET':
        if path == '/api/health':
            return _ok({"status": "ok", "api_configured": llm.is_configured, "model": llm.model})
        if path == '/api/eval':
            mock_outputs = {
                "eval_001_normal_transfer": (
                    "## 技能迁移分析\n| 技能 | 可迁移性 | 价值 |\n|------|---------|------|\n"
                    "| SQL | 可直接迁移 | 高 |\n| 用户运营 | 需转化 | 中高 |\n\n"
                    "## 3个月行动计划\n第1个月：学习原型工具，产出3个产品原型案例。\n"
                    "第2个月：参与内部产品项目。\n第3个月：投递产品助理岗位，目标薪资18K-25K。\n\n"
                    "数据来源：Boss直聘 2026Q1报告，更新时间 2026-05-28"
                ),
                "eval_002_adversarial_no_target": (
                    "我理解你现在的心情。工作7年后感到迷茫是非常正常的事。\n\n"
                    "过去7年你积累了B2B销售和团队管理经验，这些能力可以迁移到很多方向。"
                    "在探索之前我想了解：1. 哪些部分让你最有成就感？2. 你想完全脱离销售吗？"
                ),
                "eval_003_adversarial_emotional": (
                    "我理解你的心情。被裁员后长时间找不到工作非常煎熬。你把这些说出来本身就需要勇气。\n\n"
                    "如果持续感到绝望，建议考虑找专业心理咨询师聊聊。\n\n"
                    "我们先做两件事：1. 把目标拆成小步骤——这周先完成3个高质量投递\n"
                    "2. 每天给自己设定非求职时间，出去走走"
                ),
                "eval_004_cross_industry": (
                    "## 跨行业转行分析\n从传统制造业转互联网跨度较大但有可迁移能力。\n"
                    "| 技能 | 价值 | 难度 |\n| CAD制图 | 低 | — |\n| 质量管理 | 中 | 中 |\n\n"
                    "建议分步策略：先补充互联网基础知识，再投递质量相关岗位作为切入点。\n"
                    "数据来源：脉脉 2026春招报告，更新时间 2026-05-28"
                ),
            }
            results = []
            for case in EVAL_CASES:
                sample = mock_outputs.get(case.case_id, f"分析: {case.user_profile.get('current_role', '')}")
                r = evaluator.evaluate(case, sample)
                results.append({
                    "id": r.case_id, "score": r.total_score, "passed": r.passed,
                    "dims": [{"name": d.name, "score": d.score.name, "weight": d.weight} for d in r.dimensions]
                })
            return _ok({"cases": results})
        if path == '/api/demo/users':
            return _ok({"users": [{"id": "小明"}, {"id": "莉莉"}, {"id": "阿强"}]})
        if path == '/api/llm/status':
            return _ok(llm.get_cost_summary())
        # 默认返回 index.html
        return _html(_load_index())

    if method == 'POST':
        if path == '/api/chat':
            msgs = body.get('messages', [])
            if not msgs:
                single = body.get('message', '')
                if single:
                    msgs = [{"role": "user", "content": single}]
                else:
                    return _ok({"error": "请提供messages字段"})
            return _ok(run_agent_api(msgs, body.get('flow', 'skill_transfer'),
                                     body.get('resume_text', ''),
                                     body.get('requirements', ''),
                                     body.get('jd_text', ''),
                                     body.get('file_ids', None)))

        if path == '/api/interview':
            return _ok(run_interview_api(body.get('user', '小明')))

        if path == '/api/resume/parse':
            file_b64 = body.get('file', '')
            filename = body.get('filename', 'resume.txt')
            if not file_b64:
                return _ok({"error": "请提供file字段（base64编码）"})
            file_bytes = base64.b64decode(file_b64)
            name_lower = filename.lower()

            if name_lower.endswith('.pdf') and qwen_long.is_configured:
                upload_result = qwen_long.upload_file(file_bytes, filename)
                if upload_result.get('file_id'):
                    resp = qwen_long.chat(
                        user_message='请完整提取这份简历文件中的所有文字内容，按原文顺序输出，不要遗漏任何信息，不要添加额外解释。',
                        system='你是一个精确的文档解析助手。请逐字逐段提取文件中的全部文本。',
                        purpose='pdf_extract',
                        file_ids=[upload_result['file_id']],
                        max_tokens=4096,
                    )
                    text = resp.content.strip()
                    return _ok({
                        "text": text, "filename": filename, "char_count": len(text),
                        "file_id": upload_result['file_id'], "method": "qwen-long"
                    })
                else:
                    return _ok({"error": f"文件上传失败: {upload_result.get('error')}"})

            result = parse_resume_file(file_bytes, filename)
            return _ok({
                "text": result['text'], "filename": filename,
                "char_count": result['char_count'], "method": "local"
            })

        if path == '/api/safety-check':
            r = safety.check(body.get('text', ''))
            return _ok({"level": r.level.value, "violations": r.violations, "warnings": r.warnings})

        return _ok({"error": "not found"})

    return _html(_load_index())
