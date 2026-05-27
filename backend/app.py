import sys
import io
import re as _re

# 修复 Windows GBK 编码问题：强制 stdout/stderr 使用 UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def _sanitize_json(obj):
    """递归清理对象中的非法 Unicode 代理对字符（\\ud800-\\udfff），避免 JSON 序列化失败"""
    if isinstance(obj, str):
        return _re.sub(r'[\ud800-\udfff]', '�', obj)
    elif isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_json(item) for item in obj]
    else:
        return obj

def _safe_json_dumps(obj):
    """安全地将对象序列化到 JSON，自动清理非法字符"""
    return json.dumps(_sanitize_json(obj), ensure_ascii=False)

from flask import Flask, request, jsonify, current_app, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import logging
import json
import threading
import uuid
from datetime import datetime

# ── 异步任务管理 ──
_task_lock = threading.Lock()
_tasks = {}  # task_id -> {status, progress, step, result, error, started_at}

def _create_task():
    tid = str(uuid.uuid4())[:8]
    with _task_lock:
        _tasks[tid] = {
            'status': 'pending',   # pending | running | done | error
            'progress': 0,
            'step': '初始化',
            'result': None,
            'error': None,
            'started_at': datetime.utcnow().isoformat(),
        }
    return tid

def _update_task(tid, **kwargs):
    with _task_lock:
        if tid in _tasks:
            _tasks[tid].update(kwargs)

def _get_task(tid):
    with _task_lock:
        return dict(_tasks.get(tid, {}))

# 导入配置和模型
from config import Config
from models import db, User, StudentProfile, ResearchTask, ResearchPlan, BlindReview, SystemLog
from agents import (
    StudentProfileAgent, ProblemDefinitionAgent, EvidenceRetrievalAgent,
    PlanGenerationAgent, CritiqueAgent, RevisionAgent
)
from debug_logger import debug_logger, LogLevel
from auth import jwt, authenticate_user, generate_tokens, get_current_user_id, require_role
from flask_jwt_extended import jwt_required, get_jwt_identity

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _check_disease_match(keyword: str, disease: str) -> bool:
    """检查关键词是否匹配疾病，避免部分匹配导致的误判"""
    import re

    # 对于较短的疾病名，使用单词边界匹配
    if len(disease) <= 3:
        pattern = r'\b' + re.escape(disease) + r'\b'
        return bool(re.search(pattern, keyword))
    else:
        # 对于较长疾病名，检查是否为完整包含
        return disease in keyword

def register_websocket_handlers(socketio):
    """注册WebSocket事件处理器"""
    active_connections = set()

    @socketio.on('connect')
    def handle_connect():
        """客户端连接"""
        active_connections.add(request.sid)
        emit('connection_response', {'data': '已连接到调试日志系统'})
        print(f"[WebSocket] 客户端连接: {request.sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        """客户端断开连接"""
        active_connections.discard(request.sid)
        print(f"[WebSocket] 客户端断开: {request.sid}")

    @socketio.on('subscribe_logs')
    def handle_subscribe_logs(data=None):
        """订阅日志"""
        join_room('debug_logs')
        emit('subscribed', {'message': '已订阅调试日志'})
        print(f"[WebSocket] 客户端订阅日志: {request.sid}")

    @socketio.on('get_logs')
    def handle_get_logs(data=None):
        """获取历史日志"""
        if data is None:
            data = {}
        limit = data.get('limit', 100)
        level = data.get('level')
        category = data.get('category')

        logs = debug_logger.get_logs(limit=limit, level=level, category=category)
        emit('logs_history', {'logs': logs})

    @socketio.on('clear_logs')
    def handle_clear_logs():
        """清空日志"""
        debug_logger.clear_logs()
        emit('logs_cleared', {'message': '日志已清空'})

    def broadcast_log(log_entry):
        """广播日志到所有连接的客户端"""
        socketio.emit('new_log', log_entry, room='debug_logs')

    debug_logger.subscribe(broadcast_log)

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── 配置校验 ──
    missing = Config.validate()
    if missing:
        for key in missing:
            logger.warning(f"配置项缺失: {key}")

    # 配置JSON编码
    app.config['JSON_AS_ASCII'] = False
    app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'
    app.config['JSON_DECODE_ERROR_MESSAGE'] = 'Invalid JSON'

    # 自定义JSON解码器来处理中文字符
    app.json.ensure_ascii = False

    # ── 初始化扩展 ──
    db.init_app(app)
    jwt.init_app(app)

    # 初始化SocketIO
    frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:3024')
    socketio = SocketIO(app, cors_allowed_origins=frontend_url, async_mode='threading')
    app.socketio = socketio

    # 配置CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": frontend_url,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
            "supports_credentials": True,
            "max_age": 86400,
        }
    })

    # 确保数据目录存在（使用绝对路径）
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    # ── 注册蓝图 ──
    from routes.auth import auth_bp
    from routes.profile import profile_bp
    from routes.research import research_bp
    from routes.review import review_bp
    from routes.system import system_bp
    from routes.llm_settings import llm_settings_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(profile_bp, url_prefix='/api/profile')
    app.register_blueprint(research_bp, url_prefix='/api/research')
    app.register_blueprint(review_bp, url_prefix='/api/review')
    app.register_blueprint(system_bp, url_prefix='/api/system')
    app.register_blueprint(llm_settings_bp, url_prefix='/api/settings/llm')

    # 注册核心路由
    register_core_routes(app)

    # 注册WebSocket事件处理器
    register_websocket_handlers(socketio)

    return app, socketio

def register_core_routes(app):
    """注册核心路由"""

    # ── 健康检查（无需认证） ──
    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.1.0'
        })

    # ── 研究方案生成主入口（异步）— 需要认证 ──
    @app.route('/api/multi-agent/generate-plan', methods=['POST'])
    @jwt_required()
    def generate_research_plan():
        """生成研究方案 — 异步模式，立即返回任务 ID"""
        try:
            current_user_id = int(get_jwt_identity())
            data = request.get_json()
            user_id = data.get('user_id')
            student_input = data.get('student_input', '')

            if not user_id or not student_input:
                return jsonify({'error': '缺少必要参数: user_id 和 student_input'}), 400

            # 安全校验：只能为自己生成方案
            current_user = User.query.get(current_user_id)
            if current_user_id != user_id and current_user.user_type != 'admin':
                return jsonify({'error': '只能为自己的账户生成方案'}), 403

            task_id = _create_task()
            log_action(user_id, 'generate_plan', 'multi_agent', f'异步任务已创建: {task_id}')

            _pipeline_done = threading.Event()

            def _progress_simulator():
                stages = [
                    (15, '解析学生输入...'),
                    (25, '构建学生画像...'),
                    (35, '定义临床问题...'),
                    (50, '检索文献证据...'),
                    (65, '生成研究方案...'),
                    (80, '专家评审方案...'),
                    (90, '修订完善方案...'),
                ]
                for pct, step_name in stages:
                    if _pipeline_done.wait(timeout=30):
                        return
                    _update_task(task_id, progress=pct, step=step_name)

            def _run_pipeline():
                with app.app_context():
                    try:
                        _update_task(task_id, status='running', step='获取学生画像', progress=5)
                        student_profile_data = get_student_profile(user_id)

                        _update_task(task_id, step='多智能体协同生成', progress=10)
                        from agents import multi_agent_coordinator
                        result = multi_agent_coordinator.coordinate_research_plan_generation(
                            student_input, student_profile_data
                        )

                        if 'error' in result:
                            _update_task(task_id, status='error', error=result['error'])
                            log_action(user_id, 'generate_plan_error', 'multi_agent', result['error'])
                            return

                        final_plan = result.get('final_plan', {})
                        process_summary = result.get('process_summary', {})

                        required_fields = [
                            'title', 'background', 'clinical_problem', 'scientific_problem',
                            'hypothesis', 'objectives', 'study_design', 'subjects_criteria',
                            'variables_endpoints', 'statistical_analysis', 'innovation',
                            'risks_alternatives', 'timeline'
                        ]
                        for field in required_fields:
                            if field not in final_plan or not final_plan[field]:
                                final_plan[field] = f"待补充: {field}"

                        _update_task(task_id, progress=95, step='保存方案到数据库...')
                        evidence_data = process_summary.get('evidence_summary', {})
                        evidence_pool_data = result.get('evidence_pool', {})
                        plan_record = save_research_plan(
                            user_id=user_id,
                            plan_content=final_plan,
                            problem_definition=process_summary.get('problem_definition', {}),
                            evidence=evidence_data,
                            critique=process_summary.get('critique'),
                            evidence_pool=evidence_pool_data,
                        )

                        _update_task(task_id, status='done', progress=100,
                                     step='完成', result={'plan_id': plan_record.id})
                        log_action(user_id, 'generate_plan_success', 'multi_agent',
                                  f'方案生成成功: plan_id={plan_record.id}')
                    except Exception as e:
                        import traceback
                        tb = traceback.format_exc()
                        logger.error(f"异步任务 {task_id} 失败: {e}\n{tb}")
                        _update_task(task_id, status='error', error=str(e))
                    finally:
                        _pipeline_done.set()

            t = threading.Thread(target=_run_pipeline, daemon=True)
            t.start()
            sim_t = threading.Thread(target=_progress_simulator, daemon=True)
            sim_t.start()

            return jsonify({'success': True, 'task_id': task_id, 'message': '方案生成已启动，请轮询进度'}), 202

        except Exception as e:
            logger.error(f"启动方案生成失败: {e}")
            return jsonify({'error': str(e)}), 500

    # ── 查询任务进度 — 需要认证 ──
    @app.route('/api/multi-agent/task/<task_id>', methods=['GET'])
    @jwt_required()
    def get_task_status(task_id):
        """查询异步任务进度"""
        task = _get_task(task_id)
        if not task:
            return jsonify({'error': '任务不存在'}), 404
        return jsonify({'success': True, 'task': task})

    # ── 同步生成方案（仅调试）— 需要认证 ──
    @app.route('/api/multi-agent/generate-plan-sync', methods=['POST'])
    @jwt_required()
    def generate_research_plan_sync():
        """同步生成（仅用于调试）"""
        try:
            current_user_id = int(get_jwt_identity())
            data = request.get_json()
            user_id = data.get('user_id')
            student_input = data.get('student_input', '')

            if not user_id or not student_input:
                return jsonify({'error': '缺少必要参数: user_id 和 student_input'}), 400

            current_user = User.query.get(current_user_id)
            if current_user_id != user_id and current_user.user_type != 'admin':
                return jsonify({'error': '只能为自己的账户生成方案'}), 403

            with app.app_context():
                student_profile_data = get_student_profile(user_id)
                from agents import multi_agent_coordinator
                result = multi_agent_coordinator.coordinate_research_plan_generation(
                    student_input, student_profile_data
                )

                if 'error' in result:
                    return jsonify({'error': result['error']}), 500

                final_plan = result.get('final_plan', {})
                process_summary = result.get('process_summary', {})

                required_fields = [
                    'title', 'background', 'clinical_problem', 'scientific_problem',
                    'hypothesis', 'objectives', 'study_design', 'subjects_criteria',
                    'variables_endpoints', 'statistical_analysis', 'innovation',
                    'risks_alternatives', 'timeline'
                ]
                for field in required_fields:
                    if field not in final_plan or not final_plan[field]:
                        final_plan[field] = f"待补充: {field}"

                evidence_data = process_summary.get('evidence_summary', {})
                plan_record = save_research_plan(
                    user_id=user_id,
                    plan_content=final_plan,
                    problem_definition=process_summary.get('problem_definition', {}),
                    evidence=evidence_data,
                    critique=process_summary.get('critique'),
                )

            return jsonify({'success': True, 'plan_id': plan_record.id})

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"研究方案生成失败: {str(e)}\n{tb}")
            return jsonify({'error': f'研究方案生成失败: {str(e)}'}), 500


# ── 创建应用实例 ──
app, socketio = create_app()

# 初始化数据库
with app.app_context():
    db.create_all()


def get_student_profile(user_id: int) -> dict:
    """获取学生画像"""
    try:
        profile = StudentProfile.query.filter_by(user_id=user_id).first()
        if profile:
            return profile.to_dict()
        return {}
    except Exception as e:
        logger.error(f"获取学生画像失败: {str(e)}")
        return {}


def save_research_plan(user_id: int, plan_content: dict, problem_definition: dict, evidence: dict, critique: dict = None, comparison_data: dict = None, evidence_pool: dict = None) -> ResearchPlan:
    """保存研究方案到数据库"""
    try:
        plan_record = ResearchPlan(
            user_id=user_id,
            title=plan_content.get('title', '研究方案'),
            input_type='multi_agent',
            content=_safe_json_dumps(plan_content),
            problem_definition=_safe_json_dumps(problem_definition),
            evidence_summary=_safe_json_dumps(evidence),
            critique_feedback=_safe_json_dumps(critique) if critique else None,
            comparison_data=_safe_json_dumps(comparison_data) if comparison_data else None,
            evidence_pool_data=_safe_json_dumps(evidence_pool) if evidence_pool else None,
        )
        db.session.add(plan_record)
        db.session.commit()
        return plan_record
    except Exception as e:
        db.session.rollback()
        logger.error(f"保存研究方案失败: {str(e)}")
        raise e


def log_action(user_id: int, action: str, module: str, details: str):
    """记录系统日志"""
    try:
        log = SystemLog(
            user_id=user_id,
            action=action,
            module=module,
            details=details
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"记录日志失败: {str(e)}")


# ── 错误处理器 ──
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500


# ============ 日志API端点（需要认证） ============

@app.route('/api/debug/logs', methods=['GET'])
@jwt_required()
def get_debug_logs():
    """获取调试日志"""
    limit = request.args.get('limit', 100, type=int)
    level = request.args.get('level')
    category = request.args.get('category')

    logs = debug_logger.get_logs(limit=limit, level=level, category=category)
    return jsonify({
        'success': True,
        'logs': logs,
        'total': len(logs)
    })

@app.route('/api/debug/logs/clear', methods=['POST'])
@jwt_required()
def clear_debug_logs():
    """清空调试日志"""
    debug_logger.clear_logs()
    return jsonify({'success': True, 'message': '日志已清空'})

@app.route('/api/debug/logs/categories', methods=['GET'])
@jwt_required()
def get_log_categories():
    """获取日志分类"""
    categories = set()
    for log in debug_logger.logs:
        categories.add(log['category'])

    return jsonify({
        'success': True,
        'categories': list(categories)
    })


# ============ PubMed API 端点（需要认证） ============

@app.route('/api/pubmed/recommendations', methods=['POST'])
@jwt_required()
def get_pubmed_recommendations():
    """获取PubMed个性化文献推荐"""
    try:
        data = request.get_json()

        student_profile = data.get('student_profile', {
            "academic_level": "研究生二年级",
            "specialty": "胸部影像",
            "stats_background": "基础统计学知识",
            "ai_background": "了解机器学习基础"
        })

        research_interests = data.get('research_interests', '放射学研究')
        max_results = data.get('max_results', 20)

        from pubmed_recommendation_system import PubMedRecommendationSystem
        recommendation_system = PubMedRecommendationSystem()
        recommendations = recommendation_system.get_personalized_recommendations(
            student_profile=student_profile,
            research_interests=research_interests,
            max_results=max_results
        )

        return jsonify({
            'success': True,
            'data': recommendations
        })

    except Exception as e:
        logger.error(f"PubMed推荐API错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/pubmed/recommendations/search', methods=['POST'])
@jwt_required()
def search_pubmed_literature():
    """根据用户输入的关键词搜索 PubMed 文献（Biopython 实现）"""
    from Bio import Entrez
    import time

    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'success': False, 'error': '请输入搜索关键词'}), 400

        max_results = min(int(data.get('max_results', 30)), 50)
        api_key = app.config.get('PUBMED_API_KEY', '')
        email = app.config.get('PUBMED_EMAIL', '')

        if not email:
            return jsonify({'success': False, 'error': 'PubMed 邮箱未配置，请联系管理员'}), 500

        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key

        fetch_limit = min(max_results * 2, 100)
        handle = Entrez.esearch(
            db='pubmed',
            term=query,
            retmax=fetch_limit,
            sort='date',
            retmode='xml'
        )
        search_data = Entrez.read(handle)
        handle.close()

        idlist = search_data.get('IdList', [])
        if not idlist:
            return jsonify({
                'success': True,
                'data': {
                    'search_query': query,
                    'recommended_papers': [],
                    'total_results': 0,
                    'high_quality_count': 0
                }
            })

        time.sleep(0.15 if api_key else 0.4)

        handle = Entrez.efetch(db='pubmed', id=idlist, retmode='xml')
        xml_data = Entrez.read(handle)
        handle.close()

        papers = []
        for article in xml_data.get('PubmedArticle', []):
            try:
                medline = article.get('MedlineCitation', {})
                article_data = medline.get('Article', {})

                pmid = str(medline.get('PMID', ''))
                title = article_data.get('ArticleTitle', '') or ''
                title = ' '.join(title.split())

                abstract_parts = []
                abstract_node = article_data.get('Abstract', {})
                if abstract_node:
                    for abs_text in abstract_node.get('AbstractText', []):
                        if abs_text:
                            abstract_parts.append(str(abs_text))
                abstract = ' '.join(abstract_parts)
                abstract = ' '.join(abstract.split())

                if not abstract:
                    continue

                authors_list = article_data.get('AuthorList', []) or []
                authors = []
                for author in authors_list[:5]:
                    last = author.get('LastName', '')
                    first = author.get('ForeName', '')
                    if last:
                        authors.append(f"{first} {last}".strip())

                journal = article_data.get('Journal', {}).get('Title', '') or ''

                pubdate = ''
                date_node = article_data.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {})
                if date_node:
                    year = date_node.get('Year', '')
                    month = date_node.get('Month', '')
                    day = date_node.get('Day', '')
                    pubdate = '-'.join(filter(None, [str(year), str(month), str(day)]))

                doi = ''
                for aid in article.get('PubmedData', {}).get('ArticleIdList', []):
                    if aid.attributes.get('IdType') == 'doi':
                        doi = str(aid)
                        break

                ptypes = article_data.get('PublicationTypeList', []) or []
                article_type = str(ptypes[0]) if ptypes else ''

                papers.append({
                    'pmid': pmid,
                    'title': title,
                    'authors': authors,
                    'journal': journal,
                    'pubdate': pubdate,
                    'abstract': abstract,
                    'article_type': article_type,
                    'doi': doi,
                    'pubmed_url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ''
                })
            except Exception:
                continue

        return jsonify({
            'success': True,
            'data': {
                'search_query': query,
                'recommended_papers': papers[:max_results],
                'total_results': len(papers),
                'high_quality_count': 0
            }
        })

    except Exception as e:
        logger.error(f"PubMed搜索API错误: {str(e)}")
        return jsonify({'success': False, 'error': f'搜索失败: {str(e)}'}), 500


# ── 重新生成方案（需要认证） ──
@app.route('/api/research/regenerate', methods=['POST', 'OPTIONS'])
@jwt_required()
def regenerate_research():
    """重新生成研究方案"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200

    try:
        current_user_id = int(get_jwt_identity())
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        user_input = data.get('user_input', '')

        plan_agent = PlanGenerationAgent()
        profile_agent = StudentProfileAgent()

        input_data = {
            'student_profile': profile_agent.parse_student_input(user_input),
            'problem_definition': {'raw_input': user_input},
            'evidence': {},
            'input_parsing': {}
        }
        research_plan = plan_agent.generate_research_plan(input_data)

        return jsonify({
            'status': 'success',
            'research_plan': research_plan
        })

    except Exception as e:
        logger.error(f"重新生成研究方案失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/research/export-latex/<int:plan_id>', methods=['GET', 'OPTIONS'])
@jwt_required()
def export_latex(plan_id):
    """导出 LaTeX 格式研究方案"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200

    try:
        current_user_id = int(get_jwt_identity())
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '方案不存在'}), 404
        if plan.user_id != current_user_id:
            current_user = User.query.get(current_user_id)
            if current_user.user_type != 'admin':
                return jsonify({'error': '无权访问该方案'}), 403

        # 解析方案内容
        content = plan.content
        if isinstance(content, str):
            import json as _json
            try:
                content = _json.loads(content)
            except Exception:
                content = {}
        if isinstance(content, dict) and 'research_proposal' in content:
            content = content['research_proposal']

        # 字段中文映射
        field_names = {
            'title': '研究题目',
            'background': '研究背景',
            'clinical_problem': '临床问题',
            'scientific_problem': '科学问题',
            'hypothesis': '研究假设',
            'objectives': '研究目标',
            'study_design': '研究设计',
            'subjects_criteria': '研究对象与纳排标准',
            'variables_endpoints': '变量与终点',
            'statistical_analysis': '统计分析方案',
            'innovation': '创新点',
            'risks_alternatives': '风险与备选方案',
            'timeline': '实施时间表',
        }

        # 安全转义 LaTeX 特殊字符
        def escape_latex(text):
            if not text:
                return ''
            text = str(text)
            # 先处理反斜杠，再处理其他特殊字符
            replacements = [
                ('\\', '\\textbackslash{}'),
                ('&', '\\&'),
                ('%', '\\%'),
                ('$', '\\$'),
                ('#', '\\#'),
                ('_', '\\_'),
                ('{', '\\{'),
                ('}', '\\}'),
                ('~', '\\textasciitilde{}'),
                ('^', '\\textasciicircum{}'),
            ]
            for old, new in replacements:
                text = text.replace(old, new)
            # 处理换行：分号分隔转为换行
            text = text.replace('；', '\n')
            text = text.replace(';', '\n')
            return text

        # 将分号分隔的内容转为 LaTeX 列表
        def format_latex_list(text):
            """将分号/换行分隔的内容转为 itemize 列表"""
            if not text:
                return ''
            # 统一用换行分割
            text = str(text).replace('；', '\n').replace(';', '\n')
            items = [item.strip() for item in text.split('\n') if item.strip()]
            if len(items) <= 1:
                return escape_latex(text)
            lines = ['\\begin{itemize}[leftmargin=2em]']
            for item in items:
                lines.append(f'  \\item {escape_latex(item)}')
            lines.append('\\end{itemize}')
            return '\n'.join(lines)

        title = escape_latex(content.get('title', '研究方案'))
        created_at = plan.created_at.strftime('%Y-%m-%d') if plan.created_at else ''

        # 构建 LaTeX 文档
        latex_lines = []

        # ── 导言区 ──
        latex_lines.append(r'\documentclass[12pt,a4paper]{article}')
        latex_lines.append(r'\usepackage[UTF8]{ctex}')
        latex_lines.append(r'\usepackage[margin=2.5cm]{geometry}')
        latex_lines.append(r'\usepackage{setspace}')
        latex_lines.append(r'\usepackage{enumitem}')
        latex_lines.append(r'\usepackage{booktabs}')
        latex_lines.append(r'\usepackage{xcolor}')
        latex_lines.append(r'\usepackage{titlesec}')
        latex_lines.append(r'\usepackage{fancyhdr}')
        latex_lines.append(r'\usepackage{hyperref}')
        latex_lines.append('')
        # 标题格式
        latex_lines.append(r'\titleformat{\section}{\large\bfseries}{\thesection}{1em}{}')
        latex_lines.append(r'\titleformat{\subsection}{\normalsize\bfseries}{\thesubsection}{1em}{}')
        latex_lines.append('')
        # 页眉页脚
        latex_lines.append(r'\pagestyle{fancy}')
        latex_lines.append(r'\fancyhf{}')
        latex_lines.append(r'\fancyhead[L]{\small 放射学研究方案}')
        short_title = title[:15] + (r'\,\dots' if len(title) > 15 else '')
        latex_lines.append(r'\fancyhead[R]{\small ' + short_title + '}')
        latex_lines.append(r'\fancyfoot[C]{\small \thepage}')
        latex_lines.append(r'\renewcommand{\headrulewidth}{0.4pt}')
        latex_lines.append('')
        # 行距
        latex_lines.append(r'\onehalfspacing')
        latex_lines.append('')
        # 超链接
        latex_lines.append(r'\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue}')
        latex_lines.append('')
        # ── 标题 ──
        latex_lines.append(r'\begin{document}')
        latex_lines.append('')
        latex_lines.append(r'\begin{center}')
        latex_lines.append(r'  {\LARGE\bfseries ' + title + r'\\[1em]}')
        latex_lines.append(r'  {\large 放射学研究方案\\[0.5em]}')
        latex_lines.append(r'  {\normalsize 生成日期：' + created_at + r'}')
        latex_lines.append(r'\end{center}')
        latex_lines.append('')
        latex_lines.append(r'\vspace{1em}')
        latex_lines.append(r'\noindent\rule{\textwidth}{0.4pt}')
        latex_lines.append('')

        # ── 正文各节 ──
        section_order = [
            ('background', '研究背景'),
            ('clinical_problem', '临床问题'),
            ('scientific_problem', '科学问题'),
            ('hypothesis', '研究假设'),
            ('objectives', '研究目标'),
            ('study_design', '研究设计'),
            ('subjects_criteria', '研究对象与纳排标准'),
            ('variables_endpoints', '变量与终点'),
            ('statistical_analysis', '统计分析方案'),
            ('innovation', '创新点'),
            ('risks_alternatives', '风险与备选方案'),
            ('timeline', '实施时间表'),
        ]

        for field_key, section_name in section_order:
            value = content.get(field_key, '')
            if not value or (isinstance(value, str) and value.strip() == ''):
                continue

            # 跳过"待补充"的内容
            if isinstance(value, str) and '待补充' in value:
                continue

            latex_lines.append(r'\section{' + escape_latex(section_name) + '}')

            # 创新点、研究目标、风险等用列表格式
            if field_key in ('innovation', 'objectives', 'risks_alternatives', 'hypothesis'):
                latex_lines.append(format_latex_list(value))
            elif field_key == 'timeline':
                # 时间表用 tabular 环境
                timeline_text = str(value).replace('；', '\n').replace(';', '\n')
                timeline_items = [item.strip() for item in timeline_text.split('\n') if item.strip()]
                if timeline_items:
                    latex_lines.append(r'\begin{itemize}[leftmargin=2em]')
                    for item in timeline_items:
                        latex_lines.append(f'  \\item {escape_latex(item)}')
                    latex_lines.append(r'\end{itemize}')
                else:
                    latex_lines.append(escape_latex(value))
            else:
                # 长文本段落
                formatted = escape_latex(value)
                # 保留原始换行
                for para in formatted.split('\n'):
                    if para.strip():
                        latex_lines.append(para + r'\\')
                latex_lines.append('')

            latex_lines.append('')

        # ── 文献推荐 ──
        if plan.evidence_summary:
            try:
                evidence = plan.evidence_summary
                if isinstance(evidence, str):
                    import json as _json
                    evidence = _json.loads(evidence)
                papers = evidence.get('recommended_literature', {}).get('recommended_papers', [])
                if papers:
                    latex_lines.append(r'\section{推荐文献}')
                    latex_lines.append(r'\begin{enumerate}[leftmargin=2em]')
                    for i, paper in enumerate(papers[:10]):
                        p_title = escape_latex(paper.get('title', ''))
                        p_authors = escape_latex(paper.get('authors', ''))
                        p_journal = escape_latex(paper.get('journal', ''))
                        p_date = escape_latex(paper.get('pubdate', ''))
                        latex_lines.append(f'  \\item {p_title}')
                        if p_authors:
                            latex_lines.append(f'    \\\\ \\textit{{{p_authors}}}')
                        if p_journal:
                            latex_lines.append(f'    \\\\ {p_journal}, {p_date}')
                    latex_lines.append(r'\end{enumerate}')
                    latex_lines.append('')
            except Exception as e:
                logger.warning(f"文献推荐导出失败: {e}")

        # ── 结束 ──
        latex_lines.append(r'\vfill')
        latex_lines.append(r'\begin{center}')
        latex_lines.append(r'\noindent\rule{0.5\textwidth}{0.4pt}\\[0.5em]')
        latex_lines.append(r'{\small 本研究方案由放射学多智能体研究系统自动生成}')
        latex_lines.append(r'\end{center}')
        latex_lines.append('')
        latex_lines.append(r'\end{document}')

        latex_content = '\n'.join(latex_lines)

        # 返回文件
        from io import BytesIO
        buffer = BytesIO(latex_content.encode('utf-8'))
        filename = f"{content.get('title', 'research_plan').replace(' ', '_')}.tex"
        # 清理文件名中的非法字符
        import re
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

        return send_file(
            buffer,
            mimetype='application/x-tex',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"LaTeX导出失败: {str(e)}\n{tb}")
        return jsonify({'error': f'LaTeX导出失败: {str(e)}'}), 500


@app.route('/api/research/export-pdf/<int:plan_id>', methods=['GET', 'OPTIONS'])
@jwt_required()
def export_pdf(plan_id):
    """导出真正的 PDF 格式研究方案（reportlab）"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200

    try:
        current_user_id = int(get_jwt_identity())
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '方案不存在'}), 404
        if plan.user_id != current_user_id:
            current_user = User.query.get(current_user_id)
            if current_user.user_type != 'admin':
                return jsonify({'error': '无权访问该方案'}), 403

        content = plan.content
        if isinstance(content, str):
            import json as _json
            try:
                content = _json.loads(content)
            except Exception:
                content = {}
        if isinstance(content, dict) and 'research_proposal' in content:
            content = content['research_proposal']

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.colors import HexColor
        from io import BytesIO
        import os

        buffer = BytesIO()

        # 尝试注册中文字体
        font_name = 'Helvetica'
        chinese_fonts = [
            ('C:/Windows/Fonts/msyh.ttc', '微软雅黑'),
            ('C:/Windows/Fonts/simsun.ttc', '宋体'),
            ('C:/Windows/Fonts/simhei.ttf', '黑体'),
        ]
        for font_path, font_label in chinese_fonts:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('ChineseFont', font_path))
                    font_name = 'ChineseFont'
                    break
                except Exception:
                    continue

        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=25*mm, rightMargin=25*mm,
            topMargin=20*mm, bottomMargin=20*mm
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Title'],
            fontName=font_name, fontSize=18, leading=24, spaceAfter=6,
            textColor=HexColor('#1a1a2e'))
        subtitle_style = ParagraphStyle('CustomSubtitle', parent=styles['Normal'],
            fontName=font_name, fontSize=10, leading=14, spaceAfter=12,
            textColor=HexColor('#555555'))
        heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
            fontName=font_name, fontSize=13, leading=18, spaceBefore=12, spaceAfter=4,
            textColor=HexColor('#16213e'))
        body_style = ParagraphStyle('CustomBody', parent=styles['Normal'],
            fontName=font_name, fontSize=10, leading=16, spaceAfter=6,
            textColor=HexColor('#333333'))

        story = []

        # 标题
        story.append(Paragraph(content.get('title', '研究方案'), title_style))
        story.append(Paragraph(f'放射学研究方案 | 生成日期：{plan.created_at.strftime("%Y-%m-%d") if plan.created_at else ""}', subtitle_style))
        story.append(HRFlowable(width='100%', thickness=1, color=HexColor('#cccccc'), spaceAfter=10))

        # 各节
        section_order = [
            ('background', '研究背景'),
            ('clinical_problem', '临床问题'),
            ('scientific_problem', '科学问题'),
            ('hypothesis', '研究假设'),
            ('objectives', '研究目标'),
            ('study_design', '研究设计'),
            ('subjects_criteria', '研究对象与纳排标准'),
            ('variables_endpoints', '变量与终点'),
            ('statistical_analysis', '统计分析方案'),
            ('innovation', '创新点'),
            ('risks_alternatives', '风险与备选方案'),
            ('timeline', '实施时间表'),
        ]

        for field_key, section_name in section_order:
            value = content.get(field_key, '')
            if not value or not isinstance(value, str) or not value.strip():
                continue
            if '待补充' in value:
                continue

            story.append(Paragraph(section_name, heading_style))

            # 分号分隔转多行
            parts = value.replace('；', '\n').replace(';', '\n').split('\n')
            for part in parts:
                part = part.strip()
                if part:
                    # 转义 XML 特殊字符
                    part = part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(part, body_style))

            story.append(Spacer(1, 4*mm))

        # 页脚
        story.append(Spacer(1, 10*mm))
        story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#cccccc')))
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
            fontName=font_name, fontSize=8, textColor=HexColor('#999999'))
        story.append(Paragraph('本研究方案由放射学多智能体研究系统自动生成', footer_style))

        doc.build(story)
        buffer.seek(0)

        safe_title = str(content.get('title', f'方案_{plan_id}')).replace('/', '_').replace('\\', '_')[:50]
        return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                        download_name=f'{safe_title}.pdf')

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"PDF导出失败: {str(e)}\n{tb}")
        return jsonify({'error': f'PDF导出失败: {str(e)}'}), 500


@app.route('/api/research/export-bibtex/<int:plan_id>', methods=['GET', 'OPTIONS'])
@jwt_required()
def export_bibtex(plan_id):
    """导出推荐文献为 BibTeX 格式"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'OK'}), 200

    try:
        current_user_id = int(get_jwt_identity())
        plan = ResearchPlan.query.get(plan_id)
        if not plan:
            return jsonify({'error': '方案不存在'}), 404
        if plan.user_id != current_user_id:
            current_user = User.query.get(current_user_id)
            if current_user.user_type != 'admin':
                return jsonify({'error': '无权访问该方案'}), 403

        evidence = plan.evidence_summary
        if isinstance(evidence, str):
            import json as _json
            try:
                evidence = _json.loads(evidence)
            except Exception:
                evidence = {}
        papers = evidence.get('recommended_literature', {}).get('recommended_papers', [])

        if not papers:
            return jsonify({'error': '该方案暂无推荐文献'}), 404

        bibtex_entries = []
        for i, paper in enumerate(papers):
            pmid = paper.get('pmid', f'unknown{i}')
            title = paper.get('title', '').replace('{', '').replace('}', '')
            authors = paper.get('authors', [])
            if isinstance(authors, list):
                author_str = ' and '.join(authors[:5])
            else:
                author_str = str(authors)
            journal = paper.get('journal', '')
            year = (paper.get('pubdate', '') or '')[:4]
            doi = paper.get('doi', '')

            entry = f"@article{{pmid{pmid},\n"
            entry += f"  title = {{{title}}},\n"
            entry += f"  author = {{{author_str}}},\n"
            entry += f"  journal = {{{journal}}},\n"
            if year:
                entry += f"  year = {{{year}}},\n"
            if doi:
                entry += f"  doi = {{{doi}}},\n"
            entry += f"  pmid = {{{pmid}}}\n"
            entry += "}\n"
            bibtex_entries.append(entry)

        bibtex_content = '\n'.join(bibtex_entries)

        from io import BytesIO
        buffer = BytesIO(bibtex_content.encode('utf-8'))
        return send_file(buffer, mimetype='application/x-bibtex', as_attachment=True,
                        download_name=f'references_{plan_id}.bib')

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"BibTeX导出失败: {str(e)}\n{tb}")
        return jsonify({'error': f'BibTeX导出失败: {str(e)}'}), 500


if __name__ == '__main__':
    socketio.run(app, debug=True, use_reloader=False, host='0.0.0.0', port=5002)

