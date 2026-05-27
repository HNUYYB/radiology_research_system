"""
研究方案路由测试
"""
import pytest
import json


class TestResearchPlans:
    """研究方案接口测试"""

    def test_get_plans_authenticated(self, client, sample_user, auth_headers):
        """认证用户可获取方案列表"""
        response = client.get(f'/api/research/plans?user_id={sample_user.id}',
            headers=auth_headers)
        assert response.status_code == 200

    def test_get_plans_unauthorized(self, client):
        """未认证不能获取方案列表"""
        response = client.get('/api/research/plans')
        assert response.status_code == 401

    def test_get_plan_not_found(self, client, auth_headers):
        """获取不存在的方案应返回 404"""
        response = client.get('/api/research/plan/99999', headers=auth_headers)
        assert response.status_code == 404

    def test_get_task_types(self, client):
        """获取任务类型无需认证"""
        response = client.get('/api/research/task-types')
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert '方向模糊型' in data['task_types']


class TestStandardTasks:
    """标准化任务接口测试"""

    def test_create_task_admin_only(self, client, admin_auth_headers):
        """管理员可创建标准化任务"""
        response = client.post('/api/research/task',
            json={
                'specialty': '胸部',
                'task_type': '方向模糊型',
                'student_background': '研一学生'
            },
            headers=admin_auth_headers
        )
        assert response.status_code == 201

    def test_create_task_forbidden_for_student(self, client, auth_headers):
        """学生不能创建标准化任务"""
        response = client.post('/api/research/task',
            json={'specialty': '胸部'},
            headers=auth_headers
        )
        assert response.status_code == 403

    def test_get_tasks(self, client, auth_headers):
        """获取标准化任务列表"""
        response = client.get('/api/research/tasks', headers=auth_headers)
        assert response.status_code == 200


class TestGeneratePlan:
    """方案生成接口测试"""

    def test_generate_plan_requires_auth(self, client):
        """未认证不能生成方案"""
        response = client.post('/api/multi-agent/generate-plan', json={
            'user_id': 1,
            'student_input': 'test'
        })
        assert response.status_code == 401

    def test_generate_plan_missing_params(self, client, auth_headers):
        """缺少参数应返回 400"""
        response = client.post('/api/multi-agent/generate-plan',
            json={},
            headers=auth_headers
        )
        assert response.status_code == 400

    def test_generate_plan_non_radiology_input(self, client, sample_user, auth_headers):
        """非放射学输入应返回 422"""
        response = client.post('/api/multi-agent/generate-plan',
            json={
                'user_id': sample_user.id,
                'student_input': '我想研究股票市场的走势预测'
            },
            headers=auth_headers
        )
        assert response.status_code == 422

    def test_generate_plan_admin_can_create_for_others(self, client, admin_auth_headers):
        """管理员可以为他人生成方案（任务会被接受）"""
        response = client.post('/api/multi-agent/generate-plan',
            json={
                'user_id': 99999,
                'student_input': '基于CT影像的肺结节检测'
            },
            headers=admin_auth_headers
        )
        # admin 可以为他人生成，任务被接受（202）
        #  pipeline 中会因为用户不存在而失败，但请求本身被接受
        assert response.status_code == 202
