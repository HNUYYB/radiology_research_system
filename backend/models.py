from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()


def _fmt_dt(dt):
    """格式化 datetime 为带 UTC 时区后缀的 ISO 字符串，确保前端 JS 能正确解析"""
    if dt is None:
        return None
    return dt.isoformat() + '+00:00'

class User(db.Model):
    """用户模型"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 用户类型：student, expert, admin
    user_type = db.Column(db.String(20), default='student')

    # 学生相关信息
    grade = db.Column(db.String(20))  # 研一、研二、研三、博一、博二、博三、博四及以上
    specialty = db.Column(db.String(100))  # 亚专业方向

    # 用户级 LLM 配置（每个人有自己的 API Key 和提供商选择）
    llm_provider = db.Column(db.String(20), default='longcat')  # 选择的提供商 key
    llm_api_key = db.Column(db.String(200))  # 用户自己的 API Key（加密存储）

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'user_type': self.user_type,
            'grade': self.grade,
            'specialty': self.specialty,
            'llm_provider': self.llm_provider,
            'llm_api_key': self.llm_api_key,
            'created_at': _fmt_dt(self.created_at)
        }

class StudentProfile(db.Model):
    """学生画像模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # 基本信息
    grade = db.Column(db.String(20))  # 研一、研二、研三、博一、博二、博三、博四及以上
    specialty = db.Column(db.String(100))  # 亚专业方向

    # 研究条件
    available_resources = db.Column(db.Text)  # JSON格式存储
    case_scale = db.Column(db.String(50))  # 病例规模
    follow_up_available = db.Column(db.Boolean, default=False)
    gold_standard_available = db.Column(db.Boolean, default=False)

    # 技能基础
    statistical_background = db.Column(db.String(50))  # 统计基础水平
    ai_background = db.Column(db.String(50))  # AI基础水平

    # 时间约束
    time_constraint = db.Column(db.String(50))  # 时间限制
    target_journal_level = db.Column(db.String(50))  # 目标期刊层级

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='profile')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'grade': self.grade,
            'specialty': self.specialty,
            'available_resources': json.loads(self.available_resources) if self.available_resources else {},
            'case_scale': self.case_scale,
            'follow_up_available': self.follow_up_available,
            'gold_standard_available': self.gold_standard_available,
            'statistical_background': self.statistical_background,
            'ai_background': self.ai_background,
            'time_constraint': self.time_constraint,
            'target_journal_level': self.target_journal_level,
            'created_at': _fmt_dt(self.created_at),
            'updated_at': _fmt_dt(self.updated_at)
        }

class ResearchTask(db.Model):
    """标准化研究任务模型"""
    id = db.Column(db.Integer, primary_key=True)
    task_code = db.Column(db.String(50), unique=True, nullable=False)
    specialty = db.Column(db.String(100))  # 亚专科
    task_type = db.Column(db.String(50))  # 任务类型

    # 任务输入信息
    student_background = db.Column(db.Text)
    direction_info = db.Column(db.Text)
    resource_conditions = db.Column(db.Text)
    expected_timeline = db.Column(db.String(100))
    existing_concepts = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'task_code': self.task_code,
            'specialty': self.specialty,
            'task_type': self.task_type,
            'student_background': self.student_background,
            'direction_info': self.direction_info,
            'resource_conditions': self.resource_conditions,
            'expected_timeline': self.expected_timeline,
            'existing_concepts': self.existing_concepts,
            'created_at': _fmt_dt(self.created_at)
        }

class ResearchPlan(db.Model):
    """研究方案模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('research_task.id'), nullable=True)

    # 方案基本信息
    title = db.Column(db.String(200))
    input_type = db.Column(db.String(50))  # multi_agent, single_model, student_original

    # 方案内容（JSON格式存储）
    content = db.Column(db.Text)  # 完整的方案内容

    # 系统生成信息
    problem_definition = db.Column(db.Text)
    evidence_summary = db.Column(db.Text)
    critique_feedback = db.Column(db.Text)
    comparison_data = db.Column(db.Text)  # 双方案对比数据（JSON）
    evidence_pool_data = db.Column(db.Text)  # 证据池统计（JSON）

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='research_plans')
    task = db.relationship('ResearchTask', backref='research_plans')

    def to_dict(self):
        def _parse_json_field(value):
            """安全解析 JSON 字符串字段，失败时返回原始字符串"""
            if not value:
                return {} if value is None else value
            if isinstance(value, (dict, list)):
                return value
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # 尝试清理非法 Unicode 代理对后再解析
                import re as _re
                cleaned = _re.sub(r'[\ud800-\udfff]', '�', value)
                try:
                    return json.loads(cleaned)
                except (json.JSONDecodeError, TypeError):
                    return value  # 返回原始字符串

        return {
            'id': self.id,
            'user_id': self.user_id,
            'task_id': self.task_id,
            'title': self.title,
            'input_type': self.input_type,
            'content': _parse_json_field(self.content) or {},
            'problem_definition': _parse_json_field(self.problem_definition),
            'evidence_summary': _parse_json_field(self.evidence_summary),
            'critique_feedback': _parse_json_field(self.critique_feedback),
            'comparison_data': _parse_json_field(self.comparison_data),
            'evidence_pool_data': _parse_json_field(self.evidence_pool_data),
            'created_at': _fmt_dt(self.created_at),
            'updated_at': _fmt_dt(self.updated_at)
        }

    def get_student_profile_data(self):
        """获取与学生方案相关的画像数据"""
        try:
            # 尝试从用户关联的画像获取
            if self.user and hasattr(self.user, 'student_profile') and self.user.student_profile:
                profile = self.user.student_profile[0]  # 获取第一个画像
                return {
                    'grade': profile.grade or self.user.grade,
                    'specialty': profile.specialty or self.user.specialty,
                    'available_resources': json.loads(profile.available_resources) if profile.available_resources else [],
                    'case_scale': profile.case_scale,
                    'follow_up_available': profile.follow_up_available,
                    'gold_standard_available': profile.gold_standard_available,
                    'statistical_background': profile.statistical_background,
                    'ai_background': profile.ai_background,
                    'target_journal_level': profile.target_journal_level
                }
            else:
                # 从用户基本信息获取
                return {
                    'grade': self.user.grade if self.user else '',
                    'specialty': self.user.specialty if self.user else '',
                    'available_resources': [],
                    'case_scale': '',
                    'follow_up_available': False,
                    'gold_standard_available': False,
                    'statistical_background': '',
                    'ai_background': '',
                    'target_journal_level': ''
                }
        except Exception as e:
            print(f"获取学生画像数据失败: {str(e)}")
            return {}

class BlindReview(db.Model):
    """盲评模型"""
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('research_plan.id'), nullable=False)
    expert_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # 主要评分
    total_score = db.Column(db.Float)
    clinical_significance = db.Column(db.Float)
    innovation = db.Column(db.Float)
    relevance = db.Column(db.Float)
    feasibility = db.Column(db.Float)
    methodology = db.Column(db.Float)
    publication_potential = db.Column(db.Float)

    # 次要评分
    data_accessibility = db.Column(db.Float)
    endpoint_definability = db.Column(db.Float)
    statistical_closure = db.Column(db.Float)
    structure_completeness = db.Column(db.Float)
    personalization_match = db.Column(db.Float)
    proposal_acceptability = db.Column(db.Boolean)
    supervisor_adoption_willingness = db.Column(db.Boolean)
    risk_warning_ability = db.Column(db.Float)
    empty_expression_ratio = db.Column(db.Float)

    # 评语
    comments = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    plan = db.relationship('ResearchPlan', backref='reviews')
    expert = db.relationship('User', backref='reviews')

class PlanVersion(db.Model):
    """方案版本历史"""
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('research_plan.id'), nullable=False)
    version_num = db.Column(db.Integer, nullable=False)  # 版本号，从1开始
    content = db.Column(db.Text)  # 完整方案内容 JSON
    change_summary = db.Column(db.Text)  # 变更说明
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    plan = db.relationship('ResearchPlan', backref='versions')

    def to_dict(self):
        return {
            'id': self.id,
            'plan_id': self.plan_id,
            'version_num': self.version_num,
            'content': json.loads(self.content) if self.content else {},
            'change_summary': self.change_summary,
            'created_at': _fmt_dt(self.created_at)
        }


class PlanShare(db.Model):
    """方案分享链接"""
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('research_plan.id'), nullable=False)
    share_code = db.Column(db.String(32), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    password_hash = db.Column(db.String(120))  # 可选密码
    expires_at = db.Column(db.DateTime)  # 过期时间
    view_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    plan = db.relationship('ResearchPlan', backref='shares')
    creator = db.relationship('User', backref='shares')

    def to_dict(self):
        return {
            'id': self.id,
            'plan_id': self.plan_id,
            'share_code': self.share_code,
            'created_by': self.created_by,
            'expires_at': _fmt_dt(self.expires_at),
            'view_count': self.view_count,
            'created_at': _fmt_dt(self.created_at)
        }


class SystemLog(db.Model):
    """系统日志模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(100))
    module = db.Column(db.String(50))
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='logs')