"""
Mock data for AI Career Agent demo.
All data is realistic but synthetic — never use real user data in demos.
"""
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class UserProfile:
    name: str
    current_role: str
    years_of_experience: int
    industry: str
    skills: list[str]
    education: str
    salary_range: str
    target_role: Optional[str] = None
    priorities: list[str] = field(default_factory=list)  # salary, growth, wlb, stability
    emotional_state: str = "neutral"  # neutral, anxious, confident, confused

# ── Demo user profiles ──

USER_XIAOMING = UserProfile(
    name="小明",
    current_role="运营专员",
    years_of_experience=3,
    industry="互联网/电商",
    skills=["数据分析(SQL)", "活动策划", "用户运营", "公众号写作", "基础Python"],
    education="本科-市场营销",
    salary_range="10K-15K",
    target_role="产品经理",
    priorities=["成长空间", "薪资", "稳定性"]
)

USER_LILI = UserProfile(
    name="莉莉",
    current_role="Java后端开发",
    years_of_experience=5,
    industry="金融科技",
    skills=["Java", "Spring Boot", "MySQL", "微服务架构", "Redis", "系统设计"],
    education="硕士-计算机科学",
    salary_range="35K-45K",
    target_role="技术管理/架构师",
    priorities=["薪资", "稳定性", "WLB"]
)

USER_AQIANG = UserProfile(
    name="阿强",
    current_role="销售经理",
    years_of_experience=7,
    industry="企业服务/SaaS",
    skills=["B2B销售", "客户关系管理", "团队管理(5人)", "方案演示", "合同谈判"],
    education="本科-工商管理",
    salary_range="25K-35K",
    target_role=None,  # 迷茫中，不知道想做什么
    priorities=["不清楚", "想找更有意义的工作"]
)

# ── Mock job market data (simulating API responses) ──
# ⚠️ Design note: This data comes from structured API, NOT from LLM generation.
# Reason: Market data is deterministic — using LLM risks hallucinated numbers.

JOB_MARKET_DATA = {
    "产品经理": {
        "avg_salary": "18K-30K",
        "demand_trend": "↑ 增长中（2026 Q1同比+23%）",
        "top_cities": ["北京", "深圳", "上海", "杭州"],
        "top_required_skills": ["需求分析", "用户研究", "数据分析", "SQL", "原型设计", "项目管理"],
        "entry_barrier": "中等（接受运营/技术/设计转岗）",
        "data_source": "Boss直聘 2026Q1报告",
        "data_updated": "2026-05-28"
    },
    "技术管理/架构师": {
        "avg_salary": "50K-80K",
        "demand_trend": "→ 稳定",
        "top_cities": ["北京", "上海", "深圳", "杭州"],
        "top_required_skills": ["系统架构设计", "技术团队管理", "跨部门协作", "技术规划", "云原生"],
        "entry_barrier": "高（通常需要8年+技术经验+管理经验）",
        "data_source": "脉脉 2026Q1报告",
        "data_updated": "2026-05-28"
    },
    "AI产品经理": {
        "avg_salary": "30K-60K",
        "demand_trend": "↑↑ 高速增长（2026 Q1同比增8.7倍）",
        "top_cities": ["北京", "上海", "深圳", "杭州", "广州"],
        "top_required_skills": ["AI技术理解", "大模型应用", "Prompt工程", "数据分析", "产品设计"],
        "entry_barrier": "中高（接受技术/产品/运营转岗，但需AI认知）",
        "data_source": "脉脉 2026春招报告",
        "data_updated": "2026-05-28"
    },
    "运营总监": {
        "avg_salary": "35K-55K",
        "demand_trend": "→ 稳定",
        "top_cities": ["北京", "上海", "深圳", "杭州"],
        "top_required_skills": ["团队管理", "增长策略", "数据驱动决策", "预算管理", "跨部门协调"],
        "entry_barrier": "高（通常需要5年+运营经验+管理经验）",
        "data_source": "Boss直聘 2026Q1报告",
        "data_updated": "2026-05-28"
    },
    "数据分析师": {
        "avg_salary": "15K-28K",
        "demand_trend": "↑ 增长（2026 Q1同比+18%）",
        "top_cities": ["北京", "上海", "深圳", "杭州", "广州"],
        "top_required_skills": ["SQL", "Python", "数据可视化", "统计学", "业务分析", "Tableau/PowerBI"],
        "entry_barrier": "中低（接受理工科/商科转岗，需数据分析项目经验）",
        "data_source": "Boss直聘 2026Q1报告",
        "data_updated": "2026-05-28"
    },
    "前端开发": {
        "avg_salary": "18K-35K",
        "demand_trend": "→ 稳定",
        "top_cities": ["北京", "上海", "深圳", "杭州", "广州"],
        "top_required_skills": ["React/Vue", "TypeScript", "CSS", "Node.js", "工程化"],
        "entry_barrier": "中（接受培训班/自学转行，但竞争激烈）",
        "data_source": "Boss直聘 2026Q1报告",
        "data_updated": "2026-05-28"
    },
    "后端开发": {
        "avg_salary": "20K-40K",
        "demand_trend": "↑ 增长",
        "top_cities": ["北京", "上海", "深圳", "杭州", "广州"],
        "top_required_skills": ["Java/Go/Python", "数据库", "微服务", "中间件", "系统设计"],
        "entry_barrier": "中（需计算机基础，接受相关专业转行）",
        "data_source": "Boss直聘 2026Q1报告",
        "data_updated": "2026-05-28"
    },
    "AI工程师": {
        "avg_salary": "40K-80K",
        "demand_trend": "↑↑ 高速增长",
        "top_cities": ["北京", "上海", "深圳", "杭州"],
        "top_required_skills": ["Python", "PyTorch/TensorFlow", "大模型微调", "RAG", "向量数据库"],
        "entry_barrier": "高（通常需要硕士+相关经验，但需求缺口大）",
        "data_source": "脉脉 2026春招报告",
        "data_updated": "2026-05-28"
    },
    "UI/UX设计师": {
        "avg_salary": "15K-30K",
        "demand_trend": "→ 稳定",
        "top_cities": ["北京", "上海", "深圳", "杭州"],
        "top_required_skills": ["Figma", "用户研究", "交互设计", "设计系统", "可用性测试"],
        "entry_barrier": "中（作品集是关键，接受艺术/心理学等背景转行）",
        "data_source": "Boss直聘 2026Q1报告",
        "data_updated": "2026-05-28"
    },
    "测试开发": {
        "avg_salary": "20K-38K",
        "demand_trend": "↑ 增长",
        "top_cities": ["北京", "上海", "深圳", "杭州"],
        "top_required_skills": ["自动化测试", "Python/Java", "CI/CD", "性能测试", "测试框架搭建"],
        "entry_barrier": "中（接受开发/运维转岗）",
        "data_source": "Boss直聘 2026Q1报告",
        "data_updated": "2026-05-28"
    },
}

# ── Mock skill graph (simulating skill adjacency/transferability data) ──
# ⚠️ Design note: Also from structured API, not LLM.
# Reason: Skill relationships are graph data — use a graph DB/API, not LLM reasoning.

SKILL_TRANSFER_MAP = {
    # 运营类技能
    "数据分析(SQL)": {
        "transferable_to": ["产品经理", "数据分析师", "增长运营"],
        "transferability_score": 0.85,
        "gap_note": "从运营分析到产品决策分析，需要补充用户研究维度"
    },
    "活动策划": {
        "transferable_to": ["产品经理", "市场经理"],
        "transferability_score": 0.6,
        "gap_note": "活动策划的项目管理能力可迁移，但需要补充需求分析和产品设计思维"
    },
    "用户运营": {
        "transferable_to": ["产品经理", "用户研究", "增长产品"],
        "transferability_score": 0.8,
        "gap_note": "用户运营对用户的理解直接可迁移，是转产品最强的基础技能"
    },
    "公众号写作": {
        "transferable_to": ["内容运营", "内容产品"],
        "transferability_score": 0.4,
        "gap_note": "写作能力是通用技能，但对产品经理岗位帮助有限"
    },
    "基础Python": {
        "transferable_to": ["产品经理(技术方向)", "数据分析师", "AI产品经理"],
        "transferability_score": 0.7,
        "gap_note": "Python基础对技术产品方向加分，建议加深数据分析相关库的使用"
    },
    "增长策略": {
        "transferable_to": ["产品经理", "市场总监", "运营总监"],
        "transferability_score": 0.75,
        "gap_note": "增长思维对产品和市场方向高度可迁移，需补充对应领域专业工具"
    },
    # 开发类技能
    "Java": {
        "transferable_to": ["技术管理", "架构师", "后端开发", "技术产品经理"],
        "transferability_score": 0.7,
        "gap_note": "技术背景对技术管理方向是必要条件"
    },
    "Spring Boot": {
        "transferable_to": ["后端开发", "架构师"],
        "transferability_score": 0.65,
        "gap_note": "Java生态框架，对后端和架构方向直接可用"
    },
    "微服务架构": {
        "transferable_to": ["架构师", "技术管理", "后端开发"],
        "transferability_score": 0.85,
        "gap_note": "架构设计能力是高级技术岗位的核心竞争力"
    },
    "React/Vue": {
        "transferable_to": ["前端开发", "全栈开发", "技术产品经理"],
        "transferability_score": 0.7,
        "gap_note": "前端框架技能对产品方向有独特价值——理解技术边界"
    },
    "TypeScript": {
        "transferable_to": ["前端开发", "全栈开发", "后端开发(Node)"],
        "transferability_score": 0.65,
        "gap_note": "类型系统思维对代码架构的理解有帮助"
    },
    "Node.js": {
        "transferable_to": ["后端开发", "全栈开发"],
        "transferability_score": 0.6,
        "gap_note": "JS全栈能力，对中小团队尤其有价值"
    },
    "MySQL": {
        "transferable_to": ["后端开发", "数据分析师", "产品经理(数据方向)"],
        "transferability_score": 0.6,
        "gap_note": "数据库能力是技术岗位通用基础技能，但不构成差异化优势"
    },
    "Redis": {
        "transferable_to": ["后端开发", "架构师"],
        "transferability_score": 0.55,
        "gap_note": "缓存技术是后端进阶技能，对架构方向有加分"
    },
    "PyTorch/TensorFlow": {
        "transferable_to": ["AI工程师", "AI产品经理"],
        "transferability_score": 0.8,
        "gap_note": "深度学习框架是AI方向核心技能，但需结合业务场景理解"
    },
    "大模型微调": {
        "transferable_to": ["AI工程师", "AI产品经理"],
        "transferability_score": 0.9,
        "gap_note": "当前最热门技能之一，市场缺口大，但需持续跟进技术迭代"
    },
    # 管理类技能
    "团队管理(5人)": {
        "transferable_to": ["技术管理", "产品总监", "运营总监"],
        "transferability_score": 0.9,
        "gap_note": "管理经验是最普适的可迁移技能"
    },
    "项目管理": {
        "transferable_to": ["技术管理", "产品经理", "项目经理"],
        "transferability_score": 0.8,
        "gap_note": "项目推动能力对几乎所有岗位都有价值"
    },
    # 销售类技能
    "B2B销售": {
        "transferable_to": ["客户成功", "售前工程师", "解决方案架构师"],
        "transferability_score": 0.65,
        "gap_note": "客户沟通能力可迁移到客户成功或售前方向，需补充技术或行业知识"
    },
    "客户关系管理": {
        "transferable_to": ["客户成功", "产品经理", "商务拓展"],
        "transferability_score": 0.7,
        "gap_note": "对客户需求的深度理解是产品方向的核心优势"
    },
    "方案演示": {
        "transferable_to": ["售前工程师", "产品经理", "培训师"],
        "transferability_score": 0.55,
        "gap_note": "Presentation能力是通用技能，需配合专业领域知识"
    },
    # 设计类技能
    "Figma": {
        "transferable_to": ["UI/UX设计师", "产品经理"],
        "transferability_score": 0.6,
        "gap_note": "设计工具能力对产品方向和前端协作有帮助"
    },
    "用户研究": {
        "transferable_to": ["产品经理", "UI/UX设计师", "增长运营"],
        "transferability_score": 0.85,
        "gap_note": "用户研究能力是产品设计的核心，直接可迁移"
    },
    "交互设计": {
        "transferable_to": ["产品经理", "UI/UX设计师"],
        "transferability_score": 0.75,
        "gap_note": "交互思维对产品体验设计高度可迁移"
    },
}

# ── Mock resume data ──

RESUME_XIAOMING = """
小明 | 运营专员 | 3年经验 | 本科-市场营销

工作经历：
2023.06-至今 XX电商公司 运营专员
- 负责用户增长活动策划与执行，季度GMV提升15%
- 使用SQL进行用户行为分析，搭建用户分层运营体系
- 搭建公众号矩阵，累计粉丝50万
- 协调产品、设计、研发完成3次大促活动上线

2022.07-2023.05 XX科技公司 运营助理
- 协助完成日常数据报表和竞品分析
- 参与用户调研和需求整理

项目经历：
- 从0到1搭建用户标签体系，覆盖200万用户
- 用Python写脚本自动化日常数据拉取，每周节省5小时

技能：SQL(熟练) | Python(基础) | Excel(精通) | 公众号运营(精通)
"""

# ── Mock JD samples ──

JD_PRODUCT_MANAGER = """
【岗位】产品经理（中级）
【薪资】20K-35K · 14薪
【要求】
- 3年以上产品相关经验（或2年+其他岗位+1年产品经验）
- 熟练使用SQL进行数据分析
- 有用户研究/需求分析能力
- 能独立完成PRD和原型设计
- 加分项：有运营背景、懂技术、有AI产品经验
【工作内容】
- 负责电商后台核心模块的产品设计与迭代
- 基于数据分析驱动产品优化
- 协调设计、研发、测试完成需求落地
"""

JD_AI_PM = """
【岗位】AI产品经理
【薪资】35K-60K · 15薪
【要求】
- 3-5年产品经验
- 理解大模型原理（Transformer/GPT架构），不用写代码但要能看论文
- 有Prompt Engineering和RAG的实际落地经验
- 有Eval Set设计和A/B测试经验
- 加分项：有从0到1的AI产品经验
【工作内容】
- 负责AI能力在业务场景中的应用落地
- 设计AI产品的评估体系和迭代流程
- 与算法团队协作，定义模型行为规范
"""
