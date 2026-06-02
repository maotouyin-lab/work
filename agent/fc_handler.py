"""
阿里云函数计算 FC HTTP 函数入口。
与 server.py 共享所有业务逻辑（api_core.py），仅 HTTP 层适配 FC 事件模型。
"""
import json, os, sys, base64, logging

logger = logging.getLogger()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_core import (
    safety, evaluator, agent, llm, qwen_long,
    EVAL_CASES, EVAL_MOCK_OUTPUTS,
    run_agent_api, run_interview_api
)
from tools import parse_resume_file
from badcase import tracker as badcase_tracker

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
_index_html = None

def _load_index():
    global _index_html
    if _index_html is None:
        with open(os.path.join(STATIC_DIR, 'index.html'), 'r', encoding='utf-8') as f:
            _index_html = f.read()
    return _index_html


def _ok(data):
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


def handler(event, context):
    """FC HTTP 函数入口"""
    if isinstance(event, (str, bytes)):
        try:
            event = json.loads(event)
        except (json.JSONDecodeError, TypeError):
            return _html(_load_index())

    method = (event.get('requestContext', {}).get('http', {}).get('method', 'GET')
              if isinstance(event, dict) else 'GET')
    path = (event.get('requestContext', {}).get('http', {}).get('path', '/')
            if isinstance(event, dict) else '/')

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

    if method == 'OPTIONS':
        return _cors()

    if method == 'GET':
        if path == '/api/health':
            return _ok({"status": "ok", "api_configured": llm.is_configured, "model": llm.model})
        if path == '/api/eval':
            results = []
            for case in EVAL_CASES:
                sample = EVAL_MOCK_OUTPUTS.get(case.case_id, f"分析: {case.user_profile.get('current_role', '')}")
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
        if path == '/api/badcase/stats':
            return _ok(badcase_tracker.stats())
        if path == '/api/badcase/list':
            return _ok({"cases": badcase_tracker.list()})
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
        if path == '/api/badcase/add':
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
            return _ok({"case_id": case_id})
        if path == '/api/badcase/resolve':
            case_id = body.get('case_id', '')
            note = body.get('note', '')
            if case_id:
                badcase_tracker.mark_resolved(case_id, note)
                return _ok({"case_id": case_id, "resolved": True})
            return _ok({"error": "请提供case_id"})

        return _ok({"error": "not found"})

    return _html(_load_index())
