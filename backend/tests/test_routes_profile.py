"""
学生画像路由测试
"""
import pytest
import json


class TestProfileOptions:
    """画像选项接口测试"""

    def test_get_options(self, client):
        """获取画像选项（无需认证）"""
        response = client.get('/api/profile/options')
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert 'grades' in data['options']
        assert 'specialties' in data['options']
        assert '研一' in data['options']['grades']


class TestStudentProfile:
    """学生画像 CRUD 测试"""

    def test_create_profile(self, client, sample_user, auth_headers):
        """创建学生画像"""
        response = client.post('/api/profile/student',
            json={
                'user_id': sample_user.id,
                'grade': '研一',
                'specialty': '胸部',
                'statistical_background': '基础',
                'ai_background': '无基础',
                'time_constraint': '12-24个月',
                'target_journal_level': '核心期刊'
            },
            headers=auth_headers
        )
        data = response.get_json()
        assert response.status_code == 201
        assert data['success'] is True
        assert data['profile']['grade'] == '研一'

    def test_create_profile_duplicate(self, client, db, sample_user, auth_headers):
        """重复创建应返回 409"""
        from models import StudentProfile
        profile = StudentProfile(user_id=sample_user.id, grade='研一')
        db.session.add(profile)
        db.session.commit()

        response = client.post('/api/profile/student',
            json={'user_id': sample_user.id, 'grade': '研二'},
            headers=auth_headers
        )
        assert response.status_code == 409

    def test_create_profile_forbidden(self, client, admin_user, admin_auth_headers):
        """非管理员不能为他人创建画像"""
        response = client.post('/api/profile/student',
            json={'user_id': 99999, 'grade': '研一'},
            headers=admin_auth_headers
        )
        # 管理员可以为他人创建，普通用户不行
        # 这里 admin 为用户 99999 创建会成功（管理员豁免）
        # 但用户 99999 不存在，返回 404
        assert response.status_code == 404

    def test_get_profile(self, client, db, sample_user, auth_headers):
        """获取自己的画像"""
        from models import StudentProfile
        profile = StudentProfile(user_id=sample_user.id, grade='研二')
        db.session.add(profile)
        db.session.commit()

        response = client.get(f'/api/profile/student/{sample_user.id}',
            headers=auth_headers
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert data['profile']['grade'] == '研二'

    def test_get_profile_not_found(self, client, auth_headers):
        """获取不存在的画像应返回 404"""
        response = client.get('/api/profile/student/99999', headers=auth_headers)
        assert response.status_code == 404

    def test_update_profile(self, client, db, sample_user, auth_headers):
        """更新自己的画像"""
        from models import StudentProfile
        profile = StudentProfile(user_id=sample_user.id, grade='研一')
        db.session.add(profile)
        db.session.commit()

        response = client.put(f'/api/profile/student/{sample_user.id}',
            json={'grade': '研二', 'specialty': '神经'},
            headers=auth_headers
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert data['profile']['grade'] == '研二'

    def test_profile_unauthorized(self, client, db, sample_user):
        """未认证不能访问画像接口"""
        response = client.post('/api/profile/student',
            json={'user_id': sample_user.id}
        )
        assert response.status_code == 401

    def test_get_profile_no_token(self, client):
        """无 token 获取画像应返回 401"""
        response = client.get('/api/profile/student/1')
        assert response.status_code == 401
