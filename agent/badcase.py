"""
Badcase / Goodcase 追踪系统。

在 LLM 容易产生幻觉的关键节点做自动检测 + 人工标注，
持续积累 case 用于 Prompt 迭代和质量监控。

幻觉高发区：
  1. 简历优化 — LLM 编造数字（"提升30%""日均10万+"）
  2. 综合分析 — 引用不在 demo_data 中的薪资/市场数据
  3. 安全检查 — LLM 漏过的隐含风险
"""
import json, os, re, time
from dataclasses import dataclass, field
from typing import Optional

STORAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'badcases.json')
# FC 函数计算代码目录只读，自动切到 /tmp
if not os.access(os.path.dirname(STORAGE_FILE), os.W_OK):
    STORAGE_FILE = '/tmp/badcases.json'


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

    def __init__(self, storage_path: str = STORAGE_FILE):
        self.storage_path = storage_path
        self.cases: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                self.cases = json.load(f)

    def _save(self):
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.cases, f, ensure_ascii=False, indent=2)

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
        """汇总统计（每次从磁盘加载，保证跨进程一致）"""
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
        """列出 case，按时间倒序（每次从磁盘加载）"""
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

    # 提取数字模式
    num_patterns = [
        (r'提升\s*(\d+)\s*%', '百分比增幅'),
    ]

    for pattern, label in num_patterns:
        for m in re.finditer(pattern, llm_output):
            num_str = m.group(1)
            # 检查原文中是否出现该数字
            if num_str not in resume_text:
                findings.append({
                    "rule": "resume_fabrication_number",
                    "label": label,
                    "suspicious_value": m.group(0),
                    "context": llm_output[max(0, m.start()-20):m.end()+30]
                })

    # 检测具体数值（日均、月活、GMV 等）
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
    # 检测「数据来源：XXX」但不含 [示例] 标记
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


# 全局实例
tracker = BadcaseTracker()
