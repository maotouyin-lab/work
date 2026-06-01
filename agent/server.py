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
from llm import get_llm, get_qwen_llm, LLMClient

safety = SafetyGuard()
evaluator = CareerAgentEvaluator()
agent = CareerAgent(verbose=False)
llm = get_llm()
qwen_llm = get_qwen_llm()
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
            results = []
            for case in EVAL_CASES:
                sample = f"分析: {case.user_profile.get('current_role', '')}"
                r = evaluator.evaluate(case, sample)
                results.append({"id": r.case_id, "score": r.total_score, "passed": r.passed})
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
