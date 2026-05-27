"""
认证路由 — 注册、登录、Token 刷新
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from werkzeug.security import generate_password_hash
from models import db, User
from auth import authenticate_user, generate_tokens
import logging

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        user_type = data.get('user_type', 'student')

        if not username or not password:
            return jsonify({'error': '用户名和密码是必需的'}), 400

        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            return jsonify({'error': '用户名已存在'}), 409

        # 创建新用户
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            user_type=user_type
        )

        db.session.add(user)
        db.session.commit()

        # 生成 token
        tokens = generate_tokens(user.id)
        logger.info(f"用户注册成功: {username}")
        return jsonify({
            'success': True,
            'user': user.to_dict(),
            **tokens
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"用户注册失败: {str(e)}")
        return jsonify({'error': '注册失败'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录 — 返回 JWT Token"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': '用户名和密码是必需的'}), 400

        user = authenticate_user(username, password)
        if not user:
            return jsonify({'error': '用户名或密码错误'}), 401

        tokens = generate_tokens(user['id'])
        logger.info(f"用户登录成功: {username}")
        return jsonify({
            'success': True,
            'user': user,
            **tokens
        })

    except Exception as e:
        logger.error(f"用户登录失败: {str(e)}")
        return jsonify({'error': '登录失败'}), 500


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """刷新 access token"""
    try:
        user_id = get_jwt_identity()
        access_token = create_access_token(identity=user_id)
        return jsonify({
            'success': True,
            'access_token': access_token,
            'token_type': 'Bearer'
        })
    except Exception as e:
        logger.error(f"Token 刷新失败: {str(e)}")
        return jsonify({'error': 'Token 刷新失败'}), 500


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """获取当前登录用户信息"""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
    except Exception as e:
        logger.error(f"获取当前用户失败: {str(e)}")
        return jsonify({'error': '获取用户信息失败'}), 500
