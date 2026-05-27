"""
系统管理路由测试
"""
import pytest


class TestSystemHealth:
    """健康检查测试"""

    def test_health_check(self, client):
        """健康检查无需认证"""
        response = client.get('/api/system/health')
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True

    def test_health_check_public(self, client):
        """公开健康检查"""
        response = client.get('/api/health')
        data = response.get_json()
        assert response.status_code == 200
        assert data['status'] == 'healthy'


class TestSystemStats:
    """系统统计测试"""

    def test_get_stats(self, client, auth_headers):
        """认证用户可获取统计信息"""
        response = client.get('/api/system/stats', headers=auth_headers)
        data = response.get_json()
        assert response.status_code == 200
        assert 'statistics' in data

    def test_get_stats_unauthorized(self, client):
        """未认证不能获取统计信息"""
        response = client.get('/api/system/stats')
        assert response.status_code == 401


class TestSystemLogs:
    """系统日志测试"""

    def test_get_logs(self, client, auth_headers):
        """认证用户可获取日志"""
        response = client.get('/api/system/logs', headers=auth_headers)
        data = response.get_json()
        assert response.status_code == 200

    def test_get_logs_unauthorized(self, client):
        """未认证不能获取日志"""
        response = client.get('/api/system/logs')
        assert response.status_code == 401


class TestSystemExport:
    """数据导出测试"""

    def test_export_admin_only(self, client, admin_auth_headers):
        """管理员可导出数据"""
        response = client.get('/api/system/export-data', headers=admin_auth_headers)
        assert response.status_code == 200

    def test_export_forbidden_for_student(self, client, auth_headers):
        """学生不能导出数据"""
        response = client.get('/api/system/export-data', headers=auth_headers)
        assert response.status_code == 403


class TestSystemMaintenance:
    """系统维护测试"""

    def test_cleanup_logs_admin_only(self, client, admin_auth_headers):
        """管理员可清理日志"""
        response = client.post('/api/system/maintenance',
            json={'action': 'cleanup_logs'},
            headers=admin_auth_headers
        )
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is True

    def test_maintenance_forbidden_for_student(self, client, auth_headers):
        """学生不能执行维护操作"""
        response = client.post('/api/system/maintenance',
            json={'action': 'cleanup_logs'},
            headers=auth_headers
        )
        assert response.status_code == 403

    def test_maintenance_invalid_action(self, client, admin_auth_headers):
        """无效操作应返回 400"""
        response = client.post('/api/system/maintenance',
            json={'action': 'invalid_action'},
            headers=admin_auth_headers
        )
        assert response.status_code == 400

    def test_maintenance_unauthorized(self, client):
        """未认证不能执行维护操作"""
        response = client.post('/api/system/maintenance',
            json={'action': 'cleanup_logs'}
        )
        assert response.status_code == 401
