"""
研究方案路由 — 需要 JWT 认证
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, ResearchPlan, ResearchTask, User, PlanVersion, PlanShare
from datetime import datetime, timedelta
import json
import logging
import uuid

research_bp = Blueprint('research', __name__)
logger = logging.getLogger(__name__)


def _check_plan_ownership(plan, current_user_id, current_user):
    """检查方案所有权"""
    return plan.user_id == current_user_id or current_user.user_type == 'admin'


@research_bp.route('/plans', methods=['GET'])
@jwt_required()
def get_research_plans():
    """获取研究方案列表"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        user_id = request.args.get('user_id', type=int)

        # 非管理员只能查看自己的方案
        if not current_user or (current_user.user_type != 'admin' and user_id and user_id != current_user_id):
            return jsonify({'error': '权限不足'}), 403

        # 如果没有指定 user_id，返回当前用户的方案
        query_user_id = user_id if user_id else current_user_id

        # 管理员可以查看所有方案
        if current_user.user_type == 'admin' and not user_id:
            plans = ResearchPlan.query.order_by(ResearchPlan.created_at.desc()).all()
        else:
            plans = ResearchPlan.query.filter_by(user_id=query_user_id).order_by(
                ResearchPlan.created_at.desc()
            ).all()

        return jsonify({
            'success': True,
            'plans': [plan.to_dict() for plan in plans]
        })

    except Exception as e:
        logger.error(f"获取研究方案列表失败: {str(e)}")
        return jsonify({'error': '获取研究方案列表失败'}), 500


@research_bp.route('/plan/<int:plan_id>', methods=['GET'])
@jwt_required()
def get_research_plan(plan_id):
    """获取单个研究方案"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        plan = ResearchPlan.query.get(plan_id)

        if not plan:
            return jsonify({'error': '研究方案不存在'}), 404

        if not _check_plan_ownership(plan, current_user_id, current_user):
            return jsonify({'error': '无权查看此方案'}), 403

        return jsonify({
            'success': True,
            'plan': plan.to_dict()
        })

    except Exception as e:
        logger.error(f"获取研究方案失败: {str(e)}")
        return jsonify({'error': '获取研究方案失败'}), 500


@research_bp.route('/plan/<int:plan_id>', methods=['PUT'])
@jwt_required()
def update_research_plan(plan_id):
    """更新研究方案"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        plan = ResearchPlan.query.get(plan_id)

        if not plan:
            return jsonify({'error': '研究方案不存在'}), 404

        if not _check_plan_ownership(plan, current_user_id, current_user):
            return jsonify({'error': '无权修改此方案'}), 403

        data = request.get_json()

        if 'content' in data:
            plan.content = json.dumps(data['content'], ensure_ascii=False)
        if 'title' in data:
            plan.title = data['title']

        plan.updated_at = db.func.now()
        db.session.commit()

        logger.info(f"研究方案更新成功: ID {plan_id}")
        return jsonify({
            'success': True,
            'plan': plan.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"更新研究方案失败: {str(e)}")
        return jsonify({'error': '更新研究方案失败'}), 500


@research_bp.route('/tasks', methods=['GET'])
@jwt_required()
def get_standard_tasks():
    """获取标准化任务列表"""
    try:
        specialty = request.args.get('specialty')
        task_type = request.args.get('task_type')

        query = ResearchTask.query
        if specialty:
            query = query.filter_by(specialty=specialty)
        if task_type:
            query = query.filter_by(task_type=task_type)

        tasks = query.order_by(ResearchTask.created_at.desc()).all()

        return jsonify({
            'success': True,
            'tasks': [task.to_dict() for task in tasks]
        })

    except Exception as e:
        logger.error(f"获取标准化任务列表失败: {str(e)}")
        return jsonify({'error': '获取标准化任务列表失败'}), 500


@research_bp.route('/task', methods=['POST'])
@jwt_required()
def create_standard_task():
    """创建标准化任务（管理员）"""
    try:
        current_user_id = int(get_jwt_identity())
        current_user = User.query.get(current_user_id)
        if current_user.user_type != 'admin':
            return jsonify({'error': '仅管理员可创建标准化任务'}), 403

        data = request.get_json()

        task_count = ResearchTask.query.count() + 1
        task_code = f"TASK_{task_count:03d}"

        task = ResearchTask(
            task_code=task_code,
            specialty=data.get('specialty', ''),
            task_type=data.get('task_type', ''),
            student_background=data.get('student_background', ''),
            direction_info=data.get('direction_info', ''),
            resource_conditions=data.get('resource_conditions', ''),
            expected_timeline=data.get('expected_timeline', ''),
            existing_concepts=data.get('existing_concepts', '')
        )

        db.session.add(task)
        db.session.commit()

        logger.info(f"标准化任务创建成功: {task_code}")
        return jsonify({
            'success': True,
            'task': task.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"创建标准化任务失败: {str(e)}")
        return jsonify({'error': '创建标准化任务失败'}), 500


@research_bp.route('/task/<int:task_id>', methods=['GET'])
@jwt_required()
def get_standard_task(task_id):
    """获取单个标准化任务"""
    try:
        task = ResearchTask.query.get(task_id)
        if not task:
            return jsonify({'error': '标准化任务不存在'}), 404

        return jsonify({
            'success': True,
            'task': task.to_dict()
        })

    except Exception as e:
        logger.error(f"获取标准化任务失败: {str(e)}")
        return jsonify({'error': '获取标准化任务失败'}), 500


@research_bp.route('/task-types', methods=['GET'])
def get_task_types():
    """获取任务类型选项（无需认证）"""
    task_types = [
        '方向模糊型',
        '方向初步明确型',
        '资源已具备型',
        '方案粗稿型',
        '条件不足型'
    ]

    return jsonify({
        'success': True,
        'task_types': task_types
    })


@research_bp.route('/edit-and-regenerate', methods=['POST', 'OPTIONS'])
@jwt_required()
def edit_and_regenerate():
    """编辑并优化研究方案"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200

    try:
        current_user_id = int(get_jwt_identity())
        data = request.get_json()
        if not data:
            return jsonify({'error': '未提供数据'}), 400

        user_id = data.get('user_id')
        plan_id = data.get('plan_id')

        # 安全校验
        if current_user_id != user_id:
            current_user = User.query.get(current_user_id)
            if not current_user or current_user.user_type != 'admin':
                return jsonify({'error': '只能编辑自己的方案'}), 403

        plan_record = ResearchPlan.query.filter_by(id=plan_id, user_id=user_id).first()
        if not plan_record:
            return jsonify({'error': '未找到研究方案'}), 404

        original_content = plan_record.content
        if isinstance(original_content, str):
            original_content = json.loads(original_content)

        user_edits = data.get('user_edits', {})
        optimization_focus = data.get('optimization_focus', '')

        optimized_plan = {**original_content, **user_edits}

        if optimization_focus:
            from agents import RevisionAgent
            revision_agent = RevisionAgent()
            input_data = {
                'research_plan': optimized_plan,
                'critique': {},
                'user_feedback': optimization_focus
            }
            revised = revision_agent.revise_research_plan(input_data)
            if revised and 'error' not in revised and 'revised_plan' in revised:
                optimized_plan = revised['revised_plan']

        # 保存版本快照
        try:
            max_ver = PlanVersion.query.filter_by(plan_id=plan_id).order_by(PlanVersion.version_num.desc()).first()
            new_ver_num = (max_ver.version_num + 1) if max_ver else 1
            change_desc = optimization_focus if optimization_focus else '编辑优化'
            version = PlanVersion(
                plan_id=plan_id, version_num=new_ver_num,
                content=json.dumps(original_content, ensure_ascii=False),
                change_summary=f'编辑优化：{change_desc[:50]}'
            )
            db.session.add(version)
        except Exception as ver_err:
            logger.warning(f"版本快照保存失败: {ver_err}")

        plan_record.content = json.dumps(optimized_plan, ensure_ascii=False)
        plan_record.updated_at = db.func.now()
        db.session.commit()

        return jsonify({
            'success': True,
            'optimized_plan': optimized_plan,
            'plan_id': plan_id
        })

    except Exception as e:
        logger.error(f"编辑优化研究方案失败: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ── 方案对比 ──

@research_bp.route('/compare', methods=['POST'])
@jwt_required()
def compare_plans():
    """对比多个研究方案"""
    try:
        current_user_id = int(get_jwt_identity())
        data = request.get_json()
        plan_ids = data.get('plan_ids', [])

        if not plan_ids or len(plan_ids) < 2:
            return jsonify({'error': '至少需要选择2个方案进行对比'}), 400
        if len(plan_ids) > 4:
            return jsonify({'error': '最多对比4个方案'}), 400

        plans = []
        for pid in plan_ids:
            plan = ResearchPlan.query.get(pid)
            if not plan:
                return jsonify({'error': f'方案 {pid} 不存在'}), 404
            if plan.user_id != current_user_id:
                current_user = User.query.get(current_user_id)
                if not current_user or current_user.user_type != 'admin':
                    return jsonify({'error': f'无权查看方案 {pid}'}), 403

            content = plan.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except Exception:
                    content = {}
            if isinstance(content, dict) and 'research_proposal' in content:
                content = content['research_proposal']

            # 获取评分
            critique = plan.critique_feedback
            if isinstance(critique, str):
                try:
                    critique = json.loads(critique)
                except Exception:
                    critique = {}

            plans.append({
                'id': plan.id,
                'title': plan.title,
                'content': content,
                'critique': critique,
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat(),
            })

        # 评分维度
        score_dims = [
            ('feasibility', '可行性'),
            ('innovation', '创新性'),
            ('methodology', '方法学'),
            ('sample_size', '样本量'),
            ('endpoint', '终点清晰度'),
            ('innovation_authentic', '创新真实性'),
            ('logic_chain', '逻辑链'),
        ]

        comparison = {
            'plans': plans,
            'score_dimensions': score_dims,
            'fields': [
                ('title', '研究题目'),
                ('background', '研究背景'),
                ('clinical_problem', '临床问题'),
                ('scientific_problem', '科学问题'),
                ('hypothesis', '研究假设'),
                ('objectives', '研究目标'),
                ('study_design', '研究设计'),
                ('subjects_criteria', '纳排标准'),
                ('variables_endpoints', '变量与终点'),
                ('statistical_analysis', '统计分析'),
                ('innovation', '创新点'),
                ('risks_alternatives', '风险与备选'),
                ('timeline', '时间表'),
            ]
        }

        return jsonify({'success': True, 'comparison': comparison})

    except Exception as e:
        logger.error(f"方案对比失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ── 方案版本历史 ──

@research_bp.route('/plan/<int:plan_id>/versions', methods=['GET'])
@jwt_required()
def get_plan_versions(plan_id):
    """获取方案版本历史"""
    try:
        current_user_id = int(get_jwt_identity())
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '方案不存在'}), 404
        if plan.user_id != current_user_id:
            current_user = User.query.get(current_user_id)
            if not current_user or current_user.user_type != 'admin':
                return jsonify({'error': '无权查看'}), 403

        versions = PlanVersion.query.filter_by(plan_id=plan_id).order_by(PlanVersion.version_num.desc()).all()
        return jsonify({
            'success': True,
            'versions': [v.to_dict() for v in versions]
        })
    except Exception as e:
        logger.error(f"获取版本历史失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@research_bp.route('/plan/<int:plan_id>/versions', methods=['POST'])
@jwt_required()
def save_plan_version(plan_id):
    """保存当前方案为新版本"""
    try:
        current_user_id = int(get_jwt_identity())
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '方案不存在'}), 404
        if plan.user_id != current_user_id:
            return jsonify({'error': '无权操作'}), 403

        data = request.get_json()
        change_summary = data.get('change_summary', '手动保存版本')

        # 计算新版本号
        max_ver = PlanVersion.query.filter_by(plan_id=plan_id).order_by(PlanVersion.version_num.desc()).first()
        new_version_num = (max_ver.version_num + 1) if max_ver else 1

        version = PlanVersion(
            plan_id=plan_id,
            version_num=new_version_num,
            content=plan.content,
            change_summary=change_summary
        )
        db.session.add(version)
        db.session.commit()

        return jsonify({'success': True, 'version': version.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"保存版本失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@research_bp.route('/plan/<int:plan_id>/versions/<int:version_id>/restore', methods=['POST'])
@jwt_required()
def restore_plan_version(plan_id, version_id):
    """回退到指定版本"""
    try:
        current_user_id = int(get_jwt_identity())
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '方案不存在'}), 404
        if plan.user_id != current_user_id:
            return jsonify({'error': '无权操作'}), 403

        version = PlanVersion.query.filter_by(id=version_id, plan_id=plan_id).first()
        if not version:
            return jsonify({'error': '版本不存在'}), 404

        # 先保存当前版本
        max_ver = PlanVersion.query.filter_by(plan_id=plan_id).order_by(PlanVersion.version_num.desc()).first()
        new_version_num = (max_ver.version_num + 1) if max_ver else 1
        backup = PlanVersion(
            plan_id=plan_id,
            version_num=new_version_num,
            content=plan.content,
            change_summary=f'回退前自动备份（回退到版本 {version.version_num}）'
        )
        db.session.add(backup)

        # 回退
        plan.content = version.content
        plan.updated_at = db.func.now()
        db.session.commit()

        return jsonify({'success': True, 'plan': plan.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"回退版本失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ── 方案分享 ──

@research_bp.route('/plan/<int:plan_id>/share', methods=['POST'])
@jwt_required()
def create_share_link(plan_id):
    """创建分享链接"""
    try:
        current_user_id = int(get_jwt_identity())
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '方案不存在'}), 404
        if plan.user_id != current_user_id:
            return jsonify({'error': '无权操作'}), 403

        data = request.get_json() or {}
        password = data.get('password', '')
        expire_days = data.get('expire_days', 7)

        share_code = uuid.uuid4().hex[:12]
        password_hash = None
        if password:
            from werkzeug.security import generate_password_hash
            password_hash = generate_password_hash(password)

        expires_at = datetime.utcnow() + timedelta(days=expire_days) if expire_days > 0 else None

        share = PlanShare(
            plan_id=plan_id,
            share_code=share_code,
            created_by=current_user_id,
            password_hash=password_hash,
            expires_at=expires_at
        )
        db.session.add(share)
        db.session.commit()

        return jsonify({
            'success': True,
            'share': share.to_dict(),
            'share_url': f'/share/{share_code}',
            'share_code': share_code
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建分享链接失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@research_bp.route('/share/<share_code>', methods=['GET', 'POST'])
def view_shared_plan(share_code):
    """通过分享链接查看方案（无需登录）"""
    try:
        share = PlanShare.query.filter_by(share_code=share_code).first()
        if not share:
            return jsonify({'error': '分享链接不存在'}), 404

        # 检查过期
        if share.expires_at and share.expires_at < datetime.utcnow():
            return jsonify({'error': '分享链接已过期'}), 410

        # 检查密码
        if share.password_hash:
            if request.method == 'GET':
                return jsonify({'require_password': True})
            data = request.get_json() or {}
            password = data.get('password', '')
            from werkzeug.security import check_password_hash
            if not check_password_hash(share.password_hash, password):
                return jsonify({'error': '密码错误'}), 401

        # 增加浏览次数
        share.view_count += 1
        db.session.commit()

        plan = share.plan
        content = plan.content
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                content = {}
        if isinstance(content, dict) and 'research_proposal' in content:
            content = content['research_proposal']

        return jsonify({
            'success': True,
            'plan': {
                'id': plan.id,
                'title': plan.title,
                'content': content,
                'created_at': plan.created_at.isoformat(),
            },
            'share_info': {
                'view_count': share.view_count,
                'expires_at': share.expires_at.isoformat() if share.expires_at else None,
            }
        })
    except Exception as e:
        logger.error(f"查看分享方案失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ── 批量导出 ──

@research_bp.route('/export-all', methods=['GET'])
@jwt_required()
def export_all_plans():
    """批量导出所有方案为 ZIP"""
    try:
        current_user_id = int(get_jwt_identity())
        plans = ResearchPlan.query.filter_by(user_id=current_user_id).order_by(ResearchPlan.created_at.desc()).all()

        import zipfile
        from io import BytesIO, StringIO

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for plan in plans:
                content = plan.content
                if isinstance(content, str):
                    try:
                        content = json.loads(content)
                    except Exception:
                        content = {}
                if isinstance(content, dict) and 'research_proposal' in content:
                    content = content['research_proposal']

                title = content.get('title', plan.title or f'方案_{plan.id}')
                # 清理文件名
                safe_title = str(title).replace('/', '_').replace('\\', '_').replace(':', '_')[:50]

                # 生成每份方案的文本
                lines = [f'# {title}', '']
                field_names = {
                    'background': '研究背景', 'clinical_problem': '临床问题',
                    'scientific_problem': '科学问题', 'hypothesis': '研究假设',
                    'objectives': '研究目标', 'study_design': '研究设计',
                    'subjects_criteria': '纳排标准', 'variables_endpoints': '变量与终点',
                    'statistical_analysis': '统计分析', 'innovation': '创新点',
                    'risks_alternatives': '风险与备选', 'timeline': '时间表',
                }
                for key, name in field_names.items():
                    val = content.get(key, '')
                    if val and isinstance(val, str) and val.strip():
                        lines.append(f'## {name}')
                        lines.append(val)
                        lines.append('')

                text_content = '\n'.join(lines)
                zf.writestr(f'{safe_title}.txt', text_content.encode('utf-8'))

        buffer.seek(0)
        from flask import send_file
        return send_file(
            buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='研究方案合集.zip'
        )
    except Exception as e:
        logger.error(f"批量导出失败: {str(e)}")
        return jsonify({'error': str(e)}), 500
