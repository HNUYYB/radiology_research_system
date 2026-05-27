#!/usr/bin/env python3
# coding=utf-8
"""
Input Adapter System
"""

import re
import json
from typing import Dict, List, Tuple, Any
from enum import Enum


class InputType(Enum):
    RESEARCH_IDEA = "research_idea"
    TECHNICAL_SPECS = "technical_specs"
    ACADEMIC_PROFILE = "academic_profile"
    SPECIFIC_QUESTION = "specific_question"
    GENERAL_QUERY = "general_query"


class InputAdapter:
    """Smart input adapter"""

    def __init__(self):
        self.input_classifiers = {
            InputType.RESEARCH_IDEA: self._classify_research_idea,
            InputType.TECHNICAL_SPECS: self._classify_technical_specs,
            InputType.ACADEMIC_PROFILE: self._classify_academic_profile,
            InputType.SPECIFIC_QUESTION: self._classify_specific_question
        }

    def adapt_input(self, user_input: str, context: Dict = None) -> Dict:
        """Main adaptation function"""
        input_type = self.classify_input_type(user_input, context)

        strategies = {
            InputType.RESEARCH_IDEA: self._strategy_research_idea,
            InputType.TECHNICAL_SPECS: self._strategy_technical_specs,
            InputType.ACADEMIC_PROFILE: self._strategy_academic_profile,
            InputType.SPECIFIC_QUESTION: self._strategy_specific_question,
            InputType.GENERAL_QUERY: self._strategy_general_query
        }

        strategy_result = strategies[input_type](user_input, context or {})

        return {
            "input_type": input_type.value,
            "confidence": strategy_result.get("confidence", 0.8),
            "processed_input": strategy_result.get("processed_input", user_input),
            "strategy_used": strategy_result.get("strategy_name", "default"),
            "recommendations": strategy_result.get("recommendations", []),
            "next_steps": strategy_result.get("next_steps", []),
            "metadata": strategy_result.get("metadata", {})
        }

    def classify_input_type(self, user_input: str, context: Dict = None) -> InputType:
        """Classify input type"""
        scores = {}

        for input_type, classifier in self.input_classifiers.items():
            scores[input_type] = classifier(user_input, context or {})

        best_type = max(scores.items(), key=lambda x: x[1])[0]

        if scores[best_type] < 0.3:
            return InputType.GENERAL_QUERY

        return best_type

    def _classify_research_idea(self, user_input: str, context: Dict) -> float:
        """Classify research idea input"""
        research_keywords = ['研究', '课题', '项目', '方向', '想法', '思路', '探索', '分析', '评估', '创新']
        medical_keywords = ['影像', 'CT', 'MRI', '诊断', '检测', '分割', '分类', '预测', '筛查', '肺结节', '脑卒中', '乳腺癌']

        research_score = sum(1 for kw in research_keywords if kw in user_input)
        medical_score = sum(1 for kw in medical_keywords if kw in user_input)

        # 增强研究意图识别
        if '想' in user_input and ('研究' in user_input or '做' in user_input):
            research_score += 3
        if '希望' in user_input and ('研究' in user_input or '探索' in user_input):
            research_score += 2
        if '想要' in user_input and ('做' in user_input or '实现' in user_input):
            research_score += 2

        total_score = (research_score * 0.6 + medical_score * 0.4) / 8
        return min(total_score, 1.0)

    def _classify_technical_specs(self, user_input: str, context: Dict) -> float:
        """Classify technical specs input"""
        technical_keywords = ['设备', '硬件', '资源', '条件', '病例', '数据', 'GPU', '内存']

        spec_patterns = [
            r'\d+\s*(例|个|张|份|台|GB|G|小时|天|月)',
            r'(有|具备|拥有|可用|现有)',
            r'(需要|要求|需求|期望)'
        ]

        keyword_score = sum(1 for kw in technical_keywords if kw in user_input)
        pattern_score = sum(1 for pattern in spec_patterns if re.search(pattern, user_input))

        total_score = (keyword_score * 0.6 + pattern_score * 0.4) / 8
        return min(total_score, 1.0)

    def _classify_academic_profile(self, user_input: str, context: Dict) -> float:
        """Classify academic profile input"""
        academic_keywords = ['年级', '专业', '背景', '基础', '水平', '经验', '研一', '研二', '博士', '硕士']

        grade_patterns = [
            r'(研|博|本|硕)[一二三四]',
            r'(研究|博士|硕士|本科)生',
            r'(年级|专业|方向)'
        ]

        skill_patterns = [
            r'(统计|AI|编程|机器学习|深度学习).*(基础|水平|经验)',
            r'(会|掌握|熟悉|了解).*(Python|R|MATLAB)'
        ]

        keyword_score = sum(1 for kw in academic_keywords if kw in user_input)
        grade_score = sum(1 for pattern in grade_patterns if re.search(pattern, user_input))
        skill_score = sum(1 for pattern in skill_patterns if re.search(pattern, user_input))

        total_score = (keyword_score * 0.4 + grade_score * 0.3 + skill_score * 0.3) / 6
        return min(total_score, 1.0)

    def _classify_specific_question(self, user_input: str, context: Dict) -> float:
        """Classify specific question input"""
        question_patterns = [
            r'^(如何|怎样|怎么|什么|哪个|哪些|哪种)',
            r'(吗|呢|？|\?|什么|哪个)',
            r'(建议|推荐|选择|比较|区别|优劣|效果|准确率|性能)'
        ]

        specific_keywords = ['方法', '模型', '算法', '技术', '方案', '工具', 'U-Net', 'DeepLab', 'ResNet', '准确率', '效果', '性能']

        question_score = sum(1 for pattern in question_patterns if re.search(pattern, user_input))
        keyword_score = sum(1 for kw in specific_keywords if kw in user_input)

        # 增强疑问句识别
        if '？' in user_input or '?' in user_input:
            question_score += 2
        if '哪种' in user_input or '哪个' in user_input:
            question_score += 2

        total_score = (question_score * 0.7 + keyword_score * 0.3) / 6
        return min(total_score, 1.0)

    def _strategy_research_idea(self, user_input: str, context: Dict) -> Dict:
        """Research idea strategy"""
        return {
            "strategy_name": "research_idea_analysis",
            "confidence": 0.85,
            "processed_input": self._extract_research_elements(user_input),
            "recommendations": self._generate_innovation_suggestions(user_input),
            "next_steps": [
                "完善研究目标和假设",
                "收集相关文献支持",
                "确定技术路线和方法"
            ],
            "metadata": {
                "feasibility": "medium",
                "innovation_level": "standard",
                "complexity": "medium"
            }
        }

    def _strategy_technical_specs(self, user_input: str, context: Dict) -> Dict:
        """Technical specs strategy"""
        return {
            "strategy_name": "technical_specs_matching",
            "confidence": 0.8,
            "processed_input": self._parse_technical_specifications(user_input),
            "recommendations": [
                "基于您的数据规模推荐最适合的方法",
                "考虑使用迁移学习方法",
                "建议数据增强策略"
            ],
            "next_steps": [
                "确认技术条件的准确性",
                "选择最适合的技术方案",
                "制定资源配置计划"
            ],
            "metadata": {
                "resource_level": "medium",
                "optimization_potential": ["数据采样", "分布式训练"],
                "risk_factors": ["样本量限制", "计算资源约束"]
            }
        }

    def _strategy_academic_profile(self, user_input: str, context: Dict) -> Dict:
        """Academic profile strategy"""
        return {
            "strategy_name": "academic_profile_adaptation",
            "confidence": 0.9,
            "processed_input": self._parse_academic_background(user_input),
            "recommendations": [
                "根据您的背景推荐合适难度的项目",
                "建议学习路径和技能提升计划",
                "设定阶段性研究目标"
            ],
            "next_steps": [
                "确认学术背景的准确性",
                "选择合适的入门项目",
                "制定技能提升计划"
            ],
            "metadata": {
                "experience_level": "intermediate",
                "difficulty_adjustment": {
                    "model_complexity": "medium",
                    "implementation_guidance": "detailed"
                },
                "skill_gaps": ["深度学习", "医学图像处理"]
            }
        }

    def _strategy_specific_question(self, user_input: str, context: Dict) -> Dict:
        """Specific question strategy"""
        return {
            "strategy_name": "specific_question_resolution",
            "confidence": 0.88,
            "processed_input": self._analyze_question_type(user_input),
            "recommendations": [
                "提供多种解决方案对比",
                "推荐最适合的具体方法",
                "提供实施建议和注意事项"
            ],
            "next_steps": [
                "深入理解问题核心",
                "评估建议方案适用性",
                "选择最优解决方案"
            ],
            "metadata": {
                "question_category": "method_selection",
                "implementation_complexity": "medium"
            }
        }

    def _strategy_general_query(self, user_input: str, context: Dict) -> Dict:
        """General query strategy"""
        return {
            "strategy_name": "general_query_response",
            "confidence": 0.6,
            "processed_input": user_input,
            "recommendations": [
                "请提供更具体的研究想法或需求",
                "描述您的学术背景和技术条件",
                "说明具体的研究目标和期望成果"
            ],
            "next_steps": [
                "明确研究意图和目标",
                "提供必要的背景信息",
                "描述具体的技术需求"
            ],
            "metadata": {
                "needs_clarification": True,
                "suggested_prompts": [
                    "您想研究什么具体的医学问题？",
                    "您的技术条件和数据资源如何？",
                    "您的学术背景和研究经验如何？"
                ]
            }
        }

    def _extract_research_elements(self, user_input: str) -> Dict:
        """Extract research elements"""
        return {
            "disease_focus": self._extract_disease_focus(user_input),
            "anatomical_region": self._extract_anatomical_region(user_input),
            "imaging_modality": self._extract_imaging_modality(user_input),
            "task_type": self._extract_task_type(user_input),
            "innovation_approach": self._extract_innovation_approach(user_input)
        }

    def _extract_disease_focus(self, text: str) -> str:
        """Extract disease focus"""
        diseases = {
            '肺结节': ['肺结节', '肺部结节'],
            '肺癌': ['肺癌', '肺肿瘤'],
            '脑卒中': ['脑卒中', '中风'],
            '脑肿瘤': ['脑肿瘤', '颅内肿瘤'],
            '肝癌': ['肝癌', '肝肿瘤'],
            '乳腺癌': ['乳腺癌', '乳腺肿瘤']
        }

        for disease, keywords in diseases.items():
            if any(keyword in text for keyword in keywords):
                return disease
        return ""

    def _extract_anatomical_region(self, text: str) -> str:
        """Extract anatomical region"""
        anatomy_map = {
            '胸部': ['胸部', '胸', '肺部'],
            '脑部': ['脑', '头部', '颅内'],
            '肝脏': ['肝', '肝脏'],
            '乳腺': ['乳腺', '乳房'],
            '心脏': ['心脏', '心血管'],
            '骨骼': ['骨', '骨骼'],
            '腹部': ['腹部', '腹腔']
        }

        for region, keywords in anatomy_map.items():
            if any(keyword in text for keyword in keywords):
                return region
        return ""

    def _extract_imaging_modality(self, text: str) -> str:
        """Extract imaging modality"""
        modality_map = {
            'CT': ['CT', '计算机断层'],
            'MRI': ['MRI', '磁共振'],
            'X线': ['X线', 'X光'],
            '超声': ['超声', 'B超'],
            '钼靶': ['钼靶', '乳腺钼靶'],
            'PET': ['PET', '正电子']
        }

        for modality, keywords in modality_map.items():
            if any(keyword in text for keyword in keywords):
                return modality
        return 'CT'

    def _extract_task_type(self, text: str) -> str:
        """Extract task type"""
        if any(word in text for word in ['检测', '识别', '发现']):
            return '检测'
        elif any(word in text for word in ['分割', '划分', '区域']):
            return '分割'
        elif any(word in text for word in ['分类', '鉴别', '区分']):
            return '分类'
        elif any(word in text for word in ['预测', '预后', '转归']):
            return '预测'
        elif any(word in text for word in ['诊断', '辅助诊断', '筛查']):
            return '诊断'
        else:
            return '分析'

    def _extract_innovation_approach(self, text: str) -> str:
        """Extract innovation approach"""
        if any(word in text for word in ['早期', '早筛', '筛查']):
            return '早期筛查'
        elif any(word in text for word in ['精准', '精确', '准确']):
            return '精准医疗'
        elif any(word in text for word in ['实时', '快速', '效率']):
            return '高效诊断'
        elif any(word in text for word in ['多模态', '多参数', '多序列']):
            return '多模态融合'
        elif any(word in text for word in ['可解释', '解释性', '透明']):
            return '可解释AI'
        elif any(word in text for word in ['小样本', '少样本', '数据稀缺']):
            return '小样本学习'
        else:
            return '智能辅助'

    def _generate_innovation_suggestions(self, user_input: str) -> List[str]:
        """Generate innovation suggestions"""
        suggestions = []
        elements = self._extract_research_elements(user_input)

        disease = elements.get("disease_focus", "")
        task_type = elements.get("task_type", "")
        innovation = elements.get("innovation_approach", "")

        if disease and task_type:
            suggestions.append(f"探索{disease}的新型{task_type}方法")

        if "早期筛查" in innovation:
            suggestions.append("考虑开发基于生物标志物的早期筛查模型")

        if "多模态融合" in innovation:
            suggestions.append("设计跨模态特征对齐与融合策略")

        if "可解释AI" in innovation:
            suggestions.append("集成可解释性模块")

        return suggestions

    def _parse_technical_specifications(self, text: str) -> Dict:
        """Parse technical specifications"""
        specs = {
            "data_scale": self._extract_data_scale(text),
            "hardware_resources": self._extract_hardware_resources(text),
            "time_constraints": self._extract_time_constraints(text)
        }
        return specs

    def _extract_data_scale(self, text: str) -> Dict:
        """Extract data scale"""
        patterns = {
            "case_count": r'(\d+)\s*(例|个|份|张|病例)',
            "image_count": r'(\d+)\s*(张|幅|图像)',
            "data_size": r'(\d+)\s*(GB|G|MB|M)'
        }

        result = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                result[key] = int(match.group(1))

        return result

    def _extract_hardware_resources(self, text: str) -> Dict:
        """Extract hardware resources"""
        hardware = {}

        gpu_match = re.search(r'(GPU|显卡).*?(\d+)\s*(GB|G)', text)
        if gpu_match:
            hardware["gpu_memory"] = int(gpu_match.group(2))

        ram_match = re.search(r'(内存|RAM).*?(\d+)\s*(GB|G)', text)
        if ram_match:
            hardware["ram"] = int(ram_match.group(2))

        return hardware

    def _extract_time_constraints(self, text: str) -> Dict:
        """Extract time constraints"""
        time_info = {}

        time_match = re.search(r'(\d+)\s*(天|周|月|年|小时)', text)
        if time_match:
            time_info["duration"] = int(time_match.group(1))
            time_info["unit"] = time_match.group(2)

        return time_info

    def _parse_academic_background(self, text: str) -> Dict:
        """Parse academic background"""
        background = {
            "grade": self._extract_grade(text),
            "specialty": self._extract_specialty(text),
            "skills": self._extract_skills(text),
            "experience": self._extract_experience(text)
        }
        return background

    def _extract_grade(self, text: str) -> str:
        """Extract grade"""
        grade_patterns = {
            '研一': r'研一|研1|研究生一年级',
            '研二': r'研二|研2|研究生二年级',
            '研三': r'研三|研3|研究生三年级',
            '博一': r'博一|博1|博士一年级',
            '博二': r'博二|博2|博士二年级',
            '博士': r'博士|博士生'
        }

        for grade, pattern in grade_patterns.items():
            if re.search(pattern, text):
                return grade
        return ""

    def _extract_specialty(self, text: str) -> str:
        """Extract specialty"""
        specialties = ['放射学', '影像医学', '生物医学工程', '计算机科学', '人工智能']

        for specialty in specialties:
            if specialty in text:
                return specialty
        return ""

    def _extract_skills(self, text: str) -> List[str]:
        """Extract skills"""
        skills = []
        known_skills = {
            'Python': ['Python', 'python'],
            'MATLAB': ['MATLAB', 'matlab'],
            'R': ['R语言', 'R编程'],
            '统计学': ['统计', '统计学'],
            '机器学习': ['机器学习', 'ML', '深度学习', 'DL', 'AI'],
            '图像处理': ['图像处理', '计算机视觉']
        }

        for skill, keywords in known_skills.items():
            if any(keyword in text for keyword in keywords):
                skills.append(skill)

        return skills

    def _extract_experience(self, text: str) -> str:
        """Extract experience level"""
        if any(word in text for word in ['新手', '初学者', '零基础', '不会']):
            return 'beginner'
        elif any(word in text for word in ['有一定', '基础', '了解', '熟悉']):
            return 'intermediate'
        elif any(word in text for word in ['熟练', '精通', '经验丰富', '擅长']):
            return 'advanced'
        else:
            return 'unknown'

    def _analyze_question_type(self, user_input: str) -> Dict:
        """Analyze question type"""
        if any(word in user_input for word in ['方法', '模型', '算法']):
            return {"category": "method_selection", "focus": "methodology"}
        elif any(word in user_input for word in ['准确率', '性能', '效果']):
            return {"category": "performance_evaluation", "focus": "metrics"}
        elif any(word in user_input for word in ['实现', '代码', '编程']):
            return {"category": "implementation", "focus": "coding"}
        else:
            return {"category": "general", "focus": "overview"}


# Test function
def test_input_adapter():
    """Test input adapter system"""
    print("=== Input Adapter System Test ===\n")

    adapter = InputAdapter()

    test_cases = [
        {
            "name": "Research Idea",
            "input": "我想研究肺结节的早期检测，用深度学习方法",
            "expected_type": InputType.RESEARCH_IDEA
        },
        {
            "name": "Technical Specs",
            "input": "我有500个病例数据，GPU是RTX 3080",
            "expected_type": InputType.TECHNICAL_SPECS
        },
        {
            "name": "Academic Profile",
            "input": "我是研一学生，专业是影像医学，会Python基础",
            "expected_type": InputType.ACADEMIC_PROFILE
        },
        {
            "name": "Specific Question",
            "input": "哪种神经网络模型在医学图像分割中效果最好？",
            "expected_type": InputType.SPECIFIC_QUESTION
        },
        {
            "name": "General Query",
            "input": "医学影像分析",
            "expected_type": InputType.GENERAL_QUERY
        }
    ]

    results = []

    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Input: {test_case['input']}")

        result = adapter.adapt_input(test_case['input'])

        print(f"Detected Type: {result['input_type']}")
        print(f"Strategy: {result['strategy_used']}")
        print(f"Confidence: {result['confidence']:.2f}")

        actual_type = InputType(result['input_type'])
        expected_type = test_case['expected_type']
        is_correct = actual_type == expected_type

        print(f"Expected: {expected_type.value}")
        print(f"Result: {'Correct' if is_correct else 'Wrong'}")

        if result['recommendations']:
            print("Recommendations:")
            for rec in result['recommendations'][:2]:
                print(f"  - {rec}")

        results.append({
            'test_name': test_case['name'],
            'is_correct': is_correct,
            'confidence': result['confidence']
        })

        print("-" * 60)

    # Summary
    total_tests = len(results)
    correct_tests = sum(1 for r in results if r['is_correct'])
    accuracy = correct_tests / total_tests
    avg_confidence = sum(r['confidence'] for r in results) / total_tests

    print(f"\n=== Test Summary ===")
    print(f"Total Tests: {total_tests}")
    print(f"Correct: {correct_tests}")
    print(f"Accuracy: {accuracy:.2%}")
    print(f"Avg Confidence: {avg_confidence:.2f}")

    return results


if __name__ == "__main__":
    test_input_adapter()