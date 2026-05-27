"""
JWT 认证模块
提供 token 生成、验证、登录认证等功能
"""
import functools
from datetime import timedelta
from flask import request, jsonify, current_app
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, verify_jwt_in_request
)
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, User

jwt = JWTManager()


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({'error': 'Token 已过期，请重新登录', 'code': 'TOKEN_EXPIRED'}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({'error': '无效的 Token', 'code': 'INVALID_TOKEN'}), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({'error': '请求缺少认证 Token', 'code': 'MISSING_TOKEN'}), 401


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify({'error': 'Token 已被撤销', 'code': 'TOKEN_REVOKED'}), 401


def authenticate_user(username: str, password: str) -> dict:
    """
    验证用户凭据，成功返回 user dict，失败返回 None
    """
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        return user.to_dict()
    return None


def generate_tokens(user_id: int) -> dict:
    """
    生成 access token 和 refresh token
    """
    expires = timedelta(seconds=current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', 86400))
    access_token = create_access_token(
        identity=str(user_id),
        expires_delta=expires
    )
    refresh_token = create_refresh_token(identity=str(user_id))
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'Bearer'
    }


def get_current_user_id() -> int:
    """从 JWT 中获取当前用户 ID"""
    return int(get_jwt_identity())


def require_role(*roles):
    """
    角色权限装饰器
    用法: @require_role('expert', 'admin')
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_current_user_id()
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': '用户不存在'}), 404
            if roles and user.user_type not in roles:
                return jsonify({'error': '权限不足', 'required_roles': list(roles)}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
