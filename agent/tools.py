"""
Tool implementations for Career Agent.

⚠️ 核心设计决策（面试重点）:
- Tool 2 (skill_graph) 和 Tool 3 (job_market) 是纯函数调用，不走AI
- Tool 1/4/5/6 需要LLM做语义理解和生成
- Tool 7 (resume_parser) 纯Python解析PDF/DOCX/TXT，零第三方依赖
"""
import re
import io
import zipfile
from xml.etree import ElementTree
from demo_data import (
    UserProfile, SKILL_TRANSFER_MAP, JOB_MARKET_DATA,
    RESUME_XIAOMING, JD_PRODUCT_MANAGER, JD_AI_PM
)
from cost import estimate_tokens


# ═══════════════════════════════════════════════
# Tool 1: Skill Graph Query (NO AI — pure structured API)
# ═══════════════════════════════════════════════

def query_skill_graph(skills: list[str], target_role: str) -> dict:
    """
    查询技能图谱，分析技能可迁移性。
    uses_ai: False — 这是确定性图查询，走结构化API/数据库。

    面试话术: "技能之间的关系是图数据。图查询是确定性操作——
    用Neo4j/Cypher或图谱API返回结果就行，不需要LLM推理。
    用LLM反而可能编造不存在的技能关系。"
    """
    result = {}
    for skill in skills:
        if skill in SKILL_TRANSFER_MAP:
            info = SKILL_TRANSFER_MAP[skill]
            # 检查该技能是否对目标岗位有用
            is_relevant = target_role in str(info['transferable_to'])
            result[skill] = {
                "transferable_to": info['transferable_to'],
                "score": info['transferability_score'],
                "relevant_to_target": is_relevant,
                "note": info['gap_note']
            }
        else:
            result[skill] = {
                "transferable_to": ["未知"],
                "score": 0.3,
                "relevant_to_target": False,
                "note": "该技能不在标准图谱中，建议补充评估"
            }

    return {
        "token_estimate": 0,  # ⚠️ 不走AI，token消耗为0
        "source": "Skill Graph DB v2.3",
        "data": result,
        "query_time_ms": 45
    }


# ═══════════════════════════════════════════════
# Tool 3: Job Market Data Query (NO AI — pure structured API)
# ═══════════════════════════════════════════════

def query_job_market(target_role: str, city: str = None) -> dict:
    """
    查询招聘市场数据。
    uses_ai: False — 这是结构化数据查询，走招聘平台API。

    面试话术: "薪资数据不走LLM。Boss直聘/脉脉API返回什么就是什么。
    LLM可能会'创造'一个看起来很合理但完全虚构的薪资数字——
    在职业规划场景里，这会让用户基于错误信息做决策。"
    """
    if target_role in JOB_MARKET_DATA:
        data = JOB_MARKET_DATA[target_role].copy()
    else:
        data = {
            "avg_salary": "数据暂缺",
            "demand_trend": "暂无数据",
            "note": f"'{target_role}'不在当前数据库中，建议手动查询招聘平台"
        }

    return {
        "token_estimate": 0,  # ⚠️ 不走AI
        "source": data.pop("data_source", "未知来源"),
        "updated": data.pop("data_updated", "未知"),
        "data": data,
        "query_time_ms": 120
    }


# ═══════════════════════════════════════════════
# Tool 4: Resume File Parser (NO AI — pure Python extraction)
# ═══════════════════════════════════════════════

def _find_matching_bb(b: bytes, start: int) -> int:
    """Find the matching >> for a << starting at `start`, handling nesting."""
    depth = 1
    i = start + 2
    while i < len(b) - 1 and depth > 0:
        if b[i:i+2] == b'<<':
            depth += 1
            i += 2
        elif b[i:i+2] == b'>>':
            depth -= 1
            if depth == 0:
                return i + 2  # return position after >>
            i += 2
        else:
            i += 1
    return -1


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from PDF bytes, handling FlateDecode compressed streams."""
    import zlib

    text_lines = []
    seen = set()

    # Find stream objects, handling nested <<>> in dictionaries
    stream_pattern = re.compile(rb'stream\r?\n(.*?)endstream', re.DOTALL)

    for sm in stream_pattern.finditer(file_bytes):
        stream_data = sm.group(1)
        before = file_bytes[:sm.start()]

        # Find the dictionary that belongs to this stream by locating
        # the last << before 'stream' and matching its >> (handles nesting)
        dict_start = before.rfind(b'<<')
        if dict_start == -1:
            continue
        dict_end = _find_matching_bb(before, dict_start)
        if dict_end == -1:
            continue
        dict_raw = before[dict_start+2:dict_end-2].decode('latin-1', errors='replace')

        # Decode: decompress if FlateDecode, otherwise use raw
        if '/FlateDecode' in dict_raw:
            try:
                decoded = zlib.decompress(stream_data).decode('latin-1', errors='replace')
            except (zlib.error, Exception):
                decoded = stream_data.decode('latin-1', errors='replace')
        else:
            decoded = stream_data.decode('latin-1', errors='replace')

        # Extract BT..ET text blocks from this stream
        _extract_bt_text(decoded, text_lines, seen)

    # Step 2: fallback — extract BT..ET from the raw file
    if not text_lines:
        raw_str = file_bytes.decode('latin-1', errors='replace')
        _extract_bt_text(raw_str, text_lines, seen)

    return '\n'.join(text_lines)


def _decode_hex_string(hex_str: str) -> str:
    """Try to decode a PDF hex string to readable text.

    PDFs encode text in hex strings several ways:
    - UTF-16BE with BOM (FEFF...) → common for ToUnicode fonts
    - GBK/GB18030 (Chinese PDFs from WPS/Word) — try FIRST for CJK use case
    - UTF-16BE without BOM (Identity-H CMap)
    - Raw ASCII (basic fonts)
    """
    try:
        raw = bytes.fromhex(hex_str.strip())
    except ValueError:
        return f'<{hex_str}>'

    if len(raw) < 2:
        return raw.decode('ascii', errors='replace')

    # UTF-16BE with BOM — unambiguous, use immediately
    if raw[:2] == b'\xfe\xff':
        return raw[2:].decode('utf-16-be', errors='replace')

    candidates = []

    # Try GB18030 first (covers GBK, common for WPS/Word Chinese PDFs)
    try:
        text = raw.decode('gb18030')
        good = sum(1 for c in text if c.isprintable() or c in '\n\r\t ')
        candidates.append((good / max(len(text), 1), 'gb18030', text))
    except (UnicodeDecodeError, LookupError):
        pass

    # Try UTF-16BE without BOM (common for Identity-H CMap on modern PDFs)
    if len(raw) % 2 == 0 and len(raw) >= 4:
        try:
            text = raw.decode('utf-16-be')
            good = sum(1 for c in text if c.isprintable() or c in '\n\r\t ')
            candidates.append((good / max(len(text), 1), 'utf-16-be', text))
        except UnicodeDecodeError:
            pass

    # Try UTF-8
    try:
        text = raw.decode('utf-8')
        good = sum(1 for c in text if c.isprintable() or c in '\n\r\t ')
        candidates.append((good / max(len(text), 1), 'utf-8', text))
    except UnicodeDecodeError:
        pass

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][2]

    return raw.decode('latin-1', errors='replace')


def _extract_bt_text(content: str, text_lines: list, seen: set):
    """Extract text from BT..ET blocks in a decoded content stream.

    Handles: (text) Tj, <hex> Tj, [(text) kerning (text)] TJ
    Each BT block produces one logical line.
    """
    for bt_match in re.finditer(r'BT(.*?)ET', content, re.DOTALL):
        bt = bt_match.group(1)
        block_texts = []

        # 1. TJ arrays: [(text) -5 (text) <hex> (text)] TJ
        for tj_match in re.finditer(r'\[(.*?)\]\s*TJ', bt, re.DOTALL):
            tj_content = tj_match.group(1)
            # Collect all strings inside the array, in order
            strings = re.findall(r'\(([^)]*)\)|<([0-9A-Fa-f\s]+)>', tj_content)
            for paren_text, hex_text in strings:
                if paren_text:
                    block_texts.append(paren_text)
                elif hex_text:
                    block_texts.append(_decode_hex_string(hex_text))

        # 2. Standalone operators: (text) Tj, (text) ', <hex> Tj, <hex> '
        if not block_texts:
            for m in re.finditer(r'\(([^)]*)\)\s*Tj', bt):
                block_texts.append(m.group(1))
            for m in re.finditer(r'\(([^)]*)\)\s*\'', bt):
                block_texts.append(m.group(1))
            for m in re.finditer(r'<([0-9A-Fa-f\s]+)>\s*Tj', bt):
                block_texts.append(_decode_hex_string(m.group(1)))
            for m in re.finditer(r'<([0-9A-Fa-f\s]+)>\s*\'', bt):
                block_texts.append(_decode_hex_string(m.group(1)))

        if block_texts:
            line = ''.join(block_texts).strip()
            if line and line not in seen:
                text_lines.append(line)
                seen.add(line)


def parse_resume_file(file_bytes: bytes, filename: str) -> dict:
    """
    Parse resume text from uploaded file. Pure Python — zero dependencies.
    Supports: PDF (text layer), DOCX, TXT, and common image-based PDF
    returns text placeholder.

    面试话术: "简历文件解析走纯Python标准库——PDF用正则提取文本流，
    DOCX用zipfile解压XML。这些是确定性操作，不需要也不应该走LLM。"
    """
    name_lower = filename.lower()
    text = ""

    try:
        if name_lower.endswith('.txt'):
            text = file_bytes.decode('utf-8', errors='replace')

        elif name_lower.endswith('.docx'):
            # DOCX = ZIP containing word/document.xml
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                xml_content = z.read('word/document.xml')
            root = ElementTree.fromstring(xml_content)
            # Extract all text from <w:t> elements
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = []
            for para in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                p_text = ''.join(
                    t.text or ''
                    for t in para.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')
                )
                if p_text.strip():
                    paragraphs.append(p_text.strip())
            text = '\n'.join(paragraphs)

        elif name_lower.endswith('.pdf'):
            import zlib
            text = _extract_pdf_text(file_bytes)
            if len(text.strip()) < 50:
                text = '[此PDF为图片扫描版，无法直接提取文本。请粘贴简历文本或上传TXT/DOCX格式。]'

        else:
            # Try UTF-8 decode as fallback
            try:
                text = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                text = f'[不支持的文件格式: {filename}。支持: PDF / DOCX / TXT]'

    except Exception as e:
        text = f'[文件解析失败: {str(e)}。请尝试粘贴文本。]'

    return {
        "token_estimate": 0,  # 不走AI
        "text": text.strip(),
        "filename": filename,
        "char_count": len(text.strip()),
        "source": "Python stdlib parser (zipfile+xml for DOCX, regex for PDF, utf-8 for TXT)"
    }


# ── Tool Registry ──

TOOL_REGISTRY = {
    "query_skill_graph": {
        "function": query_skill_graph,
        "uses_ai": False,
        "description": "查询技能图谱数据库，获取技能可迁移性数据（确定性查询）"
    },
    "query_job_market": {
        "function": query_job_market,
        "uses_ai": False,
        "description": "查询招聘市场数据库，获取薪资/需求趋势（确定性查询）"
    },
    "parse_resume_file": {
        "function": parse_resume_file,
        "uses_ai": False,
        "description": "纯Python标准库解析PDF/DOCX/TXT简历文件（零依赖）"
    },
}
