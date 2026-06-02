"""
Career Agent Server — http://localhost:3000
零依赖（除openai+dotenv），纯Python标准库HTTP服务。
"""
import json, os, sys, io, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from demo_data import USER_XIAOMING, USER_LILI, USER_AQIANG
from safety import SafetyGuard, SafetyLevel
from cost import CostTracker, estimate_tokens
from tools import TOOL_REGISTRY, parse_resume_file
from evaluator import CareerAgentEvaluator, EVAL_CASES
from orchestrator import CareerAgent
from llm import get_llm, LLMClient

safety = SafetyGuard()
evaluator = CareerAgentEvaluator()
agent = CareerAgent(verbose=False)
llm = get_llm()
# PDF 文件解析专用 qwen-long 客户端（独立于简历优化用的 qwen-turbo）
qwen_long = LLMClient(provider='qwen', model='qwen-long')
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


def run_agent_api(messages, flow="skill_transfer", resume_text="", requirements="", jd_text="", file_ids=None):
    """对外的Agent API，接收消息数组（多轮对话），返回JSON可序列化的结果"""
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


class Handler(BaseHTTPRequestHandler):
    def _ok(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        try:
            with open(path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def do_GET(self):
        p = urlparse(self.path).path
        if p == '/api/health':
            return self._ok({"status": "ok", "api_configured": llm.is_configured, "model": llm.model})
        if p == '/api/eval':
            # Mock outputs with varied quality to demonstrate 5-dimension scoring
            mock_outputs = {
                "eval_001_normal_transfer": (
                    "## 技能迁移分析\n| 技能 | 可迁移性 | 价值 |\n|------|---------|------|\n"
                    "| SQL | 可直接迁移 | 高 |\n| 用户运营 | 需转化 | 中高 |\n\n"
                    "## 技能缺口\n产品经理核心技能需求包括需求分析和原型设计，目前缺失。\n\n"
                    "## 推荐路径\n分步转岗：先内部转产品运营岗，积累产品经验后再转纯产品岗。\n\n"
                    "## 3个月行动计划\n第1个月：学习Axure/Figma原型工具，产出3个产品原型案例。\n"
                    "第2个月：参与1个公司内部产品项目，积累产品文档经验。\n"
                    "第3个月：投递产品助理岗位，目标薪资18K-25K。\n\n"
                    "数据来源：Boss直聘 2026Q1报告，更新时间 2026-05-28"
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
            return self._ok({"cases": results})
        if p == '/api/demo/users':
            return self._ok({"users": [{"id": "小明"}, {"id": "莉莉"}, {"id": "阿强"}]})
        if p == '/api/llm/status':
            return self._ok(llm.get_cost_summary())
        # Static files
        if p == '/' or p == '':
            p = '/index.html'
        return self._file(os.path.join(STATIC, p.lstrip('/')))

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            clen = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(clen).decode('utf-8')) if clen > 0 else {}
        except:
            body = {}

        if p == '/api/chat':
            # 支持两种模式：messages数组（多轮） 或 message字符串（单轮兼容）
            msgs = body.get('messages', [])
            if not msgs:
                single = body.get('message', '')
                if single:
                    msgs = [{"role": "user", "content": single}]
                else:
                    return self._ok({"error": "请提供messages字段"})
            return self._ok(run_agent_api(msgs, body.get('flow', 'skill_transfer'),
                                         body.get('resume_text', ''),
                                         body.get('requirements', ''),
                                         body.get('jd_text', ''),
                                         body.get('file_ids', None)))
        if p == '/api/interview':
            return self._ok(run_interview_api(body.get('user', '小明')))
        if p == '/api/resume/parse':
            file_b64 = body.get('file', '')
            filename = body.get('filename', 'resume.txt')
            if not file_b64:
                return self._ok({"error": "请提供file字段（base64编码）"})

            import base64
            file_bytes = base64.b64decode(file_b64)
            name_lower = filename.lower()

            # PDF: upload to DashScope (qwen-long) for reliable parsing
            if name_lower.endswith('.pdf') and qwen_long.is_configured:
                upload_result = qwen_long.upload_file(file_bytes, filename)
                if upload_result.get('file_id'):
                    # Call qwen-long to extract text from the uploaded file
                    resp = qwen_long.chat(
                        user_message='请完整提取这份简历文件中的所有文字内容，按原文顺序输出，不要遗漏任何信息，不要添加额外解释。',
                        system='你是一个精确的文档解析助手。请逐字逐段提取文件中的全部文本。',
                        purpose='pdf_extract',
                        file_ids=[upload_result['file_id']],
                        max_tokens=4096,
                    )
                    text = resp.content.strip()
                    return self._ok({
                        "text": text,
                        "filename": filename,
                        "char_count": len(text),
                        "file_id": upload_result['file_id'],
                        "method": "qwen-long"
                    })
                else:
                    return self._ok({"error": f"文件上传失败: {upload_result.get('error')}"})

            # DOCX / TXT / fallback: local parsing
            result = parse_resume_file(file_bytes, filename)
            return self._ok({
                "text": result['text'],
                "filename": filename,
                "char_count": result['char_count'],
                "method": "local"
            })
        if p == '/api/safety-check':
            r = safety.check(body.get('text', ''))
            return self._ok({"level": r.level.value, "violations": r.violations, "warnings": r.warnings})
        self._ok({"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, fmt, *args): pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"""
╔══════════════════════════════════════════════════╗
║   AI职业规划与求职Agent — Server v2.0          ║
║   后端: http://0.0.0.0:{port:<5}                   ║
║   API:  {'DeepSeek已连接' if llm.is_configured else '模拟模式（请配置.env）':<40} ║
║   按 Ctrl+C 停止                                 ║
╚══════════════════════════════════════════════════╝
""")
    httpd = HTTPServer(('0.0.0.0', port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止。")
        httpd.server_close()
