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
# Tool 1: User Profile Parser (uses AI — needs semantic understanding)
# ═══════════════════════════════════════════════

def parse_user_profile(raw_input: str) -> dict:
    """
    从用户自由文本输入中提取结构化档案。
    uses_ai: True — 需要语义理解能力
    """
    # 在实际部署中，这里调用LLM做信息提取
    # 本demo返回预置数据
    return {
        "token_estimate": estimate_tokens(raw_input) + 500,  # input + output
        "extracted": {
            "skills_detected": True,
            "years_confirmed": True,
            "target_clarity": "clear" if "产品" in raw_input else "unclear"
        }
    }


# ═══════════════════════════════════════════════
# Tool 2: Skill Graph Query (NO AI — pure structured API)
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
# Tool 4: Resume Analyzer (uses AI — needs semantic parsing)
# ═══════════════════════════════════════════════

def analyze_resume(resume_text: str) -> dict:
    """
    解析简历文本，结构化提取信息。
    uses_ai: True — 简历是自由文本，需要语义理解和信息提取
    """
    return {
        "token_estimate": estimate_tokens(resume_text) + 800,
        "parsed": {
            "years_of_experience": "3年",
            "current_role": "运营专员",
            "education_level": "本科",
            "key_achievements": [
                "季度GMV提升15%",
                "搭建200万用户标签体系",
                "公众号矩阵50万粉丝"
            ],
            "skill_keywords": ["SQL", "数据分析", "用户运营", "项目管理", "Python基础"]
        }
    }


# ═══════════════════════════════════════════════
# Tool 5: JD Parser (uses AI — needs semantic understanding)
# ═══════════════════════════════════════════════

def parse_jd(jd_text: str) -> dict:
    """
    解析岗位JD，提取核心要求和加分项。
    uses_ai: True — JD是自由文本，需要结构化提取
    """
    return {
        "token_estimate": estimate_tokens(jd_text) + 600,
        "parsed": {
            "role": "产品经理",
            "level": "中级",
            "must_have": ["3年经验", "SQL数据分析", "用户研究", "PRD和原型设计"],
            "nice_to_have": ["运营背景", "技术理解", "AI产品经验"],
            "salary_range": "20K-35K · 14薪"
        }
    }


# ═══════════════════════════════════════════════
# Tool 6: Interview Simulator (uses AI — needs generation capability)
# ═══════════════════════════════════════════════

def generate_interview_questions(user_profile: UserProfile, target_jd: str) -> dict:
    """
    基于用户背景和JD生成个性化面试题。
    uses_ai: True — 需要生成能力
    """
    questions = [
        {
            "type": "背景深挖",
            "question": "你提到用SQL做用户分层运营，具体是怎么做的？分层后针对不同用户采取了什么差异化策略？",
            "intent": "验证数据分析能力的深度——不是用过SQL就叫会数据分析",
            "difficulty": "中等",
            "probability": "90%"
        },
        {
            "type": "背景深挖",
            "question": "你从0到1搭建了200万用户的标签体系，过程中最大的挑战是什么？",
            "intent": "看项目复杂度+解决问题的方式",
            "difficulty": "中等",
            "probability": "80%"
        },
        {
            "type": "能力验证",
            "question": "作为产品经理，如果研发说'这个需求做不了'，你怎么办？请用你过去的实际经历举例。",
            "intent": "验证跨部门沟通和推动力——运营转PM的核心考察点",
            "difficulty": "中高",
            "probability": "85%"
        },
        {
            "type": "能力验证",
            "question": "给你一个电商后台的退货率下降10%的目标，你作为PM会怎么拆解和推进？",
            "intent": "场景题——看产品思维和分析框架，不是要正确答案",
            "difficulty": "高",
            "probability": "70%"
        },
        {
            "type": "转行动机",
            "question": "运营做得好好的，为什么要转产品？你了解过产品经理日常工作的哪些部分？",
            "intent": "验证转行动机是否经过深思熟虑，而非跟风",
            "difficulty": "中等",
            "probability": "95%"
        },
    ]

    return {
        "token_estimate": 1500,  # output tokens for question generation
        "questions": questions,
        "total_questions": len(questions)
    }


# ═══════════════════════════════════════════════
# Tool 7: Resume File Parser (NO AI — pure Python extraction)
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
    "parse_user_profile": {
        "function": parse_user_profile,
        "uses_ai": True,
        "description": "语义解析用户自由文本输入，提取结构化档案"
    },
    "query_skill_graph": {
        "function": query_skill_graph,
        "uses_ai": False,  # ⭐ 不走AI
        "description": "查询技能图谱数据库，获取技能可迁移性数据（确定性查询）"
    },
    "query_job_market": {
        "function": query_job_market,
        "uses_ai": False,  # ⭐ 不走AI
        "description": "查询招聘市场数据库，获取薪资/需求趋势（确定性查询）"
    },
    "analyze_resume": {
        "function": analyze_resume,
        "uses_ai": True,
        "description": "语义解析简历文本，结构化提取经历和技能"
    },
    "parse_jd": {
        "function": parse_jd,
        "uses_ai": True,
        "description": "语义解析JD文本，提取核心要求和加分项"
    },
    "generate_interview_questions": {
        "function": generate_interview_questions,
        "uses_ai": True,
        "description": "基于用户背景+JD生成个性化面试模拟题"
    },
    "parse_resume_file": {
        "function": parse_resume_file,
        "uses_ai": False,  # ⭐ 不走AI
        "description": "纯Python标准库解析PDF/DOCX/TXT简历文件（零依赖）"
    },
}
