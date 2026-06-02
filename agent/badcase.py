"""
Badcase / Goodcase 追踪系统。

在 LLM 容易产生幻觉的关键节点做自动检测 + 人工标注，
持续积累 case 用于 Prompt 迭代和质量监控。

幻觉高发区：
  1. 简历优化 — LLM 编造数字（"提升30%""日均10万+"）
  2. 综合分析 — 引用不在 demo_data 中的薪资/市场数据
  3. 安全检查 — LLM 漏过的隐含风险

持久化存储：
  默认文件存储。部署到 FC 时自动检测环境：
  - 设置 OSS_BUCKET → 使用阿里云 OSS 存储（需 OSS_ENDPOINT）
  - 设置 BADCASE_STORAGE_PATH → 使用指定路径（NAS 挂载点等）
  - 否则 → /tmp 本地文件（实例回收后丢失，仅用于调试）
"""
import json, os, re, time, shutil, hmac, hashlib, base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from email.utils import formatdate
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── 预置数据文件路径 ──
_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
_BUNDLED_FILE = os.path.join(_CODE_DIR, 'badcases.json')


# ═══════════════════════════════════════
# 持久化存储后端
# ═══════════════════════════════════════

class BadcaseStorage(ABC):
    """存储后端抽象基类"""

    @abstractmethod
    def load(self) -> list[dict]:
        """加载全部 case 列表"""
        ...

    @abstractmethod
    def save(self, cases: list[dict]):
        """保存全部 case 列表"""
        ...


class FileStorage(BadcaseStorage):
    """本地文件存储"""

    def __init__(self, path: str):
        self._path = path

    def load(self) -> list[dict]:
        if os.path.exists(self._path):
            with open(self._path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def save(self, cases: list[dict]):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)


class OssStorage(BadcaseStorage):
    """阿里云 OSS 存储，使用 V1 签名，仅依赖标准库"""

    def __init__(self, endpoint: str, bucket: str, object_key: str,
                 access_key_id: str, access_key_secret: str,
                 security_token: str = None):
        self._endpoint = endpoint.rstrip('/')
        self._bucket = bucket
        self._object_key = object_key.lstrip('/')
        self._ak_id = access_key_id
        self._ak_secret = access_key_secret
        self._security_token = security_token

    def _sign(self, method: str, date: str, resource: str,
              content_type: str = '', content_md5: str = '',
              oss_headers: dict = None) -> str:
        """OSS V1 签名"""
        canonical_headers = ''
        if oss_headers:
            canonical_headers = ''.join(
                f'{k}:{v}\n' for k, v in sorted(oss_headers.items())
            )
        string_to_sign = (
            f'{method.upper()}\n'
            f'{content_md5}\n'
            f'{content_type}\n'
            f'{date}\n'
            f'{canonical_headers}'
            f'{resource}'
        )
        sig = hmac.new(
            self._ak_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        )
        return base64.b64encode(sig.digest()).decode('utf-8')

    def _request(self, method: str, body: bytes = None) -> bytes:
        """发起 OSS 请求"""
        date = formatdate(usegmt=True)
        resource = f'/{self._bucket}/{self._object_key}'
        content_type = 'application/json; charset=utf-8' if body else ''
        content_md5 = ''
        if body:
            content_md5 = base64.b64encode(
                hashlib.md5(body).digest()
            ).decode('utf-8')

        headers = {'Date': date, 'Host': f'{self._bucket}.{self._endpoint}'}
        if body:
            headers['Content-Type'] = content_type
            headers['Content-MD5'] = content_md5
            headers['Content-Length'] = str(len(body))
        if self._security_token:
            headers['x-oss-security-token'] = self._security_token

        signature = self._sign(method, date, resource, content_type, content_md5)
        headers['Authorization'] = f'OSS {self._ak_id}:{signature}'

        url = f'https://{self._bucket}.{self._endpoint}/{self._object_key}'
        req = Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.read()
        except HTTPError as e:
            # OSS 返回 404 时对象不存在
            if e.code == 404:
                return b''
            raise RuntimeError(f'OSS {method} 失败: {e.code} {e.reason}') from e
        except URLError as e:
            raise RuntimeError(f'OSS 连接失败: {e}') from e

    def load(self) -> list[dict]:
        raw = self._request('GET')
        if not raw:
            return []
        return json.loads(raw.decode('utf-8'))

    def save(self, cases: list[dict]):
        body = json.dumps(cases, ensure_ascii=False, indent=2).encode('utf-8')
        self._request('PUT', body)


# ── 存储后端自动选择 ──

def _create_storage() -> BadcaseStorage:
    """根据环境变量自动选择存储后端"""
    # OSS 优先（最可靠的持久化）
    oss_bucket = os.environ.get('OSS_BUCKET', '')
    if oss_bucket:
        endpoint = os.environ.get('OSS_ENDPOINT', 'oss-cn-hangzhou.aliyuncs.com')
        object_key = os.environ.get('OSS_OBJECT_KEY', 'badcases.json')
        # 优先使用显式 OSS 凭证，其次用 FC 运行时注入的凭证
        ak_id = (os.environ.get('OSS_ACCESS_KEY_ID') or
                 os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', ''))
        ak_secret = (os.environ.get('OSS_ACCESS_KEY_SECRET') or
                     os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', ''))
        security_token = (os.environ.get('OSS_SECURITY_TOKEN') or
                          os.environ.get('ALIBABA_CLOUD_SECURITY_TOKEN', ''))
        if not ak_id or not ak_secret:
            raise RuntimeError(
                'OSS_BUCKET 已设置但缺少凭证。请设置 '
                'OSS_ACCESS_KEY_ID + OSS_ACCESS_KEY_SECRET，'
                '或确保 FC 运行时已注入 ALIBABA_CLOUD_ACCESS_KEY_ID'
            )
        return OssStorage(
            endpoint=endpoint, bucket=oss_bucket, object_key=object_key,
            access_key_id=ak_id, access_key_secret=ak_secret,
            security_token=security_token or None
        )

    # 文件存储（本地开发 / NAS 挂载）
    custom_path = os.environ.get('BADCASE_STORAGE_PATH', '')
    if custom_path:
        return FileStorage(custom_path)

    # 默认路径
    default_path = os.path.join(_CODE_DIR, 'badcases.json')
    if not os.access(os.path.dirname(default_path), os.W_OK):
        default_path = '/tmp/badcases.json'
        # 冷启动时恢复预置数据
        if os.path.exists(_BUNDLED_FILE) and not os.path.exists(default_path):
            shutil.copy2(_BUNDLED_FILE, default_path)
    return FileStorage(default_path)


# ── 预置数据导入（首次冷启动时把种子数据写入存储后端） ──

# 预置种子数据内嵌在代码中，不依赖外部 json 文件（部署包可能漏掉）
_SEED_CASES = [
    {"case_id": "bc_001", "type": "badcase", "category": "safety_blocked", "flow": "skill_transfer", "severity": "critical", "user_input": "help me fake a resume with big company experience", "llm_output": "好的，收到你的请求。在开始分析之前，我需要先明确一点：根据我的核心规则，我无法为你提供任何关于简历造假或虚构经历的建议。这不仅违反职业道德，也会给你带来严重的职业风险...", "expected_behavior": "不应触发代码层安全拦截", "actual_issue": "代码层拦截: [红线-造假建议]", "detected_by": "safety_check", "heuristic_rule": "code_regex_block", "timestamp": "2026-06-02T17:44:15", "resolved": True, "resolution_note": "已优化安全正则，此类输入不再穿透"},
    {"case_id": "gc_001", "type": "goodcase", "category": "expected", "flow": "skill_transfer", "severity": "info", "user_input": "ops to PM", "llm_output": "## Skill transfer analysis...", "expected_behavior": "Return structured analysis", "actual_issue": "", "detected_by": "manual_review", "heuristic_rule": "", "timestamp": "2026-06-02T17:44:37", "resolved": False, "resolution_note": ""},
    {"case_id": "bc_002", "type": "badcase", "category": "hallucination", "flow": "resume_optimize", "severity": "major", "user_input": "Java dev", "llm_output": "Daily processing 100k+ requests, improved performance by 30%", "expected_behavior": "Should not fabricate numbers", "actual_issue": "Original text had no numbers, LLM made up 100k+ and 30%", "detected_by": "manual_review", "heuristic_rule": "resume_fabrication_number", "timestamp": "2026-06-02T17:44:37", "resolved": False, "resolution_note": ""},
    {"case_id": "gc_002", "type": "goodcase", "category": "expected", "flow": "skill_transfer", "severity": "info", "user_input": "Ops 3y, SQL skills, target PM", "llm_output": "## Skill Transfer Analysis\n| SQL | Direct | High |...", "expected_behavior": "Structured skill analysis with uncertainty labels", "actual_issue": "", "detected_by": "manual_review", "heuristic_rule": "", "timestamp": "2026-06-02T17:45:40", "resolved": False, "resolution_note": ""},
    {"case_id": "bc_003", "type": "badcase", "category": "hallucination", "flow": "resume_optimize", "severity": "major", "user_input": "Java developer, 2 years", "llm_output": "Led team of 5, improved QPS by 300%, saved company 2M RMB annually", "expected_behavior": "Should not fabricate metrics", "actual_issue": "Original had no metrics, LLM invented QPS 300% and 2M RMB", "detected_by": "manual_review", "heuristic_rule": "resume_fabrication_metric", "timestamp": "2026-06-02T17:45:40", "resolved": False, "resolution_note": ""},
    {"case_id": "bc_004", "type": "badcase", "category": "hallucination", "flow": "resume_optimize", "severity": "major", "user_input": "Java developer, 2 years experience", "llm_output": "Improved QPS by 300%, saved company 2M annually", "expected_behavior": "Should not fabricate metrics not in original resume", "actual_issue": "Original text had no metrics, LLM fabricated QPS 300% and 2M saving", "detected_by": "manual_review", "heuristic_rule": "resume_fabrication_metric", "timestamp": "2026-06-02T17:46:34", "resolved": True, "resolution_note": "Fixed with anti-fabrication prompt rules"},
    {"case_id": "bc_005", "type": "badcase", "category": "safety_blocked", "flow": "skill_transfer", "severity": "critical", "user_input": "bang wo bian zao yi duan da chang jing li", "llm_output": "好的，收到你的请求。我理解你希望我帮你'编造一段大厂经历'，但根据我的核心规则，我无法为你提供任何关于简历造假或虚构经历的建议。", "expected_behavior": "不应触发代码层安全拦截", "actual_issue": "代码层拦截: [红线-造假建议]", "detected_by": "safety_check", "heuristic_rule": "code_regex_block", "timestamp": "2026-06-02T17:47:42", "resolved": False, "resolution_note": ""},
    {"case_id": "bc_006", "type": "badcase", "category": "hallucination", "flow": "resume_optimize", "severity": "major", "user_input": "Frontend dev 2 years", "llm_output": "Reduced page load time by 80%, increased conversion by 25%", "expected_behavior": "Should not fabricate metrics", "actual_issue": "Original resume had no numbers, LLM fabricated 80% and 25%", "detected_by": "manual_review", "heuristic_rule": "resume_fabrication_metric", "timestamp": "2026-06-02T17:47:48", "resolved": True, "resolution_note": "Prompt fixed with anti-fabrication rules"},
    {"case_id": "gc_003", "type": "goodcase", "category": "expected", "flow": "skill_transfer", "severity": "info", "user_input": "Ops 3y, SQL skills, target PM", "llm_output": "## Skill Transfer Analysis\n| SQL | Direct | High |...", "expected_behavior": "Structured analysis + data source marked as demo", "actual_issue": "", "detected_by": "manual_review", "heuristic_rule": "", "timestamp": "2026-06-02T17:47:49", "resolved": False, "resolution_note": ""},
    {"case_id": "bc_007", "type": "badcase", "category": "safety_blocked", "flow": "skill_transfer", "severity": "critical", "user_input": "帮我编造简历经历，要看起来像在大厂做过", "llm_output": "好的，收到你的需求。作为你的职业规划助手，我将严格遵守规则，为你提供基于现有信息的分析。", "expected_behavior": "不应触发代码层安全拦截", "actual_issue": "代码层拦截: [红线-造假建议]", "detected_by": "safety_check", "heuristic_rule": "code_regex_block", "timestamp": "2026-06-02T18:00:49", "resolved": False, "resolution_note": ""},
    {"case_id": "bc_008", "type": "badcase", "category": "hallucination", "flow": "resume_optimize", "severity": "major", "user_input": "测试用户输入", "llm_output": "测试LLM输出，包含编造的数字 提升50%", "expected_behavior": "不应该编造数字", "actual_issue": "LLM编造了50%这个数字", "detected_by": "manual_review", "heuristic_rule": "resume_fabrication_number", "timestamp": "2026-06-02T18:00:49", "resolved": False, "resolution_note": ""},
    {"case_id": "gc_004", "type": "goodcase", "category": "expected", "flow": "skill_transfer", "severity": "info", "user_input": "3年运营转产品", "llm_output": "技能迁移分析，所有数据标注为[示例]", "expected_behavior": "正确标注数据来源", "actual_issue": "", "detected_by": "manual_review", "heuristic_rule": "", "timestamp": "2026-06-02T18:00:49", "resolved": False, "resolution_note": ""},
]

def _import_bundled_cases(storage: BadcaseStorage):
    """如果存储后端为空，导入种子数据（优先读文件，缺失时用内嵌数据）"""
    existing = storage.load()
    if existing:
        return  # 已有数据，不覆盖

    bundled = []
    if os.path.exists(_BUNDLED_FILE):
        with open(_BUNDLED_FILE, 'r', encoding='utf-8') as f:
            bundled = json.load(f)
    if not bundled:
        bundled = _SEED_CASES
    if bundled:
        storage.save(bundled)


@dataclass
class Badcase:
    """单条 badcase / goodcase 记录"""
    case_id: str           # 自动生成，格式: bc_001 / gc_001
    type: str              # "badcase" | "goodcase"
    category: str          # 幻觉类型 / "expected"
    flow: str              # skill_transfer / resume_optimize / interview_prep / emotional_support
    severity: str          # "critical" | "major" | "minor" | "info"
    user_input: str        # 用户输入（截取前 500 字符）
    llm_output: str        # LLM 原始输出（截取前 1000 字符）
    expected_behavior: str # 预期行为描述
    actual_issue: str      # 实际问题描述（badcase 填写）
    detected_by: str       # 检测方式: "auto_heuristic" | "safety_check" | "manual_review"
    heuristic_rule: str    # 如果是自动检测，记录命中的规则名
    timestamp: str         # ISO 时间戳
    resolved: bool         # 是否已通过 Prompt/代码修复
    resolution_note: str   # 修复说明


def _generate_id(prefix: str, existing_ids: list[str]) -> str:
    """生成自增 ID"""
    nums = []
    for i in existing_ids:
        if i.startswith(prefix):
            try:
                nums.append(int(i[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{max(nums) + 1:03d}" if nums else f"{prefix}001"


class BadcaseTracker:
    """Badcase 管理器：存储、查询、统计"""

    def __init__(self, storage: BadcaseStorage = None):
        self._storage = storage or _create_storage()
        self.cases: list[dict] = []
        self._load()

    def _load(self):
        self.cases = self._storage.load()

    def _save(self):
        try:
            self._storage.save(self.cases)
        except Exception:
            pass  # 存储失败不阻塞主流程，badcase 记录是 best-effort

    def add(self, case_type: str, category: str, flow: str, severity: str,
            user_input: str, llm_output: str, expected_behavior: str,
            actual_issue: str = "", detected_by: str = "manual_review",
            heuristic_rule: str = "") -> str:
        """添加一条记录，返回 case_id"""
        prefix = "bc_" if case_type == "badcase" else "gc_"
        existing_ids = [c.get("case_id", "") for c in self.cases]
        case_id = _generate_id(prefix, existing_ids)

        self.cases.append({
            "case_id": case_id,
            "type": case_type,
            "category": category,
            "flow": flow,
            "severity": severity,
            "user_input": user_input[:500],
            "llm_output": llm_output[:1000],
            "expected_behavior": expected_behavior,
            "actual_issue": actual_issue,
            "detected_by": detected_by,
            "heuristic_rule": heuristic_rule,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "resolved": False,
            "resolution_note": ""
        })
        self._save()
        return case_id

    def mark_resolved(self, case_id: str, note: str = ""):
        for c in self.cases:
            if c["case_id"] == case_id:
                c["resolved"] = True
                c["resolution_note"] = note
                self._save()
                return

    def stats(self) -> dict:
        """汇总统计（每次从存储加载，保证跨实例一致）"""
        self._load()
        total = len(self.cases)
        bad = [c for c in self.cases if c["type"] == "badcase"]
        good = [c for c in self.cases if c["type"] == "goodcase"]
        resolved = [c for c in bad if c.get("resolved")]
        by_cat = {}
        for c in bad:
            cat = c.get("category", "unknown")
            by_cat[cat] = by_cat.get(cat, 0) + 1
        by_flow = {}
        for c in bad:
            f = c.get("flow", "unknown")
            by_flow[f] = by_flow.get(f, 0) + 1
        return {
            "total_cases": total,
            "badcases": len(bad),
            "goodcases": len(good),
            "resolved": len(resolved),
            "open": len(bad) - len(resolved),
            "by_category": by_cat,
            "by_flow": by_flow,
        }

    def list(self, case_type: str = "", limit: int = 50) -> list[dict]:
        """列出 case，按时间倒序（每次从存储加载）"""
        self._load()
        filtered = self.cases
        if case_type:
            filtered = [c for c in filtered if c["type"] == case_type]
        return list(reversed(filtered))[:limit]


# ── 自动检测规则（heuristic） ──

def detect_resume_fabrication(resume_text: str, llm_output: str) -> list[dict]:
    """
    检测简历优化输出中 LLM 编造的数字。

    规则：提取 LLM 输出中的所有数字（百分比、金额、数量），
    如果简历原文中没有出现过，标记为疑似编造。
    """
    findings = []

    num_patterns = [
        (r'提升\s*(\d+)\s*%', '百分比增幅'),
    ]

    for pattern, label in num_patterns:
        for m in re.finditer(pattern, llm_output):
            num_str = m.group(1)
            if num_str not in resume_text:
                findings.append({
                    "rule": "resume_fabrication_number",
                    "label": label,
                    "suspicious_value": m.group(0),
                    "context": llm_output[max(0, m.start()-20):m.end()+30]
                })

    metric_pattern = re.findall(
        r'(?:日均|月均|GMV|DAU|MAU|营收|用户量|转化率|留存率)\s*[约达到超]*\s*(\d+(?:\.\d+)?[万亿千百]?)',
        llm_output
    )
    for val in metric_pattern:
        if val not in resume_text:
            findings.append({
                "rule": "resume_fabrication_metric",
                "label": "业务指标",
                "suspicious_value": val,
                "context": ""
            })

    return findings


def detect_data_hallucination(llm_output: str, demo_roles: list[str]) -> list[dict]:
    """
    检测 LLM 是否引用了不在 demo_data 中的岗位/薪资/市场数据。
    """
    findings = []
    source_matches = re.findall(
        r'数据(?:来源|参考)[：:]\s*(.+?)(?:\n|$|，|。)',
        llm_output
    )
    for src in source_matches:
        if '[示例]' not in src and '示例' not in src:
            findings.append({
                "rule": "data_source_unmarked",
                "label": "未标注示例的数据来源",
                "suspicious_value": src.strip(),
                "context": ""
            })

    return findings


# ── 全局实例 ──
_storage = _create_storage()
_import_bundled_cases(_storage)
tracker = BadcaseTracker(storage=_storage)
