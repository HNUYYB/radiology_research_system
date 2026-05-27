"""
LLM 模型设置 API

GET  /api/settings/llm       — 获取当前 LLM 配置和所有可用预设
POST /api/settings/llm/switch — 切换 LLM 模型 provider
POST /api/settings/llm/test   — 测试当前 LLM 连接
"""

import logging
import requests
from flask import Blueprint, request, jsonify
from config import Config, LLM_PRESETS

logger = logging.getLogger(__name__)

llm_settings_bp = Blueprint('llm_settings', __name__)


@llm_settings_bp.route('', methods=['GET'])
def get_llm_settings():
    """获取当前 LLM 配置和所有可用模型预设"""
    try:
        active = Config.get_active_llm_config()
        presets = Config.get_all_presets()

        # 检查每个 provider 是否有配置 API Key
        for key, preset in presets.items():
            api_key_env = LLM_PRESETS[key]['api_key_env']
            preset['has_key'] = bool(
                __import__('os').environ.get(api_key_env, '') or
                getattr(Config, api_key_env, None)
            )

        return jsonify({
            'success': True,
            'active_provider': active['provider'],
            'active_label': active['label'],
            'active_icon': active['icon'],
            'active_config': {
                'provider': active['provider'],
                'base_url': active['base_url'],
                'model': active['model'],
                'has_key': bool(active['api_key']),
                'api_key_env': active['api_key_env'],
                'description': active['description'],
            },
            'presets': presets,
        })
    except Exception as e:
        logger.error(f"获取 LLM 配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_settings_bp.route('/switch', methods=['POST'])
def switch_llm():
    """切换 LLM 模型 provider 并更新配置

    请求体:
    {
        "provider": "deepseek",
        "api_key": "sk-xxx...",        // 可选，不提供则使用已有
        "base_url": "https://...",      // 可选，不提供则使用预设默认值
        "model": "deepseek-chat",       // 可选，不提供则使用预设默认值
        "save_to_env": true             // 是否持久化到 .env 文件，默认 true
    }
    """
    try:
        data = request.get_json()
        if not data or 'provider' not in data:
            return jsonify({'success': False, 'error': '缺少 provider 参数'}), 400

        provider = data['provider']
        if provider not in LLM_PRESETS:
            return jsonify({
                'success': False,
                'error': f'不支持的 provider: {provider}',
                'available': list(LLM_PRESETS.keys()),
            }), 400

        api_key = data.get('api_key')
        base_url = data.get('base_url')
        model = data.get('model')
        save_to_env = data.get('save_to_env', True)

        # 如果没传 api_key，尝试从已有环境变量读取
        if api_key is None:
            api_key_env = LLM_PRESETS[provider]['api_key_env']
            api_key = __import__('os').environ.get(api_key_env, '')

        if not api_key:
            return jsonify({
                'success': False,
                'error': f'请先输入 {LLM_PRESETS[provider]["api_key_label"]}',
            }), 400

        # 持久化到 .env
        if save_to_env:
            Config.update_llm_env(
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )

        # 运行时切换
        Config.set_active_provider(provider)

        # 同时更新 ANTHROPIC_ 兼容字段（让现有 AnthropicClient 能工作）
        # LongCat 本身就是 Anthropic 兼容的，DeepSeek/OpenAI 需要在 AnthropicClient 中处理
        if provider == 'longcat':
            import os
            os.environ['ANTHROPIC_BASE_URL'] = base_url or LLM_PRESETS[provider]['base_url']
            os.environ['ANTHROPIC_MODEL'] = model or LLM_PRESETS[provider]['model']
            if api_key:
                os.environ['ANTHROPIC_API_KEY'] = api_key
        else:
            # 对于 DeepSeek / OpenAI，也写入兼容字段
            # AnthropicClient 会根据 provider 适配
            import os
            os.environ['ANTHROPIC_BASE_URL'] = base_url or LLM_PRESETS[provider]['base_url']
            os.environ['ANTHROPIC_MODEL'] = model or LLM_PRESETS[provider]['model']
            if api_key:
                os.environ['ANTHROPIC_API_KEY'] = api_key

        active = Config.get_active_llm_config()
        logger.info(f"LLM 已切换至: {provider} ({active['label']})")

        return jsonify({
            'success': True,
            'message': f'已切换至 {LLM_PRESETS[provider]["label"]}',
            'active': {
                'provider': active['provider'],
                'label': active['label'],
                'icon': active['icon'],
                'base_url': active['base_url'],
                'model': active['model'],
                'has_key': bool(active['api_key']),
            },
        })
    except Exception as e:
        logger.error(f"切换 LLM 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_settings_bp.route('/test', methods=['POST'])
def test_llm_connection():
    """测试当前 LLM 连接是否正常

    请求体（可选）:
    {
        "provider": "deepseek",   // 不传则测试当前激活的
        "api_key": "sk-xxx...",
        "base_url": "https://...",
        "model": "deepseek-chat"
    }
    """
    try:
        data = request.get_json() or {}

        provider = data.get('provider', Config.get_active_provider())
        if provider not in LLM_PRESETS:
            return jsonify({'success': False, 'error': f'不支持的 provider: {provider}'}), 400

        api_key = data.get('api_key', '')
        base_url = data.get('base_url', LLM_PRESETS[provider]['base_url'])
        model = data.get('model', LLM_PRESETS[provider]['model'])

        if not api_key:
            api_key_env = LLM_PRESETS[provider]['api_key_env']
            api_key = __import__('os').environ.get(api_key_env, '')

        if not api_key:
            return jsonify({
                'success': False,
                'error': f'请先输入 {LLM_PRESETS[provider]["api_key_label"]}',
            }), 400

        # 发送测试请求
        if provider == 'longcat':
            # Anthropic 兼容格式
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
        elif provider == 'openai':
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
        elif provider == 'deepseek':
            # DeepSeek 使用 OpenAI 兼容格式
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
        else:
            return jsonify({'success': False, 'error': f'未实现 {provider} 的测试逻辑'}), 400

        if resp.status_code == 200:
            return jsonify({
                'success': True,
                'message': f'{LLM_PRESETS[provider]["label"]} 连接正常',
                'provider': provider,
                'model': model,
                'http_status': resp.status_code,
            })
        else:
            return jsonify({
                'success': False,
                'error': f'HTTP {resp.status_code}: {resp.text[:200]}',
                'provider': provider,
                'http_status': resp.status_code,
            }), 200

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': '连接超时，请检查 Base URL 和网络'}), 200
    except requests.exceptions.ConnectionError as e:
        return jsonify({'success': False, 'error': f'连接失败: {str(e)[:100]}'}), 200
    except Exception as e:
        logger.error(f"测试 LLM 连接失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
