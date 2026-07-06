import os
import re
from pathlib import Path

# 项目根目录（backend/ 的父目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 后端目录（config.py 所在目录）
BACKEND_ROOT = Path(__file__).resolve().parent

# 加载 .env 文件（如果存在）
# 使用哨兵变量防止 re-entrant import 导致 Config 类尚未初始化就被引用
if not os.environ.get('_DOTENV_LOADED'):
    try:
        from dotenv import load_dotenv
        env_path = PROJECT_ROOT / '.env'
        if env_path.exists():
            load_dotenv(env_path)
        os.environ['_DOTENV_LOADED'] = '1'
    except ImportError:
        pass


# ── LLM 模型预设（公共配置，不含 API Key） ──
# 每个用户有自己的 API Key，提供商定义是全局的
LLM_PRESETS = {
    'longcat': {
        'label': 'LongCat 2.0 Preview',
        'base_url': 'https://api.longcat.chat/anthropic',
        'model': 'LongCat-2.0',
        'api_key_label': 'LongCat API Key',
        'api_key_placeholder': 'sk-xxxxxxxxxxxxxxxx',
        'icon': '🐱',
        'description': 'LongCat 2.0 预览版，兼容 Anthropic API 格式',
        'format': 'anthropic',
    },
    'deepseek': {
        'label': 'DeepSeek V4 Flash',
        'base_url': 'https://api.ssopen.top/v1',
        'model': 'deepseek-v4-flash',
        'api_key_label': 'API Key',
        'api_key_placeholder': 'sk-xxxxxxxxxxxxxxxx',
        'icon': '🔍',
        'description': 'DeepSeek V4 Flash，通过 api.ssopen.top 代理',
        'format': 'openai',
    },
    'gpt54': {
        'label': 'GPT-5.4 Mini',
        'base_url': 'https://api.ssopen.top/v1',
        'model': 'gpt-5.4-mini',
        'api_key_label': 'API Key',
        'api_key_placeholder': 'sk-xxxxxxxxxxxxxxxx',
        'icon': '🤖',
        'description': 'GPT-5.4 Mini，通过 api.ssopen.top 代理',
        'format': 'openai',
    },
}

# 默认提供商（新用户默认使用）
DEFAULT_PROVIDER = 'gpt54'

# 默认 API Key（从环境变量读取，禁止硬编码）
DEFAULT_API_KEY = os.environ.get('DEFAULT_API_KEY', '')


class Config:
    """应用配置类 — 所有敏感信息均从环境变量读取，禁止硬编码"""

    # ── 数据库配置 ──
    _default_db_path = str(BACKEND_ROOT / 'instance' / 'research_system.db')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{_default_db_path}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── JWT 配置 ──
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 86400))  # 默认 24 小时

    # ── LongCat / Anthropic API 配置 ──
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.longcat.chat/anthropic')
    ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'LongCat-2.0')
    ANTHROPIC_SMALL_FAST_MODEL = os.environ.get('ANTHROPIC_SMALL_FAST_MODEL', 'LongCat-2.0')

    # 兼容旧配置
    CLAUDE_API_KEY = ANTHROPIC_API_KEY
    CLAUDE_API_URL = ANTHROPIC_BASE_URL

    # ── DeepSeek API 配置 ──
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
    DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
    DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

    # ── OpenAI API 配置 ──
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o')

    # ── 应用配置 ──
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    PORT = int(os.environ.get('PORT', 5002))

    # ── 文件上传配置 ──
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = str(PROJECT_ROOT / 'uploads')

    # ── PubMed API 配置 ──
    PUBMED_API_KEY = os.environ.get('PUBMED_API_KEY', '')
    PUBMED_BASE_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    PUBMED_EMAIL = os.environ.get('PUBMED_EMAIL', '')

    # ── 日志配置 ──
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    @classmethod
    def get_all_presets(cls):
        """获取所有模型预设（公共配置，不含 API Key）"""
        result = {}
        for key, preset in LLM_PRESETS.items():
            result[key] = {
                'label': preset['label'],
                'icon': preset['icon'],
                'base_url': preset['base_url'],
                'model': preset['model'],
                'api_key_label': preset['api_key_label'],
                'api_key_placeholder': preset['api_key_placeholder'],
                'description': preset['description'],
                'format': preset.get('format', 'openai'),
            }
        return result

    @classmethod
    def get_preset(cls, provider: str):
        """获取指定提供商的公共配置"""
        if provider not in LLM_PRESETS:
            raise ValueError(f'未知的 provider: {provider}')
        return LLM_PRESETS[provider]

    @classmethod
    def test_provider_connection(cls, provider: str, api_key: str,
                                base_url: str = None, model: str = None) -> dict:
        """测试指定提供商的连接"""
        import requests

        preset = cls.get_preset(provider)
        base_url = base_url or preset['base_url']
        model = model or preset['model']
        provider_format = preset.get('format', 'openai')

        try:
            if provider_format == 'anthropic':
                resp = requests.post(
                    f"{base_url.rstrip('/')}/v1/messages",
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {api_key}',
                        'anthropic-version': '2023-06-01',
                    },
                    json={
                        'model': model,
                        'max_tokens': 50,
                        'messages': [{'role': 'user', 'content': '回复"连接成功"三个字'}],
                    },
                    timeout=15,
                )
            else:
                resp = requests.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {api_key}',
                    },
                    json={
                        'model': model,
                        'max_tokens': 50,
                        'messages': [{'role': 'user', 'content': '回复"连接成功"三个字'}],
                    },
                    timeout=15,
                )

            if resp.status_code == 200:
                return {
                    'success': True,
                    'message': f'{preset["label"]} 连接正常',
                    'provider': provider,
                    'model': model,
                }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {resp.status_code}: {resp.text[:200]}',
                    'provider': provider,
                }

        except requests.exceptions.Timeout:
            return {'success': False, 'error': '连接超时，请检查 Base URL 和网络'}
        except requests.exceptions.ConnectionError as e:
            return {'success': False, 'error': f'连接失败: {str(e)[:100]}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @classmethod
    def validate(cls):
        """启动时校验必要配置，缺失则给出明确提示"""
        missing = []
        if not cls.ANTHROPIC_API_KEY:
            missing.append('ANTHROPIC_API_KEY')
        if not cls.SECRET_KEY:
            missing.append('SECRET_KEY')
        if not cls.JWT_SECRET_KEY:
            missing.append('JWT_SECRET_KEY')
        if not cls.PUBMED_API_KEY:
            missing.append('PUBMED_API_KEY (PubMed 搜索功能将受限)')
        if not cls.PUBMED_EMAIL:
            missing.append('PUBMED_EMAIL (PubMed 搜索功能将受限)')
        return missing
