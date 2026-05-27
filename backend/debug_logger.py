"""
实时调试日志系统 - 通过WebSocket推送后台操作日志
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Callable
from enum import Enum

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    API_CALL = "API_CALL"
    AI_RESPONSE = "AI_RESPONSE"
    AGENT_ACTION = "AGENT_ACTION"
    LITERATURE_SEARCH = "LITERATURE_SEARCH"
    PLAN_GENERATION = "PLAN_GENERATION"
    CRITIQUE = "CRITIQUE"
    REVISION = "REVISION"

class DebugLogger:
    """实时调试日志记录器"""

    def __init__(self):
        self.logs: List[Dict] = []
        self.subscribers: List[Callable] = []
        self.max_logs = 1000

    def subscribe(self, callback: Callable):
        """订阅日志更新"""
        self.subscribers.append(callback)

    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        if callback in self.subscribers:
            self.subscribers.remove(callback)

    def _notify_subscribers(self, log_entry: Dict):
        """通知所有订阅者"""
        for callback in self.subscribers:
            try:
                callback(log_entry)
            except Exception as e:
                print(f"通知订阅者失败: {e}")

    def log(self, level: LogLevel, message: str, data: Dict = None, category: str = "general"):
        """记录日志"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level.value,
            'message': message,
            'category': category,
            'data': data or {}
        }

        self.logs.append(log_entry)

        # 保持日志数量在限制内
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]

        # 通知订阅者
        self._notify_subscribers(log_entry)

        # 同时打印到控制台
        self._print_log(log_entry)

    def _print_log(self, log_entry: Dict):
        """打印日志到控制台"""
        timestamp = log_entry['timestamp']
        level = log_entry['level']
        message = log_entry['message']
        category = log_entry['category']

        print(f"[{timestamp}] [{level}] [{category}] {message}")

        if log_entry['data']:
            print(f"  数据: {json.dumps(log_entry['data'], ensure_ascii=False, indent=2)}")

    def api_call(self, api_name: str, method: str, url: str, headers: Dict = None, payload: Dict = None):
        """记录API调用"""
        self.log(
            LogLevel.API_CALL,
            f"调用 {api_name} API",
            {
                'api_name': api_name,
                'method': method,
                'url': url,
                'headers': {k: v for k, v in (headers or {}).items() if k.lower() not in ['authorization', 'api-key']},
                'payload': payload
            },
            category='api'
        )

    def api_response(self, api_name: str, status_code: int, response_data: Dict = None, error: str = None):
        """记录API响应"""
        self.log(
            LogLevel.AI_RESPONSE if 'anthropic' in api_name.lower() else LogLevel.INFO,
            f"{api_name} API 响应: {status_code}",
            {
                'api_name': api_name,
                'status_code': status_code,
                'response': response_data,
                'error': error
            },
            category='api'
        )

    def agent_action(self, agent_name: str, action: str, input_data: Dict = None, output_data: Dict = None):
        """记录智能体动作"""
        self.log(
            LogLevel.AGENT_ACTION,
            f"智能体 {agent_name}: {action}",
            {
                'agent_name': agent_name,
                'action': action,
                'input': input_data,
                'output': output_data
            },
            category='agent'
        )

    def prompt_sent(self, model: str, prompt: str, max_tokens: int = None):
        """记录发送的完整Prompt"""
        self.log(
            LogLevel.DEBUG,
            f"发送Prompt到 {model}（长度={len(prompt)}）",
            {
                'model': model,
                'prompt': prompt,
                'prompt_length': len(prompt),
                'max_tokens': max_tokens
            },
            category='prompt'
        )

    def ai_response_received(self, model: str, response: str, tokens_used: int = None):
        """记录AI响应（完整）"""
        self.log(
            LogLevel.AI_RESPONSE,
            f"收到 {model} 响应（长度={len(response)}）",
            {
                'model': model,
                'response': response,
                'response_length': len(response),
                'tokens_used': tokens_used
            },
            category='ai'
        )

    def get_logs(self, limit: int = 100, level: str = None, category: str = None) -> List[Dict]:
        """获取日志"""
        logs = self.logs

        if level:
            logs = [log for log in logs if log['level'] == level]

        if category:
            logs = [log for log in logs if log['category'] == category]

        return logs[-limit:]

    def clear_logs(self):
        """清空日志"""
        self.logs = []

    # 多智能体专用日志方法
    def literature_search(self, message: str, data: Dict = None):
        """记录文献检索日志"""
        self.log(LogLevel.LITERATURE_SEARCH, message, data, "literature_search")

    def plan_generation(self, message: str, data: Dict = None):
        """记录方案生成日志"""
        self.log(LogLevel.PLAN_GENERATION, message, data, "plan_generation")

    def critique(self, message: str, data: Dict = None):
        """记录批判评估日志"""
        self.log(LogLevel.CRITIQUE, message, data, "critique")

    def revision(self, message: str, data: Dict = None):
        """记录修订日志"""
        self.log(LogLevel.REVISION, message, data, "revision")

# 全局调试日志实例
debug_logger = DebugLogger()
