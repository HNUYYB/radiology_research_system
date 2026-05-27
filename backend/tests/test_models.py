"""
数据库模型测试
"""
import pytest
from werkzeug.security import generate_password_hash


class TestUserModel:
    """用户模型测试"""

    def test_create_user(self, db):
        """创建用户"""
        from models import User
        user = User(
            username='modeltest',
            email='model@test.com',
            password_hash=generate_password_hash('testpass'),
            user_type='student'
        )
        db.session.add(user)
        db.session.commit()

        assert user.id is not None
        assert user.username == 'modeltest'
        assert user.user_type == 'student'

    def test_user_to_dict(self, db):
        """用户序列化"""
        from models import User
        user = User(
            username='dicttest',
            email='dict@test.com',
            password_hash=generate_password_hash('testpass'),
            user_type='expert'
        )
        db.session.add(user)
        db.session.commit()

        user_dict = user.to_dict()
        assert 'id' in user_dict
        assert user_dict['username'] == 'dicttest'
        assert user_dict['user_type'] == 'expert'

    def test_user_unique_username(self, db):
        """用户名唯一约束"""
        from models import User
        user1 = User(
            username='unique',
            email='u1@test.com',
            password_hash=generate_password_hash('pass1')
        )
        user2 = User(
            username='unique',
            email='u2@test.com',
            password_hash=generate_password_hash('pass2')
        )
        db.session.add(user1)
        db.session.commit()

        db.session.add(user2)
        with pytest.raises(Exception):
            db.session.commit()


class TestStudentProfile:
    """学生画像模型测试"""

    def test_create_profile(self, db, sample_user):
        """创建学生画像"""
        from models import StudentProfile
        profile = StudentProfile(
            user_id=sample_user.id,
            grade='研二',
            specialty='神经',
            case_scale='中型(50-200例)',
            statistical_background='中等',
            ai_background='基础',
            time_constraint='12-24个月',
            target_journal_level='SCI中等'
        )
        db.session.add(profile)
        db.session.commit()

        assert profile.id is not None
        assert profile.user_id == sample_user.id

    def test_profile_to_dict(self, db, sample_user):
        """画像序列化"""
        from models import StudentProfile
        profile = StudentProfile(
            user_id=sample_user.id,
            grade='研一',
            specialty='胸部'
        )
        db.session.add(profile)
        db.session.commit()

        profile_dict = profile.to_dict()
        assert 'id' in profile_dict
        assert profile_dict['grade'] == '研一'

    def test_profile_user_relationship(self, db, sample_user):
        """画像与用户关联"""
        from models import StudentProfile
        profile = StudentProfile(
            user_id=sample_user.id,
            grade='研三'
        )
        db.session.add(profile)
        db.session.commit()

        assert profile.user.id == sample_user.id


class TestResearchPlan:
    """研究方案模型测试"""

    def test_create_plan(self, db, sample_user):
        """创建研究方案"""
        from models import ResearchPlan
        plan = ResearchPlan(
            user_id=sample_user.id,
            title='基于深度学习的肺结节检测',
            input_type='multi_agent',
            content='{"title": "测试方案"}'
        )
        db.session.add(plan)
        db.session.commit()

        assert plan.id is not None
        assert plan.title == '基于深度学习的肺结节检测'
        assert plan.user_id == sample_user.id

    def test_plan_to_dict(self, db, sample_user):
        """方案序列化"""
        from models import ResearchPlan
        plan = ResearchPlan(
            user_id=sample_user.id,
            title='测试方案',
            input_type='multi_agent',
            content='{"title": "test"}'
        )
        db.session.add(plan)
        db.session.commit()

        plan_dict = plan.to_dict()
        assert plan_dict['title'] == '测试方案'
        assert plan_dict['input_type'] == 'multi_agent'


class TestBlindReview:
    """盲审模型测试"""

    def test_create_review(self, db, sample_user, expert_user):
        """创建评审"""
        from models import ResearchPlan, BlindReview

        # 先创建一个方案
        plan = ResearchPlan(
            user_id=sample_user.id,
            title='待评审方案',
            input_type='multi_agent',
            content='{}'
        )
        db.session.add(plan)
        db.session.commit()

        # 专家评审
        review = BlindReview(
            plan_id=plan.id,
            expert_id=expert_user.id,
            total_score=4.2,
            clinical_significance=4.0,
            innovation=4.5,
            relevance=4.0,
            feasibility=4.0,
            methodology=4.5,
            publication_potential=4.0,
            comments='方案整体不错'
        )
        db.session.add(review)
        db.session.commit()

        assert review.id is not None
        assert review.total_score == 4.2
        assert review.plan_id == plan.id
        assert review.expert_id == expert_user.id
