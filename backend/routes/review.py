"""
评审路由 — 需要 JWT 认证
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, BlindReview, ResearchPlan, User
import logging

review_bp = Blueprint('review', __name__)
logger = logging.getLogger(__name__)


@review_bp.route('/assignments', methods=['GET'])
@jwt_required()
def get_review_assignments():
    """获取评审任务分配"""
    try:
        current_user_id = int(get_jwt_identity())
        expert_id = request.args.get('expert_id', type=int)

        # 非管理员只能查看自己的评审任务
        current_user = User.query.get(current_user_id)
        if current_user.user_type != 'admin' and expert_id and expert_id != current_user_id:
            return jsonify({'error': '只能查看自己的评审任务'}), 403

        query_expert_id = expert_id if expert_id else current_user_id

        assignments = db.session.query(ResearchPlan, BlindReview).outerjoin(
            BlindReview,
            db.and_(
                BlindReview.plan_id == ResearchPlan.id,
                BlindReview.expert_id == query_expert_id
            )
        ).filter(BlindReview.id.is_(None)).limit(10).all()

        result = []
        for plan, review in assignments:
            result.append({
                'plan_id': plan.id,
                'title': plan.title,
                'created_at': plan.created_at.isoformat(),
                'has_reviewed': review is not None
            })

        return jsonify({
            'success': True,
            'assignments': result
        })

    except Exception as e:
        logger.error(f"获取评审任务分配失败: {str(e)}")
        return jsonify({'error': '获取评审任务分配失败'}), 500


@review_bp.route('/submit', methods=['POST'])
@jwt_required()
def submit_review():
    """提交评审结果"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)

        data = request.get_json()
        plan_id = data.get('plan_id')
        expert_id = data.get('expert_id')

        # 安全校验：只能以自己的身份提交评审
        if current_user_id != expert_id and current_user.user_type != 'admin':
            return jsonify({'error': '只能以自己的身份提交评审'}), 403

        # 检查是否已评审
        existing_review = BlindReview.query.filter_by(
            plan_id=plan_id,
            expert_id=expert_id
        ).first()
        if existing_review:
            return jsonify({'error': '该方案已经评审过'}), 409

        review = BlindReview(
            plan_id=plan_id,
            expert_id=expert_id,
            total_score=data.get('total_score'),
            clinical_significance=data.get('clinical_significance'),
            innovation=data.get('innovation'),
            relevance=data.get('relevance'),
            feasibility=data.get('feasibility'),
            methodology=data.get('methodology'),
            publication_potential=data.get('publication_potential'),
            data_accessibility=data.get('data_accessibility'),
            endpoint_definability=data.get('endpoint_definability'),
            statistical_closure=data.get('statistical_closure'),
            structure_completeness=data.get('structure_completeness'),
            personalization_match=data.get('personalization_match'),
            proposal_acceptability=data.get('proposal_acceptability'),
            supervisor_adoption_willingness=data.get('supervisor_adoption_willingness'),
            risk_warning_ability=data.get('risk_warning_ability'),
            empty_expression_ratio=data.get('empty_expression_ratio'),
            comments=data.get('comments', '')
        )

        db.session.add(review)
        db.session.commit()

        logger.info(f"评审结果提交成功: 方案ID {plan_id}, 专家ID {expert_id}")
        return jsonify({
            'success': True,
            'review_id': review.id,
            'message': '评审结果提交成功'
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"提交评审结果失败: {str(e)}")
        return jsonify({'error': '提交评审结果失败'}), 500


@review_bp.route('/plan/<int:plan_id>', methods=['GET'])
@jwt_required()
def get_plan_for_review(plan_id):
    """获取待评审的方案"""
    try:
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '研究方案不存在'}), 404

        blinded_plan = {
            'id': plan.id,
            'title': plan.title,
            'content': plan.content,
            'created_at': plan.created_at.isoformat(),
            'input_type': plan.input_type
        }

        return jsonify({
            'success': True,
            'plan': blinded_plan
        })

    except Exception as e:
        logger.error(f"获取待评审方案失败: {str(e)}")
        return jsonify({'error': '获取待评审方案失败'}), 500


@review_bp.route('/my-reviews', methods=['GET'])
@jwt_required()
def get_my_reviews():
    """获取我的评审记录"""
    try:
        current_user_id = int(get_jwt_identity())
        expert_id = request.args.get('expert_id', type=int)

        current_user = User.query.get(current_user_id)
        if current_user.user_type != 'admin' and expert_id and expert_id != current_user_id:
            return jsonify({'error': '只能查看自己的评审记录'}), 403

        query_expert_id = expert_id if expert_id else current_user_id

        reviews = BlindReview.query.filter_by(expert_id=query_expert_id).order_by(
            BlindReview.created_at.desc()
        ).all()

        result = []
        for review in reviews:
            plan = ResearchPlan.query.get(review.plan_id)
            result.append({
                'review_id': review.id,
                'plan_id': review.plan_id,
                'plan_title': plan.title if plan else '未知',
                'total_score': review.total_score,
                'created_at': review.created_at.isoformat(),
                'comments': review.comments
            })

        return jsonify({
            'success': True,
            'reviews': result
        })

    except Exception as e:
        logger.error(f"获取评审记录失败: {str(e)}")
        return jsonify({'error': '获取评审记录失败'}), 500


@review_bp.route('/statistics', methods=['GET'])
@jwt_required()
def get_review_statistics():
    """获取评审统计信息"""
    try:
        total_plans = ResearchPlan.query.count()
        total_reviews = BlindReview.query.count()
        avg_score = db.session.query(db.func.avg(BlindReview.total_score)).scalar() or 0

        plan_types = db.session.query(
            ResearchPlan.input_type,
            db.func.count(ResearchPlan.id).label('count'),
            db.func.avg(BlindReview.total_score).label('avg_score')
        ).outerjoin(BlindReview).group_by(ResearchPlan.input_type).all()

        type_stats = []
        for row in plan_types:
            type_stats.append({
                'input_type': row.input_type,
                'count': row.count,
                'avg_score': float(row.avg_score) if row.avg_score else 0
            })

        return jsonify({
            'success': True,
            'statistics': {
                'total_plans': total_plans,
                'total_reviews': total_reviews,
                'average_score': float(avg_score),
                'type_statistics': type_stats
            }
        })

    except Exception as e:
        logger.error(f"获取评审统计信息失败: {str(e)}")
        return jsonify({'error': '获取评审统计信息失败'}), 500
