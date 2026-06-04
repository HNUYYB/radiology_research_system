"""
LLM 模型设置 API — 提供商配置（公共）与 API Key（私有）分离

GET    /api/settings/llm              — 获取所有可用提供商预设 + 当前用户的 API Key
POST   /api/settings/llm/key          — 保存/更新当前用户的 API Key
POST   /api/settings/llm/switch       — 切换当前用户的提供商
POST   /api/settings/llm/test         — 测试连接（用当前用户的 API Key）
DELETE /api/settings/llm/key          — 清除当前用户的 API Key（恢复默认）
"""

import logging
import requests
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from config import Config, LLM_PRESETS, DEFAULT_PROVIDER
from models import db, User

logger = logging.getLogger(__name__)

llm_settings_bp = Blueprint('llm_settings', __name__)


@llm_settings_bp.route('', methods=['GET'])
@jwt_required()
def get_llm_settings():
    """获取所有可用提供商预设 + 当前用户的 API Key 状态"""
    try:
        presets = Config.get_all_presets()
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)

        # 用户的 API Key 和提供商偏好
        user_provider = user.llm_provider if user and user.llm_provider else DEFAULT_PROVIDER
        has_custom_key = bool(user and user.llm_api_key)

        return jsonify({
            'success': True,
            'presets': presets,
            'user_provider': user_provider,
            'has_custom_key': has_custom_key,
            'default_provider': DEFAULT_PROVIDER,
        })
    except Exception as e:
        logger.error(f"获取 LLM 配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_settings_bp.route('/key', methods=['POST'])
@jwt_required()
def save_user_api_key():
    """保存/更新当前用户的 API Key

    请求体:
    {
        "api_key": "sk-xxx...",
        "provider": "deepseek"  // 可选，不提供则保持当前选择
    }
    """
    try:
        data = request.get_json()
        if not data or not data.get('api_key', '').strip():
            return jsonify({'success': False, 'error': '请输入 API Key'}), 400

        api_key = data['api_key'].strip()
        provider = data.get('provider', '').strip()

        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        user.llm_api_key = api_key
        if provider:
            if provider not in LLM_PRESETS:
                return jsonify({
                    'success': False,
                    'error': f'不支持的 provider: {provider}',
                    'available': list(LLM_PRESETS.keys()),
                }), 400
            user.llm_provider = provider

        db.session.commit()

        logger.info(f"用户 {user.username} 保存了 API Key (provider={provider or user.llm_provider})")

        return jsonify({
            'success': True,
            'message': 'API Key 已保存',
            'user_provider': user.llm_provider,
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"保存 API Key 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_settings_bp.route('/key', methods=['DELETE'])
@jwt_required()
def clear_user_api_key():
    """清除当前用户的 API Key（恢复默认）"""
    try:
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        user.llm_api_key = None
        user.llm_provider = DEFAULT_PROVIDER
        db.session.commit()

        return jsonify({'success': True, 'message': '已恢复默认配置', 'user_provider': DEFAULT_PROVIDER})
    except Exception as e:
        db.session.rollback()
        logger.error(f"清除 API Key 失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_settings_bp.route('/switch', methods=['POST'])
@jwt_required()
def switch_provider():
    """切换当前用户的提供商

    请求体:
    {
        "provider": "deepseek"
    }
    """
    try:
        data = request.get_json()
        if not data or not data.get('provider', '').strip():
            return jsonify({'success': False, 'error': '缺少 provider 参数'}), 400

        provider = data['provider'].strip()
        if provider not in LLM_PRESETS:
            return jsonify({
                'success': False,
                'error': f'不支持的 provider: {provider}',
                'available': list(LLM_PRESETS.keys()),
            }), 400

        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        user.llm_provider = provider
        db.session.commit()

        preset = LLM_PRESETS[provider]
        logger.info(f"用户 {user.username} 切换至: {provider} ({preset['label']})")

        return jsonify({
            'success': True,
            'message': f'已切换至 {preset["label"]}',
            'user_provider': provider,
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"切换提供商失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_settings_bp.route('/test', methods=['POST'])
@jwt_required()
def test_llm_connection():
    """测试当前 LLM 连接（用当前用户的 API Key）

    请求体（可选）:
    {
        "provider": "deepseek",   // 不传则测试当前用户选择的提供商
    }
    """
    try:
        data = request.get_json() or {}
        current_user_id = int(get_jwt_identity())
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'success': False, 'error': '用户不存在'}), 404

        provider = data.get('provider', user.llm_provider or DEFAULT_PROVIDER)
        if provider not in LLM_PRESETS:
            return jsonify({'success': False, 'error': f'不支持的 provider: {provider}'}), 400

        # 获取提供商的公共配置
        preset = Config.get_preset(provider)
        # 使用用户自己的 API Key（如果没有则用默认）
        api_key = user.llm_api_key if user.llm_api_key else data.get('api_key', '')

        if not api_key:
            return jsonify({
                'success': False,
                'error': '请先保存 API Key',
            }), 400

        base_url = preset['base_url']
        model = preset['model']
        provider_format = preset['format']

        # 发送测试请求
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
                return jsonify({
                    'success': True,
                    'message': f'{preset["label"]} 连接正常',
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
