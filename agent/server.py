"""
Career Agent Server — http://localhost:3000
零依赖（除openai+dotenv），纯Python标准库HTTP服务。
"""
import json, os, sys, io, base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_core import (
    safety, evaluator, agent, llm, qwen_long,
    EVAL_CASES, EVAL_MOCK_OUTPUTS,
    run_agent_api, run_interview_api
)
from tools import parse_resume_file
from badcase import tracker as badcase_tracker

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


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
                sample = EVAL_MOCK_OUTPUTS.get(case.case_id, f"分析: {case.user_profile.get('current_role', '')}")
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
        if p == '/api/badcase/stats':
            return self._ok(badcase_tracker.stats())
        if p == '/api/badcase/list':
            return self._ok({"cases": badcase_tracker.list()})
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
                    return self._ok({
                        "text": text, "filename": filename, "char_count": len(text),
                        "file_id": upload_result['file_id'], "method": "qwen-long"
                    })
                else:
                    return self._ok({"error": f"文件上传失败: {upload_result.get('error')}"})

            result = parse_resume_file(file_bytes, filename)
            return self._ok({
                "text": result['text'], "filename": filename,
                "char_count": result['char_count'], "method": "local"
            })
        if p == '/api/safety-check':
            r = safety.check(body.get('text', ''))
            return self._ok({"level": r.level.value, "violations": r.violations, "warnings": r.warnings})
        if p == '/api/badcase/add':
            case_id = badcase_tracker.add(
                case_type=body.get('type', 'badcase'),
                category=body.get('category', 'manual'),
                flow=body.get('flow', 'skill_transfer'),
                severity=body.get('severity', 'minor'),
                user_input=body.get('user_input', ''),
                llm_output=body.get('llm_output', ''),
                expected_behavior=body.get('expected_behavior', ''),
                actual_issue=body.get('actual_issue', ''),
                detected_by='manual_review',
                heuristic_rule=body.get('heuristic_rule', '')
            )
            return self._ok({"case_id": case_id})
        if p == '/api/badcase/resolve':
            case_id = body.get('case_id', '')
            note = body.get('note', '')
            if case_id:
                badcase_tracker.mark_resolved(case_id, note)
                return self._ok({"case_id": case_id, "resolved": True})
            return self._ok({"error": "请提供case_id"})
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
