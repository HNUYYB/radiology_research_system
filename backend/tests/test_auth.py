"""
认证相关测试
"""
import pytest
import json


class TestRegister:
    """用户注册测试"""

    def test_register_success(self, client):
        """正常注册"""
        response = client.post('/api/auth/register', json={
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'SecurePass123',
            'user_type': 'student'
        })
        data = response.get_json()
        assert response.status_code == 201
        assert data['success'] is True
        assert data['user']['username'] == 'newuser'
        assert 'access_token' in data
        assert 'refresh_token' in data
        assert data['token_type'] == 'Bearer'

    def test_register_duplicate_username(self, client, sample_user):
        """重复用户名应返回 409"""
        response = client.post('/api/auth/register', json={
            'username': 'testuser',
            'email': 'other@example.com',
            'password': 'SecurePass123'
        })
        assert response.status_code == 409

    def test_register_missing_username(self, client):
        """缺少用户名应返回 400"""
        response = client.post('/api/auth/register', json={
            'password': 'SecurePass123'
        })
        assert response.status_code == 400

    def test_register_missing_password(self, client):
        """缺少密码应返回 400"""
        response = client.post('/api/auth/register', json={
            'username': 'nopassword'
        })
        assert response.status_code == 400

    def test_register_default_user_type(self, client):
        """默认用户类型应为 student"""
        response = client.post('/api/auth/register', json={
            'username': 'defaulttype',
            'email': 'default@example.com',
            'password': 'SecurePass123'
        })
        data = response.get_json()
        assert response.status_code == 201
        assert data['user']['user_type'] == 'student'

    def test_register_expert_user(self, client):
        """注册专家用户"""
        response = client.post('/api/auth/register', json={
            'username': 'newexpert',
            'email': 'expert_new@example.com',
            'password': 'SecurePass123',
            'user_type': 'expert'
        })
        data = response.get_json()
        assert response.status_code == 201
        assert data['user']['user_type'] == 'expert'


class TestLogin:
    """用户登录测试"""

    def test_login_success(self, client, sample_user):
        """正常登录"""
        response = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'TestPassword123'
        })
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert 'access_token' in data
        assert 'refresh_token' in data
        assert data['user']['username'] == 'testuser'

    def test_login_wrong_password(self, client, sample_user):
        """错误密码应返回 401"""
        response = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'WrongPassword'
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client):
        """不存在的用户应返回 401"""
        response = client.post('/api/auth/login', json={
            'username': 'nosuchuser',
            'password': 'SomePassword'
        })
        assert response.status_code == 401

    def test_login_missing_fields(self, client):
        """缺少字段应返回 400"""
        response = client.post('/api/auth/login', json={
            'username': 'testuser'
        })
        assert response.status_code == 400


class TestTokenRefresh:
    """Token 刷新测试"""

    def test_refresh_token(self, client, sample_user):
        """使用 refresh token 获取新的 access token"""
        # 先登录获取 refresh token
        login_resp = client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'TestPassword123'
        })
        refresh_token = login_resp.get_json()['refresh_token']

        # 使用 refresh token
        response = client.post('/api/auth/refresh', headers={
            'Authorization': f'Bearer {refresh_token}'
        })
        data = response.get_json()
        assert response.status_code == 200
        assert 'access_token' in data


class TestGetCurrentUser:
    """获取当前用户信息测试"""

    def test_get_me(self, client, sample_user, auth_headers):
        """带有效 token 获取当前用户"""
        response = client.get('/api/auth/me', headers=auth_headers)
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True
        assert data['user']['username'] == 'testuser'

    def test_get_me_no_token(self, client):
        """无 token 应返回 401"""
        response = client.get('/api/auth/me')
        assert response.status_code == 401

    def test_get_me_invalid_token(self, client):
        """无效 token 应返回 401"""
        response = client.get('/api/auth/me', headers={
            'Authorization': 'Bearer invalid.token.here'
        })
        assert response.status_code == 401


class TestHealthCheck:
    """健康检查测试"""

    def test_health_check(self, client):
        """健康检查无需认证"""
        response = client.get('/api/health')
        data = response.get_json()
        assert response.status_code == 200
        assert data['status'] == 'healthy'
