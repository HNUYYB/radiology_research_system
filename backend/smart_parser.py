#!/usr/bin/env python3
# coding=utf-8
"""
Smart Input Parser with LLM Enhancement

This module provides advanced input parsing capabilities using LLM for semantic understanding,
replacing simple keyword matching with intelligent analysis.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from enum import Enum

# 导入现有的API客户端
from api_clients import anthropic_client

logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """置信度级别"""
    HIGH = "high"      # > 0.8 - 高度确信
    MEDIUM = "medium"  # 0.6-0.8 - 中等确信
    LOW = "low"        # < 0.6 - 低确信，需要人工干预


class SmartParser:
    """智能输入解析器 - 使用LLM进行深度语义理解"""

    def __init__(self):
        self.disease_domains = [
            '肺结节', '肺癌', '脑卒中', '脑梗死', '脑出血', '脑肿瘤',
            '乳腺癌', '肝癌', '胃癌', '结肠癌', '前列腺癌',
            '心脏病', '冠状动脉狭窄', '心肌梗死', '心律失常',
            '骨折', '骨质疏松', '关节炎', '椎间盘突出',
            '肺炎', '肺结核', '肝硬化', '肾病'
        ]

        self.technical_methods = [
            '深度学习', '机器学习', '人工智能', '影像组学', '神经网络',
            'CNN', 'RNN', 'Transformer', 'U-Net', 'ResNet', 'YOLO',
            '扩散模型', '因果推断', '图神经网络', 'NeRF', '联邦学习',
            '对比学习', '元学习', '持续学习', '胶囊网络', '神经微分方程',
            '拓扑数据分析', '隐式神经表示', '知识蒸馏', '自监督学习',
            '传统算法', '统计学方法', '计算机辅助诊断'
        ]

        self.research_tasks = [
            '诊断', '检测', '分割', '分类', '预测', '预后',
            '筛查', '识别', '量化', '评估', '监测'
        ]

    def parse_input(self, user_input: str, context: Dict = None) -> Dict:
        """主解析函数 - 使用LLM进行智能解析"""
        try:
            # 使用LLM进行深度解析
            llm_result = self._call_llm_parser(user_input, context or {})

            # 验证和增强解析结果
            validated_result = self._validate_and_enhance(llm_result, user_input)

            # 计算置信度
            confidence = self._calculate_confidence(validated_result, user_input)

            # 如果置信度太低，返回错误而不是猜测
            if confidence['level'] == ConfidenceLevel.LOW.value:
                return {
                    'success': False,
                    'error': '无法准确理解您的输入，请提供更详细的研究描述',
                    'suggestions': self._generate_input_suggestions(user_input),
                    'confidence': confidence
                }

            return {
                'success': True,
                'parsed_result': validated_result,
                'confidence': confidence,
                'metadata': {
                    'parser_version': '2.0',
                    'method': 'llm_enhanced',
                    'input_length': len(user_input)
                }
            }

        except Exception as e:
            logger.error(f"智能解析失败: {str(e)}")
            raise

    def _call_llm_parser(self, user_input: str, context: Dict) -> Dict:
        """调用LLM进行输入解析"""
        prompt = self._build_parsing_prompt(user_input, context)

        try:
            response = anthropic_client.call_longcat_api(
                prompt,
                max_tokens=1500
            )

            # 尝试解析JSON响应
            try:
                result = json.loads(response)
                return result
            except json.JSONDecodeError:
                # 如果LLM没有返回有效的JSON，使用备用解析
                return self._extract_info_from_text(response)

        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}")
            raise

    def _build_parsing_prompt(self, user_input: str, context: Dict) -> str:
        """构建LLM提示词"""
        grade = context.get('grade', '未知')
        specialty = context.get('specialty', '医学影像')

        prompt = f"""您是一个专业的医学影像研究输入解析器。请分析以下用户输入，提取关键信息。

用户输入: "{user_input}"

用户背景:
- 年级: {grade}
- 专业: {specialty}

请提取以下信息并以JSON格式返回:
{{
  "disease_domain": "疾病领域（如：肺结节、脑卒中等，如未明确提及则为null）",
  "technical_methods": ["技术方法列表"],
  "research_task": "主要研究任务（诊断/检测/分割等）",
  "research_objectives": "研究目标和期望结果",
  "data_requirements": "数据需求描述",
  "innovation_focus": "创新点或特色",
  "key_concepts": ["关键概念列表"],
  "ambiguity_level": "输入的模糊程度（low/medium/high）",
  "clarity_score": "输入清晰度评分（0-1）"
}}

重要指导原则:
1. 只有当用户明确提及相关疾病时才提取疾病领域，避免猜测
2. 仔细识别技术方法和研究任务
3. 如果信息不明确，请如实反映，不要编造
4. 对于模糊或不清楚的部分，标记为null或空列表
5. 重点关注用户的真实意图，而不是关键词匹配

请确保返回有效的JSON格式。"""

        return prompt

    def _validate_and_enhance(self, llm_result: Dict, original_input: str) -> Dict:
        """验证和增强LLM解析结果"""
        validated = llm_result.copy()

        # 验证疾病领域
        if validated.get('disease_domain'):
            # 确保疾病领域在预定义列表中
            if validated['disease_domain'] not in self.disease_domains:
                # 检查是否是已知疾病的变体
                matched_disease = self._find_closest_disease(validated['disease_domain'])
                if matched_disease:
                    validated['disease_domain'] = matched_disease
                else:
                    validated['disease_domain'] = None

        # 验证技术方法
        if validated.get('technical_methods'):
            validated['technical_methods'] = [
                method for method in validated['technical_methods']
                if method in self.technical_methods or len(method) > 1
            ]

        # 验证研究任务
        if validated.get('research_task'):
            if validated['research_task'] not in self.research_tasks:
                # 尝试找到最接近的研究任务
                closest_task = self._find_closest_task(validated['research_task'])
                if closest_task:
                    validated['research_task'] = closest_task
                else:
                    validated['research_task'] = None

        # 添加原始输入的备份
        validated['original_input'] = original_input

        return validated

    def _calculate_confidence(self, parsed_result: Dict, original_input: str) -> Dict:
        """计算解析结果的置信度"""
        score = 0.0
        factors = []

        # 疾病领域置信度
        if parsed_result.get('disease_domain'):
            score += 0.3
            factors.append("明确提及疾病领域")
        else:
            factors.append("未明确提及疾病领域")

        # 技术方法置信度
        if parsed_result.get('technical_methods') and len(parsed_result['technical_methods']) > 0:
            score += 0.25
            factors.append("明确提及技术方法")
        else:
            factors.append("技术方法不明确")

        # 研究任务置信度
        if parsed_result.get('research_task'):
            score += 0.25
            factors.append("明确提及研究任务")
        else:
            factors.append("研究任务不明确")

        # 输入长度和清晰度
        input_length = len(original_input)
        if input_length > 50:
            score += 0.1
            factors.append("输入详细")
        elif input_length < 20:
            factors.append("输入过于简短")

        # 清晰度评分
        clarity_score = parsed_result.get('clarity_score', 0.5)
        try:
            clarity_score = float(clarity_score)
        except (ValueError, TypeError):
            clarity_score = 0.5
        score += clarity_score * 0.1

        # 确定置信度级别
        if score >= 0.8:
            level = ConfidenceLevel.HIGH.value
        elif score >= 0.6:
            level = ConfidenceLevel.MEDIUM.value
        else:
            level = ConfidenceLevel.LOW.value

        return {
            'score': round(score, 2),
            'level': level,
            'factors': factors,
            'clarity_score': clarity_score
        }

    def _find_closest_disease(self, disease: str) -> Optional[str]:
        """找到最接近的已知疾病"""
        for known_disease in self.disease_domains:
            if disease in known_disease or known_disease in disease:
                return known_disease
        return None

    def _find_closest_task(self, task: str) -> Optional[str]:
        """找到最接近的已知研究任务"""
        for known_task in self.research_tasks:
            if task in known_task or known_task in task:
                return known_task
        return None

    def _extract_info_from_text(self, text: str) -> Dict:
        """从LLM文本响应中提取信息（备用方法）"""
        # 简单的文本解析作为备用
        result = {
            'disease_domain': None,
            'technical_methods': [],
            'research_task': None,
            'research_objectives': None,
            'key_concepts': [],
            'ambiguity_level': 'high',
            'clarity_score': 0.3
        }

        # 检查疾病领域
        for disease in self.disease_domains:
            if disease in text:
                result['disease_domain'] = disease
                break

        # 检查技术方法
        for method in self.technical_methods:
            if method in text:
                result['technical_methods'].append(method)

        # 检查研究任务
        for task in self.research_tasks:
            if task in text:
                result['research_task'] = task
                break

        return result

    def _generate_input_suggestions(self, user_input: str) -> List[str]:
        """生成输入改进建议"""
        suggestions = []

        if len(user_input) < 30:
            suggestions.append("请提供更详细的研究描述，包括具体的研究目标和方法")

        if not any(word in user_input for word in ['研究', '分析', '检测', '诊断', '预测']):
            suggestions.append("请明确说明您的研究任务（如：诊断、检测、分割、预测等）")

        if not any(word in user_input for word in ['深度学习', '机器学习', 'AI', '算法', '方法']):
            suggestions.append("请提及您计划使用的技术方法或算法")

        suggestions.append("可以包括：研究领域、技术方法、预期目标、数据需求等信息")

        return suggestions


def create_smart_parser():
    """创建智能解析器实例"""
    return SmartParser()
