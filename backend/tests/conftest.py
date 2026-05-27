"""
pytest 配置和共享 Fixtures
"""
import os
import sys
import pytest

# 把 backend 目录加入 sys.path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# 设置测试环境变量（必须在导入 app 之前）
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-testing-only')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-key-for-testing-only')
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-api-key')
os.environ.setdefault('PUBMED_API_KEY', '')
os.environ.setdefault('PUBMED_EMAIL', 'test@example.com')
os.environ.setdefault('FRONTEND_URL', 'http://localhost:3024')


@pytest.fixture(scope='session')
def app():
    """创建测试用 Flask 应用"""
    from app import create_app
    from models import db as _db

    app, socketio = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'JWT_SECRET_KEY': 'test-jwt-secret-key',
        'SECRET_KEY': 'test-secret-key',
    })

    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield app


@pytest.fixture(scope='function')
def db(app):
    """每个测试函数独立的数据库会话"""
    from models import db as _db

    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield _db
        _db.session.rollback()


@pytest.fixture(scope='function')
def client(app, db):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def sample_user(db):
    """创建一个测试学生用户"""
    from models import User
    from werkzeug.security import generate_password_hash
    user = User(
        username='testuser',
        email='test@example.com',
        user_type='student',
        grade='研一',
        specialty='胸部',
        password_hash=generate_password_hash('TestPassword123')
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(db):
    """创建一个管理员用户"""
    from models import User
    from werkzeug.security import generate_password_hash
    user = User(
        username='adminuser',
        email='admin@example.com',
        user_type='admin',
        password_hash=generate_password_hash('AdminPassword123')
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def expert_user(db):
    """创建一个专家用户"""
    from models import User
    from werkzeug.security import generate_password_hash
    user = User(
        username='expertuser',
        email='expert@example.com',
        user_type='expert',
        password_hash=generate_password_hash('ExpertPassword123')
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def auth_headers(client, sample_user):
    """获取认证 token 并返回请求头"""
    response = client.post('/api/auth/login', json={
        'username': 'testuser',
        'password': 'TestPassword123'
    })
    data = response.get_json()
    token = data.get('access_token', '')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


@pytest.fixture
def admin_auth_headers(client, admin_user):
    """获取管理员认证 token"""
    response = client.post('/api/auth/login', json={
        'username': 'adminuser',
        'password': 'AdminPassword123'
    })
    data = response.get_json()
    token = data.get('access_token', '')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


@pytest.fixture
def expert_auth_headers(client, expert_user):
    """获取专家认证 token"""
    response = client.post('/api/auth/login', json={
        'username': 'expertuser',
        'password': 'ExpertPassword123'
    })
    data = response.get_json()
    token = data.get('access_token', '')
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
