"""
系统管理路由 — 需要 JWT 认证，部分操作仅限管理员
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, SystemLog, User
import logging
from datetime import datetime, timedelta

system_bp = Blueprint('system', __name__)
logger = logging.getLogger(__name__)


@system_bp.route('/logs', methods=['GET'])
@jwt_required()
def get_system_logs():
    """获取系统日志（管理员可查看全部，普通用户仅可查看自己的）"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        user_id = request.args.get('user_id', type=int)
        module = request.args.get('module')
        days = int(request.args.get('days', 7))

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)

        query = SystemLog.query.filter(SystemLog.created_at >= start_time)

        # 非管理员只能查看自己的日志
        if current_user.user_type != 'admin':
            query = query.filter_by(user_id=current_user_id)
        elif user_id:
            query = query.filter_by(user_id=user_id)

        if module:
            query = query.filter_by(module=module)

        logs = query.order_by(SystemLog.created_at.desc()).limit(100).all()

        result = []
        for log in logs:
            user = User.query.get(log.user_id) if log.user_id else None
            result.append({
                'id': log.id,
                'username': user.username if user else '系统',
                'action': log.action,
                'module': log.module,
                'details': log.details,
                'created_at': log.created_at.isoformat()
            })

        return jsonify({
            'success': True,
            'logs': result
        })

    except Exception as e:
        logger.error(f"获取系统日志失败: {str(e)}")
        return jsonify({'error': '获取系统日志失败'}), 500


@system_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_system_stats():
    """获取系统统计信息"""
    try:
        total_users = User.query.count()
        student_users = User.query.filter_by(user_type='student').count()
        expert_users = User.query.filter_by(user_type='expert').count()

        week_ago = datetime.utcnow() - timedelta(days=7)
        active_users = db.session.query(SystemLog.user_id).filter(
            SystemLog.created_at >= week_ago,
            SystemLog.user_id.isnot(None)
        ).distinct().count()

        module_stats = db.session.query(
            SystemLog.module,
            db.func.count(SystemLog.id).label('count')
        ).filter(
            SystemLog.created_at >= week_ago
        ).group_by(SystemLog.module).all()

        module_usage = {}
        for stat in module_stats:
            module_usage[stat.module] = stat.count

        return jsonify({
            'success': True,
            'statistics': {
                'total_users': total_users,
                'student_users': student_users,
                'expert_users': expert_users,
                'active_users_7days': active_users,
                'module_usage': module_usage
            }
        })

    except Exception as e:
        logger.error(f"获取系统统计信息失败: {str(e)}")
        return jsonify({'error': '获取系统统计信息失败'}), 500


@system_bp.route('/export-data', methods=['GET'])
@jwt_required()
def export_system_data():
    """导出系统数据（仅管理员）"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        if current_user.user_type != 'admin':
            return jsonify({'error': '仅管理员可导出数据'}), 403

        from models import ResearchPlan, BlindReview, ResearchTask, StudentProfile

        plans = ResearchPlan.query.all()
        plan_data = [plan.to_dict() for plan in plans]

        reviews = BlindReview.query.all()
        review_data = []
        for review in reviews:
            review_dict = {
                'id': review.id,
                'plan_id': review.plan_id,
                'expert_id': review.expert_id,
                'total_score': review.total_score,
                'clinical_significance': review.clinical_significance,
                'innovation': review.innovation,
                'relevance': review.relevance,
                'feasibility': review.feasibility,
                'methodology': review.methodology,
                'publication_potential': review.publication_potential,
                'created_at': review.created_at.isoformat()
            }
            review_data.append(review_dict)

        tasks = ResearchTask.query.all()
        task_data = [task.to_dict() for task in tasks]

        profiles = StudentProfile.query.all()
        profile_data = [profile.to_dict() for profile in profiles]

        export_data = {
            'export_time': datetime.utcnow().isoformat(),
            'research_plans': plan_data,
            'reviews': review_data,
            'standard_tasks': task_data,
            'student_profiles': profile_data
        }

        return jsonify({
            'success': True,
            'data': export_data
        })

    except Exception as e:
        logger.error(f"导出系统数据失败: {str(e)}")
        return jsonify({'error': '导出系统数据失败'}), 500


@system_bp.route('/maintenance', methods=['POST'])
@jwt_required()
def system_maintenance():
    """系统维护操作（仅管理员）"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        if current_user.user_type != 'admin':
            return jsonify({'error': '仅管理员可执行维护操作'}), 403

        action = request.json.get('action')

        if action == 'cleanup_logs':
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            deleted_count = SystemLog.query.filter(
                SystemLog.created_at < thirty_days_ago
            ).delete()
            db.session.commit()

            logger.info(f"清理日志完成，删除 {deleted_count} 条记录")
            return jsonify({
                'success': True,
                'message': f'清理日志完成，删除 {deleted_count} 条记录'
            })

        elif action == 'backup_database':
            return jsonify({
                'success': True,
                'message': '数据库备份功能待实现'
            })

        else:
            return jsonify({'error': '不支持的操作类型'}), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"系统维护操作失败: {str(e)}")
        return jsonify({'error': '系统维护操作失败'}), 500


@system_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查（无需认证）"""
    return jsonify({
        'success': True,
        'message': '系统运行正常',
        'timestamp': datetime.utcnow().isoformat()
    })


@system_bp.route('/test-json-format', methods=['POST'])
@jwt_required()
def test_json_format():
    """测试JSON格式生成"""
    try:
        data = request.get_json()
        prompt = data.get('prompt', '我是研一学生，想研究肺结节相关的课题')

        from api_clients import anthropic_client
        ai_result = anthropic_client.call_longcat_api(prompt, max_tokens=2000)

        try:
            plan_data = json.loads(ai_result)

            required_fields = [
                "title", "background", "clinical_problem", "scientific_problem",
                "hypothesis", "objectives", "study_design", "subjects_criteria",
                "variables_endpoints", "statistical_analysis", "innovation",
                "risks_alternatives", "timeline"
            ]

            missing_fields = [f for f in required_fields if f not in plan_data]

            if missing_fields:
                return jsonify({
                    'success': False,
                    'message': f'缺少必需字段: {missing_fields}',
                    'raw_response': ai_result
                })

            return jsonify({
                'success': True,
                'message': 'JSON格式正确',
                'plan': plan_data,
                'fields': required_fields
            })

        except json.JSONDecodeError as e:
            return jsonify({
                'success': False,
                'message': f'JSON解析失败: {str(e)}',
                'raw_response': ai_result
            })

    except Exception as e:
        logger.error(f"测试JSON格式失败: {str(e)}")
        return jsonify({'error': '测试失败'}), 500
