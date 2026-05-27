"""
Agent 工具箱 - 所有 Agent 可自主调用的工具集合

每个 Tool 是一个可被 LLM 理解和调用的函数。
Agent 通过 ReAct 循环自主决定调用哪些工具、调用顺序、调用次数。
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from api_clients import anthropic_client
from evidence_pool import EvidencePool, EvidenceLevel, evidence_pool

logger = logging.getLogger(__name__)


# ── 工具调用结果 ──
@dataclass
class ToolResult:
    """工具调用结果"""
    tool_name: str
    success: bool
    data: Any = None
    error: str = ""
    observation: str = ""       # 给 Agent 的观察摘要
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_observation(self) -> str:
        """转换为 LLM 可读的观察文本"""
        if not self.success:
            return f"[工具: {self.tool_name}] 调用失败: {self.error}"
        return f"[工具: {self.tool_name}] {self.observation}"


# ── 工具基类 ──
@dataclass
class Tool:
    """
    工具定义

    name: 工具名称（LLM 用此名称调用）
    description: 工具描述（LLM 用此理解工具的用途和参数）
    func: 实际执行函数
    params_schema: 参数描述（给 LLM 看的）
    """
    name: str
    description: str
    func: Callable
    params_schema: Dict = field(default_factory=dict)

    def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        try:
            result = self.func(**kwargs)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(tool_name=self.name, success=True, data=result, observation=str(result)[:200])
        except Exception as e:
            logger.error(f"[Tool:{self.name}] 执行失败: {e}")
            return ToolResult(tool_name=self.name, success=False, error=str(e))

    def to_llm_description(self) -> str:
        """输出给 LLM 的工具描述"""
        params_desc = ", ".join(f"{k}({v})" for k, v in self.params_schema.items()) if self.params_schema else "无参数"
        return f"- {self.name}: {self.description} | 参数: {params_desc}"


# ══════════════════════════════════════════════════════════════
#  检索工具（所有 Agent 可调用）
# ══════════════════════════════════════════════════════════════

def tool_search_pubmed(query: str, max_results: int = 20, retrieved_by: str = "agent") -> ToolResult:
    """
    检索 PubMed 文献，自动入库证据池
    """
    from Bio import Entrez

    try:
        Entrez.email = "79047879@qq.com"
        Entrez.api_key = "1307550aa4966b0cbbc68a6b2d4cb1ff8009"

        # esearch
        handle = Entrez.esearch(db='pubmed', term=query, retmax=max_results, sort='relevance', retmode='xml')
        search_data = Entrez.read(handle)
        handle.close()
        idlist = search_data.get('IdList', [])

        if not idlist:
            return ToolResult(
                tool_name="search_pubmed", success=True, data=[],
                observation=f"PubMed 检索 '{query[:50]}' 无结果"
            )

        time.sleep(0.15)

        # efetch
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

                ptypes = article_data.get('PublicationTypeList', []) or []
                article_type = str(ptypes[0]) if ptypes else ''

                mesh_terms = []
                mesh_list = medline.get('MeshHeadingList', [])
                if mesh_list:
                    for mesh in mesh_list:
                        desc = mesh.get('DescriptorName', '')
                        if desc:
                            mesh_terms.append(str(desc))

                papers.append({
                    'pmid': pmid,
                    'title': title,
                    'authors': authors,
                    'abstract': abstract,
                    'journal': journal,
                    'pubdate': str(year),
                    'article_type': article_type,
                    'doi': doi,
                    'pubmed_url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    'mesh_terms': mesh_list,
                    'source': 'pubmed',
                })
            except Exception:
                continue

        # 批量入库证据池
        new_count = evidence_pool.add_papers_batch(papers, retrieved_by=retrieved_by)

        return ToolResult(
            tool_name="search_pubmed",
            success=True,
            data=papers,
            observation=f"PubMed 检索 '{query[:50]}...': 获取 {len(papers)} 篇，新增 {new_count} 篇入证据池（当前共 {evidence_pool.size} 篇）"
        )

    except Exception as e:
        return ToolResult(tool_name="search_pubmed", success=False, error=str(e))


def tool_search_arxiv(query: str, max_results: int = 10, retrieved_by: str = "agent") -> ToolResult:
    """
    检索 arXiv 预印本，自动入库证据池
    """
    from api_clients import arxiv_client

    try:
        papers = arxiv_client.search(query, max_results=max_results)
        if not papers:
            return ToolResult(
                tool_name="search_arxiv", success=True, data=[],
                observation=f"arXiv 检索 '{query[:50]}' 无结果"
            )

        # 标记来源并入库
        for p in papers:
            p['source'] = 'arxiv'
        new_count = evidence_pool.add_papers_batch(papers, retrieved_by=retrieved_by)

        return ToolResult(
            tool_name="search_arxiv",
            success=True,
            data=papers,
            observation=f"arXiv 检索 '{query[:50]}...': 获取 {len(papers)} 篇，新增 {new_count} 篇入证据池"
        )

    except Exception as e:
        return ToolResult(tool_name="search_arxiv", success=False, error=str(e))


def tool_query_evidence_pool(topic: str = None, level: int = None, modality: str = None,
                              disease: str = None, task: str = None, limit: int = 10) -> ToolResult:
    """
    查询证据池中的已有文献
    """
    try:
        papers = evidence_pool.query(
            topic=topic, level=level, modality=modality,
            disease=disease, task=task, limit=limit
        )
        if not papers:
            return ToolResult(
                tool_name="query_evidence_pool", success=True, data=[],
                observation=f"证据池中未找到匹配文献 (topic={topic})"
            )

        summary = evidence_pool.get_evidence_summary()
        return ToolResult(
            tool_name="query_evidence_pool",
            success=True,
            data=[p.to_structured_dict() for p in papers],
            observation=f"证据池查询: 找到 {len(papers)} 篇匹配文献（总池: {summary['total']} 篇，高质量: {summary.get('high_quality_count', 0)} 篇）"
        )

    except Exception as e:
        return ToolResult(tool_name="query_evidence_pool", success=False, error=str(e))


def tool_get_evidence_summary() -> ToolResult:
    """
    获取证据池统计摘要
    """
    try:
        summary = evidence_pool.get_evidence_summary()
        gaps = evidence_pool.discover_research_gaps()
        observation = (
            f"证据池: 共 {summary['total']} 篇 | "
            f"高质量: {summary.get('high_quality_count', 0)} 篇 | "
            f"等级分布: {summary.get('levels', {})} | "
            f"发现研究空白: 方法学{len(gaps['methodological_gaps'])}个, 数据{len(gaps['data_gaps'])}个, 矛盾{len(gaps['conflict_gaps'])}个"
        )
        return ToolResult(
            tool_name="get_evidence_summary",
            success=True,
            data={"summary": summary, "gaps": gaps},
            observation=observation
        )

    except Exception as e:
        return ToolResult(tool_name="get_evidence_summary", success=False, error=str(e))


def tool_detect_conflicts(topic: str = None) -> ToolResult:
    """
    检测证据池中的文献冲突
    """
    try:
        conflicts = evidence_pool.detect_conflicts(topic=topic)
        if not conflicts:
            return ToolResult(
                tool_name="detect_conflicts", success=True, data=[],
                observation="未检测到文献冲突"
            )
        return ToolResult(
            tool_name="detect_conflicts",
            success=True,
            data=conflicts,
            observation=f"检测到 {len(conflicts)} 组文献冲突"
        )

    except Exception as e:
        return ToolResult(tool_name="detect_conflicts", success=False, error=str(e))


def tool_discover_gaps() -> ToolResult:
    """
    自动发现研究空白
    """
    try:
        gaps = evidence_pool.discover_research_gaps()
        total = sum(len(v) for v in gaps.values())
        if total == 0:
            return ToolResult(
                tool_name="discover_gaps", success=True, data=gaps,
                observation="当前证据池未发现明显研究空白（可能需要更多文献）"
            )
        gap_list = []
        for category, items in gaps.items():
            for item in items[:3]:
                gap_list.append(f"[{category}] {item}")
        return ToolResult(
            tool_name="discover_gaps",
            success=True,
            data=gaps,
            observation=f"发现 {total} 个研究空白: {'; '.join(gap_list[:5])}"
        )

    except Exception as e:
        return ToolResult(tool_name="discover_gaps", success=False, error=str(e))


def tool_get_evidence_for_llm(topic: str = None, max_papers: int = 8) -> ToolResult:
    """
    获取格式化的证据池上下文（直接注入 LLM prompt）
    """
    try:
        context = evidence_pool.to_llm_context(topic=topic, max_papers=max_papers)
        return ToolResult(
            tool_name="get_evidence_for_llm",
            success=True,
            data=context,
            observation=f"已格式化 {max_papers} 篇文献为 LLM 上下文"
        )

    except Exception as e:
        return ToolResult(tool_name="get_evidence_for_llm", success=False, error=str(e))


# ══════════════════════════════════════════════════════════════
#  方法学工具（供 CritiqueAgent / PlanGenerationAgent 使用）
# ══════════════════════════════════════════════════════════════

def tool_validate_sample_size(study_design: str, target_metric: str = "AUC", alpha: float = 0.05,
                               power: float = 0.8) -> ToolResult:
    """
    验证样本量合理性
    """
    try:
        import re as _re
        numbers = _re.findall(r'\d+', study_design)
        if not numbers:
            return ToolResult(
                tool_name="validate_sample_size", success=True,
                data={"has_sample_size": False},
                error="未在方案中找到样本量数字，请补充样本量计算依据"
            )

        sample_size = int(numbers[0])

        # 简单的样本量建议规则
        suggestions = {
            "诊断试验": 200,
            "预后研究": 300,
            "回顾性": 150,
            "前瞻性": 400,
            "多中心": 500,
        }

        required = 150  # 默认最低
        for key, val in suggestions.items():
            if key in study_design:
                required = val
                break

        adequate = sample_size >= required
        return ToolResult(
            tool_name="validate_sample_size",
            success=True,
            data={"sample_size": sample_size, "required": required, "adequate": adequate},
            observation=f"样本量 {sample_size}: {'充足' if adequate else '不足'}（建议最低 {required} 例）"
        )

    except Exception as e:
        return ToolResult(tool_name="validate_sample_size", success=False, error=str(e))


def tool_check_statistical_methods(study_design: str, statistical_analysis: str) -> ToolResult:
    """
    检查统计方法与研究设计是否匹配
    """
    try:
        issues = []
        design_lower = study_design.lower()
        stats_lower = statistical_analysis.lower()

        # 诊断试验应包含 ROC/AUC
        if any(kw in design_lower for kw in ['诊断', 'diagnostic', '筛查', 'screening']):
            if not any(kw in stats_lower for kw in ['roc', 'auc', 'sensitivity', 'specificity', '敏感', '特异']):
                issues.append("诊断试验应包含 ROC/AUC、敏感度/特异度分析")

        # 预后研究应包含生存分析
        if any(kw in design_lower for kw in ['预后', 'prognosis', '生存', 'survival']):
            if not any(kw in stats_lower for kw in ['survival', 'kaplan', 'cox', '生存']):
                issues.append("预后研究应包含生存分析（Kaplan-Meier 或 Cox 回归）")

        # 预测模型应包含区分度和校准度
        if any(kw in design_lower for kw in ['预测', 'prediction', '模型', 'model']):
            if not any(kw in stats_lower for kw in ['c-index', 'calibration', '区分', '校准']):
                issues.append("预测模型应评估区分度（C-index）和校准度")

        # 样本量计算
        if not any(kw in stats_lower for kw in ['sample size', 'power', '样本量', '检验效能']):
            issues.append("缺少样本量计算或检验效能说明")

        if not issues:
            observation = "统计方法与研究设计基本匹配"
        else:
            observation = f"发现问题: {'; '.join(issues)}"

        return ToolResult(
            tool_name="check_statistical_methods",
            success=True,
            data={"issues": issues, "match": len(issues) == 0},
            observation=observation
        )

    except Exception as e:
        return ToolResult(tool_name="check_statistical_methods", success=False, error=str(e))


# ══════════════════════════════════════════════════════════════
#  工具箱注册表 - 所有可用工具
# ══════════════════════════════════════════════════════════════

# 检索类工具（所有 Agent 共享）
RETRIEVAL_TOOLS = [
    Tool(
        name="search_pubmed",
        description="检索 PubMed 文献。自动入库证据池，所有 Agent 可共享。适用于获取临床研究证据。",
        func=tool_search_pubmed,
        params_schema={
            "query": "PubMed 检索式（必填）",
            "max_results": "最大返回数量（默认20）",
        }
    ),
    Tool(
        name="search_arxiv",
        description="检索 arXiv 预印本。自动入库证据池。适用于获取最新 AI/ML 方法论文。",
        func=tool_search_arxiv,
        params_schema={
            "query": "arXiv 检索关键词（英文，必填）",
            "max_results": "最大返回数量（默认10）",
        }
    ),
    Tool(
        name="query_evidence_pool",
        description="查询证据池中已有的文献。在不发起新检索的情况下获取相关知识。",
        func=tool_query_evidence_pool,
        params_schema={
            "topic": "主题关键词（可选）",
            "level": "证据等级上限（1-4，可选）",
            "modality": "影像模态（可选）",
            "disease": "疾病（可选）",
            "limit": "最大返回数量（默认10）",
        }
    ),
    Tool(
        name="get_evidence_summary",
        description="获取证据池统计摘要和研究空白。了解当前知识全貌。",
        func=tool_get_evidence_summary,
        params_schema={}
    ),
    Tool(
        name="detect_conflicts",
        description="检测证据池中的文献冲突。识别相互矛盾的研究结论。",
        func=tool_detect_conflicts,
        params_schema={
            "topic": "检测主题（可选，不填则检测全部）"
        }
    ),
    Tool(
        name="discover_gaps",
        description="自动发现研究空白。分析证据池，找出方法学空白、数据空白和矛盾空白。",
        func=tool_discover_gaps,
        params_schema={}
    ),
    Tool(
        name="get_evidence_for_llm",
        description="获取格式化的证据池上下文，直接注入 LLM prompt。",
        func=tool_get_evidence_for_llm,
        params_schema={
            "topic": "主题关键词（可选）",
            "max_papers": "最大文献数（默认8）"
        }
    ),
]

# 方法学工具（CritiqueAgent / PlanGenerationAgent 专用）
METHODOLOGY_TOOLS = [
    Tool(
        name="validate_sample_size",
        description="验证样本量合理性。根据研究设计类型给出最低样本量建议。",
        func=tool_validate_sample_size,
        params_schema={
            "study_design": "研究设计描述（必填）",
        }
    ),
    Tool(
        name="check_statistical_methods",
        description="检查统计方法与研究设计是否匹配。识别方法学缺陷。",
        func=tool_check_statistical_methods,
        params_schema={
            "study_design": "研究设计描述（必填）",
            "statistical_analysis": "统计分析描述（必填）",
        }
    ),
]

# 全量工具注册表
ALL_TOOLS: Dict[str, Tool] = {}
for t in RETRIEVAL_TOOLS + METHODOLOGY_TOOLS:
    ALL_TOOLS[t.name] = t


def get_tools_for_agent(agent_name: str) -> List[Tool]:
    """
    根据 Agent 名称返回其可用的工具列表

    - 所有 Agent 都有检索工具
    - 只有特定 Agent 有方法学验证工具
    """
    # 所有 Agent 都有检索工具
    tools = list(RETRIEVAL_TOOLS)

    # 方法学工具只给特定 Agent
    methodology_agents = {"CritiqueAgent", "PlanGenerationAgent", "RevisionAgent"}
    if agent_name in methodology_agents:
        tools.extend(METHODOLOGY_TOOLS)

    return tools


def format_tools_for_llm(tools: List[Tool]) -> str:
    """将工具列表格式化为 LLM 可读的描述"""
    lines = ["## 可用工具（你可以自主决定调用哪些工具、调用顺序和次数）"]
    for t in tools:
        lines.append(t.to_llm_description())
    lines.append("\n调用格式：输出 JSON: {\"tool\": \"工具名\", \"params\": {\"参数名\": \"参数值\"}}")
    lines.append("当你认为任务完成时，输出 JSON: {\"tool\": \"finish\", \"params\": {\"result\": \"你的最终输出\"}}")
    return "\n".join(lines)
