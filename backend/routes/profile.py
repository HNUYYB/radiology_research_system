"""
学生画像路由 — 需要 JWT 认证
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, StudentProfile, User
import json
import logging

profile_bp = Blueprint('profile', __name__)
logger = logging.getLogger(__name__)


@profile_bp.route('/student', methods=['POST'])
@jwt_required()
def create_student_profile():
    """创建学生画像"""
    try:
        data = request.get_json(force=True) if request.is_json else json.loads(request.get_data(as_text=True))
        user_id = data.get('user_id')

        # 安全校验：只能为自己创建画像（除非管理员）
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        if current_user_id != user_id and current_user.user_type != 'admin':
            return jsonify({'error': '只能为自己的账户创建画像'}), 403

        if not user_id:
            return jsonify({'error': '用户ID是必需的'}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404

        existing_profile = StudentProfile.query.filter_by(user_id=user_id).first()
        if existing_profile:
            return jsonify({'error': '学生画像已存在'}), 409

        profile = StudentProfile(
            user_id=user_id,
            grade=data.get('grade', ''),
            specialty=data.get('specialty', ''),
            available_resources=json.dumps(data.get('available_resources', {}), ensure_ascii=False),
            case_scale=data.get('case_scale', ''),
            follow_up_available=data.get('follow_up_available', False),
            gold_standard_available=data.get('gold_standard_available', False),
            statistical_background=data.get('statistical_background', ''),
            ai_background=data.get('ai_background', ''),
            time_constraint=data.get('time_constraint', ''),
            target_journal_level=data.get('target_journal_level', '')
        )

        if data.get('grade'):
            user.grade = data.get('grade')
        if data.get('specialty'):
            user.specialty = data.get('specialty')

        db.session.add(profile)
        db.session.commit()

        logger.info(f"学生画像创建成功: 用户ID {user_id}")
        return jsonify({
            'success': True,
            'profile': profile.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"创建学生画像失败: {str(e)}")
        return jsonify({'error': '创建学生画像失败'}), 500


@profile_bp.route('/student/<int:user_id>', methods=['GET'])
@jwt_required()
def get_student_profile(user_id):
    """获取学生画像"""
    try:
        profile = StudentProfile.query.filter_by(user_id=user_id).first()
        if not profile:
            return jsonify({'error': '学生画像不存在'}), 404

        return jsonify({'success': True, 'profile': profile.to_dict()})

    except Exception as e:
        logger.error(f"获取学生画像失败: {str(e)}")
        return jsonify({'error': '获取学生画像失败'}), 500


@profile_bp.route('/student/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_student_profile(user_id):
    """更新学生画像"""
    try:
        # 安全校验：只能更新自己的画像（除非管理员）
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        if current_user_id != user_id and current_user.user_type != 'admin':
            return jsonify({'error': '只能更新自己的画像'}), 403

        profile = StudentProfile.query.filter_by(user_id=user_id).first()
        if not profile:
            return jsonify({'error': '学生画像不存在'}), 404

        data = request.get_json()

        updatable_fields = [
            'grade', 'specialty', 'case_scale',
            'follow_up_available', 'gold_standard_available',
            'statistical_background', 'ai_background',
            'time_constraint', 'target_journal_level',
        ]
        for field in updatable_fields:
            if field in data:
                setattr(profile, field, data[field])

        if 'available_resources' in data:
            profile.available_resources = json.dumps(data['available_resources'], ensure_ascii=False)

        profile.updated_at = db.func.now()
        db.session.commit()

        logger.info(f"学生画像更新成功: 用户ID {user_id}")
        return jsonify({
            'success': True,
            'profile': profile.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"更新学生画像失败: {str(e)}")
        return jsonify({'error': '更新学生画像失败'}), 500


@profile_bp.route('/options', methods=['GET'])
def get_profile_options():
    """获取画像选项（无需认证）"""
    options = {
        'grades': ['研一', '研二', '研三', '博一', '博二', '博三', '博四及以上'],
        'specialties': [
            '胸部', '神经', '乳腺', '腹部', '骨肌', '介入',
            '心血管', '儿科', '头颈', '泌尿', '妇科', '急诊',
            '功能影像', '分子影像', '核医学', '超声', '病理影像',
            '放射治疗', '核磁共振', 'CT专项', 'X线专项', '其他'
        ],
        'case_scales': ['小型(<50例)', '中型(50-200例)', '大型(200-500例)', '超大型(>500例)'],
        'statistical_backgrounds': ['基础', '中等', '熟练'],
        'ai_backgrounds': ['无基础', '基础', '中等', '熟练'],
        'time_constraints': ['6个月以内', '6-12个月', '12-24个月', '24个月以上'],
        'target_journal_levels': ['核心期刊', 'SCI一般', 'SCI中等', 'SCI高分']
    }

    return jsonify({
        'success': True,
        'options': options
    })
