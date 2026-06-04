"""
多智能体协同系统 - 放射学研究方案生成
实现了完整的智能体协作流程（ReAct + 工具调用 + 证据池）
"""

import json
import logging
import re
import threading
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# 导入必要的客户端
from api_clients import anthropic_client
from literature_search import search_radiology_literature, literature_search
from debug_logger import debug_logger, LogLevel
from agent_tools import (
    Tool, ToolResult, ALL_TOOLS, get_tools_for_agent, format_tools_for_llm,
    evidence_pool,
)
from evidence_pool import EvidencePool

logger = logging.getLogger(__name__)


def _safe_json_parse(response: str, context: str = "") -> dict:
    """安全解析AI返回的JSON，带多重清理和截断修复"""
    import re as _re

    text = response.strip()

    # 1. 移除 markdown 代码块
    text = _re.sub(r'^```(?:json)?\s*', '', text)
    text = _re.sub(r'\s*```$', '', text)
    text = text.strip()

    # 2. 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. 尝试修复截断的 JSON：找到最后一个完整的 "key": "value" 对，然后补全
    last_complete = text.rfind('"}')
    if last_complete > 0:
        truncated = text[:last_complete + 2]
        open_braces = truncated.count('{') - truncated.count('}')
        open_brackets = truncated.count('[') - truncated.count(']')
        fixed = truncated + ']' * open_brackets + '}' * open_braces
        try:
            result = json.loads(fixed)
            logger.warning(f"JSON解析：通过截断修复成功 [{context}]")
            return result
        except json.JSONDecodeError:
            pass

    # 4. 尝试用正则提取所有 "key": "value" 对，手动构建 dict
    try:
        pairs = _re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', text)
        if pairs:
            result = {k: v for k, v in pairs}
            logger.warning(f"JSON解析：通过正则提取成功 [{context}]，提取了 {len(result)} 个字段")
            return result
    except Exception:
        pass

    # 5. 全部失败
    logger.error(f"JSON解析失败 [{context}]，原始响应前200字符: {text[:200]}")
    raise ValueError(f"无法解析AI返回的JSON [{context}]")


@dataclass
class AgentMessage:
    """智能体消息类"""
    sender: str
    receiver: str
    content: Any
    timestamp: datetime
    message_type: str  # 'request', 'response', 'data', 'error'


# ── Agent 工作记忆 ──
@dataclass
class WorkingMemory:
    """Agent 的工作记忆 - 在 ReAct 循环中累积"""
    entries: List[Dict] = field(default_factory=list)

    def add(self, role: str, content: Any, tool_name: str = None):
        entry = {
            "role": role,  # "thought" / "action" / "observation" / "llm_output"
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if tool_name:
            entry["tool_name"] = tool_name
        self.entries.append(entry)

    def to_context(self) -> str:
        """格式化为 LLM 可读的上下文"""
        lines = []
        for entry in self.entries:
            role = entry["role"]
            content = entry["content"]
            if role == "thought":
                lines.append(f"[思考] {content}")
            elif role == "action":
                lines.append(f"[行动] 调用工具: {content}")
            elif role == "observation":
                lines.append(f"[观察] {content}")
            elif role == "llm_output":
                lines.append(f"[LLM输出] {content}")
            else:
                lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    def last_observation(self) -> str:
        """获取最近的观察"""
        for entry in reversed(self.entries):
            if entry["role"] == "observation":
                return str(entry["content"])
        return ""

    @property
    def action_count(self) -> int:
        return sum(1 for e in self.entries if e["role"] == "action")


# ══════════════════════════════════════════════════════════════
#  重构后的 BaseAgent - 加入 tools + memory + act() 循环
# ══════════════════════════════════════════════════════════════

class BaseAgent:
    """
    智能体基类（ReAct 模式）

    核心升级：
    1. tools: 工具列表，Agent 可自主决定调用
    2. memory: 工作记忆，记录思考-行动-观察链
    3. act(): ReAct 循环入口，子类可覆写 decide() 和 execute_tool()

    子类只需实现：
    - build_system_prompt(): 返回 system prompt
    - build_user_prompt(message): 根据输入消息构建 user prompt
    - parse_final_output(llm_output): 解析 LLM 的最终输出为结构化结果
    - max_steps(): 最大工具调用次数（默认 10）
    """

    def __init__(self, name: str):
        self.name = name
        self.message_history: List[AgentMessage] = []
        self.tools: List[Tool] = get_tools_for_agent(name)
        self.tool_map: Dict[str, Tool] = {t.name: t for t in self.tools}
        self.memory = WorkingMemory()
        logger.info(f"[{name}] 初始化完成，可用工具: {[t.name for t in self.tools]}")

    @staticmethod
    def _safe_dict_get(value, default=None):
        """安全获取dict，如果value是string则尝试JSON解析"""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        return default if default is not None else {}

    def send_message(self, receiver: str, content: Any, message_type: str = 'data') -> AgentMessage:
        """发送消息"""
        message = AgentMessage(
            sender=self.name,
            receiver=receiver,
            content=content,
            timestamp=datetime.now(),
            message_type=message_type
        )
        self.message_history.append(message)
        return message

    def receive_message(self, message: AgentMessage) -> Any:
        """接收消息并处理"""
        self.message_history.append(message)
        return self.process_message(message)

    # ── 子类必须实现的方法 ──

    def build_system_prompt(self) -> str:
        """构建 system prompt（子类实现）"""
        raise NotImplementedError

    def build_user_prompt(self, message: AgentMessage) -> str:
        """根据输入消息构建 user prompt（子类实现）"""
        raise NotImplementedError

    def parse_final_output(self, llm_output: str) -> Any:
        """解析 LLM 最终输出为结构化结果（子类实现）"""
        raise NotImplementedError

    def max_steps(self) -> int:
        """最大工具调用次数"""
        return 10

    # ── ReAct 核心循环 ──

    def process_message(self, message: AgentMessage) -> Any:
        """
        主处理入口 - 支持两种模式：

        模式 1（传统）：子类直接覆写 process_message，完全自定义逻辑
        模式 2（ReAct）：子类覆写 build_system_prompt / build_user_prompt / parse_final_output，
                        本方法自动执行 ReAct 循环

        判断标准：如果子类覆写了 process_message 且不是 BaseAgent.process_message，用模式 1。
        """
        # 重置工作记忆
        self.memory = WorkingMemory()

        # 执行 ReAct 循环
        return self._react_loop(message)

    def _react_loop(self, message: AgentMessage) -> Any:
        """
        ReAct 核心循环：
        1. 构建 prompt（system + user + 工具描述 + 记忆上下文）
        2. 调用 LLM
        3. 解析 LLM 输出
           - 如果是工具调用 → 执行工具 → 记录观察 → 回到步骤 1
           - 如果是最终结果 → 解析并返回
        """
        system_prompt = self.build_system_prompt()
        user_prompt = self.build_user_prompt(message)
        tools_desc = format_tools_for_llm(self.tools)

        for step in range(self.max_steps()):
            # 构建完整 prompt
            memory_context = self.memory.to_context()
            if memory_context:
                full_user_prompt = f"{user_prompt}\n\n## 你的思考和工作记忆\n{memory_context}\n\n请决定下一步行动（调用工具或输出最终结果）："
            else:
                full_user_prompt = f"{user_prompt}\n\n请决定下一步行动（调用工具或输出最终结果）："

            full_prompt = f"{tools_desc}\n\n{full_user_prompt}"

            logger.info(f"[{self.name}] ReAct 循环 step {step + 1}/{self.max_steps()}")

            # 调用 LLM
            try:
                llm_output = anthropic_client.call_longcat_api(
                    full_prompt, max_tokens=2000, system_prompt=system_prompt
                )
            except Exception as e:
                logger.error(f"[{self.name}] LLM 调用失败 (step {step + 1}): {e}")
                return {'error': f'LLM 调用失败: {str(e)}'}

            self.memory.add("llm_output", llm_output[:500])

            # 解析 LLM 输出：判断是工具调用还是最终结果
            parsed = self._parse_llm_decision(llm_output)

            if parsed.get("type") == "tool_call":
                # ── 工具调用 ──
                tool_name = parsed.get("tool", "")
                params = parsed.get("params", {})

                self.memory.add("thought", f"决定调用工具: {tool_name}，参数: {params}")
                logger.info(f"[{self.name}] 调用工具: {tool_name}")

                # 执行工具
                result = self._execute_tool(tool_name, params)
                self.memory.add("observation", result.to_observation(), tool_name=tool_name)

                if not result.success:
                    logger.warning(f"[{self.name}] 工具 {tool_name} 执行失败: {result.error}")

            elif parsed.get("type") == "finish":
                # ── 最终结果 ──
                final_output = parsed.get("result", "")
                logger.info(f"[{self.name}] ReAct 循环完成，共 {step + 1} 步")
                try:
                    return self.parse_final_output(final_output)
                except Exception as e:
                    logger.error(f"[{self.name}] 最终输出解析失败: {e}")
                    return {'error': f'输出解析失败: {str(e)}', 'raw_output': final_output[:500]}

            else:
                # 无法解析，尝试当作最终结果
                logger.warning(f"[{self.name}] 无法解析 LLM 输出，尝试当作最终结果")
                try:
                    return self.parse_final_output(llm_output)
                except Exception:
                    return {'error': '无法解析 LLM 输出', 'raw_output': llm_output[:500]}

        # 超过最大步数
        logger.warning(f"[{self.name}] ReAct 循环超过最大步数 {self.max_steps()}")
        return {'error': f'超过最大工具调用次数 {self.max_steps()}', 'memory': self.memory.to_context()}

    def _parse_llm_decision(self, llm_output: str) -> Dict:
        """
        解析 LLM 输出，判断是工具调用还是最终结果

        期望的工具调用格式：
        {"tool": "工具名", "params": {"参数名": "参数值"}}

        期望的完成格式：
        {"tool": "finish", "params": {"result": "最终输出"}}
        """
        text = llm_output.strip()

        # 尝试提取 JSON
        # 1. 直接解析
        try:
            data = json.loads(text)
            if "tool" in data:
                return {"type": "tool_call" if data["tool"] != "finish" else "finish",
                        "tool": data["tool"], "params": data.get("params", {})}
        except (json.JSONDecodeError, TypeError):
            pass

        # 2. 从文本中提取 JSON
        json_match = re.search(r'\{[^{}]*"tool"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if "tool" in data:
                    return {"type": "tool_call" if data["tool"] != "finish" else "finish",
                            "tool": data["tool"], "params": data.get("params", {})}
            except (json.JSONDecodeError, TypeError):
                pass

        # 3. 没有找到工具调用格式，当作最终结果
        return {"type": "finish", "result": text}

    def _execute_tool(self, tool_name: str, params: Dict) -> ToolResult:
        """执行工具调用"""
        if tool_name == "finish":
            return ToolResult(tool_name="finish", success=True, observation="完成")

        tool = self.tool_map.get(tool_name)
        if not tool:
            return ToolResult(tool_name=tool_name, success=False, error=f"未知工具: {tool_name}")

        # 注入调用者信息
        params.setdefault("retrieved_by", self.name)

        return tool.execute(**params)

    # ── 兼容旧接口 ──

    def log_action(self, action: str, input_data: Dict = None, output_data: Dict = None):
        """记录智能体动作到调试日志"""
        debug_logger.agent_action(
            self.name,
            action,
            input_data=input_data,
            output_data=output_data
        )

    def _check_phrase_match(self, text: str, phrase: str) -> bool:
        """检查文本中是否包含完整短语，避免单字匹配导致的误判"""
        if len(phrase) <= 2:
            pattern = r'\b' + re.escape(phrase) + r'\b'
            return bool(re.search(pattern, text))
        else:
            return phrase in text

    # ── 证据池快捷方法 ──

    def search_evidence(self, query: str, source: str = "pubmed", max_results: int = 20) -> List[Dict]:
        """快捷方法：检索文献并返回结果"""
        if source == "pubmed":
            result = tool_search_pubmed(query=query, max_results=max_results, retrieved_by=self.name)
        elif source == "arxiv":
            result = tool_search_arxiv(query=query, max_results=max_results, retrieved_by=self.name)
        else:
            return []
        return result.data if result.success else []

    def query_evidence(self, topic: str = None, level: int = None, limit: int = 10) -> List[Dict]:
        """快捷方法：查询证据池"""
        result = tool_query_evidence_pool(topic=topic, level=level, limit=limit)
        return result.data if result.success else []

    def get_evidence_context(self, topic: str = None, max_papers: int = 8) -> str:
        """快捷方法：获取格式化的证据上下文"""
        result = tool_get_evidence_for_llm(topic=topic, max_papers=max_papers)
        return result.data if result.success else ""

    def detect_conflicts(self, topic: str = None) -> List[Dict]:
        """快捷方法：检测证据池中的文献冲突"""
        result = tool_detect_conflicts(topic=topic)
        return result.data if result.success else []

class StudentProfileAgent(BaseAgent):
    """学生画像智能体 - 负责解析和结构化学生信息（检索增强版）"""

    def __init__(self):
        super().__init__("StudentProfileAgent")

    def process_message(self, message: AgentMessage) -> Dict:
        """处理学生输入，构建结构化画像（自动注入证据池上下文）"""
        if message.message_type == 'student_input':
            if isinstance(message.content, dict) and 'extracted_info' in message.content:
                return message.content
            else:
                # 【增强】检索该学生方向的常见研究模式，注入证据池
                student_input = message.content if isinstance(message.content, str) else str(message.content)
                self._pre_search_student_patterns(student_input)
                return self.parse_student_input(message.content)
        return {}

    def _pre_search_student_patterns(self, student_input: str):
        """预检索该方向的学生研究模式，为后续 Agent 提供证据基础"""
        try:
            # 提取关键词做简单检索
            specialty = self.extract_specialty(student_input)
            if specialty:
                query = f"{specialty} radiology AI deep learning"
                result = tool_search_pubmed(query=query, max_results=5, retrieved_by="StudentProfileAgent")
                if result.success:
                    logger.info(f"  [StudentProfileAgent] 预检索 '{specialty}' 方向文献 {len(result.data or [])} 入证据池")
        except Exception as e:
            logger.debug(f"  [StudentProfileAgent] 预检索跳过: {e}")

    def parse_student_input(self, student_input) -> Dict:
        """解析学生输入，提取关键信息 - 增强版"""
        import json as _json
        logger.info(f"parse_student_input called with type={type(student_input).__name__}, keys={list(student_input.keys()) if isinstance(student_input, dict) else 'N/A'}")
        try:
            # 检查输入类型
            if isinstance(student_input, dict):
                # 已经包含结构化数据
                if 'extracted_info' in student_input:
                    # 完整的学生画像数据
                    return student_input
                elif 'raw_input' in student_input:
                    # 包含原始输入，需要解析
                    raw_input = student_input['raw_input']
                    # 兼容两种格式：
                    # 1. 嵌套在 structured_profile 中（旧格式）
                    # 2. 平铺在 dict 顶层（新格式，coordinator 直接传入 flat profile）
                    structured_data = student_input.get('structured_profile', {})
                    if not structured_data:
                        # 从顶层提取数据库画像字段
                        structured_data = {
                            'grade': student_input.get('grade', ''),
                            'specialty': student_input.get('specialty', ''),
                            'available_resources': student_input.get('available_resources', []),
                            'case_scale': student_input.get('case_scale', ''),
                            'follow_up_available': student_input.get('follow_up_available', False),
                            'gold_standard_available': student_input.get('gold_standard_available', False),
                            'statistical_background': student_input.get('statistical_background', ''),
                            'ai_background': student_input.get('ai_background', ''),
                            'time_constraint': student_input.get('time_constraint', ''),
                            'target_journal_level': student_input.get('target_journal_level', ''),
                        }

                    # 合并数据库中的结构化信息和从文本中提取的信息
                    extracted_info = self.extract_basic_info(raw_input)

                    # 优先使用数据库中的信息
                    if structured_data:
                        extracted_info.update({
                            'grade': structured_data.get('grade', extracted_info.get('grade', '未知')),
                            'specialty': structured_data.get('specialty', extracted_info.get('specialty', '未知')),
                            'available_resources': structured_data.get('available_resources', extracted_info.get('available_resources', [])),
                            'case_scale': structured_data.get('case_scale', ''),
                            'follow_up_available': structured_data.get('follow_up_available', False),
                            'gold_standard_available': structured_data.get('gold_standard_available', False),
                            'statistical_background': structured_data.get('statistical_background', ''),
                            'ai_background': structured_data.get('ai_background', ''),
                            'time_constraint': structured_data.get('time_constraint', extracted_info.get('time_constraint', '中等')),
                            'target_journal_level': structured_data.get('target_journal_level', '')
                        })

                    logger.info(f"  [ProfileAgent] 合并后: ai_bg={extracted_info.get('ai_background', '')}, "
                               f"stats_bg={extracted_info.get('statistical_background', '')}, "
                               f"grade={extracted_info.get('grade', '')}, "
                               f"time={extracted_info.get('time_constraint', '')}, "
                               f"journal={extracted_info.get('target_journal_level', '')}")

                    profile = {
                        'raw_input': raw_input,
                        'extracted_info': extracted_info,
                        'research_focus': self.identify_research_focus(raw_input),
                        'complexity_level': self.assess_complexity(raw_input),
                        'suggested_approach': self.suggest_approach(raw_input)
                    }
                    return profile
                else:
                    # 未知字典格式，转换为字符串处理
                    student_input = str(student_input)

            # 处理字符串输入
            if not isinstance(student_input, str):
                student_input = str(student_input)

            profile = {
                'raw_input': student_input,
                'extracted_info': self.extract_basic_info(student_input),
                'research_focus': self.identify_research_focus(student_input),
                'complexity_level': self.assess_complexity(student_input),
                'suggested_approach': self.suggest_approach(student_input)
            }
            return profile

        except Exception as e:
            import traceback, sys
            tb = traceback.format_exc()
            exc_type, exc_val, exc_tb = sys.exc_info()
            logger.error(f"学生画像解析失败: [{exc_type.__name__}] {str(e)}\n{tb}")
            print(f"[StudentProfileAgent] 异常类型: {exc_type.__name__}, 异常值: {e}", flush=True)
            return {'error': str(e)}

    def extract_basic_info(self, text) -> Dict:
        """提取基本信息 - 完整版，覆盖画像所需的15个维度"""
        logger.info(f"extract_basic_info called with type={type(text).__name__}")
        # 如果输入是字符串，先用规则提取，再用AI补全缺失维度
        if isinstance(text, str):
            info = self._extract_from_text(text)
            # 对规则提取的结果，用AI补全缺失的关键维度
            info = self._ai_complete_profile(info, text)
            return info

        # 如果输入是字典（结构化数据），合并数据库字段后也用AI补全
        if isinstance(text, dict):
            info = {
                'grade': text.get('grade', '未知'),
                'specialty': text.get('specialty', '未知'),
                'experience_level': self.map_background_to_experience(text),
                'available_resources': text.get('available_resources', []),
                'case_scale': text.get('case_scale', ''),
                'follow_up_available': text.get('follow_up_available', False),
                'gold_standard_available': text.get('gold_standard_available', False),
                'statistical_background': text.get('statistical_background', ''),
                'ai_background': text.get('ai_background', ''),
                'time_constraint': text.get('time_constraint', '中等'),
                'target_journal_level': text.get('target_journal_level', ''),
                # 初始化缺失维度，由AI补全
                'has_data': text.get('has_data', None),
                'data_volume': text.get('data_volume', ''),
                'software_capability': text.get('software_capability', ''),
                'expected_graduation': text.get('expected_graduation', ''),
                'supervisor_support': text.get('supervisor_support', ''),
                'ethical_feasibility': text.get('ethical_feasibility', None),
                'cross_dept_resources': text.get('cross_dept_resources', None),
            }
            # 用AI补全仍未填写的关键维度
            raw_text = text.get('raw_input', '') or str(text)
            info = self._ai_complete_profile(info, raw_text)
            return info

        # 其他类型转换为字符串处理
        return self.extract_basic_info(str(text))

    def _extract_from_text(self, text: str) -> Dict:
        """从自由文本中规则提取基础信息"""
        return {
            # 1. 培养阶段
            'grade': self.extract_grade(text),
            # 2. 亚专业方向
            'specialty': self.extract_specialty(text),
            # 3. 经验水平
            'experience_level': self.extract_experience(text),
            # 4. 可用资源
            'available_resources': self.extract_resources(text),
            # 5. 时间约束
            'time_constraint': self.extract_time_constraint(text),
            # 6. 是否已有数据
            'has_data': self._detect_has_data(text),
            # 7. 数据量
            'data_volume': self._detect_data_volume(text),
            # 8. 是否有金标准
            'gold_standard_available': self._detect_gold_standard(text),
            # 9. 是否有随访
            'follow_up_available': self._detect_follow_up(text),
            # 10. 可用软件能力
            'software_capability': self._detect_software(text),
            # 11. 统计基础
            'statistical_background': self._detect_stats_background(text),
            # 12. AI基础
            'ai_background': self._detect_ai_background(text),
            # 13. 预期毕业时间
            'expected_graduation': self._detect_graduation_time(text),
            # 14. 目标期刊层级
            'target_journal_level': self._detect_journal_target(text),
            # 15. 导师支持程度
            'supervisor_support': self._detect_supervisor_support(text),
            # 16. 伦理可行性
            'ethical_feasibility': self._detect_ethical_feasibility(text),
            # 17. 跨科合作资源
            'cross_dept_resources': self._detect_cross_dept(text),
            # 病例规模（兼容旧字段）
            'case_scale': self._detect_case_scale(text),
        }

    def _ai_complete_profile(self, info: Dict, raw_text: str) -> Dict:
        """用AI补全规则提取未覆盖或未确定的画像维度"""
        from api_clients import anthropic_client

        # 找出尚未确定的字段
        undetermined = []
        for field in ['has_data', 'data_volume', 'gold_standard_available',
                      'follow_up_available', 'software_capability',
                      'statistical_background', 'ai_background',
                      'expected_graduation', 'target_journal_level',
                      'supervisor_support', 'ethical_feasibility',
                      'cross_dept_resources']:
            val = info.get(field)
            if val is None or val == '' or val == '未知':
                undetermined.append(field)

        if not undetermined:
            logger.info("  [ProfileAgent] 所有字段已确定，无需AI补全")
            return info

        logger.info(f"  [ProfileAgent] AI补全字段: {undetermined}")
        logger.info(f"  [ProfileAgent] 补全前: grade={info.get('grade','?')}, ai_bg={info.get('ai_background','?')}, stats_bg={info.get('statistical_background','?')}")

        prompt = f"""
你是一名放射学研究生导师。请根据以下学生的自我描述，补全其研究画像中尚未确定的字段。

学生描述："{raw_text}"

当前已提取的信息：{json.dumps({k: v for k, v in info.items() if k not in undetermined}, ensure_ascii=False)}

请补全以下字段（如果学生描述中没有明确信息，请根据上下文合理推断，无法推断则填"未知"）：
- has_data: 是否已有数据（true/false/null表示不确定）
- data_volume: 数据量描述（如"约500例"、"无数据"、"未知"）
- gold_standard_available: 是否有金标准（如病理确诊、专家共识等）（true/false/不确定）
- follow_up_available: 是否有随访数据（true/false/不确定）
- software_capability: 可用软件/编程能力（如"Python+PyTorch"、"仅SPSS"、"无编程基础"）
- statistical_background: 统计基础水平（"熟练"/"中等"/"基础"/"薄弱"）
- ai_background: AI/ML基础水平（"熟练"/"中等"/"基础"/"薄弱"）
- expected_graduation: 预期毕业时间（如"2027年6月"、"未知"）
- target_journal_level: 目标期刊层级（如"SCI Q1"/"核心期刊"/"未知"）
- supervisor_support: 导师支持程度（"强"/"中等"/"弱"/"未知"）
- ethical_feasibility: 是否具备伦理可行性（true/false/需评估）
- cross_dept_resources: 是否有跨科合作资源（如"有信息科合作"/"无"/"未知"）

返回JSON格式，只包含上述字段。只返回JSON，不要额外文字。
"""

        profile_sp = "你是一名放射学研究生导师。请根据学生描述补全研究画像中尚未确定的字段，只返回JSON格式，不要额外文字。"
        try:
            response = anthropic_client.call_longcat_api(prompt, max_tokens=500, system_prompt=profile_sp)
            ai_data = _safe_json_parse(response, context="StudentProfile._ai_complete_profile")
            for field in undetermined:
                if field in ai_data and ai_data[field] not in (None, '', '未知'):
                    info[field] = ai_data[field]
        except Exception as e:
            logger.warning(f"  [ProfileAgent] AI补全失败，使用默认值: {e}")
        return info

    def _detect_has_data(self, text: str):
        """检测是否已有数据"""
        if any(w in text for w in ['有数据', '有病例', '收集了', '数据库', '已有']):
            return True
        if any(w in text for w in ['没有数据', '无数据', '缺少数据']):
            return False
        return None

    def _detect_data_volume(self, text: str) -> str:
        """检测数据量"""
        import re
        patterns = [
            r'(\d+)\s*(?:例|个|份|张|病例|样本|患者|图像|CT|MRI)',
            (r'(?:数百|几百)\s*(?:例|个|份)', '数百例'),
            (r'(?:上千|几千|数千)\s*(?:例|个|份)', '上千例'),
            (r'(?:几十)\s*(?:例|个|份)', '几十例'),
        ]
        for pat in patterns:
            if isinstance(pat, tuple):
                if pat[0] in text:
                    return pat[1]
            else:
                m = re.search(pat, text)
                if m:
                    return m.group(0)
        return ''

    def _detect_gold_standard(self, text: str) -> str:
        """检测是否有金标准"""
        if any(w in text for w in ['病理', '活检', '手术确诊', '金标准', '专家共识', '确诊']):
            return True
        if any(w in text for w in ['无金标准', '没有病理']):
            return False
        return '未知'

    def _detect_follow_up(self, text: str) -> str:
        """检测是否有随访"""
        if any(w in text for w in ['随访', '复查', '预后', '追踪', 'follow-up', 'follow up']):
            return True
        if any(w in text for w in ['无随访', '没有随访', '失访']):
            return False
        return '未知'

    def _detect_software(self, text: str) -> str:
        """检测软件/编程能力"""
        tools = []
        tool_map = {
            'Python': ['python', 'Python', 'PYTHON'],
            'PyTorch': ['pytorch', 'torch', 'PyTorch'],
            'TensorFlow': ['tensorflow', 'TensorFlow', 'tf'],
            'R语言': ['R语言', 'R编程', 'R studio', 'RStudio'],
            'MATLAB': ['matlab', 'MATLAB'],
            'SPSS': ['spss', 'SPSS'],
            'SAS': ['sas', 'SAS'],
            'ITK-SNAP': ['itk-snap', 'ITK-SNAP'],
            '3D Slicer': ['3d slicer', '3D Slicer', 'slicer'],
            'PyRadiomics': ['pyradiomics', 'PyRadiomics'],
        }
        for tool, keywords in tool_map.items():
            if any(kw in text for kw in keywords):
                tools.append(tool)
        return '、'.join(tools) if tools else ''

    def _detect_stats_background(self, text: str) -> str:
        """检测统计基础"""
        if any(w in text for w in ['精通统计', '熟练统计', '统计专业', '统计学基础好']):
            return '熟练'
        if any(w in text for w in ['会用SPSS', '学过统计', '了解统计', '基础统计']):
            return '基础'
        if any(w in text for w in ['统计薄弱', '不会统计', '没学过统计']):
            return '薄弱'
        if any(w in text for w in ['多元统计', '生存分析', 'Cox回归', 'Logistic回归']):
            return '中等'
        return ''

    def _detect_ai_background(self, text: str) -> str:
        """检测AI基础"""
        if any(w in text for w in ['精通深度学习', '做过AI项目', '发表过AI论文', '熟练AI']):
            return '熟练'
        if any(w in text for w in ['学过机器学习', '了解深度学习', '用过PyTorch', '用过TensorFlow']):
            return '中等'
        if any(w in text for w in ['AI零基础', '没接触过AI', '不会AI']):
            return '薄弱'
        if any(w in text for w in ['机器学习', '深度学习', '神经网络']):
            return '基础'
        return ''

    def _detect_graduation_time(self, text: str) -> str:
        """检测预期毕业时间"""
        import re
        # 匹配年份模式
        m = re.search(r'(20\d{2})\s*年\s*(?:6月|7月|毕业|答辩)', text)
        if m:
            return m.group(0)
        # 根据年级推断
        grade = self.extract_grade(text)
        from datetime import datetime
        year = datetime.now().year
        month = datetime.now().month
        grad_map = {
            '研一': f'{year + 3}年6月' if month <= 6 else f'{year + 3}年6月',
            '研二': f'{year + 2}年6月' if month <= 6 else f'{year + 2}年6月',
            '研三': f'{year + 1}年6月',
            '博一': f'{year + 4}年6月',
            '博二': f'{year + 3}年6月',
            '博三': f'{year + 2}年6月',
        }
        return grad_map.get(grade, '')

    def _detect_journal_target(self, text: str) -> str:
        """检测目标期刊层级"""
        if any(w in text for w in ['Nature', 'Science', 'Cell', 'Lancet', 'NEJM', 'JAMA', '顶刊']):
            return '顶级期刊'
        if any(w in text for w in ['Radiology', 'European Radiology', 'Medical Image Analysis', 'IEEE TMI', 'Q1', '一区']):
            return 'SCI Q1'
        if any(w in text for w in ['Q2', '二区', 'SCI', '英文期刊']):
            return 'SCI Q2'
        if any(w in text for w in ['核心期刊', '中文核心', '北核']):
            return '核心期刊'
        if any(w in text for w in ['普刊', '一般期刊']):
            return '普刊'
        return ''

    def _detect_supervisor_support(self, text: str) -> str:
        """检测导师支持程度"""
        if any(w in text for w in ['导师很支持', '导师有项目', '导师强', '导师资源丰富', '实验室条件好']):
            return '强'
        if any(w in text for w in ['导师放养', '导师不管', '导师不支持', '导师很忙']):
            return '弱'
        if any(w in text for w in ['导师会指导', '有导师带', '导师一般']):
            return '中等'
        return ''

    def _detect_ethical_feasibility(self, text: str):
        """检测伦理可行性"""
        if any(w in text for w in ['回顾性', '脱敏', '已获伦理', '伦理已过']):
            return True
        if any(w in text for w in ['前瞻性', '涉及患者', '需要知情同意', '伦理复杂']):
            return '需评估'
        if any(w in text for w in ['动物实验', '体外']):
            return True
        return None

    def _detect_cross_dept(self, text: str):
        """检测跨科合作资源"""
        if any(w in text for w in ['信息科', '计算机系', '合作', '跨学科', '多学科', '联合']):
            return True
        if any(w in text for w in ['独立', '一个人', '没有合作']):
            return False
        return None

    def _detect_case_scale(self, text: str) -> str:
        """检测病例规模"""
        vol = self._detect_data_volume(text)
        if vol:
            return vol
        return ''

    def map_background_to_experience(self, profile_data: Dict) -> str:
        """将背景信息映射为经验水平"""
        statistical_bg = profile_data.get('statistical_background', '')
        ai_bg = profile_data.get('ai_background', '')
        grade = profile_data.get('grade', '')

        # 基于统计和AI背景判断经验水平
        if '熟练' in statistical_bg or '熟练' in ai_bg:
            return '经验丰富'
        elif '中等' in statistical_bg or '中等' in ai_bg or '基础' in statistical_bg or '基础' in ai_bg:
            return '有一定基础'
        elif grade == '研一':
            return '初学者'
        else:
            return '中等水平'

    def extract_grade(self, text: str) -> str:
        """提取年级信息"""
        grade_patterns = {
            '研一': ['研一', '研1', '硕士一年级', 'graduate year 1'],
            '研二': ['研二', '研2', '硕士二年级', 'graduate year 2'],
            '研三': ['研三', '研3', '硕士三年级', 'graduate year 3'],
            '博士': ['博士', '博士生', 'phd']
        }

        for grade, patterns in grade_patterns.items():
            if any(pattern in text for pattern in patterns):
                return grade
        return '未知'

    def extract_specialty(self, text: str) -> str:
        """提取专业方向"""
        radiology_specialties = {
            '胸部影像': ['胸部', '肺', '胸部CT', '胸部MRI', 'lung', 'chest'],
            '神经影像': ['神经', '脑', '头颈', '神经影像', 'brain', 'neurological'],
            '骨肌影像': ['骨肌', '骨骼', '肌肉', '骨科', 'musculoskeletal'],
            '腹部影像': ['腹部', '肝胆', '腹部CT', 'abdomen'],
            '心血管影像': ['心血管', '心脏', '血管', 'cardiovascular'],
            '乳腺影像': ['乳腺', '乳房', 'breast'],
            '介入放射学': ['介入', 'interventional']
        }

        for specialty, keywords in radiology_specialties.items():
            if any(keyword in text for keyword in keywords):
                return specialty
        return '放射科通用'

    def extract_experience(self, text: str) -> str:
        """提取经验水平"""
        experience_indicators = {
            '初学者': ['新手', '刚开始', '零基础', '第一次', 'beginner'],
            '有一定基础': ['有一定基础', '学过', '了解', 'some experience'],
            '经验丰富': ['熟练', '经验丰富', '做过类似', 'experienced']
        }

        for level, indicators in experience_indicators.items():
            if any(indicator in text for indicator in indicators):
                return level
        return '中等水平'

    def extract_resources(self, text: str) -> List[str]:
        """提取可用资源"""
        resources = []

        # 检查是否有特定资源提及
        if any(word in text for word in ['数据', '病例', 'dataset', 'data available']):
            resources.append('有数据资源')
        if any(word in text for word in ['导师', '老师', 'supervisor', 'mentor']):
            resources.append('有导师指导')
        if any(word in text for word in ['实验室', 'lab', '研究团队']):
            resources.append('有实验室支持')

        return resources if resources else ['基础资源']

    def extract_time_constraint(self, text: str) -> str:
        """提取时间限制"""
        time_patterns = {
            '紧急': ['紧急', '尽快', '马上', 'urgent'],
            '中等': ['几个月', '半年', 'semester'],
            '宽松': ['一年', '长期', 'flexible']
        }

        for constraint, patterns in time_patterns.items():
            if any(pattern in text for pattern in patterns):
                return constraint
        return '中等'

    def identify_research_focus(self, text: str) -> Dict:
        """识别研究重点"""
        focus_areas = {
            '疾病诊断': ['诊断', 'detection', 'diagnosis'],
            '疾病分期': ['分期', 'staging', 'classification'],
            '预后预测': ['预后', '预测', 'prognosis', 'prediction'],
            '治疗评估': ['治疗', '疗效', 'treatment', 'therapy'],
            '影像组学': ['组学', 'radiomics', 'quantitative imaging'],
            '深度学习': ['深度学习', 'deep learning', 'AI', 'artificial intelligence'],
            '传统机器学习': ['机器学习', 'machine learning', '传统算法']
        }

        identified_focus = []
        for area, keywords in focus_areas.items():
            if any(keyword in text for keyword in keywords):
                identified_focus.append(area)

        return {
            'primary_focus': identified_focus[0] if identified_focus else '疾病诊断',
            'secondary_focus': identified_focus[1:] if len(identified_focus) > 1 else [],
            'technical_approach': self.identify_technical_approach(text)
        }

    def identify_technical_approach(self, text: str) -> str:
        """使用AI理解用户意图并推荐合适的技术方法"""
        from api_clients import anthropic_client

        prompt = f"""
你是一名医学影像AI研究专家。请分析以下用户研究需求，推荐最适合的技术方法。

用户输入：{text}

请基于以下维度进行分析：
1. 研究任务类型（检测、分割、分类、预测等）
2. 技术复杂度要求
3. 医学图像特点
4. 实现可行性

返回JSON格式：
{{
  "technical_approach": "推荐的具体技术方法",
  "rationale": "推荐理由",
  "complexity_level": "技术复杂度（基础/中等/高级）",
  "implementation_notes": "实现注意事项"
}}

要求：
- 避免使用泛化的"深度学习"、"CNN"等表述
- 推荐具体、可实现的技术方法
- 考虑医学图像研究的特殊性
- 只返回JSON，不要额外文字
"""

        try:
            tech_rec_sp = "你是一名医学影像AI研究专家。请分析研究需求并推荐最适合的技术方法，只返回JSON格式，不要额外文字。"
            ai_response = anthropic_client.call_longcat_api(prompt, max_tokens=500, system_prompt=tech_rec_sp)
            result = _safe_json_parse(ai_response, context="StudentProfile._ai_recommend_tech")
            return result.get('technical_approach', '')
        except Exception as e:
            logger.warning(f"  [ProfileAgent] 技术方法推荐失败: {e}")
            return ''

    def assess_complexity(self, text: str) -> str:
        """评估研究复杂度"""
        complexity_indicators = {
            '简单': ['简单', '基础', '入门', 'basic', 'simple'],
            '中等': ['中等', '一般', 'moderate'],
            '复杂': ['复杂', '高级', 'advanced', 'sophisticated']
        }

        for level, indicators in complexity_indicators.items():
            if any(indicator in text for indicator in indicators):
                return level
        return '中等'

    def suggest_approach(self, text: str) -> List[str]:
        """建议研究方法"""
        suggestions = []

        # 基于年级建议
        grade = self.extract_grade(text)
        if grade == '研一':
            suggestions.extend(['文献综述', '基础方法学习', '小样本研究'])
        elif grade in ['研二', '研三']:
            suggestions.extend(['方法创新', '临床应用', '多中心研究'])

        # 基于专业方向建议
        specialty = self.extract_specialty(text)
        if specialty == '胸部影像':
            suggestions.append('肺结节相关研究')
        elif specialty == '神经影像':
            suggestions.append('脑卒中或神经退行性疾病')

        return suggestions

class ProblemDefinitionAgent(BaseAgent):
    """问题定义智能体 - 将模糊需求转化为具体的研究问题框架
    核心能力：把"我想做胸部影像AI"压缩成"胸部CT报告质控/肺结节良恶性预测/随访风险分层"等可研究方向
    自动补全：研究类型、研究对象、研究终点、比较框架
    """

    def __init__(self):
        super().__init__("ProblemDefinitionAgent")

    def process_message(self, message: AgentMessage) -> Dict:
        """处理学生画像，定义研究问题（检索增强版）"""
        if message.message_type == 'student_profile':
            # 【增强】先检索该方向的研究热点和空白，为问题定义提供证据
            self._pre_search_problem_space(message.content)
            return self.define_research_problem(message.content)
        return {}

    def _pre_search_problem_space(self, student_profile: Dict):
        """预检索该问题空间的研究现状，验证创新性，发现研究空白"""
        try:
            raw_input = student_profile.get('raw_input', '')
            if isinstance(raw_input, dict):
                raw_input = str(raw_input)
            research_focus = student_profile.get('research_focus', {})
            focus = research_focus.get('primary_focus', '')
            specialty = student_profile.get('extracted_info', {}).get('specialty', '')
            if focus or specialty:
                query = f"{specialty} {focus} radiology AI"
                result = tool_search_pubmed(query=query, max_results=8, retrieved_by="ProblemDefinitionAgent")
                if result.success and result.data:
                    # 检查证据池中是否已有该方向的文献，如果没有则标记为新方向
                    gaps = tool_discover_gaps()
                    logger.info(f"  [ProblemDefinitionAgent] 预检索完成，证据池共 {evidence_pool.size} 篇")
        except Exception as e:
            logger.debug(f"  [ProblemDefinitionAgent] 预检索跳过: {e}")

    def define_research_problem(self, student_profile: Dict) -> Dict:
        """定义研究问题 - 使用AI将模糊需求转化为清晰的研究问题框架"""
        try:
            # 【增强】在 prompt 中注入证据池上下文
            evidence_context = self._get_evidence_context_for_problem(student_profile)

            # 优先使用AI进行深度问题定义
            ai_result = self._ai_define_research_problem(student_profile, evidence_context)
            if ai_result and 'error' not in ai_result:
                return ai_result

            # AI失败时回退到规则方法
            logger.warning("AI问题定义失败，使用规则回退")
            problem_definition = {
                'clinical_problem': self.extract_clinical_problem(student_profile),
                'scientific_problem': self.formulate_scientific_problem(student_profile),
                'research_questions': self.generate_research_questions(student_profile),
                'hypotheses': self.generate_hypotheses(student_profile),
                'study_objectives': self.define_study_objectives(student_profile),
                'research_type': self._infer_research_type(student_profile),
                'comparison_framework': self._infer_comparison_framework(student_profile),
            }
            return problem_definition
        except Exception as e:
            logger.error(f"问题定义失败: {str(e)}")
            return {'error': str(e)}

    def _ai_define_research_problem(self, student_profile: Dict, evidence_context: str = "") -> Dict:
        """使用AI将模糊需求转化为清晰的研究问题框架（检索增强版）"""
        from api_clients import anthropic_client

        raw_input = student_profile.get('raw_input', '')
        extracted_info = student_profile.get('extracted_info', {})
        research_focus = student_profile.get('research_focus', {})

        # 【增强】获取证据池上下文
        if not evidence_context:
            try:
                evidence_context = self._get_evidence_context_for_problem(student_profile)
            except Exception:
                evidence_context = ""

        # 构建上下文
        context = f"""
=== 学生原始需求 ===
"{raw_input}"

=== 学生背景 ===
- 培养阶段：{extracted_info.get('grade', '未知')}
- 专业方向：{extracted_info.get('specialty', '未知')}
- 统计基础：{extracted_info.get('statistical_background', '未知')}
- AI基础：{extracted_info.get('ai_background', '未知')}
- 是否有数据：{extracted_info.get('has_data', '未知')}
- 数据量：{extracted_info.get('data_volume', '未知')}
- 是否有金标准：{extracted_info.get('gold_standard_available', '未知')}
- 是否有随访：{extracted_info.get('follow_up_available', '未知')}
- 预期毕业：{extracted_info.get('expected_graduation', '未知')}
- 目标期刊：{extracted_info.get('target_journal_level', '未知')}
- 导师支持：{extracted_info.get('supervisor_support', '未知')}
- 伦理可行性：{extracted_info.get('ethical_feasibility', '未知')}
- 跨科合作：{extracted_info.get('cross_dept_resources', '未知')}
- 可用软件：{extracted_info.get('software_capability', '未知')}

=== 初步分析 ===
- 研究重点：{research_focus.get('primary_focus', '未知')}
- 技术方向：{research_focus.get('technical_approach', '未知')}
"""

        evidence_section = ""
        if evidence_context:
            evidence_section = f"""
=== 文献证据（来自全局证据池）===
{evidence_context}

请基于以上文献证据来定义研究问题：
- 研究问题必须指向文献中的研究空白
- 避免选择已经被充分研究的方向
- 优先选择有初步证据支持但尚未深入的方向
"""

        prompt = f"""
你是一名资深放射学科研导师。学生提出了一个模糊的研究需求，你需要将其转化为一个**清晰、具体、可开题**的研究问题框架。

{context}
{evidence_section}

请完成以下任务：

1. **需求压缩**：把学生的模糊需求压缩成2-3个具体可研究的方向。
   - 压缩方向必须**严格来自学生的原始输入**，不要引入输入中未提及的疾病或器官
   - 示例（仅作格式参考，不要照搬内容）：如果学生说"脑卒中"，可压缩为"脑卒中早期CT灌注分析"、"脑卒中预后预测"等
   - 如果学生说"骨折"，可压缩为"骨折X线自动检测"、"骨折分型AI辅助"等
   - **禁止**：学生未提及肺部时，不要生成任何与肺/胸部/肺结节相关的方向

2. **问题定义**：针对最匹配的方向，定义：
   - 临床问题（必须是一段完整的描述，指出当前临床实践中的具体痛点、不足或未满足的需求，至少30字。例如：在胸部CT筛查中放射科医生对小结节的良恶性判断一致性较差导致不必要活检或漏诊。禁止输出空字符串或待补充）
   - 科学问题（需要回答的科学假设）
   - 研究问题列表（2-4个可验证的具体问题）

3. **研究框架补全**：
   - 研究类型（诊断试验/预后研究/横断面/回顾性队列/前瞻性等）
   - 研究对象（具体的人群/疾病/影像模态）
   - 研究终点（主要终点和次要终点）
   - 比较框架（与什么比较：金标准/传统方法/不同模型等）

4. **研究假设**：2-3个可验证的假设

5. **研究目标**：主要目标和次要目标

返回JSON格式：
{{
  "compressed_directions": ["方向1", "方向2", "方向3"],
  "selected_direction": "选定的最佳方向",
  "clinical_problem": "临床问题描述",
  "scientific_problem": "科学问题描述",
  "research_questions": ["问题1", "问题2", "问题3"],
  "research_type": "研究类型",
  "study_subjects": "研究对象（人群/疾病/模态）",
  "primary_endpoint": "主要终点",
  "secondary_endpoints": ["次要终点1", "次要终点2"],
  "comparison_framework": "比较框架",
  "hypotheses": ["假设1", "假设2"],
  "study_objectives": {{"primary": "主要目标", "secondary": ["次要目标1", "次要目标2"]}},
  "rationale": "选择该方向的理由（考虑了学生的年级、基础、资源等）"
}}

要求：
- 方向压缩要具体，避免泛泛的"基于深度学习的XX诊断"
- 临床问题要指向真实的临床痛点
- 科学问题要可验证、可量化
- 研究类型要合理（研一不宜前瞻性研究）
- 终点要可测量
- 只返回JSON，不要额外文字
"""

        problem_sp = "你是一名放射学研究设计专家。请根据学生需求定义研究问题，只返回JSON格式，不要额外文字。"
        response = anthropic_client.call_longcat_api(prompt, max_tokens=2000, system_prompt=problem_sp)
        result = _safe_json_parse(response, context="ProblemDefinition._ai_define_problem")
        return result

    def _get_evidence_context_for_problem(self, student_profile: Dict) -> str:
        """获取用于问题定义的证据池上下文"""
        try:
            raw_input = student_profile.get('raw_input', '')
            if isinstance(raw_input, dict):
                raw_input = str(raw_input)
            research_focus = student_profile.get('research_focus', {})
            focus = research_focus.get('primary_focus', '')
            query = f"{raw_input[:50]} {focus}"
            return self.get_evidence_context(topic=query, max_papers=5)
        except Exception:
            return ""

    def _infer_research_type(self, profile: Dict) -> str:
        """根据学生画像推断合适的研究类型"""
        extracted_info = profile.get('extracted_info', {})
        grade = extracted_info.get('grade', '')
        has_data = extracted_info.get('has_data')
        follow_up = extracted_info.get('follow_up_available')
        ethical = extracted_info.get('ethical_feasibility')

        # 研一/无数据/伦理受限 → 横断面或回顾性
        if grade in ['研一', '博一']:
            if has_data:
                return '回顾性横断面研究'
            else:
                return '回顾性研究（利用公开数据集）'
        # 有随访数据 → 可做预后研究
        if follow_up and follow_up not in (False, '未知'):
            if ethical is True:
                return '回顾性队列研究或前瞻性验证研究'
            else:
                return '回顾性队列研究'
        # 默认
        return '回顾性诊断准确性研究'

    def _infer_comparison_framework(self, profile: Dict) -> str:
        """推断比较框架"""
        raw_input = profile.get('raw_input', '')
        extracted_info = profile.get('extracted_info', '')
        gold_standard = extracted_info.get('gold_standard_available', '') if isinstance(extracted_info, dict) else ''

        comparisons = []
        if gold_standard and gold_standard not in (False, '未知'):
            comparisons.append('以病理金标准为参照')
        if any(w in raw_input for w in ['AI', '人工智能', '深度学习']):
            comparisons.append('与放射科医生诊断对比')
            comparisons.append('与传统影像学方法比较')
        if not comparisons:
            comparisons.append('与现有临床诊断方法比较')
        return '；'.join(comparisons)

    def extract_clinical_problem(self, profile: Dict) -> str:
        """提取临床问题 - 规则回退方法"""
        extracted_info = profile.get('extracted_info', {})
        specialty = extracted_info.get('specialty', '')
        grade = extracted_info.get('grade', '')
        research_focus = profile.get('research_focus', {})
        focus = research_focus.get('primary_focus', '')
        raw_input = profile.get('raw_input', '')

        # 基于专业方向的通用临床问题（覆盖所有放射学亚专业）
        base_problems = {
            '胸部影像': '胸部CT影像中病变的准确识别和诊断存在效率瓶颈，影响早期疾病筛查效果',
            '神经影像': '神经影像中疾病的早期诊断和预后评估的准确性有待提高',
            '骨肌影像': '骨肌系统疾病的早期诊断和定量评估缺乏客观标准',
            '心血管影像': '心血管影像的定量分析和风险分层存在主观性差异',
            '腹部影像': '腹部影像中病灶的精确检测和鉴别诊断具有挑战性',
            '乳腺影像': '乳腺影像筛查的敏感性和特异性需要进一步提升',
            '介入影像': '介入放射学治疗的精准导航和疗效评估缺乏实时客观的影像引导标准',
            '儿科影像': '儿童影像检查中辐射剂量优化与诊断准确性的平衡面临挑战',
            '头颈影像': '头颈部复杂解剖区域病变的早期检测和精确分期存在困难',
            '泌尿影像': '泌尿系统肿瘤的影像组学特征提取和临床转化应用尚不成熟',
            '妇科影像': '妇科肿瘤的术前精确评估和疗效监测缺乏标准化的影像指标体系',
            '急诊影像': '急诊影像的快速诊断和危急值识别效率有待提升，漏诊率偏高',
            '功能影像': '功能影像数据的标准化处理和临床解读缺乏统一规范',
            '分子影像': '分子影像探针的临床转化和精准定量分析技术有待突破',
            '核医学': '核医学影像的定量分析和多模态融合诊断价值尚未充分发挥',
            '超声': '超声检查的操作者依赖性高，诊断一致性和标准化面临挑战',
            '病理影像': '病理影像的自动化分析和辅助诊断系统开发尚不完善',
            '放射治疗': '放疗计划的精准靶区勾画和正常组织保护需要更智能的影像辅助',
            '核磁共振': 'MRI扫描时间长、伪影干扰等问题影响诊断效率和准确性',
            'CT专项': 'CT辐射剂量优化与图像质量平衡的智能化管理有待加强',
            'X线专项': 'X线平片的低对比分辨率限制了对早期病变和微小异常的检出率',
        }

        base_problem = base_problems.get(specialty,
            f'{specialty}领域中{focus}相关的临床需求尚未充分满足')

        return base_problem

    def formulate_scientific_problem(self, profile: Dict) -> str:
        """形成科学问题 - 规则回退"""
        extracted_info = profile.get('extracted_info', {})
        specialty = extracted_info.get('specialty', '')
        research_focus = profile.get('research_focus', {})
        focus = research_focus.get('primary_focus', '')
        approach = research_focus.get('technical_approach', '')

        return f'如何应用{approach}方法解决{specialty}领域中{focus}的关键科学问题，提高临床决策的准确性和效率？'

    def generate_research_questions(self, profile: Dict) -> List[str]:
        """生成研究问题 - 规则回退"""
        specialty = profile.get('extracted_info', {}).get('specialty', '')
        focus = profile.get('research_focus', {}).get('primary_focus', '')
        return [
            f'{specialty}领域中{focus}的关键影响因素有哪些？',
            f'现有方法在{specialty}{focus}方面存在哪些局限性？',
            f'新方法在不同数据条件下的泛化能力如何？',
        ]

    def generate_hypotheses(self, profile: Dict) -> List[str]:
        """生成研究假设 - 规则回退"""
        specialty = profile.get('extracted_info', {}).get('specialty', '')
        focus = profile.get('research_focus', {}).get('primary_focus', '')
        approach = profile.get('research_focus', {}).get('technical_approach', '')
        grade = profile.get('extracted_info', {}).get('grade', '')

        h1 = f'H1: 基于{approach}的{specialty}{focus}方法性能优于或等效于现有方法'
        if grade == '研一':
            return [h1]
        return [h1, 'H2: 多因素整合模型优于单一因素模型', 'H3: 方法在不同数据条件下具有稳定性']

    def define_study_objectives(self, profile: Dict) -> Dict:
        """定义研究目标 - 规则回退"""
        specialty = profile.get('extracted_info', {}).get('specialty', '')
        focus = profile.get('research_focus', {}).get('primary_focus', '')
        approach = profile.get('research_focus', {}).get('technical_approach', '')
        grade = profile.get('extracted_info', {}).get('grade', '')

        return {
            'primary': f'构建并验证基于{approach}的{specialty}{focus}方法',
            'secondary': [
                '评估方法的性能指标',
                '与现有方法进行比较分析',
                '探索方法在不同条件下的适用性',
            ],
            'exploratory': [
                f'探索{specialty}领域的潜在应用场景',
                '分析方法的局限性和改进方向',
            ]
        }

class InputParsingAgent(BaseAgent):
    """输入解析智能体 — LLM驱动语义理解 + 检索增强

    核心能力：
    1. LLM语义理解用户输入 → 提取疾病域、影像模态、研究任务等关键信息
    2. 自动判断输入完整度 → 识别缺失信息，生成追问建议
    3. 【新】检索该方向的最新文献 → 为下游 Agent 预填充证据池
    4. 输出结构化解析结果 → 供下游Agent使用
    """

    def __init__(self):
        super().__init__("InputParsingAgent")

    def build_system_prompt(self) -> str:
        return """你是一名科研助手。你的任务是分析学生的研究需求输入，提取关键信息，
并检索该方向的最新文献，为后续研究方案生成提供证据基础。

你可以使用工具：
- search_pubmed: 检索 PubMed 文献
- search_arxiv: 检索 arXiv 预印本
- query_evidence_pool: 查询已有证据

先用工具检索该研究方向的文献，然后基于检索结果和用户输入，输出结构化的解析结果。"""

    def build_user_prompt(self, message: AgentMessage) -> str:
        student_input = message.content if isinstance(message.content, str) else str(message.content)
        return f"""学生输入："{student_input}"

请完成以下任务：
1. 先用 search_pubmed 检索该研究方向的最近文献（检索式基于学生输入的关键词）
2. 分析学生输入，提取：
   - 疾病域（严格从输入中提取）
   - 影像模态
   - 研究任务类型
   - 技术方向
   - 临床场景
   - 创新关注点
   - 输入完整度（complete/partial/vague）
   - 缺失信息
   - 追问建议
   - 增强描述（补全隐含假设，但不添加未提及的疾病/器官）

最后输出 JSON（包含 tool: finish 格式）：
{{
  "tool": "finish",
  "params": {{
    "result": {{
      "disease_domain": "疾病域",
      "imaging_modality": "影像模态",
      "research_task": "研究任务类型",
      "technical_direction": "技术方向",
      "clinical_scenario": "临床场景",
      "innovation_focus": "创新关注点",
      "input_completeness": "complete/partial/vague",
      "missing_info": ["缺失项1"],
      "follow_up_questions": ["建议追问1"],
      "enhanced_description": "增强后的研究需求描述"
    }}
  }}
}}"""

    def parse_final_output(self, llm_output: str) -> Dict:
        result = _safe_json_parse(llm_output, context="InputParsingAgent")
        if 'raw_input' not in result:
            result['raw_input'] = ''
        return result

    def max_steps(self) -> int:
        return 3  # 最多：1次检索 + 1次分析 + 1次输出

    # 保留旧接口兼容
    def process_message(self, message: AgentMessage) -> Dict:
        if message.message_type == 'raw_student_input':
            self.memory = WorkingMemory()
            return self._react_loop(message)
        return {}

    def parse_input(self, student_input: str) -> Dict:
        """兼容旧接口"""
        msg = AgentMessage(
            sender="coordinator", receiver="InputParsingAgent",
            content=student_input, timestamp=datetime.now(),
            message_type='raw_student_input'
        )
        return self.process_message(msg)

class EvidenceRetrievalAgent(BaseAgent):
    """证据检索智能体 — LLM驱动检索策略 + 全局证据池写入

    核心改进：
    1. LLM分析研究意图 → 自主构造PubMed检索式
    2. LLM对每篇文献做相关性评估 → 筛选高质量文献
    3. LLM从文献中提炼方法学趋势和研究空白
    4. 【新】所有检索结果自动写入全局证据池，供所有 Agent 共享
    5. 【新】检索后自动检测文献冲突和研究空白
    """

    def __init__(self):
        super().__init__("EvidenceRetrievalAgent")

    def process_message(self, message: AgentMessage) -> Dict:
        if message.message_type == 'problem_definition':
            return self.retrieve_evidence(message.content)
        return {}

    def retrieve_evidence(self, input_data: Dict) -> Dict:
        """检索相关证据 — LLM驱动，PubMed + arXiv 双源检索 + 证据池写入

        返回结构（统一前后端）：
        {
            "keywords": [...],
            "recommended_literature": {
                "recommended_papers": [...],
                "total_results": N,
                "search_query": "...",
                "search_summary": "...",
                "sources": ["pubmed", "arxiv"]
            },
            "research_gaps": {...},
            "evidence_summary": {
                "summary": "...",
                "key_findings": [...],
                "supporting_evidence": "...",
                "contradictory_evidence": "..."
            },
            "methodological_insights": [...],
            "search_strategy": {...},
            "evidence_pool_stats": {...},   # 【新】证据池统计
            "conflicts": [...],              # 【新】检测到的文献冲突
        }
        """
        if isinstance(input_data, dict) and 'problem_definition' in input_data:
            problem_definition = input_data['problem_definition']
            student_profile = input_data.get('student_profile', None)
        else:
            problem_definition = input_data
            student_profile = None

        try:
            # ── Step 1: LLM生成检索策略 ──
            logger.info("  [EvidenceRetrieval] LLM分析研究意图，生成检索策略")
            search_strategy = self._llm_generate_search_strategy(
                problem_definition, student_profile
            )
            logger.info(f"  [EvidenceRetrieval] 检索策略: {search_strategy.get('strategy_name', 'default')}")

            pubmed_query = search_strategy.get('primary_query', '')
            arxiv_query = search_strategy.get('arxiv_query', '') or self._build_arxiv_query(search_strategy)

            # ── Step 2: 并行检索 PubMed + arXiv（自动写入证据池）──
            import time as _time

            # 2a. PubMed检索 → 自动写入证据池
            logger.info("  [EvidenceRetrieval] 检索 PubMed...")
            pubmed_papers = []
            try:
                pubmed_papers = self._execute_pubmed_searches(search_strategy)
                # 【新】写入证据池
                if pubmed_papers:
                    new_count = evidence_pool.add_papers_batch(pubmed_papers, retrieved_by="EvidenceRetrievalAgent")
                    logger.info(f"  [EvidenceRetrieval] PubMed 返回 {len(pubmed_papers)} 篇，{new_count} 篇新入库（证据池共 {evidence_pool.size} 篇）")
                else:
                    logger.info(f"  [EvidenceRetrieval] PubMed 返回 0 篇")
            except Exception as e:
                logger.warning(f"  [EvidenceRetrieval] PubMed 检索失败: {e}")

            # 2b. arXiv检索 → 后台线程（不阻塞主流程）
            # arXiv API 限速严格，放到后台慢慢检索，PubMed 结果先用于方案生成
            arxiv_papers = []
            arxiv_done = threading.Event()

            def _arxiv_search_bg():
                """后台线程：检索 arXiv，完成后写入证据池"""
                try:
                    from api_clients import arxiv_client
                    logger.info("  [EvidenceRetrieval] 后台检索 arXiv（不阻塞主流程）...")
                    arxiv_raw = arxiv_client.search(arxiv_query, max_results=10)
                    nonlocal arxiv_papers
                    arxiv_papers = arxiv_raw  # 已经是标准化格式
                    if arxiv_papers:
                        for p in arxiv_papers:
                            p['source'] = 'arxiv'
                        new_count = evidence_pool.add_papers_batch(
                            arxiv_papers, retrieved_by="EvidenceRetrievalAgent"
                        )
                        logger.info(
                            f"  [EvidenceRetrieval] arXiv 后台检索完成: "
                            f"{len(arxiv_papers)} 篇，{new_count} 篇入库"
                        )
                    else:
                        logger.info("  [EvidenceRetrieval] arXiv 后台检索返回 0 篇")
                except Exception as e:
                    logger.warning(f"  [EvidenceRetrieval] arXiv 后台检索失败: {e}")
                finally:
                    arxiv_done.set()

            arxiv_thread = threading.Thread(target=_arxiv_search_bg, daemon=True)
            arxiv_thread.start()

            # 主流程只用 PubMed 结果，arXiv 结果后续从证据池补充
            all_papers = pubmed_papers

            # 保存引用，供后续 _wait_for_arxiv 使用
            self._arxiv_thread_ref = arxiv_thread
            self._arxiv_done_event = arxiv_done

            if not all_papers:
                logger.warning("  [EvidenceRetrieval] 未检索到任何文献")
                return {
                    'keywords': search_strategy.get('keywords', []),
                    'recommended_literature': {
                        'recommended_papers': [],
                        'total_results': 0,
                        'search_query': pubmed_query,
                        'search_summary': '未检索到相关文献',
                        'sources': [],
                    },
                    'research_gaps': {},
                    'evidence_summary': {'summary': '未检索到相关文献'},
                    'methodological_insights': [],
                    'search_strategy': search_strategy,
                }

            # ── Step 2c: 等待 arXiv 后台检索完成（最多60秒）──
            logger.info("  [EvidenceRetrieval] 等待 arXiv 后台检索（最多60秒）...")
            arxiv_done.wait(timeout=60)
            if arxiv_thread.is_alive():
                logger.warning("  [EvidenceRetrieval] arXiv 后台检索超时（60s），继续使用 PubMed 结果")
            else:
                # arXiv 完成了，把结果补充到 all_papers
                all_papers = pubmed_papers + arxiv_papers
                if arxiv_papers:
                    logger.info(f"  [EvidenceRetrieval] arXiv 检索成功，补充 {len(arxiv_papers)} 篇")

            logger.info(f"  [EvidenceRetrieval] 共检索到 {len(all_papers)} 篇原始文献 (PubMed:{len(pubmed_papers)}, arXiv:{len(arxiv_papers)})")

            # ── Step 3: LLM评估相关性 ──
            logger.info("  [EvidenceRetrieval] LLM评估文献相关性...")
            filtered_papers = self._llm_filter_relevant_papers(
                all_papers, problem_definition, student_profile
            )
            logger.info(f"  [EvidenceRetrieval] 相关性筛选后保留 {len(filtered_papers)} 篇")

            # ── Step 4: LLM提炼证据 ──
            logger.info("  [EvidenceRetrieval] LLM提炼证据综述...")
            evidence_analysis = self._llm_analyze_evidence(
                filtered_papers, problem_definition, student_profile
            )

            # ── 构建统一返回结构（与前端 ModernEvidenceDisplay 匹配）──
            sources = []
            if pubmed_papers:
                sources.append("pubmed")
            if arxiv_papers:
                sources.append("arxiv")

            recommended_literature = {
                'recommended_papers': filtered_papers,
                'total_results': len(filtered_papers),
                'search_query': pubmed_query,
                'arxiv_query': arxiv_query,
                'search_summary': f"LLM驱动双源检索：PubMed({len(pubmed_papers)}篇) + arXiv({len(arxiv_papers)}篇)，筛选出 {len(filtered_papers)} 篇相关文献",
                'sources': sources,
                'search_metadata': {
                    'strategy': search_strategy.get('strategy_name', 'default'),
                    'queries_used': search_strategy.get('queries', []),
                    'llm_driven': True,
                },
            }

            # 【新】获取证据池统计和研究空白
            pool_stats = evidence_pool.get_evidence_summary()
            conflicts = evidence_pool.detect_conflicts()
            auto_gaps = evidence_pool.discover_research_gaps()

            # 合并 LLM 分析的研究空白和自动发现的研究空白
            merged_gaps = evidence_analysis.get('research_gaps', {})
            if auto_gaps.get('methodological_gaps'):
                merged_gaps.setdefault('auto_methodological_gaps', []).extend(auto_gaps['methodological_gaps'][:3])
            if auto_gaps.get('data_gaps'):
                merged_gaps.setdefault('auto_data_gaps', []).extend(auto_gaps['data_gaps'][:3])

            return {
                'keywords': search_strategy.get('keywords', []),
                'recommended_literature': recommended_literature,
                'research_gaps': merged_gaps,
                'evidence_summary': evidence_analysis.get('evidence_summary', {}),
                'methodological_insights': evidence_analysis.get('methodological_insights', []),
                'search_strategy': search_strategy,
                # 【新】证据池信息
                'evidence_pool_stats': {
                    'total_papers': pool_stats['total'],
                    'high_quality_count': pool_stats.get('high_quality_count', 0),
                    'level_distribution': pool_stats.get('levels', {}),
                    'modalities': pool_stats.get('modalities', {}),
                },
                'conflicts': conflicts,
            }

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"证据检索失败: {str(e)}\n{tb}")
            return {'error': str(e)}

    # ── Step 1: LLM生成检索策略 ──

    def _llm_generate_search_strategy(self, problem_definition: Dict, student_profile: Dict = None) -> Dict:
        """由LLM分析研究意图，自主决定检索策略（关键词、检索式、搜索重点）"""
        from api_clients import anthropic_client

        clinical_problem = problem_definition.get('clinical_problem', '')
        scientific_problem = problem_definition.get('scientific_problem', '')
        research_questions = problem_definition.get('research_questions', [])
        if isinstance(research_questions, str):
            research_questions = [research_questions]

        # 学生背景
        student_context = ""
        if student_profile:
            extracted = self._safe_dict_get(student_profile.get('extracted_info', {}))
            raw = student_profile.get('raw_input', '')
            if isinstance(raw, dict):
                raw = str(raw)
            student_context = f"""
学生背景：
- 年级：{extracted.get('grade', '未知')}
- 专业：{extracted.get('specialty', '未知')}
- 统计基础：{extracted.get('statistical_background', '未知')}
- AI基础：{extracted.get('ai_background', '未知')}
- 原始需求："{raw[:200] if raw else ''}"
"""

        prompt = f"""你是一名医学影像文献检索专家，精通PubMed和arXiv检索。请为以下研究问题制定高质量的双源检索策略。

研究问题：
- 临床问题：{clinical_problem}
- 科学问题：{scientific_problem}
- 具体研究问题：{'；'.join(research_questions) if research_questions else '待定义'}
{student_context}

## 检索策略要求

### Step 1: 分析核心要素
- 疾病/解剖部位（中英文）：
- 影像模态（CT/MRI/超声/X线/PET等）：
- AI技术/方法（深度学习/影像组学/分割/检测/分类等）：
- 临床任务（诊断/筛查/分期/预后/疗效评估等）：

### Step 2: PubMed检索式（主要来源）
构造完整PubMed检索式，要求：
1. 使用 MeSH 术语（带 [Mesh] 标签）+ 自由词（带 [Title/Abstract]）
2. AND 连接不同概念维度，OR 连接同义词
3. 限定近7年：("2019/01/01"[Date - Publication] : "2026/12/31"[Date - Publication])
4. 限定文献类型：("Journal Article"[pt] OR "Review"[pt] OR "Meta-Analysis"[pt])
5. 排除：NOT ("Editorial"[pt] OR "Letter"[pt] OR "Comment"[pt])

### Step 3: arXiv检索式（补充来源，获取最新AI方法论文）
构造arXiv检索式，要求：
1. 使用英文关键词，简洁精准
2. 适合arXiv的搜索语法（空格=AND，OR用大写OR）
3. 聚焦 cs.CV / cs.LG / eess.IV 领域的医学影像AI论文
4. 示例格式：(deep learning OR transformer) AND (medical imaging OR radiology) AND (segmentation OR detection)

返回JSON格式：
{{
  "strategy_name": "策略名称（简洁，反映学生实际研究问题）",
  "keywords": ["中文关键词1", "english_keyword1", "english_keyword2", ...],
  "primary_query": "完整PubMed检索式（可直接用于esearch）",
  "arxiv_query": "arXiv英文检索式（简洁，关键词组合）",
  "additional_queries": ["补充PubMed检索式2（如有）"],
  "search_focus": "检索重点说明（1-2句话）",
  "expected_paper_types": ["Journal Article", "Review", "Meta-Analysis"]
}}

严格要求：
- primary_query 必须是完整PubMed检索式
- arxiv_query 必须是英文，适合arXiv搜索
- 所有疾病/关键词/模态必须来自学生实际输入
- 只返回JSON，不要任何额外文字
"""

        search_strategy_sp = """你是一名医学影像文献检索专家，精通PubMed和arXiv检索。请根据研究问题制定高质量的双源检索策略，只返回JSON格式，不要额外文字。"""
        response = anthropic_client.call_longcat_api(prompt, max_tokens=2500, system_prompt=search_strategy_sp)
        result = _safe_json_parse(response, context="EvidenceRetrieval._ai_generate_search_strategy")

        # ── 字段别名归一化：LLM可能返回中文字段名或不同英文名 ──
        # keywords: 接受 keywords / 关键词 / 自由词 / search_terms
        kw_aliases = ['keywords', '关键词', '自由词', 'search_terms', 'key_words']
        keywords = []
        for alias in kw_aliases:
            if alias in result and result[alias]:
                val = result[alias]
                if isinstance(val, list):
                    keywords = val
                elif isinstance(val, str):
                    keywords = [k.strip() for k in val.replace('；', ';').split(';') if k.strip()]
                break
        if not keywords:
            # 最后尝试：从嵌套结构中提取（如 result['检索']['自由词']）
            for k, v in result.items():
                if isinstance(v, dict):
                    for alias in kw_aliases:
                        if alias in v and v[alias]:
                            val = v[alias]
                            keywords = val if isinstance(val, list) else [val]
                            break
                if keywords:
                    break
        if not keywords:
            raise ValueError("缺少必要字段: keywords（LLM未返回任何关键词）")
        result['keywords'] = keywords

        # primary_query: 接受 primary_query / 检索式 / pubmed_query / query
        pq_aliases = ['primary_query', '检索式', 'pubmed_query', 'query', 'pubmed检索式']
        primary_query = ''
        for alias in pq_aliases:
            if alias in result and result[alias]:
                val = result[alias]
                if isinstance(val, str):
                    primary_query = val
                elif isinstance(val, dict):
                    # 可能是 {"PubMed": "...", "Embase": "..."} 格式
                    primary_query = val.get('PubMed', val.get('pubmed', ''))
                break
        if not primary_query:
            logger.warning("LLM未生成primary_query，用关键词拼接回退")
            primary_query = self._fallback_pubmed_query(keywords)
        result['primary_query'] = primary_query

        # arxiv_query: 接受 arxiv_query / arxiv检索式
        aq_aliases = ['arxiv_query', 'arxiv检索式', 'arxiv_query_string']
        arxiv_query = ''
        for alias in aq_aliases:
            if alias in result and result[alias]:
                arxiv_query = result[alias] if isinstance(result[alias], str) else str(result[alias])
                break
        if not arxiv_query:
            arxiv_query = self._build_arxiv_query(result)
        result['arxiv_query'] = arxiv_query

        return result

    def _fallback_pubmed_query(self, keywords: list) -> str:
        """当LLM未生成primary_query时，用关键词拼接一个基础PubMed检索式"""
        # 过滤中英文关键词
        en_kw = [k for k in keywords if k.isascii() and len(k) > 1][:5]
        zh_kw = [k for k in keywords if not k.isascii()][:3]

        # 构建简单检索式：英文关键词用 OR 连接，加时间限制
        parts = []
        if en_kw:
            parts.append(' OR '.join(f'"{k}"[Title/Abstract]' for k in en_kw))
        if zh_kw:
            parts.append(' OR '.join(f'"{k}"[Title/Abstract]' for k in zh_kw))

        query = ' AND '.join(parts) if parts else '"deep learning"[Title/Abstract] AND "medical imaging"[Title/Abstract]'
        # 加时间限制和文献类型限制
        query += ' AND ("2019/01/01"[Date - Publication] : "2026/12/31"[Date - Publication])'
        query += ' AND ("Journal Article"[pt] OR "Review"[pt])'
        return query

    def _build_arxiv_query(self, search_strategy: Dict) -> str:
        """从检索策略构建arXiv查询（英文关键词组合）"""
        keywords = search_strategy.get('keywords', [])
        # 过滤出英文关键词（arXiv主要收录英文论文）
        en_keywords = [k for k in keywords if k.isascii() and len(k) > 1]
        if not en_keywords:
            # 没有英文关键词，从策略名称构建
            strategy_name = search_strategy.get('strategy_name', '')
            en_keywords = [w for w in strategy_name.split() if w.isascii() and len(w) > 2]
        # 取前5个关键词，用 AND 组合
        return ' AND '.join(en_keywords[:5]) if en_keywords else 'deep learning medical imaging'

    def _normalize_arxiv_paper(self, paper: Dict) -> Dict:
        """将arXiv论文标准化为与PubMed论文统一的格式"""
        return {
            'pmid': '',
            'arxiv_id': paper.get('arxiv_url', '').split('/')[-1] if paper.get('arxiv_url') else '',
            'title': paper.get('title', ''),
            'authors': paper.get('authors', [])[:5],
            'abstract': paper.get('abstract', ''),
            'journal': 'arXiv',
            'pubdate': paper.get('published', ''),
            'doi': '',
            'pubmed_url': paper.get('arxiv_url', ''),
            'url': paper.get('arxiv_url', ''),
            'article_type': 'preprint',
            'categories': paper.get('categories', []),
            'mesh_terms': [],
            'keywords': paper.get('categories', []),
            'source': 'arxiv',
            'relevance_score': 0,
        }

    # ── Step 2: 执行PubMed检索 ──

    def _execute_pubmed_searches(self, search_strategy: Dict) -> List[Dict]:
        """执行PubMed检索（支持多个检索式），返回合并去重后的文献列表"""
        from Bio import Entrez
        import time as _time

        all_papers = []
        seen_pmids = set()

        queries = [search_strategy['primary_query']] + search_strategy.get('additional_queries', [])

        for query in queries:
            try:
                Entrez.email = "79047879@qq.com"
                Entrez.api_key = "1307550aa4966b0cbbc68a6b2d4cb1ff8009"

                # esearch
                handle = Entrez.esearch(
                    db='pubmed', term=query, retmax=30, sort='relevance', retmode='xml'
                )
                search_data = Entrez.read(handle)
                handle.close()
                idlist = search_data.get('IdList', [])

                if not idlist:
                    continue

                _time.sleep(0.15)

                # efetch
                handle = Entrez.efetch(db='pubmed', id=idlist, retmode='xml')
                xml_data = Entrez.read(handle)
                handle.close()

                for article in xml_data.get('PubmedArticle', []):
                    try:
                        medline = article.get('MedlineCitation', {})
                        article_data = medline.get('Article', {})
                        pmid = str(medline.get('PMID', ''))

                        if pmid in seen_pmids or not pmid:
                            continue
                        seen_pmids.add(pmid)

                        title = article_data.get('ArticleTitle', '') or ''
                        title = ' '.join(title.split())

                        abstract_parts = []
                        abs_node = article_data.get('Abstract', {})
                        if abs_node:
                            for t in abs_node.get('AbstractText', []):
                                if t:
                                    abstract_parts.append(str(t))
                        abstract = ' '.join(abstract_parts)
                        abstract = ' '.join(abstract.split())

                        if not abstract:
                            continue

                        authors = []
                        for a in article_data.get('AuthorList', [])[:5]:
                            last = a.get('LastName', '')
                            first = a.get('ForeName', '')
                            if last:
                                authors.append(f"{first} {last}".strip())

                        journal = article_data.get('Journal', {}).get('Title', '')
                        pubdate_node = article_data.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {})
                        year = pubdate_node.get('Year', '')
                        month = pubdate_node.get('Month', '')
                        day = pubdate_node.get('Day', '')
                        pubdate = '-'.join(filter(None, [str(year), str(month), str(day)]))

                        doi = ''
                        for aid in article.get('PubmedData', {}).get('ArticleIdList', []):
                            if aid.attributes.get('IdType') == 'doi':
                                doi = str(aid)
                                break

                        ptypes = article_data.get('PublicationTypeList', []) or []
                        article_type = str(ptypes[0]) if ptypes else ''

                        # 提取MeSH术语
                        mesh_terms = []
                        mesh_list = medline.get('MeshHeadingList', [])
                        if mesh_list:
                            for mesh in mesh_list:
                                desc = mesh.get('DescriptorName', '')
                                if desc:
                                    mesh_terms.append(str(desc))

                        # 提取作者关键词
                        keywords = []
                        kw_list = medline.get('KeywordList', [])
                        if kw_list:
                            for kw_group in kw_list:
                                if hasattr(kw_group, 'Keyword'):
                                    for kw in kw_group.Keyword:
                                        if kw:
                                            keywords.append(str(kw))

                        all_papers.append({
                            'pmid': pmid,
                            'title': title,
                            'authors': authors,
                            'journal': journal,
                            'pubdate': str(year),
                            'abstract': abstract,
                            'article_type': article_type,
                            'doi': doi,
                            'pubmed_url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else '',
                            'mesh_terms': mesh_terms,
                            'keywords': keywords,
                        })
                    except Exception:
                        continue

                _time.sleep(0.15)

            except Exception as e:
                logger.warning(f"PubMed检索失败 ({query[:50]}...): {e}")
                continue

        # 回退：如果精确检索没有结果，用简化关键词再搜一次
        if not all_papers:
            logger.warning("PubMed精确检索无结果，尝试简化检索...")
            try:
                keywords = search_strategy.get('keywords', [])
                en_kw = [k for k in keywords if k.isascii() and len(k) > 1][:3]
                if en_kw:
                    simple_query = ' OR '.join(f'"{k}"[Title/Abstract]' for k in en_kw)
                    simple_query += ' AND ("2019/01/01"[Date - Publication] : "2026/12/31"[Date - Publication])'
                    handle = Entrez.esearch(db='pubmed', term=simple_query, retmax=20, sort='relevance', retmode='xml')
                    search_data = Entrez.read(handle)
                    handle.close()
                    idlist = search_data.get('IdList', [])
                    if idlist:
                        _time.sleep(0.15)
                        handle = Entrez.efetch(db='pubmed', id=idlist, retmode='xml')
                        xml_data = Entrez.read(handle)
                        handle.close()
                        for article in xml_data.get('PubmedArticle', []):
                            try:
                                medline = article.get('MedlineCitation', {})
                                article_data = medline.get('Article', {})
                                pmid = str(medline.get('PMID', ''))
                                if pmid in seen_pmids or not pmid:
                                    continue
                                seen_pmids.add(pmid)
                                title = article_data.get('ArticleTitle', '') or ''
                                title = ' '.join(title.split())
                                abstract_parts = []
                                abs_node = article_data.get('Abstract', {})
                                if abs_node:
                                    for t in abs_node.get('AbstractText', []):
                                        if t:
                                            abstract_parts.append(str(t))
                                abstract = ' '.join(abstract_parts)
                                abstract = ' '.join(abstract.split())
                                if not abstract:
                                    continue
                                authors = []
                                for a in article_data.get('AuthorList', [])[:5]:
                                    last = a.get('LastName', '')
                                    first = a.get('ForeName', '')
                                    if last:
                                        authors.append(f"{first} {last}".strip())
                                journal = article_data.get('Journal', {}).get('Title', '')
                                pubdate_node = article_data.get('Journal', {}).get('JournalIssue', {}).get('PubDate', {})
                                year = pubdate_node.get('Year', '')
                                doi = ''
                                for aid in article.get('PubmedData', {}).get('ArticleIdList', []):
                                    if aid.attributes.get('IdType') == 'doi':
                                        doi = str(aid)
                                        break
                                all_papers.append({
                                    'pmid': pmid,
                                    'title': title,
                                    'authors': authors,
                                    'journal': journal,
                                    'pubdate': str(year),
                                    'abstract': abstract,
                                    'article_type': '',
                                    'doi': doi,
                                    'pubmed_url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                    'mesh_terms': [],
                                    'keywords': [],
                                })
                            except Exception:
                                continue
                        logger.info(f"PubMed简化检索回退: 获取 {len(all_papers)} 篇")
            except Exception as e:
                logger.warning(f"PubMed简化检索也失败: {e}")

        return all_papers

    # ── Step 3: LLM评估文献相关性 ──

    def _llm_filter_relevant_papers(self, papers: List[Dict], problem_definition: Dict, student_profile: Dict = None) -> List[Dict]:
        """
        由LLM评估每篇文献的相关性，与算法评分融合后筛选。

        评分融合策略：
        - 算法分（英文keyword+IF+recency+MeSH）占 30%
        - LLM语义分（0-3映射到0-100）占 70%
        - 最终分 = 算法分 * 0.3 + LLM分 * 0.7
        - 如果query以中文为主（无英文关键词），完全依赖LLM分
        - 筛选阈值：融合分 >= 25（相当于LLM给2分即可通过）
        """
        if not papers:
            return []

        try:
            from api_clients import anthropic_client

            clinical_problem = problem_definition.get('clinical_problem', '')
            scientific_problem = problem_definition.get('scientific_problem', '')

            # ── 构建算法评分用的英文query ──
            # 1) 从原始输入和临床问题中提取已有的英文术语（CT/MRI/AI等）
            raw_input = student_profile.get('raw_input', '') if student_profile else ''
            if isinstance(raw_input, dict):
                raw_input = str(raw_input)
            all_text = raw_input + ' ' + clinical_problem + ' ' + scientific_problem
            import re
            en_terms = list(set(re.findall(r'[a-zA-Z][a-zA-Z0-9_\-]+', all_text)))

            # 2) 中文医学术语 → 英文映射（覆盖疾病/模态/技术/任务）
            cn_to_en = {
                # 疾病
                '脑卒中': 'stroke', '中风': 'stroke', '脑梗': 'cerebral infarction',
                '肺癌': 'lung cancer', '肺结节': 'pulmonary nodule',
                '肝癌': 'liver cancer', '乳腺癌': 'breast cancer',
                '脑肿瘤': 'brain tumor', '骨折': 'fracture',
                '冠心病': 'coronary heart disease', '心肌': 'myocardial',
                '肺炎': 'pneumonia', '结核': 'tuberculosis',
                '糖尿病': 'diabetic', '视网膜': 'retinal',
                '前列腺': 'prostate', '胰腺': 'pancreatic',
                '结肠': 'colorectal', '直肠': 'rectal',
                '脊柱': 'spinal', '膝关节': 'knee', '关节': 'joint',
                '动脉': 'artery', '血管': 'vascular', '静脉': 'venous',
                # 成像模态
                'ct': 'CT', 'mri': 'MRI', 'x线': 'x-ray', 'x光': 'x-ray',
                '超声': 'ultrasound', '造影': 'contrast',
                'pet': 'PET', '核医学': 'nuclear medicine',
                '钼靶': 'mammography', 'dsa': 'DSA',
                '影像': 'imaging', '图像': 'image',
                # AI/技术
                '深度学习': 'deep learning', '机器学习': 'machine learning',
                '神经网络': 'neural network', '卷积': 'convolutional',
                '分割': 'segmentation', '检测': 'detection',
                '分类': 'classification', '诊断': 'diagnosis',
                '辅助诊断': 'computer-aided diagnosis',
                '特征提取': 'feature extraction',
                '迁移学习': 'transfer learning',
                '预训练': 'pre-training', '微调': 'fine-tuning',
                '生成对抗': 'generative adversarial', '对抗网络': 'GAN',
                '注意力机制': 'attention mechanism', 'transformer': 'transformer',
                '自然语言处理': 'natural language processing',
                # 临床任务
                '筛查': 'screening', '预测': 'prediction',
                '预后': 'prognosis', '治疗': 'treatment',
                '良恶性': 'benign malignant', '恶性': 'malignant',
                '分期': 'staging', '分级': 'grading',
                '量化': 'quantification', '测量': 'measurement',
                '三维': '3d', '重建': 'reconstruction',
                '随访': 'follow-up', '生存': 'survival',
                '报告': 'report', '文本': 'text',
                '回顾性': 'retrospective', '前瞻性': 'prospective',
                '多中心': 'multicenter', '随机': 'randomized',
            }
            for cn, en in cn_to_en.items():
                if cn in all_text:
                    en_terms.append(en)
            en_terms = list(set(en_terms))  # 去重

            algo_query = ' '.join(en_terms) if en_terms else clinical_problem + ' ' + scientific_problem

            # 为每篇文献计算算法分（用于融合）
            algo_scores = self._compute_algo_scores(papers, algo_query)

            # 分批处理：每批15篇，避免LLM输出截断
            batch_size = 15
            batch_responses = []

            for batch_start in range(0, min(len(papers), 30), batch_size):
                batch_end = min(batch_start + batch_size, len(papers))
                batch = papers[batch_start:batch_end]

                papers_text = ""
                for i, p in enumerate(batch):
                    abstract_preview = (p.get('abstract', '') or '')[:200]
                    algo = algo_scores.get(batch_start + i, 50)
                    papers_text += f"[{batch_start + i + 1}] (算法参考分: {algo:.0f}) {p.get('title', '')}\n    摘要: {abstract_preview}...\n\n"

                prompt = f"""你是一名医学影像研究评审专家。请评估以下文献与研究问题的语义相关性。

研究问题：
- 临床问题：{clinical_problem}
- 科学问题：{scientific_problem}

评分标准：
- 3分（高度相关）：研究问题高度重叠，方法可直接迁移
- 2分（中度相关）：部分维度重叠，有借鉴价值
- 1分（低相关）：仅大领域相同
- 0分（不相关）：无关

文献列表（编号从{batch_start + 1}到{batch_end}）：
{papers_text}

返回JSON格式：
{{
  "relevant_papers": [
    {{"index": {batch_start + 1}, "score": 3, "reason": "简短说明", "key_insight": "关键发现"}},
    {{"index": {batch_start + 2}, "score": 2, "reason": "...", "key_insight": "..."}}
  ]
}}

要求：只返回JSON，不要额外文字。"""

                batch_max_tokens = 2000
                filter_sp = "你是一名医学影像研究评审专家。请评估文献与研究问题的语义相关性，只返回JSON格式，不要额外文字。"
                response = anthropic_client.call_longcat_api(prompt, max_tokens=batch_max_tokens, system_prompt=filter_sp)
                batch_responses.append(response)

            # 解析所有批次结果
            all_filtered = []
            for batch_idx, response in enumerate(batch_responses):
                try:
                    result = _safe_json_parse(response, context=f"EvidenceRetrieval._ai_screen_papers_batch{batch_idx}")
                    relevant = result.get('relevant_papers', [])

                    for item in relevant:
                        idx = item.get('index', 0) - 1
                        if 0 <= idx < len(papers):
                            llm_score_raw = item.get('score', 0)
                            llm_map = {0: 0.0, 1: 45.0, 2: 72.0, 3: 100.0}
                            llm_score = llm_map.get(llm_score_raw, 0.0)
                            algo_score = algo_scores.get(idx, 0)
                            algo_has_signal = algo_score > 10
                            fused = algo_score * 0.3 + llm_score * 0.7 if algo_has_signal else llm_score

                            if fused >= 20:
                                paper = papers[idx].copy()
                                paper['relevance_score'] = round(fused, 1)
                                paper['relevance_reason'] = item.get('reason', '')
                                paper['key_insight'] = item.get('key_insight', '')
                                paper['_algo_score'] = round(algo_score, 1)
                                paper['_llm_score'] = round(llm_score, 1)
                                all_filtered.append(paper)
                except (ValueError, KeyError) as e:
                    logger.warning(f"批次{batch_idx} JSON解析失败: {e}")
                    continue

            # 去重（按pmid或title）
            seen = set()
            filtered = []
            for p in all_filtered:
                key = p.get('pmid', '') or p.get('title', '')
                if key not in seen:
                    seen.add(key)
                    filtered.append(p)

            # 按融合分排序
            filtered.sort(key=lambda p: p['relevance_score'], reverse=True)

            if filtered:
                logger.info(f"  [EvidenceRetrieval] 融合评分: "
                           f"最高={filtered[0]['relevance_score']:.1f}, "
                           f"最低={filtered[-1]['relevance_score']:.1f}, "
                           f"共{len(filtered)}篇")
                return filtered

            # 回退：按算法分取前15篇
            logger.warning("  [EvidenceRetrieval] LLM未选出相关文献，回退到算法排序")
            fallback = sorted(range(len(papers)), key=lambda i: algo_scores.get(i, 50), reverse=True)
            return [papers[i] for i in fallback[:15]]

        except Exception as e:
            logger.warning(f"LLM相关性评估失败: {e}")
            return papers[:15]

    def _compute_algo_scores(self, papers: List[Dict], query: str) -> Dict[int, float]:
        """
        为每篇文献计算算法相关性分（0-100），用于与LLM分数融合。

        改进：
        - 接收已翻译的英文关键词query（由 _llm_filter_relevant_papers 构建）
        - 英文关键词匹配标题/摘要
        - 时效性 + 期刊质量 + MeSH匹配
        - 无任何匹配时返回基础分5（而非0），避免完全无信号
        """
        import math
        import re

        query_lower = query.lower().strip()

        # 提取英文关键词（长度>1的纯英文/数字词）
        query_words_en = [w for w in query_lower.split() if len(w) > 1 and re.match(r'^[a-zA-Z0-9_\-]+$', w)]

        # 如果没有英文关键词，返回基础分5（保留时效性和期刊分）
        if not query_words_en:
            return {idx: 5.0 for idx in range(len(papers))}

        scores = {}
        for idx, paper in enumerate(papers):
            score = 0.0
            title = (paper.get('title', '') or '').lower()
            abstract = (paper.get('abstract', '') or '').lower()
            mesh_terms = paper.get('mesh_terms', [])
            keywords = paper.get('keywords', [])

            # ── 1. 标题匹配（最高35分）──
            title_matched = sum(1 for w in query_words_en if w in title)
            if title_matched > 0:
                coverage = title_matched / len(query_words_en)
                score += coverage * 35.0
                # 连续词组匹配额外加分
                for i in range(len(query_words_en) - 1):
                    bigram = f"{query_words_en[i]} {query_words_en[i+1]}"
                    if bigram in title:
                        score += 5.0

            # ── 2. 摘要匹配（最高30分）──
            abs_matched = sum(1 for w in query_words_en if w in abstract)
            if abs_matched > 0:
                coverage = abs_matched / len(query_words_en)
                score += coverage * 20.0
                # 频次加权（对数TF）
                total_count = sum(abstract.count(w) for w in query_words_en if w in abstract)
                tf_bonus = min(math.log(1 + total_count) * 2, 10)
                score += tf_bonus

            # ── 3. MeSH/关键词匹配（最高15分）──
            mesh_kw_text = ' '.join(mesh_terms + keywords).lower()
            mesh_matched = sum(1 for w in query_words_en if w in mesh_kw_text)
            if mesh_matched > 0:
                score += min(mesh_matched * 5.0, 15.0)

            # ── 4. 时效性（最高12分）──
            pubdate = paper.get('pubdate', '')
            if pubdate:
                try:
                    year = int(str(pubdate)[:4])
                    diff = 2026 - year
                    recency = 100 * math.exp(-0.15 * max(diff, 0))
                    score += recency * 0.12
                except:
                    score += 3.0
            else:
                score += 3.0

            # ── 5. 期刊质量（最高8分）──
            journal = (paper.get('journal', '') or '').lower()
            if journal:
                if any(kw in journal for kw in ['radiology', 'european radiol', 'ajr', 'investigative radiol']):
                    score += 7.0
                elif any(kw in journal for kw in ['medical image', 'ieee tmi', 'neuroimage']):
                    score += 7.5
                elif any(kw in journal for kw in ['nature', 'science', 'cell', 'lancet', 'jama', 'nejm', 'bmj']):
                    score += 8.0
                elif any(kw in journal for kw in ['clinical', 'academic', 'journal of']):
                    score += 5.0
                else:
                    score += 3.0

            scores[idx] = min(score, 100.0)

        return scores

    # ── Step 4: LLM从文献中提炼证据 ──

    def _llm_analyze_evidence(self, papers: List[Dict], problem_definition: Dict, student_profile: Dict = None) -> Dict:
        """由LLM从筛选后的文献中提炼：方法学趋势、研究空白、证据综述"""
        if not papers:
            return {
                'research_gaps': {},
                'evidence_summary': {'summary': '未检索到相关文献'},
                'methodological_insights': [],
            }

        try:
            from api_clients import anthropic_client

            clinical_problem = problem_definition.get('clinical_problem', '')

            # 构建文献摘要文本（最多10篇，每篇摘要截取300字）
            papers_text = ""
            for i, p in enumerate(papers[:10]):
                abstract = (p.get('abstract', '') or '')[:300]
                insight = p.get('key_insight', '')
                papers_text += f"[{i+1}] {p.get('title', '')} ({p.get('journal', '')}, {p.get('pubdate', '')})\n    摘要: {abstract}...\n    关键发现: {insight}\n\n"

            prompt = f"""你是一名医学影像研究专家。请基于以下文献，对研究问题进行深度证据分析。

研究问题：{clinical_problem}

已筛选的相关文献（共{len(papers)}篇）：
{papers_text}

请完成以下分析：
1. **方法学趋势**：这些文献中使用了哪些主要的研究方法和技术？有哪些值得借鉴的设计？
2. **研究空白**：现有研究存在哪些不足？有哪些尚未解决的问题？（这些将是你方案的创新点来源）
3. **证据综述**：已有研究得出了哪些关键结论？对你研究问题的支撑程度如何？
4. **可借鉴的方法**：哪些文献的实验设计、统计方法、技术路线可以直接借鉴？

返回JSON格式：
{{
  "research_gaps": {{
    "methodological_gaps": ["方法学空白1", "方法学空白2"],
    "technical_gaps": ["技术空白1", "技术空白2"],
    "clinical_gaps": ["临床空白1"],
    "research_gaps": ["总体研究空白1", "总体研究空白2"]
  }},
  "evidence_summary": {{
    "summary": "证据综述总览（2-3句话）",
    "key_findings": ["关键发现1", "关键发现2", "关键发现3"],
    "supporting_evidence": "对研究问题的支撑程度评价",
    "contradictory_evidence": "是否存在相矛盾的证据"
  }},
  "methodological_insights": [
    {{"method": "方法名称", "description": "方法描述", "source_paper": "来源文献编号", "applicability": "对你研究的适用性评价"}},
    {{"method": "...", "description": "...", "source_paper": "...", "applicability": "..."}}
  ]
}}

要求：
- 研究空白要具体，不要泛泛而谈
- 方法学洞察要可操作，直接指出可以用什么方法
- 只返回JSON
"""

            analyze_sp = "你是一名医学影像研究专家。请基于文献对研究问题进行深度证据分析，只返回JSON格式，不要额外文字。"
            response = anthropic_client.call_longcat_api(prompt, max_tokens=3500, system_prompt=analyze_sp)
            try:
                result = _safe_json_parse(response, context="EvidenceRetrieval._ai_analyze_evidence")
                return result
            except (ValueError, KeyError) as e:
                logger.warning(f"LLM证据分析JSON解析失败: {e}")
                return {
                    'research_gaps': {'general': ['证据分析失败']},
                    'evidence_summary': {'summary': f'检索到 {len(papers)} 篇文献，但证据分析失败'},
                    'methodological_insights': [],
                }

        except Exception as e:
            logger.warning(f"LLM证据分析失败: {e}")
            return {
                'research_gaps': {'general': [f'证据分析失败: {str(e)}']},
                'evidence_summary': {'summary': f'检索到 {len(papers)} 篇文献'},
                'methodological_insights': [],
            }

class PlanGenerationAgent(BaseAgent):
    """方案生成智能体 - 负责生成研究方案（检索增强版）

    【新】在生成方案时自动注入全局证据池上下文，
    确保每个模块的生成都基于真实文献证据。
    """

    def __init__(self):
        super().__init__("PlanGenerationAgent")

    def process_message(self, message: AgentMessage) -> Dict:
        """处理证据和需求，生成研究方案（检索增强版）"""
        if message.message_type == 'evidence_and_requirements':
            # 【新】在生成前查询证据池，为 prompt 注入文献上下文
            input_data = message.content
            problem_definition = input_data.get('problem_definition', {})
            student_profile = input_data.get('student_profile', {})
            self._inject_evidence_context(input_data, problem_definition, student_profile)
            return self.generate_research_plan(input_data)
        return {}

    def _inject_evidence_context(self, input_data: Dict, problem_definition: Dict, student_profile: Dict):
        """将证据池上下文注入到 input_data 中，供 build_research_prompt 使用"""
        try:
            clinical_problem = problem_definition.get('clinical_problem', '')
            specialty = student_profile.get('extracted_info', {}).get('specialty', '')
            raw_input = student_profile.get('raw_input', '')
            if isinstance(raw_input, dict):
                raw_input = str(raw_input)

            query = f"{clinical_problem} {specialty} {raw_input[:50]}"
            evidence_text = self.get_evidence_context(topic=query, max_papers=8)

            if evidence_text:
                # 注入到 evidence 字段中
                input_data['_evidence_pool_context'] = evidence_text
                logger.info(f"  [PlanGeneration] 注入证据池上下文: {len(evidence_text)} 字符")
        except Exception as e:
            logger.debug(f"  [PlanGeneration] 证据池注入跳过: {e}")

    def generate_research_plan(self, input_data: Dict) -> Dict:
        """生成研究方案"""
        try:
            # 准备输入数据
            student_profile = input_data.get('student_profile', {})
            problem_definition = input_data.get('problem_definition', {})
            evidence = input_data.get('evidence', {})
            input_parsing = input_data.get('input_parsing', {})

            # 最多尝试3次生成：首次4000 tokens → 超时则降为2500 → 再超时则2000
            max_tokens_options = [3000, 2500, 2000]
            last_error = None
            for attempt in range(min(3, len(max_tokens_options))):
                try:
                    max_tokens = max_tokens_options[attempt]
                    # 构建完整的Prompt
                    prompt = self.build_research_prompt(student_profile, problem_definition, evidence, input_parsing, attempt)

                    logger.info(f"  [PlanGeneration] 尝试生成 (attempt={attempt+1}, max_tokens={max_tokens})")
                    # 调用AI生成方案
                    ai_response = anthropic_client.call_longcat_api(prompt, max_tokens=max_tokens)

                    # 解析和结构化AI响应
                    research_plan = self.parse_ai_response(ai_response)

                    # 检查AI生成的方案是否与用户输入相关
                    if self.is_plan_relevant(research_plan, student_profile):
                        # 后处理和优化
                        optimized_plan = self.optimize_plan(research_plan, student_profile, evidence)
                        # 如果 timeline 太短或太模板化，用画像重新生成
                        optimized_plan = self._ensure_timeline_quality(optimized_plan, student_profile, evidence)
                        return optimized_plan
                    else:
                        if attempt < 2:
                            logger.warning("AI生成的方案相关性不足，尝试重新生成")
                            continue
                        else:
                            logger.warning("多次生成方案相关性仍不足，返回已生成的最优方案")
                            optimized_plan = self.optimize_plan(research_plan, student_profile, evidence)
                            optimized_plan = self._ensure_timeline_quality(optimized_plan, student_profile, evidence)
                            return optimized_plan

                except Exception as ai_error:
                    import traceback
                    tb = traceback.format_exc()
                    last_error = ai_error
                    logger.error(f"AI生成失败 (attempt {attempt+1}): {str(ai_error)}")
                    # 如果是超时错误，降低max_tokens重试
                    err_str = str(ai_error).lower()
                    if 'timeout' in err_str or 'timed out' in err_str:
                        logger.warning(f"  [PlanGeneration] 超时，降低max_tokens为{max_tokens_options[min(attempt+1, len(max_tokens_options)-1)]}重试")
                        continue
                    # 其他错误也重试一次
                    if attempt < 2:
                        continue
                    break

            # 所有尝试均失败
            err_msg = str(last_error) if last_error else '未知错误'
            logger.error(f"  [PlanGeneration] 所有{max_tokens_options[:3]}tokens尝试均失败，最后错误: {err_msg}")
            return {
                'error': '研究方案生成失败',
                'details': f'AI服务暂时不可用，已尝试3次均失败。最后错误: {err_msg}',
                'suggestion': '这可能是由于AI服务暂时繁忙。请稍后重试，或尝试简化您的研究需求描述。'
            }

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"方案生成失败: {str(e)}\n{tb}")
            return {'error': str(e)}

    def build_research_prompt(self, student_profile: Dict, problem_definition: Dict, evidence: Dict, input_parsing: Dict = None, attempt: int = 0) -> str:
        """构建研究方案生成的Prompt — 基于真实文献证据生成方案"""

        # 【新】优先使用证据池注入的上下文（来自全局证据池查询）
        _evidence_pool_context = evidence.get('_evidence_pool_context', '')

        raw_input = student_profile.get('raw_input', '')
        extracted_info = self._safe_dict_get(student_profile.get('extracted_info', {}))
        research_focus = self._safe_dict_get(student_profile.get('research_focus', {}))

        # 学生基本信息
        grade = extracted_info.get('grade', '未知')
        specialty = extracted_info.get('specialty', '未知')
        experience = extracted_info.get('experience_level', '中等')
        resources = extracted_info.get('available_resources', [])
        # available_resources 可能是列表（旧格式）或字典（新格式，如 {"imaging_equipment": true}）
        if isinstance(resources, dict):
            resources_str = ', '.join(k for k, v in resources.items() if v) if any(resources.values()) else '基础资源'
        else:
            resources_str = ', '.join(resources) if resources else '基础资源'
        # 关键画像字段
        time_constraint = extracted_info.get('time_constraint', '未知')
        statistical_bg = extracted_info.get('statistical_background', '未知')
        ai_bg = extracted_info.get('ai_background', '未知')
        target_journal = extracted_info.get('target_journal_level', '未知')
        has_data = extracted_info.get('has_data', '未知')
        data_volume = extracted_info.get('data_volume', '未知')
        gold_standard = extracted_info.get('gold_standard_available', '未知')
        follow_up = extracted_info.get('follow_up_available', '未知')
        case_scale = extracted_info.get('case_scale', '未知')
        expected_grad = extracted_info.get('expected_graduation', '未知')
        supervisor = extracted_info.get('supervisor_support', '未知')
        ethical = extracted_info.get('ethical_feasibility', '未知')
        cross_dept = extracted_info.get('cross_dept_resources', '未知')
        software = extracted_info.get('software_capability', '未知')

        # 输入解析结果
        disease_domain = input_parsing.get('disease_domain', '未指定') if input_parsing else '未指定'
        imaging_modality = input_parsing.get('imaging_modality', '未指定') if input_parsing else '未指定'
        research_task = input_parsing.get('research_task', '未指定') if input_parsing else '未指定'

        # 问题定义
        clinical_problem = problem_definition.get('clinical_problem', '')
        scientific_problem = problem_definition.get('scientific_problem', '')
        hypotheses = problem_definition.get('hypotheses', [])
        if isinstance(hypotheses, str):
            hypotheses = [hypotheses]
        _so = problem_definition.get('study_objectives', '')
        if isinstance(_so, dict):
            study_objectives = _so.get('primary', '')
        elif isinstance(_so, list):
            study_objectives = '; '.join(str(x) for x in _so)
        else:
            study_objectives = str(_so)

        # ── 文献证据（优先使用证据池上下文） ──
        _evidence_pool_used = bool(_evidence_pool_context)

        if _evidence_pool_used:
            # 使用证据池注入的结构化上下文（全局证据池查询结果）
            papers_text = _evidence_pool_context
            total_results = evidence.get('evidence_pool_stats', {}).get('total_papers', 0)
        else:
            # 回退到旧的 evidence 结构
            literature_results = evidence.get('literature_results', {})
            recommended_papers = literature_results.get('recommended_papers', [])
            total_results = literature_results.get('total_results', 0)
            search_strategy = evidence.get('search_strategy', {})

            # 格式化前8篇文献（标题+摘要+关键发现）
            papers_text = ""
            for i, paper in enumerate(recommended_papers[:8]):
                title = paper.get('title', '')
                journal = paper.get('journal', '')
                pubdate = paper.get('pubdate', '')
                abstract = (paper.get('abstract', '') or '')[:300]
                key_insight = paper.get('key_insight', '')
                relevance = paper.get('relevance_score', '')
                relevance_reason = paper.get('relevance_reason', '')
                papers_text += f"[{i+1}] {title} ({journal}, {pubdate})"
                if relevance:
                    # 用★直观显示相关度
                    stars = '★' * min(int(relevance / 20), 5) + '☆' * (5 - min(int(relevance / 20), 5))
                    papers_text += f"\n    相关度: {relevance}/100 {stars}"
                    if relevance_reason:
                        papers_text += f" — {relevance_reason}"
                papers_text += f"\n    摘要: {abstract}..."
                if key_insight:
                    papers_text += f"\n    关键发现: {key_insight}"
                papers_text += "\n\n"

        # 研究空白（新结构：含子分类）
        gaps = evidence.get('research_gaps', {})
        gap_text = ""
        if gaps:
            gap_parts = []
            gap_labels = {
                'methodological_gaps': '方法学空白',
                'technical_gaps': '技术空白',
                'clinical_gaps': '临床空白',
                'research_gaps': '总体空白',
            }
            for key, label in gap_labels.items():
                items = gaps.get(key, [])
                if items:
                    gap_parts.append(f"{label}：{'；'.join(items)}")
            if gap_parts:
                gap_text = '\n'.join(gap_parts)

        # 方法学洞察
        method_insights = evidence.get('methodological_insights', [])
        insights_text = ""
        if method_insights:
            for i, mi in enumerate(method_insights[:5]):
                method = mi.get('method', '')
                desc = mi.get('description', '')
                applicability = mi.get('applicability', '')
                source = mi.get('source_paper', '')
                insights_text += f"  {i+1}. {method}：{desc}"
                if applicability:
                    insights_text += f"（适用性：{applicability}）"
                if source:
                    insights_text += f" ——来自文献{source}"
                insights_text += "\n"

        # 证据综述
        evidence_summary = evidence.get('evidence_summary', {})
        summary_text = ""
        if evidence_summary:
            summary_desc = evidence_summary.get('summary', '')
            key_findings = evidence_summary.get('key_findings', [])
            supporting = evidence_summary.get('supporting_evidence', '')
            summary_text = f"证据总览：{summary_desc}\n"
            if key_findings:
                summary_text += "关键发现：\n" + '\n'.join(f"  - {f}" for f in key_findings[:5]) + "\n"
            if supporting:
                summary_text += f"对研究的支撑：{supporting}\n"

        # 如果是重试，加强约束
        retry_hint = ""
        if attempt > 0:
            retry_hint = f"""
⚠️ 重要提醒：这是第{attempt+1}次生成。方案必须紧密围绕学生的原始需求："{raw_input}"
- 研究题目必须包含学生需求中的核心术语
- 临床问题和科学问题必须直接回应学生的研究兴趣
- 不要生成泛泛的模板化方案
"""

        prompt = f"""你是一名放射学科研方法专家。请根据学生的真实需求和已检索的文献证据，生成一份**具体、可实施、紧扣学生输入**的研究方案。

## 学生的真实需求（核心依据）
"{raw_input}"
{retry_hint}
## 学生背景
- 年级：{grade} | 专业：{specialty} | 经验水平：{experience}
- 可用资源：{resources_str}
- 时间约束：{time_constraint} | 预期毕业：{expected_grad}
- 统计基础：{statistical_bg} | AI基础：{ai_bg}
- 目标期刊：{target_journal}
- 数据情况：{'已有数据（' + str(data_volume) + '）' if has_data == True else '无数据' if has_data == False else '未知'}
- 金标准：{'有' if gold_standard == True else '无' if gold_standard == False else '未知'}
- 随访数据：{'有' if follow_up == True else '无' if follow_up == False else '未知'}
- 病例规模：{case_scale}
- 软件/编程能力：{software}
- 导师支持：{supervisor} | 伦理可行性：{ethical}
- 跨科合作：{cross_dept}

## 研究问题
- 临床问题：{clinical_problem}
- 科学问题：{scientific_problem}
- 假设：{'；'.join(hypotheses) if hypotheses else '待完善'}
- 目标：{study_objectives}

## 文献证据（共检索到{total_results}篇相关文献）

### 核心文献
{papers_text if papers_text else '暂无检索到相关文献'}

### 研究空白
{gap_text if gap_text else '暂无明确研究空白'}

### 可借鉴的方法学
{insights_text if insights_text else '暂无特定方法学建议'}

### 证据综述
{summary_text if summary_text else '暂无综述'}

## 生成要求
1. 方案必须**紧扣学生的原始需求**"{raw_input}"，不能偏离
2. 研究题目中必须包含学生需求中的核心关键词
3. 技术方案要具体（说明用什么模型/方法/数据），不要泛泛而谈
4. 研究设计要与技术方案一致
5. 创新点要基于上述研究空白，指出具体的新贡献
6. 统计分析方法要与研究设计和终点指标匹配，并考虑学生的统计基础（{statistical_bg}）
7. **实施时间表必须根据学生情况定制**：
   - 年级（{grade}）：研一学生需要更多学习时间，研三需要更紧凑
   - 时间约束（{time_constraint}）：紧急项目需压缩时间线，宽松项目可分阶段
   - 预期毕业（{expected_grad}）：时间表中关键节点必须早于毕业时间
   - 数据情况：无数据时需预留数据收集时间，有数据时可缩短前期
   - 导师支持（{supervisor}）：支持弱时需预留更多自主探索时间
   - **总时间跨度**：如果时间约束是24个月以上，timeline必须覆盖24-36个月的完整周期，不能只写12个月；如果是12-24个月，必须覆盖12-24个月
8. 研究设计要考虑学生的实际条件：{'无数据时必须使用公开数据集或合作获取数据' if has_data == False else ''}{'；有' + str(data_volume) + '数据时可进行内部验证' if has_data == True else ''}
9. 所有字段值必须是纯文本字符串，列表用分号或换行分隔
10. 只返回JSON，不要任何额外文字
11. **禁止在创新点和标题中使用"首次""首创""国内首次""世界首次"等绝对化表述**，因为这类表述极易被文献证伪。应使用"本研究尝试""本研究旨在探索""本研究拟结合"等谦逊表述。

## 输出JSON格式
{{
  "title": "研究题目（从上述'可借鉴的方法学'和'研究空白'中选取最具创新性的技术切入点，标题中必须体现具体的技术方法名称，如'基于原型网络的少样本肺结节分类'而非泛化的'基于深度学习的肺结节诊断'；如果研究空白指向数据稀缺问题，标题应体现小样本/半监督/自监督等方向；如果研究空白指向可解释性，标题应体现可解释AI方向）",
  "background": "研究背景（指出具体的研究空白和意义，必须引用上述文献证据中的具体不足）",
  "clinical_problem": "临床问题（必填！必须输出上方「临床问题」部分的完整内容，不得留空、不得写待补充）",
  "scientific_problem": "科学问题",
  "hypothesis": "研究假设（必须与上述研究空白直接对应）",
  "objectives": "研究目标（分号分隔）",
  "study_design": "研究设计（具体的研究类型和方法，必须与技术方案一致）",
  "subjects_criteria": "纳排标准（分号分隔）",
  "variables_endpoints": "变量与终点（分号分隔）",
  "statistical_analysis": "统计分析方法",
  "innovation": "创新点（必须逐条对应上述'研究空白'，每条创新点要说明解决了哪个具体空白，分号分隔）",
  "risks_alternatives": "风险与备选（分号分隔）",
  "timeline": "研究时间表（分号分隔，精确到月，必须覆盖时间约束要求的全部月数。如24个月则必须包含第1-24月的安排，不能只写前12个月）"
}}"""

        return prompt

    def is_plan_relevant(self, research_plan: Dict, student_profile: Dict) -> bool:
        """检查生成的方案是否与用户输入相关 — 宽松匹配，避免误杀"""
        raw_input = student_profile.get('raw_input', '')
        if isinstance(raw_input, dict):
            logger.warning(f"is_plan_relevant: raw_input is dict: {list(raw_input.keys())}")
            raw_input = str(raw_input)
        elif not isinstance(raw_input, str):
            raw_input = str(raw_input)
        raw_input = raw_input.strip()
        if not raw_input or len(raw_input) < 3:
            return True

        title = (research_plan.get('title', '') or '')
        clinical_problem = (research_plan.get('clinical_problem', '') or '')
        scientific_problem = (research_plan.get('scientific_problem', '') or '')
        study_design = (research_plan.get('study_design', '') or '')
        objectives = (research_plan.get('objectives', '') or '')
        background = (research_plan.get('background', '') or '')
        hypothesis = (research_plan.get('hypothesis', '') or '')
        plan_text = f"{title} {clinical_problem} {scientific_problem} {study_design} {objectives} {background} {hypothesis}"

        import re
        # 提取中文词汇（1-6字）— 降低最小长度到1，捕获"肺"、"CT"等单字/双字术语
        cn_words = re.findall(r'[一-鿿]{1,6}', raw_input)
        # 提取英文术语（含数字，如CT、MRI、ResNet50）
        en_words = re.findall(r'[a-zA-Z][a-zA-Z0-9]*', raw_input)
        keywords = list(set(cn_words + en_words))

        # 过滤掉太通用的词
        stop_words = {'研究', '分析', '使用', '通过', '进行', '需要', '希望',
                      '应该', '可以', '实现', '方法', '技术', '系统', '模型',
                      '我想', '想要', '一个', '什么', '怎么', '如何',
                      'the', 'and', 'for', 'with', 'this', 'that', 'from', 'are',
                      'was', 'were', 'been', 'have', 'has', 'had', 'will', 'would',
                      'could', 'should', 'may', 'might', 'can', 'shall'}
        keywords = [kw for kw in keywords if kw.lower() not in stop_words and len(kw) >= 1]

        if not keywords:
            return True

        # 对每个关键词做子串匹配（不区分大小写）
        plan_text_lower = plan_text.lower()
        matched = []
        for kw in keywords:
            if kw.lower() in plan_text_lower:
                matched.append(kw)

        ratio = len(matched) / len(keywords) if keywords else 1.0

        # 极宽松条件：10% 或至少1个关键词匹配即通过（AI生成的方案通常都会包含至少1个）
        if ratio < 0.1 and len(matched) < 1:
            logger.info(f"方案相关性检查失败: 匹配关键词 {matched}/{keywords} (比例: {ratio:.2f})")
            return False

        logger.info(f"方案相关性检查通过: 匹配关键词 {matched}/{keywords} (比例: {ratio:.2f})")
        return True

    def _ensure_timeline_quality(self, plan: Dict, student_profile: Dict, evidence: Dict) -> Dict:
        """确保 timeline 质量：如果太短或太模板化，用 LLM 根据画像重新生成"""
        timeline = plan.get('timeline', '')
        # 判断 timeline 是否需要重新生成
        needs_regen = (
            not timeline
            or len(timeline.strip()) < 50
            or timeline.strip() == '待补充: timeline'
            or '【请根据' in timeline  # 上一步留下的占位符
        )
        if not needs_regen:
            return plan

        logger.info("  [PlanGeneration] timeline 质量不足，根据画像重新生成")

        extracted = student_profile.get('extracted_info', {})
        grade = extracted.get('grade', '未知')
        specialty = extracted.get('specialty', '未知')
        time_constraint = extracted.get('time_constraint', '中等')
        has_data = extracted.get('has_data')
        statistical_bg = extracted.get('statistical_background', '')
        ai_bg = extracted.get('ai_background', '')
        expected_grad = extracted.get('expected_graduation', '未知')
        supervisor = extracted.get('supervisor_support', '未知')
        raw_input = student_profile.get('raw_input', '')
        study_design = plan.get('study_design', '')

        try:
            from api_clients import anthropic_client

            # 计算总月数
            _total_months = 12  # 默认
            if time_constraint in ('6个月以内', '紧急'):
                _total_months = 6
            elif time_constraint in ('6-12个月',):
                _total_months = 12
            elif time_constraint in ('12-24个月',):
                _total_months = 24
            elif time_constraint in ('24个月以上', '宽松'):
                _total_months = 36

            prompt = f"""你是一名放射学科研管理专家。请根据以下学生画像和研究方案，制定一份**详细、可执行**的实施时间表。

## 学生画像
- 年级：{grade} | 专业：{specialty}
- 时间约束：{time_constraint}（共 {_total_months} 个月）| 预期毕业：{expected_grad}
- 统计基础：{statistical_bg} | AI基础：{ai_bg}
- 导师支持：{supervisor}
- 数据情况：{'已有数据' if has_data == True else '无数据，需自行收集' if has_data == False else '未明确'}

## 研究方案概况
- 研究需求：{raw_input[:200]}
- 研究设计：{study_design[:200]}

## 制定要求
1. 时间表必须**精确到月**，覆盖从第1个月到第{_total_months}个月的完整周期，不得只写前12个月
2. 必须考虑学生年级特点：
   - 研一/博一：需包含文献调研和方法学习阶段（至少2个月）
   - 研二：可压缩学习期，聚焦创新实验
   - 研三：必须紧凑，确保毕业前完成核心工作
   - 博三/博四：需体现深度和系统性
3. 时间跨度要求：{'压缩至最短周期，优先核心实验，6个月内完成全部工作' if _total_months <= 6 else '合理安排各阶段，12个月内完成核心工作' if _total_months <= 12 else '可分阶段推进，前12个月完成数据收集和初步实验，后' + str(_total_months - 12) + '个月完成深入分析和论文撰写' if _total_months <= 24 else '可从容安排，前12个月完成基础实验，中间12个月深入验证和扩展实验，最后' + str(_total_months - 24) + '个月完成论文撰写和投稿'}
4. 数据情况：{'无数据时需预留2-3个月数据收集' if has_data == False else '有数据可直接进入方法开发'}
5. 统计/AI基础薄弱时需预留学习时间
6. 关键里程碑（开题、中期、投稿）必须早于预期毕业时间
7. 格式：用分号分隔每个阶段，每个阶段标注月份范围（如"第1-3月"、"第4-12月"、"第13-24月"）和具体任务
8. **必须覆盖全部{_total_months}个月**，不能只写前12个月

请直接输出时间表文本（不要JSON，不要解释）：
"""

            timeline_sp = "你是一名放射学科研管理专家。请根据学生画像和研究方案制定详细可执行的实施时间表，直接输出时间表文本，不要JSON，不要解释。"
            new_timeline = anthropic_client.call_longcat_api(prompt, max_tokens=1000, system_prompt=timeline_sp)
            if new_timeline and len(new_timeline.strip()) > 30:
                plan['timeline'] = new_timeline.strip()
                logger.info(f"  [PlanGeneration] timeline 重新生成成功: {plan['timeline'][:80]}...")
            else:
                logger.warning("  [PlanGeneration] timeline 重新生成失败，保留原值")

        except Exception as e:
            logger.warning(f"  [PlanGeneration] timeline 重新生成异常: {e}")

        return plan

    def generate_title_from_input(self, raw_input: str, approach: str, research_gaps: Dict = None) -> str:
        """基于用户输入生成创新性研究标题 — 完全由AI驱动，不使用模板"""

        # 防止过长输入被当作标题
        if len(raw_input) > 200:
            return ""

        # 尝试用AI生成标题
        title = self._generate_title_with_ai(raw_input, approach, research_gaps)
        if title:
            title = self._clean_title_from_json(title)
            if 10 <= len(title) <= 100:
                return title

        # 最终回退：返回空字符串，让主生成流程的AI来定标题
        return ""

    def _generate_title_with_ai(self, raw_input: str, approach: str, research_gaps: Dict = None) -> str:
        """调用AI生成非模板化标题"""
        try:
            from api_clients import anthropic_client

            # 构建研究空白上下文
            gaps_context = ""
            if research_gaps:
                gap_parts = []
                for key in ('methodological_gaps', 'technical_gaps', 'clinical_gaps', 'research_gaps'):
                    items = research_gaps.get(key, [])
                    if items:
                        gap_parts.append('；'.join(str(x) for x in items[:3]))
                if gap_parts:
                    gaps_context = f"\n\n现有研究空白：{' | '.join(gap_parts)}\n请从上述空白中选取最具创新性的方向作为标题切入点。"

            prompt = f"""
你是一名医学影像AI研究专家。用户提出了以下研究需求：
"{raw_input}"

用户提到的方法背景：{approach}{gaps_context}

请为该研究生成一个创新的研究标题。要求：
1. 绝对禁止使用"基于深度学习的"、"基于卷积神经网络的"、"基于ResNet的"、"基于U-Net的"、"基于Transformer的"、"基于机器学习的"、"基于人工智能的"等模板化表述
2. 标题必须体现具体的技术切入点（如"基于原型网络的少样本分类"），而非泛化的方向描述
3. 标题必须紧密围绕用户的实际研究需求，不要引入用户未提及的技术概念
   - 如果用户只提到了单一模态（如CT），绝对不要在标题中引入"多模态"
   - 优先从上述研究空白中找技术灵感，而非自由发挥
4. 标题长度控制在15-35字
5. 只返回标题文字，不要任何解释、引号、标点符号之外的字符

请直接输出标题：
"""

            title_sp = "你是一名医学影像AI研究专家。请为研究生成创新的研究标题，只输出标题文字，不要任何解释或额外文字。"
            title = anthropic_client.call_longcat_api(prompt, max_tokens=100, system_prompt=title_sp)
            if title:
                # 清理标题
                title = title.strip().strip('"').strip("'").strip("「」")
                # 如果标题包含多行，只取第一行
                if '\n' in title:
                    title = title.split('\n')[0].strip()
                return title
            return ""
        except Exception as e:
            logger.warning(f"AI标题生成失败: {str(e)}")
            return ""

    def extract_main_disease(self, raw_input: str) -> str:
        """提取主要疾病 — 按匹配数量选择最佳疾病，避免顺序偏向"""
        diseases = {
            '乳腺癌': ['乳腺癌', '乳腺肿瘤'],
            '肝癌': ['肝癌', '肝肿瘤', '肝细胞癌'],
            '骨折': ['骨折', '骨质断裂'],
            '脑肿瘤': ['脑肿瘤', '颅内肿瘤', '脑内占位'],
            '脑卒中': ['脑卒中', '中风', '脑血管意外'],
            '冠心病': ['冠脉狭窄', '冠状动脉狭窄', '冠心病'],
            '骨质疏松': ['骨质疏松', '骨质流失'],
            '肺炎': ['肺炎', '肺部感染'],
            '肺结核': ['肺结核', '结核'],
            '肺癌': ['肺癌', '肺肿瘤', '肺部肿瘤'],
            '肺结节': ['肺结节', '肺部结节', '肺内结节'],
        }

        # 按匹配关键词数量选择最佳疾病，避免字典顺序偏向
        best_disease = ''
        best_count = 0
        for disease, keywords in diseases.items():
            count = sum(1 for kw in keywords if kw in raw_input)
            if count > best_count:
                best_count = count
                best_disease = disease
        return best_disease

    def extract_anatomy(self, raw_input: str) -> str:
        """提取解剖部位 — 按匹配数量选择最佳部位，避免顺序偏向"""
        anatomy_map = {
            '腹部': ['腹部', '腹腔', '腹'],
            '骨骼': ['骨', '骨骼', '骨科'],
            '心脏': ['心脏', '心', '心血管'],
            '肝脏': ['肝', '肝脏'],
            '乳腺': ['乳腺', '乳房'],
            '脑部': ['脑', '头部', '颅内', '中枢神经'],
            '胸部': ['胸部', '胸', '胸腔'],
        }

        # 按匹配关键词数量选择最佳部位
        best_anatomy = ''
        best_count = 0
        for anatomy, keywords in anatomy_map.items():
            count = sum(1 for kw in keywords if kw in raw_input)
            if count > best_count:
                best_count = count
                best_anatomy = anatomy
        return best_anatomy

    def extract_modality(self, raw_input: str) -> str:
        """提取影像模态"""
        modality_map = {
            'CT': ['CT', '计算机断层', '断层扫描'],
            'MRI': ['MRI', '磁共振', '核磁共振'],
            'X线': ['X线', 'X光', '平片'],
            '超声': ['超声', 'B超', '彩超'],
            '钼靶': ['钼靶', '乳腺钼靶'],
            'PET': ['PET', '正电子', '核医学']
        }

        for modality, keywords in modality_map.items():
            if any(keyword in raw_input for keyword in keywords):
                return modality
        return 'CT'  # 默认

    def extract_task_type(self, raw_input: str) -> str:
        """提取任务类型"""
        if any(word in raw_input for word in ['检测', '识别', '发现', '检出']):
            return '检测'
        elif any(word in raw_input for word in ['分割', '划分', '区域', '边界']):
            return '分割'
        elif any(word in raw_input for word in ['分类', '鉴别', '区分', '分型']):
            return '分类'
        elif any(word in raw_input for word in ['预测', '预后', '转归', '发展']):
            return '预测'
        elif any(word in raw_input for word in ['诊断', '辅助诊断', '筛查']):
            return '诊断'
        else:
            return '分析'

    def extract_innovation_focus(self, raw_input: str) -> str:
        """提取创新关注点"""
        if any(word in raw_input for word in ['早期', '早筛', '筛查']):
            return '早期筛查'
        elif any(word in raw_input for word in ['精准', '精确', '准确']):
            return '精准医疗'
        elif any(word in raw_input for word in ['实时', '快速', '效率']):
            return '高效诊断'
        elif any(word in raw_input for word in ['多模态', '多参数', '多序列']):
            return '多模态融合'
        elif any(word in raw_input for word in ['可解释', '解释性', '透明']):
            return '可解释AI'
        elif any(word in raw_input for word in ['小样本', '少样本', '数据稀缺']):
            return '小样本学习'
        else:
            return '智能辅助'

    def generate_innovative_titles(self, disease, anatomy, modality, task_type, approach, innovation, raw_input) -> list:
        """生成创新性标题 — 完全由AI驱动，不使用任何模板"""

        # 获取AI生成的技术方案
        specific_tech = self._get_ai_enhanced_tech_solution(raw_input, disease, task_type, approach)

        # 如果AI调用失败，回退
        if not specific_tech or specific_tech == approach:
            specific_tech = self._get_rule_based_tech_solution(approach)

        specific_tech = self._clean_tech_solution(specific_tech)

        # 用AI基于技术方案生成标题
        titles = self._generate_titles_with_ai(raw_input, disease, anatomy, modality, task_type, specific_tech)

        # 清理
        cleaned_titles = []
        for title in titles:
            cleaned = self._clean_title_from_json(title)
            if cleaned and len(cleaned) > 5:
                cleaned_titles.append(cleaned)

        return cleaned_titles if cleaned_titles else []

    def _generate_titles_with_ai(self, raw_input, disease, anatomy, modality, task_type, specific_tech) -> list:
        """调用AI生成3个非模板化标题"""
        try:
            from api_clients import anthropic_client

            prompt = f"""
你是一名医学影像AI研究专家。请为以下研究需求生成3个创新的研究标题：

用户原始需求：{raw_input}
疾病：{disease or '未指定'}
检查部位：{anatomy or '未指定'}
影像模态：{modality or '未指定'}
任务类型：{task_type or '未指定'}
技术方案：{specific_tech}

要求：
1. 每个标题必须体现具体的技术切入点（如"基于不确定性量化的肺结节良恶性鉴别"），而非泛化描述
2. 绝对禁止使用"基于深度学习的"、"基于ResNet的"、"基于U-Net的"、"基于Transformer的"、"基于机器学习的"等模板
3. 标题长度15-35字
4. 3个标题必须从不同技术角度切入（不能只是换同义词）
5. 标题必须紧扣用户原始需求，不要引入用户未提及的技术概念（如用户未提多模态，则标题中不能出现多模态）
6. 技术方向应从上述技术方案（{specific_tech}）中推导，确保标题与技术方案一致
7. 每行一个标题，编号1. 2. 3.

请直接输出3个标题：
"""

            titles_sp = "你是一名医学影像AI研究专家。请为研究需求生成3个创新标题，每行一个，编号1. 2. 3.，不要任何解释。"
            response = anthropic_client.call_longcat_api(prompt, max_tokens=200, system_prompt=titles_sp)
            if not response:
                return []

            # 解析标题
            titles = []
            for line in response.strip().split('\n'):
                line = line.strip()
                # 移除编号前缀
                import re
                line = re.sub(r'^\d+[\.\、\)\s]+', '', line).strip()
                if line and len(line) > 5:
                    titles.append(line)
            return titles[:3]
        except Exception as e:
            logger.warning(f"AI标题列表生成失败: {str(e)}")
            return []

    def _extract_tech_components(self, specific_tech: str) -> dict:
        """Extract key technical components from the AI-generated technical solution"""
        components = {
            'architecture': '深度学习',  # Default fallback
            'method': '',
            'innovation': '',
            'optimization': ''
        }

        # Clean up the specific_tech string first (remove JSON formatting if present)
        clean_tech = specific_tech
        if '{' in specific_tech and '}' in specific_tech:
            # Extract content from JSON-like format
            import re
            title_match = re.search(r'"title":\s*"([^"]+)"', specific_tech)
            if title_match:
                clean_tech = title_match.group(1)
            else:
                # Fallback: extract any technical terms
                clean_tech = specific_tech

        # Extract architecture (look for model names)
        architectures = ['注意力机制网络', '医学图像分割网络', '目标检测算法', '卷积神经网络']

        for arch in architectures:
            if arch in clean_tech:
                components['architecture'] = arch
                break

        # Extract methods (look for learning paradigms)
        methods = ['自监督学习', '自监督', '无监督学习', '联邦学习', '知识蒸馏',
                  '小样本学习', '对比学习', 'self-supervised', 'federated',
                  'distillation', 'few-shot', '预训练']

        for method in methods:
            if method in clean_tech:
                components['method'] = method
                break

        # Extract innovations (look for attention mechanisms, etc.)
        innovations = ['Coordinate Attention', 'Deformable Attention', 'CBAM', 'BiFPN',
                      'Focal Loss', '自适应', '动态', '注意力机制', '注意力', 'Attention']

        for innovation in innovations:
            if innovation in clean_tech:
                components['innovation'] = innovation
                break

        # Extract optimization aspects
        optimizations = ['轻量化', '压缩', '加速', '实时', 'edge', 'mobile',
                        'lightweight', '优化', '效率', '性能提升', '低延迟']

        for opt in optimizations:
            if opt in clean_tech:
                components['optimization'] = opt
                break

        return components

    def _get_ai_enhanced_tech_solution(self, raw_input: str, disease: str, task_type: str, approach: str) -> str:
        """使用AI生成真正创新且多样化的技术方案"""
        try:
            from api_clients import anthropic_client

            # 构建专门请求技术方案的AI提示词（不是完整研究计划）
            prompt = f"""
你是一名医学影像AI技术专家。请为以下研究需求提供一个创新的技术解决方案：

研究背景：{raw_input}
疾病类型：{disease if disease else '未指定'}
任务类型：{task_type if task_type else '检测/分类/分割'}
现有方法：{approach}

请提供一个真正创新的技术方案，要求：
1. 绝对禁止：Transformer、ResNet、U-Net、CNN、自监督学习、注意力机制、多组学整合
2. 必须从以下创新角度之一切入（选最匹配的）：
   - 跨域迁移：扩散模型、因果推断、图神经网络、NeRF、持续学习、元学习
   - 问题重构：不确定性量化、可解释定位、风险分层、边界建模
   - 约束驱动：少样本学习、联邦学习、边缘部署、主动学习
   - 深度融合：影像+病理+基因组跨尺度对齐、时序-空间联合建模
3. 方案必须精确到：用什么网络结构、什么损失函数、什么训练策略
4. 字数控制在100-200字内
5. 只返回技术方案描述，不要JSON格式

请直接输出技术方案：
"""

            # 调用AI API - 使用专门的技术方案生成接口
            ai_response = anthropic_client.call_tech_solution_api(prompt, max_tokens=200)

            # 清理AI响应
            if ai_response and len(ai_response.strip()) > 20:
                cleaned_response = ai_response.strip()

                # 移除可能的markdown代码块标记
                if cleaned_response.startswith('```'):
                    cleaned_response = cleaned_response.replace('```json', '').replace('```', '')

                # 如果意外返回了JSON格式，尝试提取内容
                if cleaned_response.startswith('{') and cleaned_response.endswith('}'):
                    try:
                        parsed = _safe_json_parse(cleaned_response, context="PlanGeneration._extract_title")
                        if 'title' in parsed:
                            return parsed['title']
                        elif 'solution' in parsed:
                            return parsed['solution']
                        else:
                            # 如果是其他JSON结构，返回前200个字符
                            return cleaned_response[:200]
                    except:
                        # 如果解析失败，只返回前200个字符
                        return cleaned_response[:200]

                # 返回清理后的响应（限制长度）
                return cleaned_response[:300]
            else:
                return self._get_creative_tech_solution(approach, task_type, disease)

        except Exception as e:
            logger.warning(f"AI创新技术方案生成失败，使用创意备选方案: {str(e)}")
            return self._get_creative_tech_solution(approach, task_type, disease)

    def _get_creative_tech_solution(self, approach: str, task_type: str, disease: str) -> str:
        """提供真正创新且非套路化的技术方案 — 每次调用AI生成，不使用固定库"""
        from api_clients import anthropic_client

        prompt = f"""
你是一名医学影像AI技术专家。请为一个{task_type}任务（疾病：{disease or '未指定'}）提供1个创新的技术方案。

现有方法背景：{approach}

要求：
1. 完全跳出"Transformer"、"ResNet"、"U-Net"、"CNN"、"自监督学习"等固定模式
2. 提出具体、可行的技术创新思路，精确到模块/层结构/损失函数级别
3. 优先从以下角度切入：
   - 跨域迁移（扩散模型、因果推断、图神经网络、NeRF等）
   - 问题重构（不确定性量化、可解释定位、风险分层）
   - 约束驱动（少样本、联邦学习、边缘部署）
   - 深度融合（影像+病理+基因组跨尺度对齐）
4. 字数控制在50-150字
5. 只返回技术方案描述，不要JSON格式

请直接输出技术方案：
"""

        tech_sp = "你是一名医学影像AI技术专家。请提供创新的技术解决方案，只返回技术方案描述，不要JSON格式，不要额外解释。"
        solution = anthropic_client.call_longcat_api(prompt, max_tokens=300, system_prompt=tech_sp)
        if solution and len(solution.strip()) > 20:
            return solution.strip()
        raise RuntimeError("AI技术方案生成返回空结果")

    def _get_rule_based_tech_solution(self, approach: str) -> str:
        """基于规则的技术方案映射 — 仅作为最后手段，优先使用AI生成"""
        # 将泛化表述转换为更具体的技术方向
        tech_mapping = {
            '深度学习': '深度神经网络（需指定具体架构）',
            '机器学习': '机器学习（需指定具体算法）',
            '人工智能': 'AI技术（需指定具体方法）',
            '神经网络': '神经网络（需指定具体架构）',
            'CNN': '卷积神经网络架构（如ResNet/EfficientNet/Swin Transformer）',
            'U-Net': '编码器-解码器分割网络（如U-Net++/Attention U-Net/Nested U-Net）',
            'YOLO': '单阶段目标检测（如YOLOv8/RT-DETR）',
            'ResNet': '残差网络架构（如ResNet-50/ResNet-101/EfficientNet）',
            'Transformer': '自注意力架构（如Swin Transformer/ViT/DeiT）'
        }

        for generic_tech, specific_tech in tech_mapping.items():
            if generic_tech in approach:
                return specific_tech

        return approach

    def _clean_title_from_json(self, title: str) -> str:
        """清理标题中的JSON内容和多余文本"""
        if not title or not isinstance(title, str):
            return ""

        # 第一步：移除JSON结构
        title = title.strip()

        # 如果包含JSON-like内容，尝试提取title字段
        if '"title":' in title or "'title':" in title:
            import re
            # 尝试匹配 "title": "..." 格式
            match = re.search(r'["\']title["\']:\s*["\']([^"\']+)["\']', title)
            if match:
                title = match.group(1)
            else:
                # 如果没有匹配到，移除所有JSON标记
                title = re.sub(r'[{}\[\]"\':,]', '', title)

        # 第二步：移除JSON标记
        title = title.replace('{', '').replace('}', '').replace('[', '').replace(']', '')

        # 第三步：处理可能的多行内容 - 只保留第一行
        if '\n' in title:
            title = title.split('\n')[0]

        # 第四步：移除多余的空白字符
        title = title.strip()

        # 第五步：如果标题过长（>100字），可能包含了多个字段，只保留前半部分
        if len(title) > 100:
            # 尝试在句号、分号处截断
            for delimiter in ['。', '；', '; ', '，']:
                if delimiter in title:
                    title = title.split(delimiter)[0]
                    break
            # 如果还是太长，截断到100字
            if len(title) > 100:
                title = title[:100]

        # 第六步：移除多余的空白字符
        title = title.strip()

        # 第七步：如果标题为空或太短，返回空字符串（让调用者处理）
        if len(title) < 5:
            return ""

        return title

    def _clean_tech_solution(self, tech_solution: str) -> str:
        """清理技术方案中的JSON内容"""
        if not tech_solution or not isinstance(tech_solution, str):
            return "深度学习算法"

        # 移除JSON标记
        tech_solution = tech_solution.replace('{', '').replace('}', '')

        # 如果包含JSON-like内容，尝试提取相关内容
        if '"title":' in tech_solution:
            import re
            match = re.search(r'"title":\s*"([^"]+)"', tech_solution)
            if match:
                tech_solution = match.group(1)
            else:
                # 如果没有匹配到，移除所有引号和冒号
                tech_solution = re.sub(r'["\':]', '', tech_solution)

        # 移除可能的背景或solution字段
        if '"background":' in tech_solution:
            import re
            match = re.search(r'"background":\s*"([^"]+)"', tech_solution)
            if match:
                tech_solution = match.group(1)

        if '"solution":' in tech_solution:
            import re
            match = re.search(r'"solution":\s*"([^"]+)"', tech_solution)
            if match:
                tech_solution = match.group(1)

        # 移除多余的空白字符
        tech_solution = tech_solution.strip()

        # 如果技术方案为空或太短，返回默认值
        if len(tech_solution) < 5:
            return "深度学习算法"

        return tech_solution

    def select_best_title(self, title_options: list, raw_input: str) -> str:
        """选择最适合的标题"""
        # 基于用户输入的关键词匹配度选择
        best_title = title_options[0]  # 默认选择第一个
        max_score = 0

        for title in title_options:
            score = self.calculate_title_relevance(title, raw_input)
            if score > max_score:
                max_score = score
                best_title = title

        return best_title

    def calculate_title_relevance(self, title: str, raw_input: str) -> float:
        """计算标题与用户输入的相关性分数"""
        score = 0
        input_words = raw_input.lower().split()
        title_words = title.lower().split()

        # 关键词匹配
        for word in input_words:
            if len(word) > 1 and word in title:
                score += 1

        # 长度适中加分
        if 15 <= len(title) <= 40:
            score += 0.5

        # 包含具体疾病名称加分
        diseases = ['肺结节', '肺癌', '脑卒中', '脑肿瘤', '肝癌', '乳腺癌']
        for disease in diseases:
            if disease in raw_input and disease in title:
                score += 2

        return score

    def format_key_findings(self, findings: List[str]) -> str:
        """格式化关键发现"""
        if not findings:
            return "基于最新文献分析，该领域有较好的研究基础"

        formatted = []
        for i, finding in enumerate(findings[:3], 1):
            formatted.append(f"{i}. {finding}")

        return '\n'.join(formatted)

    def parse_ai_response(self, ai_response: str) -> Dict:
        """解析AI响应"""
        try:
            import json
            logger.info(f"Attempting to parse AI response, length: {len(ai_response)}")

            # Clean the response first - remove any markdown code blocks
            cleaned_response = ai_response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            research_plan = _safe_json_parse(cleaned_response, context="PlanGeneration._ai_generate_plan")
            logger.info(f"Successfully parsed AI response with keys: {list(research_plan.keys())}")
            return research_plan
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"AI响应解析失败: {str(e)}, response preview: {ai_response[:200]}...")
            raise

    def _enhance_with_literature(self, plan: Dict, literature_results: Dict) -> Dict:
        """基于文献检索结果增强方案内容"""
        if not literature_results or not literature_results.get('papers'):
            return plan

        papers = literature_results.get('papers', [])
        if not papers:
            return plan

        # 提取相关文献的关键信息
        recent_papers = papers[:3]  # 取最新的3篇

        # 基于文献更新背景描述
        literature_insights = []
        for paper in recent_papers:
            title = paper.get('title', '')
            if title:
                literature_insights.append(title)

        if literature_insights:
            # 更新背景描述，使其与实际文献相关联
            original_background = plan.get('background', '')
            enhanced_background = f"{original_background}\n\n基于最新文献分析，相关研究包括：{'；'.join(literature_insights[:2])}"
            plan['background'] = enhanced_background

        return plan

    def optimize_plan(self, plan: Dict, student_profile: Dict, evidence: Dict) -> Dict:
        """优化研究方案 — 根据学生画像深度定制"""
        extracted = student_profile.get('extracted_info', {})
        grade = extracted.get('grade', '')
        time_constraint = extracted.get('time_constraint', '中等')
        has_data = extracted.get('has_data')
        statistical_bg = extracted.get('statistical_background', '')
        ai_bg = extracted.get('ai_background', '')

        # ── 根据画像调整 timeline ──
        plan = self._customize_timeline(plan, grade, time_constraint, has_data, statistical_bg, ai_bg)

        # ── 根据方案复杂度调整目标 ──
        if grade in ('研一', '博一'):
            plan = self._simplify_for_junior(plan)
        elif grade in ('研三', '博三', '博四及以上'):
            plan = self._enhance_for_senior(plan)

        # 提取研究空白（用于标题优化和创新点优化）
        research_gaps = evidence.get('research_gaps', {})

        # 优化标题 - 仅在AI生成的标题明显异常时才重新生成
        current_title = plan.get('title', '').strip()
        title_is_bad = (
            not current_title or
            len(current_title) > 100 or
            '{' in current_title or '}' in current_title or
            len(current_title) < 8
        )
        if title_is_bad:
            raw_input = student_profile.get('raw_input', '')
            if raw_input and len(raw_input) < 200:
                approach = student_profile.get('research_focus', {}).get('technical_approach', '深度学习')
                optimized_title = self.generate_title_from_input(raw_input, approach, research_gaps)
                if optimized_title and 10 < len(optimized_title) < 100:
                    plan['title'] = optimized_title

        # 基于证据调整创新点（refine_innovation_points 不再做机械拼接，主Prompt已完成优化）
        if research_gaps:
            plan['innovation'] = self.refine_innovation_points(plan.get('innovation', ''), research_gaps)

        # 确保所有必需字段存在
        required_fields = [
            'title', 'background', 'clinical_problem', 'scientific_problem',
            'hypothesis', 'objectives', 'study_design', 'subjects_criteria',
            'variables_endpoints', 'statistical_analysis', 'innovation',
            'risks_alternatives', 'timeline'
        ]

        for field in required_fields:
            if field not in plan or not plan[field]:
                # innovation 字段特殊处理：若 research_gaps 可用，先尝试AI生成
                if field == 'innovation' and research_gaps:
                    plan['innovation'] = self.refine_innovation_points('', research_gaps)
                else:
                    plan[field] = f"待补充: {field}"

        return plan

    def _customize_timeline(self, plan: Dict, grade: str, time_constraint: str,
                            has_data, statistical_bg: str, ai_bg: str) -> Dict:
        """根据学生画像定制实施时间表"""
        # 构建 timeline 指导说明，让 LLM 在生成时参考
        timeline_guidelines = []

        # 年级相关
        if grade in ('研一', '博一'):
            timeline_guidelines.append("研一/博一学生：需预留1-2个月文献调研和方法学习，实践周期适当延长")
        elif grade == '研二':
            timeline_guidelines.append("研二学生：已有一定基础，可适当压缩学习周期，聚焦创新点")
        elif grade == '研三':
            timeline_guidelines.append("研三学生：时间紧张，需紧凑安排，确保毕业前完成核心实验和论文撰写")
        elif grade in ('博三', '博四及以上'):
            timeline_guidelines.append("高年级博士生：需体现深度，可安排多中心验证或更复杂的实验设计")

        # 时间约束（支持中文选项值）
        if time_constraint in ('6个月以内', '紧急'):
            timeline_guidelines.append("⚠️ 时间紧急（6个月以内）：需压缩至最短周期，优先核心实验，砍掉非必要环节")
        elif time_constraint in ('6-12个月',):
            timeline_guidelines.append("时间偏紧（6-12个月）：合理安排各阶段，确保质量，适当并行任务")
        elif time_constraint in ('12-24个月',):
            timeline_guidelines.append("时间适中（12-24个月）：可分阶段推进，预留充足的验证和优化时间")
        elif time_constraint in ('24个月以上', '宽松'):
            timeline_guidelines.append("时间宽松（24个月以上）：可从容安排各阶段，预留充足验证和深入探索时间")
        else:
            timeline_guidelines.append(f"时间约束（{time_constraint}）：合理安排各阶段，确保质量")

        # 数据情况
        if has_data == False:
            timeline_guidelines.append("⚠️ 无数据：需预留2-3个月数据收集/获取时间，建议使用公开数据集加速")
        elif has_data == True:
            timeline_guidelines.append("已有数据：可跳过数据收集阶段，直接进入方法开发和验证")

        # 技能基础
        if statistical_bg in ('薄弱', '基础'):
            timeline_guidelines.append("统计基础薄弱：建议预留时间学习统计方法，或寻求统计专家合作")
        if ai_bg in ('薄弱', '基础'):
            timeline_guidelines.append("AI基础薄弱：建议前1-2个月集中学习深度学习框架和工具")

        # 将指导注入 timeline 字段（如果 timeline 太短或太模板化）
        current_timeline = plan.get('timeline', '')
        # 如果 timeline 为空、太短（<30字）或明显是模板，用指导覆盖
        is_generic = (
            not current_timeline
            or len(current_timeline.strip()) < 30
            or current_timeline.strip() == '待补充: timeline'
        )
        if is_generic:
            # 计算总月数，确保覆盖完整周期
            _months_map = {'6个月以内': 6, '紧急': 6, '6-12个月': 12, '12-24个月': 24, '24个月以上': 36, '宽松': 36}
            _total_m = _months_map.get(time_constraint, 12)
            timeline_guidelines.insert(0, f"总时间跨度：{_total_m}个月，必须覆盖第1-{_total_m}月的完整安排，不能只写前12个月")
            plan['timeline'] = "【请根据以下学生画像信息制定详细时间表】\n" + '\n'.join(
                f"- {g}" for g in timeline_guidelines
            )
            plan['_timeline_needs_regeneration'] = True

        return plan

    def _simplify_for_junior(self, plan: Dict) -> Dict:
        """为低年级学生简化方案"""
        if 'objectives' in plan:
            obj = plan['objectives']
            if '重点学习' not in obj and '掌握' not in obj:
                plan['objectives'] = obj + "；重点掌握研究方法和基本实验流程"
        return plan

    def _enhance_for_senior(self, plan: Dict) -> Dict:
        """为高年级学生增强方案"""
        if 'objectives' in plan:
            obj = plan['objectives']
            if '高质量' not in obj:
                plan['objectives'] = obj + "；追求高质量研究成果；探索临床转化价值"
        if 'study_design' in plan:
            sd = plan['study_design']
            if '多中心' not in sd and '外部验证' not in sd:
                plan['study_design'] = sd + "；建议考虑多中心外部验证以提升说服力"
        return plan

    def refine_innovation_points(self, current_innovation: str, research_gaps: Dict) -> str:
        """基于研究空白优化创新点 — 若当前创新点为空/待补充/过短，则用AI基于研究空白生成"""
        # 检查当前创新点是否有效
        invalid_markers = ['待补充', '暂无', '无', '未填写', 'null', 'None']
        is_invalid = (
            not current_innovation
            or len(current_innovation.strip()) < 10
            or any(marker in current_innovation for marker in invalid_markers)
        )
        if not is_invalid:
            return current_innovation

        # 创新点无效，基于研究空白用AI生成
        try:
            gaps_text = json.dumps(research_gaps, ensure_ascii=False, indent=2) if research_gaps else ''
            if not gaps_text or gaps_text == '{}':
                return current_innovation if current_innovation else '本研究拟针对现有影像诊断流程中的效率瓶颈，提出基于AI的辅助诊断方案，具有一定的方法学创新和临床应用价值'

            prompt = f"""你是一名放射学科研方法学专家。以下是从文献分析中提取的「研究空白」，请基于这些空白，为该研究方案生成2-4条具体、可落地的创新点。

### 研究空白
{gaps_text}

要求：
1. 每条创新点必须明确对应一个具体的研究空白
2. 创新点要具体（说明在方法/技术/应用上的新贡献），禁止空泛表述（如"首次提出""填补空白"等）
3. 创新点之间要有区分度，不能重复
4. 用分号分隔各条创新点
5. 只输出创新点文本，不要额外解释

创新点："""

            ai_response = anthropic_client.call_longcat_api(prompt, max_tokens=800)
            generated = ai_response.strip() if ai_response else ''

            if generated and len(generated) > 10:
                logger.info(f"  [PlanGeneration] AI兜底生成创新点: {generated[:80]}...")
                return generated
            else:
                logger.warning("  [PlanGeneration] AI兜底生成创新点失败，返回默认值")
                return '本研究拟针对现有影像诊断流程中的效率瓶颈，提出基于AI的辅助诊断方案，具有一定的方法学创新和临床应用价值'

        except Exception as e:
            logger.error(f"  [PlanGeneration] AI兜底生成创新点异常: {e}")
            return current_innovation if current_innovation else '本研究拟针对现有影像诊断流程中的效率瓶颈，提出基于AI的辅助诊断方案，具有一定的方法学创新和临床应用价值'


class CritiqueAgent(BaseAgent):
    """批判评估智能体 - 负责方案评估和批判性审查"""

    def __init__(self):
        super().__init__("CritiqueAgent")

    def process_message(self, message: AgentMessage) -> Dict:
        """处理研究方案，进行批判性评估"""
        if message.message_type == 'research_plan':
            # 支持新的打包格式和旧的直接格式
            if isinstance(message.content, dict) and 'research_plan' in message.content:
                return self.critique_research_plan(
                    message.content['research_plan'],
                    student_profile=message.content.get('student_profile'),
                    evidence=message.content.get('evidence'),
                )
            return self.critique_research_plan(message.content)
        return {}

    def critique_research_plan(self, research_plan: Dict, student_profile: Dict = None, evidence: Dict = None) -> Dict:
        """批判性评估研究方案 - 使用AI进行真正的批判性审查（证据池增强版）"""
        try:
            # 【新】从证据池获取方法论和样本量参考证据，注入批判上下文
            self._inject_critique_evidence(research_plan, evidence)

            # 优先使用AI批判分析
            ai_critique = self._ai_critique_plan(research_plan, student_profile, evidence)
            if ai_critique and 'error' not in ai_critique:
                # 补充规则检查作为兜底
                ai_critique['validation_checklist'] = self.generate_validation_checklist(research_plan)
                ai_critique['ai_critiqued'] = True
                return ai_critique

            # 回退到规则方法
            logger.warning("AI批判分析失败，使用规则回退")
            critique = {
                'overall_assessment': self.assess_overall_quality(research_plan),
                'methodology_evaluation': self.evaluate_methodology(research_plan),
                'feasibility_analysis': self.analyze_feasibility(research_plan),
                'innovation_assessment': self.assess_innovation(research_plan),
                'risk_identification': self.identify_risks(research_plan),
                'improvement_suggestions': self.generate_improvement_suggestions(research_plan),
                'validation_checklist': self.generate_validation_checklist(research_plan),
                'ai_critiqued': False,
            }
            return critique

        except Exception as e:
            logger.error(f"方案评估失败: {str(e)}")
            return {'error': str(e)}

    def _inject_critique_evidence(self, research_plan: Dict, evidence: Dict):
        """【新】为批判注入证据池上下文 — 查询方法论标准和样本量参考"""
        try:
            study_design = research_plan.get('study_design', '')
            title = research_plan.get('title', '')
            query = f"{title} {study_design}"

            # 查询证据池中相关的方法学文献
            pool_context = self.get_evidence_context(topic=query, max_papers=5)
            if pool_context:
                if evidence is None:
                    evidence = {}
                evidence['_critique_pool_context'] = pool_context

            # 检查证据池中的冲突 — 如果方案的创新点与已知文献冲突，标记
            conflicts = self.detect_conflicts()
            if conflicts:
                evidence['_evidence_conflicts'] = conflicts
                logger.info(f"  [CritiqueAgent] 发现 {len(conflicts)} 个文献冲突")

        except Exception as e:
            logger.debug(f"  [CritiqueAgent] 证据注入跳过: {e}")

    def _ai_critique_plan(self, research_plan: Dict, student_profile: Dict = None, evidence: Dict = None) -> Dict:
        """使用AI对研究方案进行真正的批判性审查"""
        try:
            from api_clients import anthropic_client

            # 构建方案文本
            plan_text = ""
            field_names = {
                'title': '研究题目', 'background': '研究背景',
                'clinical_problem': '临床问题', 'scientific_problem': '科学问题',
                'hypothesis': '研究假设', 'objectives': '研究目标',
                'study_design': '研究设计', 'subjects_criteria': '纳排标准',
                'variables_endpoints': '变量与终点', 'statistical_analysis': '统计分析',
                'innovation': '创新点', 'risks_alternatives': '风险与备选',
                'timeline': '时间表',
            }
            for field, name in field_names.items():
                val = research_plan.get(field, '')
                if val and len(str(val).strip()) > 3 and '待补充' not in str(val):
                    plan_text += f"【{name}】\n{val}\n\n"

            # 学生背景
            student_context = ""
            if student_profile:
                extracted = student_profile.get('extracted_info', {})
                student_context = f"""
=== 学生背景 ===
- 培养阶段：{extracted.get('grade', '未知')}
- 专业方向：{extracted.get('specialty', '未知')}
- 统计基础：{extracted.get('statistical_background', '未知')}
- AI基础：{extracted.get('ai_background', '未知')}
- 是否有数据：{extracted.get('has_data', '未知')}
- 数据量：{extracted.get('data_volume', '未知')}
- 是否有金标准：{extracted.get('gold_standard_available', '未知')}
- 是否有随访：{extracted.get('follow_up_available', '未知')}
- 预期毕业：{extracted.get('expected_graduation', '未知')}
- 导师支持：{extracted.get('supervisor_support', '未知')}
"""

            # 文献证据摘要
            evidence_context = ""
            if evidence:
                gaps = evidence.get('research_gaps', {})
                summary = evidence.get('evidence_summary', {})
                all_gaps = []
                for k in ('methodological_gaps', 'technical_gaps', 'clinical_gaps', 'research_gaps'):
                    all_gaps.extend(gaps.get(k, []))
                if all_gaps:
                    evidence_context = f"\n=== 文献分析发现的研究空白 ===\n" + '\n'.join(f"- {g}" for g in all_gaps[:5])

                # 【新】注入证据池上下文（方法论参考 + 冲突检测）
                critique_pool = evidence.get('_critique_pool_context', '')
                if critique_pool:
                    evidence_context += f"\n\n=== 证据池参考文献（方法论与样本量标准）===\n{critique_pool}"

                conflicts = evidence.get('_evidence_conflicts', [])
                if conflicts:
                    conflict_text = '\n'.join(
                        f"- 冲突：{c.get('paper_a', '文献A')} vs {c.get('paper_b', '文献B')}：{c.get('conflict_reason', '结论不一致')}"
                        for c in conflicts[:3]
                    )
                    evidence_context += f"\n\n=== 证据池冲突警示 ===\n{conflict_text}"

            prompt = f"""
你是一名放射学科研评审专家，同时也是研究生的导师。请对以下研究方案进行**建设性评审**：既要指出真正的问题，也要认可方案中的合理成分。评分时以鼓励为主，但关键硬伤不放过。

=== 研究方案 ===
{plan_text}
{student_context}
{evidence_context}

请从以下维度进行批判性分析：

1. **可行性**：以学生的背景（年级、技术基础、资源、时间）来看，这个方案能完成吗？有哪些需要降低难度的点？给出具体改进建议，而不是一概否定。

2. **伦理可行性**：研究设计是否满足伦理要求？回顾性研究注意是否可以免除知情同意。

3. **统计闭环**：统计分析方法是否与研究设计匹配？样本量是否有依据？如果没有，给出合理的样本量建议范围即可。

4. **终点清晰度**：主要终点和次要终点是否明确定义、可测量？

5. **创新合理性**：创新点是否合理？**特别注意**：如果方案中出现了"首次将XX应用于XX""国内首次""首创"等绝对化表述，必须在 major_concerns 中明确指出并要求删除，因为这类表述极易被文献证伪，是严重的学术严谨性问题。创新点应使用"本研究尝试""本研究旨在探索"等谦逊表述。

6. **整体逻辑链**：从临床问题→假设→设计→终点，逻辑是否自洽？

返回JSON格式：
{{
  "overall_assessment": {{
    "score": 50-85的评分（以鼓励为主，有硬伤不超过85分，优秀方案可给80-85分）,
    "grade": "优秀/良好/中等/需要改进",
    "summary": "总体评价（2-3句话，先肯定合理部分，再指出核心问题）"
  }},
  "feasibility_analysis": {{
    "technical_feasibility": "技术可行性评价（给出降低难度的具体建议）",
    "resource_feasibility": "资源可行性评价",
    "time_feasibility": "时间可行性评价（给出合理的时间安排建议）",
    "ethical_feasibility": "伦理可行性评价",
    "biggest_obstacle": "最大的实施障碍（给出解决思路）"
  }},
  "methodology_evaluation": {{
    "study_design_adequacy": "研究设计是否合适",
    "sample_size_rationale": "样本量评价（如不足，给出建议范围而非一味否定）",
    "statistical_appropriateness": "统计方法是否恰当",
    "bias_control": "偏倚控制是否充分",
    "statistical_closure": "统计闭环是否完整"
  }},
  "endpoint_clarity": {{
    "primary_endpoint_clear": true/false,
    "secondary_endpoints_clear": true/false,
    "endpoint_measurable": true/false,
    "endpoint_hypothesis_aligned": true/false,
    "comments": "终点清晰度评价"
  }},
  "innovation_assessment": {{
    "novelty_level": "高/中/低",
    "innovation_authentic": true/false,
    "clinical_value": "临床价值评价",
    "technical_advancement": "技术进步评价",
    "innovation_summary": "创新合理性评价（检查是否有'首次'等绝对化表述）",
    "has_absolute_claims": true/false,
    "absolute_claims_details": "如果存在'首次''首创'等表述，列出具体内容"
  }},
  "risk_identification": {{
    "methodological_risks": ["方法学风险1"],
    "technical_risks": ["技术风险1"],
    "operational_risks": ["操作风险1"],
    "ethical_risks": ["伦理风险1"]
  }},
  "major_concerns": ["核心问题1", "核心问题2"],
  "improvement_suggestions": ["建设性建议1", "建设性建议2", "建设性建议3"],
  "logical_chain_complete": true/false,
  "logical_chain_comments": "逻辑链完整性评价"
}}

评分原则：
- 基础分60分，方案框架完整加5-10分，方法合理加5-10分，创新点合理加5-10分
- 有"首次""首创"等绝对化表述的，在 major_concerns 中指出并要求删除，score 不超过75分
- 样本量不足但其他方面良好，给65-75分并给出建议范围，而非一味打低分
- 目标是帮助学生改进方案，而非否定方案
- 只返回JSON，不要额外文字
"""

            critique_sp = "你是一名严格的放射学科研评审专家。请对研究方案进行真正有深度的批判性审查，只返回JSON格式，不要额外文字。"
            response = anthropic_client.call_longcat_api(prompt, max_tokens=2500, system_prompt=critique_sp)
            try:
                result = _safe_json_parse(response, context="CritiqueAgent._ai_critique_plan")
                return result
            except ValueError:
                logger.warning("AI批判分析JSON解析失败")
                return {'error': 'JSON解析失败'}

        except Exception as e:
            logger.warning(f"AI批判分析失败: {str(e)}")
            return {'error': str(e)}

    def assess_overall_quality(self, plan: Dict) -> Dict:
        """整体质量评估"""
        score = 0
        max_score = 100
        feedback = []

        # 检查完整性
        required_fields = ['title', 'background', 'objectives', 'study_design', 'statistical_analysis']
        completeness = sum(1 for field in required_fields if plan.get(field)) / len(required_fields)
        score += completeness * 30
        if completeness < 1.0:
            feedback.append(f"方案完整性：缺少{len(required_fields) - int(completeness * len(required_fields))}个关键部分")

        # 检查逻辑性
        logic_score = self.evaluate_logical_consistency(plan)
        score += logic_score * 25
        if logic_score < 0.8:
            feedback.append("逻辑一致性需要加强")

        # 检查可行性
        feasibility_score = self.evaluate_basic_feasibility(plan)
        score += feasibility_score * 25
        if feasibility_score < 0.7:
            feedback.append("方案可行性需要进一步论证")

        # 检查创新性
        innovation_score = self.evaluate_innovation(plan)
        score += innovation_score * 20
        if innovation_score < 0.6:
            feedback.append("创新点需要更加突出")

        return {
            'score': round(score, 1),
            'grade': self.get_grade(score),
            'feedback': feedback
        }

    def evaluate_logical_consistency(self, plan: Dict) -> float:
        """评估逻辑一致性"""
        consistency_checks = [
            ('background' in plan and 'clinical_problem' in plan),
            ('objectives' in plan and 'study_design' in plan),
            ('variables_endpoints' in plan and 'statistical_analysis' in plan)
        ]

        return sum(consistency_checks) / len(consistency_checks)

    def evaluate_basic_feasibility(self, plan: Dict) -> float:
        """评估基本可行性"""
        feasibility_indicators = [
            len(plan.get('subjects_criteria', '')) > 50,  # 纳排标准详细
            len(plan.get('statistical_analysis', '')) > 30,  # 统计方法明确
            'timeline' in plan and len(plan['timeline']) > 20  # 时间安排合理
        ]

        return sum(feasibility_indicators) / len(feasibility_indicators)

    def evaluate_innovation(self, plan: Dict) -> float:
        """评估创新性"""
        innovation = plan.get('innovation', '')
        if not innovation:
            return 0.0

        # 检查创新点是否具体
        innovation_indicators = [
            len(innovation) > 50,  # 创新点描述详细
            any(word in innovation for word in ['首次', '创新', '改进', '新方法']),  # 包含创新词汇
            ';' in innovation or '；' in innovation  # 多个创新点
        ]

        return sum(innovation_indicators) / len(innovation_indicators)

    def get_grade(self, score: float) -> str:
        """获取等级评定"""
        if score >= 90:
            return '优秀'
        elif score >= 80:
            return '良好'
        elif score >= 70:
            return '中等'
        elif score >= 60:
            return '及格'
        else:
            return '需要改进'

    def evaluate_methodology(self, plan: Dict) -> Dict:
        """方法学评估"""
        methodology_assessment = {
            'study_design_adequacy': self.assess_study_design(plan),
            'sample_size_rationale': self.assess_sample_size(plan),
            'statistical_appropriateness': self.assess_statistical_methods(plan),
            'bias_control': self.assess_bias_control(plan)
        }

        return methodology_assessment

    def assess_study_design(self, plan: Dict) -> str:
        """评估研究设计"""
        study_design = plan.get('study_design', '')

        if '回顾性' in study_design or 'retrospective' in study_design.lower():
            return '回顾性研究设计合理，适合探索性研究'
        elif '前瞻性' in study_design or 'prospective' in study_design.lower():
            return '前瞻性研究设计严谨，但实施难度较大'
        elif '横断面' in study_design or 'cross-sectional' in study_design.lower():
            return '横断面研究设计适用于描述性研究'
        else:
            return '研究设计描述不够清晰，需要进一步明确'

    def assess_sample_size(self, plan: Dict) -> str:
        """评估样本量合理性"""
        study_design = plan.get('study_design', '')

        # 检查是否提及样本量
        import re
        sample_size_mentions = re.findall(r'\d+', study_design)

        if sample_size_mentions:
            # 假设第一个数字是样本量
            sample_size = int(sample_size_mentions[0])
            if sample_size >= 100:
                return f'样本量({sample_size})充足，符合医学影像研究要求'
            elif sample_size >= 50:
                return f'样本量({sample_size})适中，但建议增加到100以上'
            else:
                return f'样本量({sample_size})偏小，可能影响统计效力'
        else:
            return '未明确提及样本量，需要补充样本量计算依据'

    def assess_statistical_methods(self, plan: Dict) -> str:
        """评估统计方法"""
        statistical_analysis = plan.get('statistical_analysis', '').lower()

        # 检查常用统计方法
        statistical_methods = {
            'roc分析': ['roc', 'auc', 'receiver operating'],
            '回归分析': ['regression', '回归', 'logistic'],
            '描述性统计': ['descriptive', '描述性', '均值', '标准差'],
            '假设检验': ['test', '检验', 't检验', '卡方']
        }

        found_methods = []
        for method, keywords in statistical_methods.items():
            if any(keyword in statistical_analysis for keyword in keywords):
                found_methods.append(method)

        if found_methods:
            return f'统计方法选择合理，包括：{"、".join(found_methods)}'
        else:
            return '统计方法描述不够详细，建议明确具体的统计检验方法'

    def assess_bias_control(self, plan: Dict) -> str:
        """评估偏倚控制"""
        bias_control_indicators = [
            plan.get('subjects_criteria', ''),  # 纳排标准
            plan.get('study_design', '')  # 研究设计
        ]

        bias_control_measures = [
            '随机' in ' '.join(bias_control_indicators),
            '盲法' in ' '.join(bias_control_indicators),
            '匹配' in ' '.join(bias_control_indicators)
        ]

        if any(bias_control_measures):
            return '考虑了偏倚控制措施，研究设计较为严谨'
        else:
            return '偏倚控制措施不够充分，建议增加随机化、盲法等控制措施'

    def analyze_feasibility(self, plan: Dict) -> Dict:
        """可行性分析"""
        feasibility = {
            'technical_feasibility': self.assess_technical_feasibility(plan),
            'resource_feasibility': self.assess_resource_feasibility(plan),
            'time_feasibility': self.assess_time_feasibility(plan),
            'ethical_feasibility': self.assess_ethical_feasibility(plan)
        }

        return feasibility

    def assess_technical_feasibility(self, plan: Dict) -> str:
        """评估技术可行性"""
        study_design = plan.get('study_design', '').lower()

        # 检查技术要求
        technical_requirements = {
            '深度学习': ['deep learning', 'cnn', '神经网络', 'ai'],
            '传统机器学习': ['machine learning', '随机森林', 'svm'],
            '统计方法': ['statistical', '回归', '假设检验']
        }

        required_tech = []
        for tech, keywords in technical_requirements.items():
            if any(keyword in study_design for keyword in keywords):
                required_tech.append(tech)

        if required_tech:
            return f'技术要求明确，包括：{"、".join(required_tech)}，在当前技术条件下可行'
        else:
            return '技术要求不够明确，建议明确具体的技术路线'

    def assess_resource_feasibility(self, plan: Dict) -> str:
        """评估资源可行性"""
        subjects_criteria = plan.get('subjects_criteria', '')

        # 检查资源需求
        if '多中心' in subjects_criteria or 'multicenter' in subjects_criteria.lower():
            return '多中心研究资源需求较大，需要充分的协作网络支持'
        elif '回顾性' in plan.get('study_design', ''):
            return '回顾性研究资源需求相对较小，可行性较高'
        else:
            return '资源需求适中，在一般研究条件下可行'

    def assess_time_feasibility(self, plan: Dict) -> str:
        """评估时间可行性"""
        timeline = plan.get('timeline', '')

        if not timeline:
            return '缺少明确的时间安排，需要制定详细的时间表'

        # 简单的时间评估
        time_indicators = ['月', 'week', 'month', '年']
        has_time_info = any(indicator in timeline for indicator in time_indicators)

        if has_time_info:
            return '时间安排明确，整体时间规划合理'
        else:
            return '时间安排不够具体，建议细化各阶段的时间节点'

    def assess_ethical_feasibility(self, plan: Dict) -> str:
        """评估伦理可行性"""
        ethical_indicators = [
            '伦理' in plan.get('study_design', ''),
            '知情同意' in plan.get('subjects_criteria', ''),
            'retrospective' in plan.get('study_design', '').lower()
        ]

        if any(ethical_indicators):
            return '伦理考虑充分，符合医学研究伦理要求'
        else:
            return '伦理考虑不够充分，建议补充伦理审批和知情同意相关内容'

    def assess_innovation(self, plan: Dict) -> Dict:
        """创新性评估"""
        innovation = plan.get('innovation', '')

        innovation_assessment = {
            'novelty_level': self.assess_novelty(innovation),
            'clinical_value': self.assess_clinical_value(innovation),
            'technical_advancement': self.assess_technical_advancement(innovation)
        }

        return innovation_assessment

    def assess_novelty(self, innovation: str) -> str:
        """评估新颖性"""
        if not innovation:
            return '创新点描述缺失'

        novelty_indicators = [
            '首次' in innovation,
            '创新' in innovation,
            '新方法' in innovation,
            '改进' in innovation
        ]

        if sum(novelty_indicators) >= 2:
            return '创新性强，具有显著的新颖性'
        elif sum(novelty_indicators) == 1:
            return '有一定创新性，但新颖性有待加强'
        else:
            return '创新性一般，建议进一步突出研究的独特之处'

    def assess_clinical_value(self, innovation: str) -> str:
        """评估临床价值"""
        clinical_keywords = ['临床', '应用', '诊断', '治疗', '患者', 'practical', 'clinical']

        if any(keyword in innovation.lower() for keyword in clinical_keywords):
            return '临床价值明确，具有实际应用前景'
        else:
            return '临床价值不够突出，建议强调研究的临床应用意义'

    def assess_technical_advancement(self, innovation: str) -> str:
        """评估技术进步"""
        technical_keywords = ['算法', '模型', '方法', '技术', 'algorithm', 'model', 'method']

        if any(keyword in innovation.lower() for keyword in technical_keywords):
            return '技术进步明显，方法学上有实质性改进'
        else:
            return '技术进步不够突出，建议明确技术层面的创新点'

    def identify_risks(self, plan: Dict) -> Dict:
        """识别研究风险"""
        risks = {
            'methodological_risks': self.identify_methodological_risks(plan),
            'technical_risks': self.identify_technical_risks(plan),
            'operational_risks': self.identify_operational_risks(plan),
            'ethical_risks': self.identify_ethical_risks(plan)
        }

        return risks

    def identify_methodological_risks(self, plan: Dict) -> List[str]:
        """识别方法学风险"""
        risks = []

        # 检查样本量风险
        study_design = plan.get('study_design', '')
        import re
        sample_sizes = re.findall(r'\d+', study_design)
        if sample_sizes and int(sample_sizes[0]) < 50:
            risks.append('样本量偏小，可能导致统计效力不足')

        # 检查研究设计风险
        if '前瞻性' in study_design and '多中心' not in study_design:
            risks.append('单中心前瞻性研究可能存在选择偏倚')

        # 检查统计方法风险
        statistical_analysis = plan.get('statistical_analysis', '')
        if not statistical_analysis or len(statistical_analysis) < 20:
            risks.append('统计方法描述不够详细，可能存在方法学缺陷')

        return risks

    def identify_technical_risks(self, plan: Dict) -> List[str]:
        """识别技术风险"""
        risks = []

        study_design = plan.get('study_design', '').lower()

        # 检查AI相关风险
        if any(tech in study_design for tech in ['deep learning', 'cnn', 'ai', '深度学习']):
            risks.append('深度学习模型可能存在过拟合风险')
            risks.append('AI模型的可解释性可能影响临床接受度')

        # 检查数据相关风险
        if '影像组学' in study_design or 'radiomics' in study_design:
            risks.append('影像组学特征可能存在批次效应和不稳定性')

        return risks

    def identify_operational_risks(self, plan: Dict) -> List[str]:
        """识别操作风险"""
        risks = []

        # 检查时间风险
        timeline = plan.get('timeline', '')
        if not timeline:
            risks.append('缺少详细时间安排，项目进度可能难以控制')

        # 检查资源风险
        subjects_criteria = plan.get('subjects_criteria', '')
        if '多中心' in subjects_criteria:
            risks.append('多中心研究协调难度大，可能存在数据标准化问题')

        return risks

    def identify_ethical_risks(self, plan: Dict) -> List[str]:
        """识别伦理风险"""
        risks = []

        # 检查伦理考虑
        study_design = plan.get('study_design', '').lower()
        if '前瞻性' in study_design and '伦理' not in study_design:
            risks.append('前瞻性研究需要充分的伦理考虑和审批')

        # 检查知情同意
        if '患者' in study_design and '知情同意' not in study_design:
            risks.append('涉及患者的研究需要完善的知情同意程序')

        return risks

    def generate_improvement_suggestions(self, plan: Dict) -> List[str]:
        """生成改进建议"""
        suggestions = []

        # 基于评估结果的改进建议
        overall_score = self.assess_overall_quality(plan).get('score', 0)

        if overall_score < 70:
            suggestions.append('整体方案需要大幅改进，建议重新审视研究设计')

        # 具体改进建议
        if not plan.get('statistical_analysis'):
            suggestions.append('补充详细的统计分析方法')

        if not plan.get('timeline'):
            suggestions.append('制定详细的研究时间表')

        if len(plan.get('innovation', '')) < 50:
            suggestions.append('进一步突出和详细描述研究的创新点')

        # 基于风险评估的建议
        risks = self.identify_risks(plan)
        all_risks = []
        for risk_type, risk_list in risks.items():
            all_risks.extend(risk_list)

        if len(all_risks) > 5:
            suggestions.append('研究风险较多，建议制定详细的风险应对策略')

        return suggestions

    def generate_validation_checklist(self, plan: Dict) -> Dict:
        """生成验证清单"""
        checklist = {
            'essential_components': self.check_essential_components(plan),
            'methodological_requirements': self.check_methodological_requirements(plan),
            'feasibility_criteria': self.check_feasibility_criteria(plan),
            'innovation_criteria': self.check_innovation_criteria(plan)
        }

        return checklist

    def check_essential_components(self, plan: Dict) -> Dict:
        """检查必要组成部分"""
        required_fields = [
            'title', 'background', 'clinical_problem', 'scientific_problem',
            'hypothesis', 'objectives', 'study_design', 'subjects_criteria',
            'variables_endpoints', 'statistical_analysis', 'innovation',
            'risks_alternatives', 'timeline'
        ]

        component_status = {}
        for field in required_fields:
            has_content = field in plan and len(str(plan[field])) > 10
            component_status[field] = {
                'present': field in plan,
                'adequate': has_content,
                'status': '完整' if has_content else ('存在' if field in plan else '缺失')
            }

        return component_status

    def check_methodological_requirements(self, plan: Dict) -> Dict:
        """检查方法学要求"""
        methodology_checks = {
            'clear_objectives': len(plan.get('objectives', '')) > 30,
            'detailed_design': len(plan.get('study_design', '')) > 50,
            'appropriate_statistics': len(plan.get('statistical_analysis', '')) > 20,
            'well_defined_criteria': len(plan.get('subjects_criteria', '')) > 30
        }

        return methodology_checks

    def check_feasibility_criteria(self, plan: Dict) -> Dict:
        """检查可行性标准"""
        feasibility_checks = {
            'reasonable_timeline': 'timeline' in plan and len(plan['timeline']) > 20,
            'clear_endpoints': len(plan.get('variables_endpoints', '')) > 20,
            'risk_assessment': 'risks_alternatives' in plan and len(plan['risks_alternatives']) > 20,
            'resource_consideration': self.check_resource_consideration(plan)
        }

        return feasibility_checks

    def check_resource_consideration(self, plan: Dict) -> bool:
        """检查资源考虑"""
        study_design = plan.get('study_design', '').lower()
        resource_indicators = ['数据', '样本', '设备', '软件', '资源']
        return any(indicator in study_design for indicator in resource_indicators)

    def check_innovation_criteria(self, plan: Dict) -> Dict:
        """检查创新性标准"""
        innovation_checks = {
            'novel_aspects': len(plan.get('innovation', '')) > 30,
            'clinical_relevance': self.check_clinical_relevance(plan),
            'technical_contribution': self.check_technical_contribution(plan)
        }

        return innovation_checks

    def check_clinical_relevance(self, plan: Dict) -> bool:
        """检查临床相关性"""
        clinical_keywords = ['临床', '诊断', '治疗', '患者', '应用']
        plan_text = ' '.join([str(v) for v in plan.values()]).lower()
        return any(keyword in plan_text for keyword in clinical_keywords)

    def check_technical_contribution(self, plan: Dict) -> bool:
        """检查技术贡献"""
        technical_keywords = ['算法', '模型', '方法', '技术', '改进']
        innovation = plan.get('innovation', '').lower()
        return any(keyword in innovation for keyword in technical_keywords)

class RevisionAgent(BaseAgent):
    """修订优化智能体 - 负责方案修订和优化"""

    def __init__(self):
        super().__init__("RevisionAgent")

    def process_message(self, message: AgentMessage) -> Dict:
        """处理评估和反馈，进行方案修订"""
        if message.message_type == 'critique_and_plan':
            return self.revise_research_plan(message.content)
        return {}

    def revise_research_plan(self, input_data: Dict) -> Dict:
        """修订研究方案 - 使用AI进行真正的问题驱动修订，并针对不同阶段学生输出不同复杂度版本（证据池增强版）"""
        try:
            original_plan = input_data.get('research_plan', {})
            critique = input_data.get('critique', {})
            user_feedback = input_data.get('user_feedback', '')
            student_profile = input_data.get('student_profile', None)

            # 【新】从证据池获取修订参考证据（方法论最佳实践、样本量标准）
            revision_evidence = self._get_revision_evidence(original_plan, critique)

            # 使用AI进行问题驱动的修订
            ai_revision = self._ai_revise_plan(original_plan, critique, user_feedback, student_profile, revision_evidence)
            if ai_revision and 'error' not in ai_revision:
                ai_revision['ai_revised'] = True
                # 对话式优化：AI 只返回修改的字段，需要合并到原方案
                if 'revised_plan' not in ai_revision:
                    # 对话式精简模式：ai_revision 本身就是修改的字段
                    merged = {**original_plan, **ai_revision}
                    ai_revision['revised_plan'] = merged
                return ai_revision

            # 回退到规则方法
            logger.warning("AI修订失败，使用规则回退")
            revision_needed = self.analyze_revision_needs(critique, user_feedback)
            revised_plan = self.perform_revisions(original_plan, revision_needed, critique)
            revision_summary = self.generate_revision_summary(original_plan, revised_plan, revision_needed)

            return {
                'revised_plan': revised_plan,
                'revision_summary': revision_summary,
                'improvement_areas': revision_needed,
                'next_steps': self.suggest_next_steps(revised_plan),
                'ai_revised': False,
            }

        except Exception as e:
            logger.error(f"方案修订失败: {str(e)}")
            return {'error': str(e)}

    def _get_revision_evidence(self, original_plan: Dict, critique: Dict) -> str:
        """【新】为修订获取证据池上下文 — 针对批判中发现的问题查询相关方法学文献"""
        try:
            # 从批判中提取关键问题作为查询词
            major_concerns = critique.get('major_concerns', [])
            methodology = critique.get('methodology_evaluation', {})
            study_design = original_plan.get('study_design', '')

            # 构建查询：方案主题 + 批判中发现的问题
            query_parts = [study_design]
            if major_concerns:
                query_parts.extend(major_concerns[:2])  # 取前2个硬伤
            if isinstance(methodology, dict):
                sample_issue = methodology.get('sample_size_rationale', '')
                if sample_issue and '不足' in sample_issue:
                    query_parts.append('sample size calculation')

            query = ' '.join(query_parts)
            evidence_text = self.get_evidence_context(topic=query, max_papers=5)
            if evidence_text:
                logger.info(f"  [RevisionAgent] 获取修订参考证据: {len(evidence_text)} 字符")
            return evidence_text or ''
        except Exception as e:
            logger.debug(f"  [RevisionAgent] 证据获取跳过: {e}")
            return ''

    def _ai_revise_plan(self, original_plan: Dict, critique: Dict, user_feedback: str, student_profile: Dict = None, revision_evidence: str = '') -> Dict:
        """使用AI进行真正的问题驱动修订，输出针对不同阶段学生的版本（证据池增强版）"""
        try:
            from api_clients import anthropic_client

            # 构建方案文本
            plan_text = ""
            field_names = {
                'title': '研究题目', 'background': '研究背景',
                'clinical_problem': '临床问题', 'scientific_problem': '科学问题',
                'hypothesis': '研究假设', 'objectives': '研究目标',
                'study_design': '研究设计', 'subjects_criteria': '纳排标准',
                'variables_endpoints': '变量与终点', 'statistical_analysis': '统计分析',
                'innovation': '创新点', 'risks_alternatives': '风险与备选',
                'timeline': '时间表',
            }
            for field, name in field_names.items():
                val = original_plan.get(field, '')
                if val and len(str(val).strip()) > 3:
                    plan_text += f"【{name}】\n{val}\n\n"

            # 批判结果
            major_concerns = critique.get('major_concerns', [])
            improvement_suggestions = critique.get('improvement_suggestions', [])
            feasibility = critique.get('feasibility_analysis', {})
            methodology = critique.get('methodology_evaluation', {})
            innovation = critique.get('innovation_assessment', {})
            risks = critique.get('risk_identification', {})

            critique_text = f"""
主要硬伤：{chr(10).join(f'- {c}' for c in major_concerns) if major_concerns else '无'}
改进建议：{chr(10).join(f'- {s}' for s in improvement_suggestions) if improvement_suggestions else '无'}
可行性评价：{json.dumps(feasibility, ensure_ascii=False)}
方法学评价：{json.dumps(methodology, ensure_ascii=False)}
创新性评价：{json.dumps(innovation, ensure_ascii=False)}
风险识别：{json.dumps(risks, ensure_ascii=False)}
"""

            # 学生背景
            student_context = ""
            if student_profile:
                extracted = student_profile.get('extracted_info', {})
                grade = extracted.get('grade', '未知')
                student_context = f"""
学生培养阶段：{grade}
专业方向：{extracted.get('specialty', '未知')}
统计基础：{extracted.get('statistical_background', '未知')}
AI基础：{extracted.get('ai_background', '未知')}
"""

            # 【新】证据池修订参考
            evidence_section = ""
            if revision_evidence:
                evidence_section = f"\n=== 证据池修订参考 ===\n{revision_evidence}\n"

            # 判断是否为对话式优化（只有少量用户反馈，无批判结果）
            is_chat_optimization = (not major_concerns and not improvement_suggestions
                                    and not any([feasibility, methodology, innovation, risks]))

            if is_chat_optimization:
                # ── 对话式优化：精简 prompt，只改用户要求的部分 ──
                prompt = f"""
你是一名放射学科研导师。用户希望对以下研究方案进行优化。

=== 当前研究方案 ===
{plan_text}

=== 用户的优化需求 ===
{user_feedback}
{student_context}
{evidence_section}

请根据用户的优化需求，对方案中**需要修改的部分**进行针对性修改。
不需要修改的内容保持原样即可。

返回JSON格式（只包含需要修改的字段，不需要修改的字段可以省略）：
{{
  "title": "（如果用户要求改题目则填写新题目，否则省略此字段）",
  "background": "（如果用户要求改背景则填写新背景，否则省略此字段）",
  "clinical_problem": "",
  "scientific_problem": "",
  "hypothesis": "",
  "objectives": "",
  "study_design": "",
  "subjects_criteria": "",
  "variables_endpoints": "",
  "statistical_analysis": "",
  "innovation": "",
  "risks_alternatives": "",
  "timeline": ""
}}

要求：
- 只修改用户要求修改的部分，其他字段省略（不要原样复制）
- 修改要实质性，不要只是换个说法
- 只返回JSON，不要额外文字
"""
            else:
                # ── 完整修订（有批判结果）：保留原有完整 prompt ──
                prompt = f"""
你是一名放射学科研导师。以下是一份研究方案和专家评审意见，请根据批判意见**重新修订方案**，并且**针对不同阶段的学生输出不同复杂度的版本**。

=== 原始研究方案 ===
{plan_text}

=== 专家评审意见（批判）===
{critique_text}

=== 用户额外反馈 ===
{user_feedback or '无'}
{student_context}
{evidence_section}

请完成：

1. **修订方案**：针对批判意见中的每个硬伤和建议，对方案进行实质性修改（不是简单加几句话，而是重新设计有问题的地方）

2. **分层输出**：根据学生的培养阶段，输出不同复杂度的版本：
   - **基础版**（适合研一/初学者）：简化技术路线，缩小样本量要求，降低方法复杂度，重点保证能完成
   - **进阶版**（适合研二/有一定基础）：保持适度复杂度，增加方法学严谨性
   - **完整版**（适合研三/博士生）：追求高质量，增加外部验证、多中心等设计

3. **修订说明**：逐条说明针对哪些批判意见做了什么修改

返回JSON格式：
{{
  "revised_plan": {{
    "title": "修订后的题目",
    "background": "修订后的背景",
    "clinical_problem": "修订后的临床问题",
    "scientific_problem": "修订后的科学问题",
    "hypothesis": "修订后的假设",
    "objectives": "修订后的目标",
    "study_design": "修订后的设计",
    "subjects_criteria": "修订后的纳排标准",
    "variables_endpoints": "修订后的终点",
    "statistical_analysis": "修订后的统计方法",
    "innovation": "修订后的创新点",
    "risks_alternatives": "修订后的风险方案",
    "timeline": "修订后的时间表"
  }},
  "tiered_versions": {{
    "basic": {{
      "title": "基础版题目",
      "study_design": "基础版设计（简化版）",
      "sample_size": "基础版样本量建议",
      "timeline": "基础版时间表",
      "key_simplifications": ["简化点1", "简化点2"]
    }},
    "intermediate": {{
      "title": "进阶版题目",
      "study_design": "进阶版设计",
      "sample_size": "进阶版样本量建议",
      "timeline": "进阶版时间表",
      "key_enhancements": ["增强点1", "增强点2"]
    }},
    "advanced": {{
      "title": "完整版题目",
      "study_design": "完整版设计",
      "sample_size": "完整版样本量建议",
      "timeline": "完整版时间表",
      "key_enhancements": ["增强点1", "增强点2", "增强点3"]
    }}
  }},
  "revision_summary": {{
    "revision_overview": "修订概述",
    "changes_made": ["修改1：针对XX问题，做了XX修改", "修改2：..."],
    "issues_resolved": ["解决了XX问题", "解决了YY问题"],
    "remaining_issues": ["仍存在的问题1"]
  }},
  "next_steps": ["步骤1", "步骤2", "步骤3"]
}}

要求：
- 修订必须针对批判意见，不能只是表面修改
- 分层版本要有实质性差异，不能只是改个标题
- 基础版必须确保研一学生在1-2年内能完成
- 只返回JSON，不要额外文字
"""

            # 对话式精简模式用更小的 max_tokens，完整修订用 3000
            is_chat = is_chat_optimization
            max_tokens = 1500 if is_chat else 3000
            revise_sp = "你是一名放射学科研导师。请根据用户需求修订研究方案，只返回JSON格式，不要额外文字。"
            response = anthropic_client.call_longcat_api(prompt, max_tokens=max_tokens, system_prompt=revise_sp)
            try:
                result = _safe_json_parse(response, context="RevisionAgent._ai_revise_plan")
                return result
            except ValueError:
                logger.warning("AI修订JSON解析失败")
                return {'error': 'JSON解析失败'}

        except Exception as e:
            logger.warning(f"AI修订失败: {str(e)}")
            return {'error': str(e)}

    def analyze_revision_needs(self, critique: Dict, user_feedback: str) -> Dict:
        """分析修订需求"""
        revision_needs = {
            'critical': [],  # 必须修改的问题
            'important': [],  # 重要修改建议
            'optional': []   # 可选优化建议
        }

        # 基于批判性评估分析
        overall_assessment = critique.get('overall_assessment', {})
        score = overall_assessment.get('score', 100)

        if score < 60:
            revision_needs['critical'].append('整体质量需要大幅提升')

        # 分析方法学问题
        methodology_eval = critique.get('methodology_evaluation', {})
        for aspect, assessment in methodology_eval.items():
            if '需要' in assessment or '不足' in assessment or '改进' in assessment:
                revision_needs['important'].append(f'方法学方面：{assessment}')

        # 分析可行性问题
        feasibility_analysis = critique.get('feasibility_analysis', {})
        for aspect, assessment in feasibility_analysis.items():
            if '风险' in assessment or '不足' in assessment:
                revision_needs['important'].append(f'可行性方面：{assessment}')

        # 分析创新性问题
        innovation_assessment = critique.get('innovation_assessment', {})
        for aspect, assessment in innovation_assessment.items():
            if '不足' in assessment or '加强' in assessment:
                revision_needs['important'].append(f'创新性方面：{assessment}')

        # 分析识别的风险
        risk_identification = critique.get('risk_identification', {})
        all_risks = []
        for risk_type, risk_list in risk_identification.items():
            if isinstance(risk_list, list):
                all_risks.extend(risk_list)

        # 高风险问题需要紧急处理
        high_risk_keywords = ['样本量', '伦理', '重大', '严重']
        for risk in all_risks:
            if any(keyword in risk for keyword in high_risk_keywords):
                revision_needs['critical'].append(f'风险管控：{risk}')
            else:
                revision_needs['important'].append(f'风险管控：{risk}')

        # 基于用户反馈分析
        if user_feedback:
            feedback_priority = self.analyze_user_feedback_priority(user_feedback)
            for priority, feedback_items in feedback_priority.items():
                if priority == 'high':
                    revision_needs['critical'].extend(feedback_items)
                elif priority == 'medium':
                    revision_needs['important'].extend(feedback_items)
                else:
                    revision_needs['optional'].extend(feedback_items)

        return revision_needs

    def analyze_user_feedback_priority(self, user_feedback: str) -> Dict:
        """分析用户反馈优先级"""
        feedback_priority = {'high': [], 'medium': [], 'low': []}

        # 关键词分析
        high_priority_keywords = ['必须', '紧急', '重要', '关键', '务必']
        medium_priority_keywords = ['建议', '希望', '最好', '考虑']

        # 简单分析反馈内容
        if any(keyword in user_feedback for keyword in high_priority_keywords):
            feedback_priority['high'].append(user_feedback)
        elif any(keyword in user_feedback for keyword in medium_priority_keywords):
            feedback_priority['medium'].append(user_feedback)
        else:
            feedback_priority['low'].append(user_feedback)

        return feedback_priority

    def perform_revisions(self, original_plan: Dict, revision_needs: Dict, critique: Dict) -> Dict:
        """执行具体修订"""
        revised_plan = original_plan.copy()

        # 处理关键修订需求
        critical_revisions = revision_needs.get('critical', [])
        for revision in critical_revisions:
            revised_plan = self.apply_critical_revision(revised_plan, revision, critique)

        # 处理重要修订需求
        important_revisions = revision_needs.get('important', [])
        for revision in important_revisions:
            revised_plan = self.apply_important_revision(revised_plan, revision, critique)

        # 处理可选优化建议
        optional_revisions = revision_needs.get('optional', [])
        for revision in optional_revisions:
            revised_plan = self.apply_optional_revision(revised_plan, revision, critique)

        # 确保所有字段都存在且有效
        revised_plan = self.ensure_plan_completeness(revised_plan)

        return revised_plan

    def apply_critical_revision(self, plan: Dict, revision: str, critique: Dict) -> Dict:
        """应用关键修订"""
        if '样本量' in revision:
            plan = self.revise_sample_size(plan, critique)
        elif '伦理' in revision:
            plan = self.revise_ethical_considerations(plan)
        elif '整体质量' in revision:
            plan = self.enhance_overall_quality(plan, critique)
        elif '风险管控' in revision:
            plan = self.enhance_risk_management(plan, revision)

        return plan

    def apply_important_revision(self, plan: Dict, revision: str, critique: Dict) -> Dict:
        """应用重要修订"""
        if '方法学' in revision:
            plan = self.improve_methodology(plan, revision)
        elif '可行性' in revision:
            plan = self.improve_feasibility(plan, revision)
        elif '创新性' in revision:
            plan = self.enhance_innovation(plan, revision)
        elif '统计' in revision:
            plan = self.improve_statistical_analysis(plan)

        return plan

    def apply_optional_revision(self, plan: Dict, revision: str, critique: Dict) -> Dict:
        """应用可选优化"""
        # 可选优化通常是对现有内容的微调
        if '语言' in revision or '表达' in revision:
            plan = self.improve_language_expression(plan)
        elif '结构' in revision or '组织' in revision:
            plan = self.improve_structure(plan)

        return plan

    def revise_sample_size(self, plan: Dict, critique: Dict) -> Dict:
        """修订样本量"""
        study_design = plan.get('study_design', '')

        # 添加样本量计算依据
        sample_size_addition = "\n样本量计算：基于预试验结果和文献回顾，预计需要至少100例患者以达到80%的统计效力（α=0.05）。"

        if study_design:
            plan['study_design'] = study_design + sample_size_addition
        else:
            plan['study_design'] = "本研究采用回顾性队列设计。" + sample_size_addition

        return plan

    def revise_ethical_considerations(self, plan: Dict) -> Dict:
        """修订伦理考虑"""
        study_design = plan.get('study_design', '')

        ethical_addition = "\n伦理考虑：本研究将严格遵守医学研究伦理原则，通过医院伦理委员会审批，所有患者均签署知情同意书。"

        if study_design:
            plan['study_design'] = study_design + ethical_addition
        else:
            plan['study_design'] = ethical_addition

        return plan

    def enhance_overall_quality(self, plan: Dict, critique: Dict) -> Dict:
        """提升整体质量"""
        # 基于批判性评估的具体建议进行改进
        improvement_suggestions = critique.get('improvement_suggestions', [])

        for suggestion in improvement_suggestions:
            if '统计' in suggestion:
                plan = self.improve_statistical_analysis(plan)
            elif '时间' in suggestion:
                plan = self.improve_timeline(plan)
            elif '创新' in suggestion:
                plan = self.enhance_innovation(plan, suggestion)

        return plan

    def enhance_risk_management(self, plan: Dict, risk_revision: str) -> Dict:
        """增强风险管理"""
        risks_alternatives = plan.get('risks_alternatives', '')

        if '风险管控' in risk_revision:
            risk_addition = "\n风险应对策略："
            if '样本量' in risk_revision:
                risk_addition += "针对样本量不足风险，将扩大病例收集范围，必要时进行多中心合作；"
            if '伦理' in risk_revision:
                risk_addition += "针对伦理风险，将严格遵循伦理规范，确保患者权益；"

            if risks_alternatives:
                plan['risks_alternatives'] = risks_alternatives + risk_addition
            else:
                plan['risks_alternatives'] = risk_addition

        return plan

    def improve_methodology(self, plan: Dict, methodology_revision: str) -> Dict:
        """改进方法学"""
        if '研究设计' in methodology_revision:
            plan['study_design'] = self.enhance_study_design_description(plan.get('study_design', ''))
        elif '统计方法' in methodology_revision:
            plan = self.improve_statistical_analysis(plan)
        elif '偏倚控制' in methodology_revision:
            plan['study_design'] = self.add_bias_control_measures(plan.get('study_design', ''))

        return plan

    def enhance_study_design_description(self, current_design: str) -> str:
        """增强研究设计描述"""
        if not current_design:
            return "本研究采用回顾性队列研究设计，收集医院放射科相关影像数据。"

        # 添加更详细的设计描述
        enhancement = "\n详细设计：采用连续入组的方式收集病例，确保样本的代表性。数据收集将遵循标准化流程，确保数据质量。"

        return current_design + enhancement

    def add_bias_control_measures(self, current_design: str) -> str:
        """添加偏倚控制措施"""
        bias_control = "\n偏倚控制：采用盲法评估影像结果，由两名经验丰富的放射科医生独立阅片，必要时由第三名医生仲裁。"

        return current_design + bias_control

    def improve_feasibility(self, plan: Dict, feasibility_revision: str) -> Dict:
        """改进可行性"""
        if '资源' in feasibility_revision:
            plan = self.enhance_resource_planning(plan)
        elif '时间' in feasibility_revision:
            plan = self.improve_timeline(plan)
        elif '技术' in feasibility_revision:
            plan = self.enhance_technical_feasibility(plan)

        return plan

    def enhance_resource_planning(self, plan: Dict) -> Dict:
        """增强资源规划"""
        study_design = plan.get('study_design', '')

        resource_addition = "\n资源规划：研究将在医院放射科和计算机中心的支持下进行，利用现有的PACS系统和计算资源。"

        if study_design:
            plan['study_design'] = study_design + resource_addition

        return plan

    def improve_timeline(self, plan: Dict) -> Dict:
        """改进时间安排 — 仅做格式校验，不注入任何默认内容"""
        timeline = plan.get('timeline', '')

        if not timeline or len(timeline) < 10:
            # timeline 为空时保持为空，让主流程的 LLM 重新生成
            plan['timeline'] = ""

        return plan

    def enhance_technical_feasibility(self, plan: Dict) -> Dict:
        """增强技术可行性 — 仅做格式校验，不注入任何默认内容"""
        return plan

    def enhance_innovation(self, plan: Dict, innovation_revision: str) -> Dict:
        """增强创新性 — 仅做格式校验，不注入任何默认内容"""
        return plan

    def improve_statistical_analysis(self, plan: Dict) -> Dict:
        """改进统计分析方法 — 仅做格式校验，不注入任何默认内容"""
        return plan

    def improve_language_expression(self, plan: Dict) -> Dict:
        """改进语言表达 — 仅去除多余空格和空行，不注入模板内容"""
        for key, value in plan.items():
            if isinstance(value, str):
                plan[key] = value.replace('  ', ' ').strip()
        return plan

    def improve_structure(self, plan: Dict) -> Dict:
        """改进结构组织"""
        # 确保逻辑顺序合理
        preferred_order = [
            'title', 'background', 'clinical_problem', 'scientific_problem',
            'hypothesis', 'objectives', 'study_design', 'subjects_criteria',
            'variables_endpoints', 'statistical_analysis', 'innovation',
            'risks_alternatives', 'timeline'
        ]

        # 重新组织plan结构
        reordered_plan = {}
        for key in preferred_order:
            if key in plan:
                reordered_plan[key] = plan[key]

        # 添加其他字段
        for key, value in plan.items():
            if key not in reordered_plan:
                reordered_plan[key] = value

        return reordered_plan

    def ensure_plan_completeness(self, plan: Dict) -> Dict:
        """确保方案完整性"""
        required_fields = [
            'title', 'background', 'clinical_problem', 'scientific_problem',
            'hypothesis', 'objectives', 'study_design', 'subjects_criteria',
            'variables_endpoints', 'statistical_analysis', 'innovation',
            'risks_alternatives', 'timeline'
        ]

        for field in required_fields:
            if field not in plan or not plan[field]:
                plan[field] = f"待补充: {field}"

        return plan

    def generate_revision_summary(self, original_plan: Dict, revised_plan: Dict, revision_needs: Dict) -> Dict:
        """生成修订说明"""
        summary = {
            'revision_overview': self.generate_overview(revision_needs),
            'key_changes': self.identify_key_changes(original_plan, revised_plan),
            'improvement_impact': self.assess_improvement_impact(original_plan, revised_plan),
            'remaining_issues': self.identify_remaining_issues(revised_plan, revision_needs)
        }

        return summary

    def generate_overview(self, revision_needs: Dict) -> str:
        """生成修订概述"""
        critical_count = len(revision_needs.get('critical', []))
        important_count = len(revision_needs.get('important', []))
        optional_count = len(revision_needs.get('optional', []))

        overview = f"本次修订共处理了{critical_count}个关键问题，{important_count}个重要问题，以及{optional_count}个可选优化建议。"

        if critical_count > 0:
            overview += "重点解决了方案中的关键缺陷，显著提升了研究质量。"
        elif important_count > 0:
            overview += "主要改进了方案的重要方面，增强了研究的可行性。"
        else:
            overview += "进行了常规优化，进一步完善了研究方案。"

        return overview

    def identify_key_changes(self, original_plan: Dict, revised_plan: Dict) -> List[str]:
        """识别关键变更"""
        key_changes = []

        for key in original_plan:
            if key in revised_plan:
                original_value = str(original_plan[key])
                revised_value = str(revised_plan[key])

                # 检查内容变化程度
                if len(original_value) != len(revised_value):
                    change_significance = abs(len(revised_value) - len(original_value)) / max(len(original_value), 1)

                    if change_significance > 0.3:  # 变化超过30%
                        key_changes.append(f"{key}: 内容进行了实质性修改")
                    elif change_significance > 0.1:  # 变化超过10%
                        key_changes.append(f"{key}: 内容进行了适度调整")

        return key_changes

    def assess_improvement_impact(self, original_plan: Dict, revised_plan: Dict) -> Dict:
        """评估改进影响"""
        impact_assessment = {
            'quality_improvement': self.assess_quality_improvement(original_plan, revised_plan),
            'feasibility_enhancement': self.assess_feasibility_enhancement(original_plan, revised_plan),
            'innovation_boost': self.assess_innovation_boost(original_plan, revised_plan)
        }

        return impact_assessment

    def assess_quality_improvement(self, original_plan: Dict, revised_plan: Dict) -> str:
        """评估质量改进"""
        # 简单评估内容完整性改进
        original_completeness = sum(1 for v in original_plan.values() if v and len(str(v)) > 10)
        revised_completeness = sum(1 for v in revised_plan.values() if v and len(str(v)) > 10)

        improvement_ratio = (revised_completeness - original_completeness) / max(original_completeness, 1)

        if improvement_ratio > 0.2:
            return "质量显著提升，内容完整性大幅改善"
        elif improvement_ratio > 0.1:
            return "质量有所提升，关键内容得到完善"
        else:
            return "质量基本保持，进行了细节优化"

    def assess_feasibility_enhancement(self, original_plan: Dict, revised_plan: Dict) -> str:
        """评估可行性增强"""
        # 检查可行性相关字段的改进
        feasibility_fields = ['study_design', 'timeline', 'risks_alternatives']

        improvements = 0
        for field in feasibility_fields:
            if field in original_plan and field in revised_plan:
                if len(str(revised_plan[field])) > len(str(original_plan[field])):
                    improvements += 1

        if improvements >= 2:
            return "可行性显著增强，研究实施路径更加清晰"
        elif improvements == 1:
            return "可行性有所增强，关键实施环节得到优化"
        else:
            return "可行性基本保持，维持了原有的实施框架"

    def assess_innovation_boost(self, original_plan: Dict, revised_plan: Dict) -> str:
        """评估创新性提升"""
        original_innovation = str(original_plan.get('innovation', ''))
        revised_innovation = str(revised_plan.get('innovation', ''))

        if len(revised_innovation) > len(original_innovation) * 1.2:
            return "创新性显著提升，研究价值得到增强"
        elif len(revised_innovation) > len(original_innovation):
            return "创新性有所提升，突出了研究的独特价值"
        else:
            return "创新性基本保持，维持了原有的创新点"

    def identify_remaining_issues(self, revised_plan: Dict, revision_needs: Dict) -> List[str]:
        """识别剩余问题"""
        remaining_issues = []

        # 检查是否还有未处理的关键问题
        critical_issues = revision_needs.get('critical', [])
        if critical_issues:
            remaining_issues.append(f"仍有{len(critical_issues)}个关键问题需要进一步关注")

        # 检查方案完整性
        required_fields = ['title', 'background', 'objectives', 'study_design']
        missing_fields = [field for field in required_fields if not revised_plan.get(field)]

        if missing_fields:
            remaining_issues.append(f"缺少关键字段：{', '.join(missing_fields)}")

        # 检查内容质量
        short_fields = [field for field, content in revised_plan.items()
                       if isinstance(content, str) and len(content) < 20]

        if short_fields:
            remaining_issues.append(f"以下字段内容较为简略，建议进一步丰富：{', '.join(short_fields)}")

        return remaining_issues

    def suggest_next_steps(self, revised_plan: Dict) -> List[str]:
        """建议后续步骤"""
        next_steps = []

        # 基于方案状态建议
        if not revised_plan.get('title') or len(revised_plan['title']) < 10:
            next_steps.append("完善研究题目，确保准确反映研究内容")

        if not revised_plan.get('background') or len(revised_plan['background']) < 100:
            next_steps.append("详细撰写研究背景，充分论证研究必要性")

        # 通用建议
        next_steps.extend([
            "与导师讨论修订后的方案，获取专业指导",
            "准备伦理申请材料（如适用）",
            "制定详细的数据收集计划",
            "确定具体的统计分析方法",
            "准备研究经费预算（如需要）"
        ])

        return next_steps

# 多智能体协调器
class MultiAgentCoordinator:
    """多智能体协调器 - 负责智能体间的协作

    流程：
      0. InputParsingAgent   — LLM语义解析用户输入
      1. StudentProfileAgent  — LLM解析用户输入，构建学生画像
      2. ProblemDefinitionAgent — LLM定义临床/科学问题
      3. EvidenceRetrievalAgent — LLM驱动PubMed检索策略，获取真实文献
      4. PlanGenerationAgent   — 结合文献证据，LLM生成研究方案
    """

    def __init__(self):
        self.agents = {
            'input_parsing': InputParsingAgent(),
            'student_profile': StudentProfileAgent(),
            'problem_definition': ProblemDefinitionAgent(),
            'evidence_retrieval': EvidenceRetrievalAgent(),
            'plan_generation': PlanGenerationAgent(),
            'critique': CritiqueAgent(),
            'revision': RevisionAgent()
        }
        self.message_history = []

    def coordinate_research_plan_generation(
        self,
        student_input: str,
        student_profile_data: Dict = None,
        api_key: str = None,
        provider: str = None,
    ) -> Dict:
        """协调整个研究方案生成流程

        Args:
            student_input: 用户原始输入（纯文本字符串）
            student_profile_data: 数据库中的学生画像
            api_key: 用户自己的 API Key（可选，不提供则用默认值）
            provider: 用户选择的提供商（可选，不提供则用默认值）
        """
        # 配置 LLM 客户端（用户级）
        try:
            anthropic_client.configure(api_key=api_key, provider=provider)
        except Exception as e:
            logger.warning(f"配置 LLM 客户端失败，使用默认配置: {e}")

        try:
            logger.info("=" * 60)
            logger.info("开始多智能体协同研究方案生成流程")
            logger.info("=" * 60)

            # 【新】重置全局证据池，确保每次研究方案生成都从干净状态开始
            evidence_pool.reset()
            logger.info("  全局证据池已重置")

            # ── 步骤0: LLM输入解析（替代硬编码InputAdapter） ──
            logger.info("[Step 0] 输入解析 — LLM语义理解用户输入")
            if not isinstance(student_input, str):
                student_input = str(student_input)

            input_parse_message = self.agents['input_parsing'].send_message(
                'student_profile', student_input, 'raw_student_input'
            )
            input_parsing_result = self.agents['input_parsing'].receive_message(input_parse_message)
            logger.info(f"  解析完成: 疾病域={input_parsing_result.get('disease_domain', '未知')}, "
                       f"模态={input_parsing_result.get('imaging_modality', '未知')}, "
                       f"完整度={input_parsing_result.get('input_completeness', '未知')}")

            # 使用增强后的描述（如果LLM生成了更好的描述）
            enhanced_input = input_parsing_result.get('enhanced_description', student_input)
            if enhanced_input and enhanced_input != student_input:
                logger.info(f"  使用增强描述: {enhanced_input[:80]}...")
                student_input = enhanced_input

            # ── 步骤1: 学生画像分析 ──
            logger.info("[Step 1] 学生画像分析 — LLM解析用户输入")
            if student_profile_data and isinstance(student_profile_data, dict):
                # 将数据库画像和原始输入合并，传给画像Agent
                profile_input = dict(student_profile_data)
                profile_input['raw_input'] = student_input
                profile_message = self.agents['student_profile'].send_message(
                    'problem_definition', profile_input, 'student_input'
                )
            else:
                # 没有数据库画像，仅从原始输入解析
                profile_message = self.agents['student_profile'].send_message(
                    'problem_definition', student_input, 'student_input'
                )

            student_profile = self.agents['student_profile'].receive_message(profile_message)
            if 'error' in student_profile:
                return {'error': f'学生画像分析失败: {student_profile["error"]}'}
            logger.info(f"  学生画像完成: {student_profile.get('extracted_info', {}).get('specialty', '未知')}")

            # ── 步骤2: 问题定义 ──
            logger.info("[Step 2] 问题定义 — LLM定义临床/科学问题")
            problem_message = self.agents['problem_definition'].send_message(
                'evidence_retrieval', student_profile, 'student_profile'
            )
            problem_definition = self.agents['problem_definition'].receive_message(problem_message)
            if 'error' in problem_definition:
                return {'error': f'问题定义失败: {problem_definition["error"]}'}
            logger.info(f"  临床问题: {problem_definition.get('clinical_problem', '')[:60]}...")

            # ── 步骤3: 证据检索（LLM驱动） ──
            logger.info("[Step 3] 证据检索 — LLM驱动PubMed检索策略")
            evidence_input = {
                'problem_definition': problem_definition,
                'student_profile': student_profile
            }
            evidence_message = self.agents['evidence_retrieval'].send_message(
                'plan_generation', evidence_input, 'problem_definition'
            )
            evidence = self.agents['evidence_retrieval'].receive_message(evidence_message)
            if 'error' in evidence:
                logger.warning(f'  证据检索遇到问题: {evidence["error"]}，继续生成方案')
                evidence = {
                    'keywords': [],
                    'literature_results': {'recommended_papers': [], 'total_results': 0},
                    'research_gaps': {},
                    'evidence_summary': {},
                }
            paper_count = evidence.get('literature_results', {}).get('total_results', 0)
            logger.info(f"  检索到 {paper_count} 篇文献")

            # ── 步骤4: 方案生成（结合文献） ──
            logger.info("[Step 4] 方案生成 — 结合文献证据生成研究方案")
            input_data = {
                'student_profile': student_profile,
                'problem_definition': problem_definition,
                'evidence': evidence,
                'input_parsing': input_parsing_result,
            }
            plan_message = self.agents['plan_generation'].send_message(
                'critique', input_data, 'evidence_and_requirements'
            )
            research_plan = self.agents['plan_generation'].receive_message(plan_message)
            if 'error' in research_plan:
                return {'error': f'方案生成失败: {research_plan["error"]}'}
            logger.info(f"  方案生成完成: {research_plan.get('title', '未知标题')[:60]}")

            # ── 步骤5: 批判评估 ──
            logger.info("[Step 5] 批判评估 — LLM对方案进行严格审查")
            critique_input = {
                'research_plan': research_plan,
                'student_profile': student_profile,
                'evidence': evidence,
            }
            critique_message = self.agents['critique'].send_message(
                'revision', critique_input, 'research_plan'
            )
            critique = self.agents['critique'].receive_message(critique_message)
            if 'error' in critique:
                logger.warning(f"  批判评估遇到问题: {critique['error']}，跳过修订")
                critique = {}
            logger.info(f"  批判评估完成: 总体评分={critique.get('overall_assessment', {}).get('score', 'N/A')}")

            # ── 步骤6: 修订优化 ──
            if critique:
                logger.info("[Step 6] 修订优化 — 根据批判意见修订方案")
                revision_input = {
                    'research_plan': research_plan,
                    'critique': critique,
                    'user_feedback': '',
                    'student_profile': student_profile,
                }
                revision_message = self.agents['revision'].send_message(
                    'plan_generation', revision_input, 'critique_and_plan'
                )
                revision_result = self.agents['revision'].receive_message(revision_message)
                if 'error' not in revision_result:
                    # 提取 revised_plan，保留 revision_summary 和 next_steps 供前端展示
                    revised_plan = revision_result.get('revised_plan', {})
                    if revised_plan and isinstance(revised_plan, dict):
                        research_plan = revised_plan
                        logger.info(f"  修订优化完成，字段: {list(revised_plan.keys())}")
                    else:
                        logger.warning("  修订结果中无 revised_plan，保留原方案")
                else:
                    logger.warning(f"  修订遇到问题: {revision_result['error']}，保留原方案")
            else:
                logger.info("[Step 6] 跳过修订（无批判结果）")

            # ── 结果构建 ──
            # 确保 final_plan 只包含标准 14 个字段（防止 revision 结果污染）
            standard_fields = [
                'title', 'background', 'clinical_problem', 'scientific_problem',
                'hypothesis', 'objectives', 'study_design', 'subjects_criteria',
                'variables_endpoints', 'statistical_analysis', 'innovation',
                'risks_alternatives', 'timeline', 'user_input'
            ]
            if isinstance(research_plan, dict):
                clean_plan = {}
                for f in standard_fields:
                    val = research_plan.get(f, '')
                    clean_plan[f] = val if val else f"待补充: {f}"
                research_plan = clean_plan
            else:
                research_plan = {f: f"待补充: {f}" for f in standard_fields}

            # ── 将用户原始输入注入 final_plan ──
            if not research_plan.get('user_input') or research_plan['user_input'].startswith('待补充'):
                research_plan['user_input'] = student_input
                logger.info(f"  [ResultBuilder] 用户原始输入已注入 final_plan")

            # ── 兜底：如果 clinical_problem 为空，从 problem_definition 中补全 ──
            if research_plan.get('clinical_problem', '').startswith('待补充'):
                pd_clinical = problem_definition.get('clinical_problem', '')
                if pd_clinical and not pd_clinical.startswith('待补充'):
                    research_plan['clinical_problem'] = pd_clinical
                    logger.info('  [ResultBuilder] clinical_problem 从 problem_definition 补全')
                else:
                    # 最后兜底：基于 specialty 生成一个基本临床问题
                    specialty = student_profile.get('extracted_info', {}).get('specialty', '')
                    raw_input = student_profile.get('raw_input', '')
                    if specialty:
                        research_plan['clinical_problem'] = f'{specialty}领域中，{raw_input[:50]}相关的临床需求尚未充分满足，亟需系统性的影像学研究来解决这一痛点'
                    logger.warning('  [ResultBuilder] clinical_problem 使用通用兜底文本')

            # 【新】收集证据池最终统计，供前端展示
            pool_final_stats = evidence_pool.get_evidence_summary()
            pool_conflicts = evidence_pool.detect_conflicts()
            pool_gaps = evidence_pool.discover_research_gaps()

            result = {
                'success': True,
                'final_plan': research_plan,
                'process_summary': {
                    'student_profile': student_profile,
                    'problem_definition': problem_definition,
                    'evidence_summary': evidence,
                    'critique': critique,
                },
                'evidence_pool': {
                    'stats': pool_final_stats,
                    'conflicts': pool_conflicts,
                    'research_gaps': pool_gaps,
                },
                'agent_collaboration_log': self.generate_collaboration_log(),
            }

            logger.info("多智能体协同研究方案生成完成")
            return result

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"多智能体协同流程失败: {str(e)}\n{tb}")
            return {'error': f'多智能体协同流程失败: {str(e)}'}

    def generate_collaboration_log(self) -> List[Dict]:
        """生成协作日志"""
        log = []
        for agent_name, agent in self.agents.items():
            agent_messages = [msg for msg in agent.message_history if isinstance(msg, AgentMessage)]
            if agent_messages:
                log.append({
                    'agent': agent_name,
                    'message_count': len(agent_messages),
                    'last_activity': agent_messages[-1].timestamp.isoformat() if agent_messages else None
                })
        return log

# 全局协调器实例
multi_agent_coordinator = MultiAgentCoordinator()