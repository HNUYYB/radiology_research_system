"""
评审路由测试
"""
import pytest


class TestReviewAssignments:
    """评审任务分配测试"""

    def test_get_assignments(self, client, expert_auth_headers):
        """专家可获取评审任务"""
        response = client.get('/api/review/assignments', headers=expert_auth_headers)
        assert response.status_code == 200

    def test_get_assignments_unauthorized(self, client):
        """未认证不能获取评审任务"""
        response = client.get('/api/review/assignments')
        assert response.status_code == 401


class TestSubmitReview:
    """提交评审测试"""

    def test_submit_review_unauthorized(self, client):
        """未认证不能提交评审"""
        response = client.post('/api/review/submit', json={
            'plan_id': 1,
            'expert_id': 1
        })
        assert response.status_code == 401

    def test_submit_review_missing_expert_id(self, client, expert_auth_headers):
        """缺少 expert_id 时，所有权检查先触发，返回 403"""
        response = client.post('/api/review/submit',
            json={'plan_id': 1},
            headers=expert_auth_headers
        )
        # 缺少 expert_id，所有权检查先触发（current_user_id != None → 403）
        assert response.status_code == 403


class TestReviewStatistics:
    """评审统计测试"""

    def test_get_statistics(self, client, auth_headers):
        """认证用户可获取评审统计"""
        response = client.get('/api/review/statistics', headers=auth_headers)
        data = response.get_json()
        assert response.status_code == 200
        assert 'statistics' in data

    def test_get_statistics_unauthorized(self, client):
        """未认证不能获取评审统计"""
        response = client.get('/api/review/statistics')
        assert response.status_code == 401


class TestMyReviews:
    """我的评审记录测试"""

    def test_get_my_reviews(self, client, expert_auth_headers):
        """专家可获取自己的评审记录"""
        response = client.get('/api/review/my-reviews', headers=expert_auth_headers)
        assert response.status_code == 200

    def test_get_my_reviews_unauthorized(self, client):
        """未认证不能获取评审记录"""
        response = client.get('/api/review/my-reviews')
        assert response.status_code == 401
