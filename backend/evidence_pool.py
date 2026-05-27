"""
全局动态证据池 - 检索驱动的多智能体协同核心

职责：
1. 存储所有检索到的文献（原始 + 结构化）
2. 证据等级评分（1-4级）
3. 订阅/推送机制（Agent 订阅主题，证据池主动推送）
4. 文献冲突检测
5. 研究空白自动发现
"""

import json
import logging
import math
import re
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Callable
from enum import IntEnum

logger = logging.getLogger(__name__)


# ── 证据等级定义 ──
class EvidenceLevel(IntEnum):
    """证据等级评分系统
    1级：指南、系统综述、Meta分析
    2级：随机对照试验、多中心前瞻性研究
    3级：单中心回顾性研究、病例对照研究
    4级：个案报道、专家意见、预印本
    """
    GUIDELINE_SYSTEMATIC_REVIEW = 1
    RCT_PROSPECTIVE = 2
    RETROSPECTIVE_CASE_CONTROL = 3
    CASE_REPORT_EXPERT_OPINION = 4

    @classmethod
    def from_paper(cls, article_type: str, journal: str = "", study_design: str = "") -> "EvidenceLevel":
        """根据文献类型自动判断证据等级"""
        text = f"{article_type} {journal} {study_design}".lower()

        # 1级：指南、系统综述、Meta分析
        level1_keywords = [
            'systematic review', 'meta-analysis', 'meta analysis', 'guideline',
            'practice guideline', 'consensus statement', 'cochrane',
            '系统综述', 'meta分析', '指南', '共识'
        ]
        if any(kw in text for kw in level1_keywords):
            return cls.GUIDELINE_SYSTEMATIC_REVIEW

        # 2级：随机对照试验、多中心前瞻性研究
        level2_keywords = [
            'randomized controlled', 'rct', 'randomised', 'multicenter',
            'multi-center', 'prospective', 'randomized',
            '随机对照', '前瞻性', '多中心'
        ]
        if any(kw in text for kw in level2_keywords):
            return cls.RCT_PROSPECTIVE

        # 3级：回顾性研究、病例对照研究
        level3_keywords = [
            'retrospective', 'case-control', 'cohort study',
            '回顾性', '病例对照', '队列研究'
        ]
        if any(kw in text for kw in level3_keywords):
            return cls.RETROSPECTIVE_CASE_CONTROL

        # 4级：默认
        return cls.CASE_REPORT_EXPERT_OPINION

    @property
    def label(self) -> str:
        labels = {
            1: "1级-指南/系统综述/Meta分析",
            2: "2级-随机对照/多中心前瞻",
            3: "3级-回顾性/病例对照",
            4: "4级-个案/专家意见/预印本"
        }
        return labels[self.value]

    @property
    def weight(self) -> float:
        """证据权重，用于加权评分"""
        weights = {1: 1.0, 2: 0.8, 3: 0.5, 4: 0.2}
        return weights[self.value]


# ── 单篇文献的结构化表示 ──
@dataclass
class EvidenceEntry:
    """证据池中的单篇文献条目"""
    paper_id: str                          # PMID 或 arXiv ID
    title: str
    authors: List[str]
    abstract: str
    journal: str
    pubdate: str
    article_type: str = ""
    doi: str = ""
    url: str = ""
    source: str = "pubmed"                 # pubmed / arxiv
    study_design: str = ""
    sample_size: int = 0
    modality: str = ""                     # CT/MRI/X线/超声等
    disease: str = ""
    task: str = ""                         # 检测/分割/分类/诊断/预测
    method: str = ""
    main_conclusion: str = ""
    limitations: str = ""
    key_quotes: List[str] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    evidence_level: int = 4
    relevance_score: float = 0.0           # 与当前研究问题的相关度
    categories: List[str] = field(default_factory=list)  # arXiv categories
    retrieved_at: str = field(default_factory=lambda: datetime.now().isoformat())
    retrieved_by: str = ""                 # 哪个 Agent 检索到的

    def to_structured_dict(self) -> Dict:
        """输出结构化字典（供 LLM 消费）"""
        return {
            "id": self.paper_id,
            "title": self.title,
            "journal": self.journal,
            "year": self.pubdate,
            "evidence_level": self.evidence_level,
            "evidence_label": EvidenceLevel(self.evidence_level).label,
            "study_design": self.study_design,
            "sample_size": self.sample_size,
            "modality": self.modality,
            "disease": self.disease,
            "task": self.task,
            "method": self.method,
            "main_conclusion": self.main_conclusion,
            "limitations": self.limitations,
            "key_quotes": self.key_quotes[:3],
            "relevance_score": self.relevance_score,
            "source": self.source,
        }

    def to_llm_text(self, index: int = 0) -> str:
        """输出供 LLM 阅读的文本格式"""
        level_label = EvidenceLevel(self.evidence_level).label
        parts = [
            f"[{index}] {self.title}",
            f"    期刊: {self.journal} ({self.pubdate}) | 证据等级: {level_label}",
        ]
        if self.study_design:
            parts.append(f"    研究设计: {self.study_design}")
        if self.sample_size:
            parts.append(f"    样本量: {self.sample_size}")
        if self.modality:
            parts.append(f"    影像模态: {self.modality}")
        if self.method:
            parts.append(f"    方法: {self.method}")
        if self.main_conclusion:
            parts.append(f"    主要结论: {self.main_conclusion}")
        if self.limitations:
            parts.append(f"    局限性: {self.limitations}")
        if self.key_quotes:
            parts.append(f"    关键引文: {'; '.join(self.key_quotes[:2])}")
        abstract_preview = (self.abstract or "")[:300]
        parts.append(f"    摘要: {abstract_preview}...")
        return "\n".join(parts)


# ── 订阅记录 ──
@dataclass
class Subscription:
    """Agent 对证据池的订阅"""
    agent_name: str
    topic: str                             # 订阅主题关键词
    callback: Optional[Callable] = None    # 推送回调
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ── 全局动态证据池 ──
class EvidencePool:
    """
    全局动态证据池 - 所有 Agent 共享的知识中枢

    核心能力：
    - 文献存储与去重
    - 结构化知识提取
    - 证据等级自动评分
    - 订阅/推送机制
    - 文献冲突检测
    - 研究空白自动发现
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式 - 全局只有一个证据池"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._pool: Dict[str, EvidenceEntry] = {}       # paper_id -> EvidenceEntry
        self._subscriptions: List[Subscription] = []
        self._search_history: List[Dict] = []
        self._conflict_reports: List[Dict] = []
        self._access_lock = threading.Lock()
        logger.info("[EvidencePool] 全局证据池初始化完成")

    def reset(self):
        """重置证据池（新任务开始时调用）"""
        with self._access_lock:
            self._pool.clear()
            self._subscriptions.clear()
            self._search_history.clear()
            self._conflict_reports.clear()
            logger.info("[EvidencePool] 证据池已重置")

    # ── 文献添加与去重 ──

    def add_paper(self, paper: Dict, retrieved_by: str = "") -> Optional[EvidenceEntry]:
        """
        添加一篇文献到证据池

        Args:
            paper: 原始文献字典（PubMed 或 arXiv 格式）
            retrieved_by: 检索此文献的 Agent 名称

        Returns:
            EvidenceEntry（如果是新文献），None（如果已存在）
        """
        paper_id = paper.get("pmid", "") or paper.get("arxiv_id", "") or paper.get("title", "")
        if not paper_id:
            return None

        with self._access_lock:
            if paper_id in self._pool:
                # 已存在，更新检索信息
                self._pool[paper_id].retrieved_by = retrieved_by
                return None

            # 结构化并评分
            entry = self._structure_paper(paper, retrieved_by)
            entry.evidence_level = EvidenceLevel.from_paper(
                entry.article_type, entry.journal, entry.study_design
            ).value
            self._pool[paper_id] = entry

        # 触发订阅推送
        self._notify_subscribers(entry)
        logger.info(f"[EvidencePool] 新文献入库: {entry.title[:50]}... | 等级: {entry.evidence_level} | 来源: {retrieved_by}")
        return entry

    def add_papers_batch(self, papers: List[Dict], retrieved_by: str = "") -> int:
        """批量添加文献，返回新增数量"""
        new_count = 0
        for paper in papers:
            if self.add_paper(paper, retrieved_by) is not None:
                new_count += 1
        logger.info(f"[EvidencePool] 批量入库: 新增 {new_count}/{len(papers)} 篇")
        return new_count

    def get_paper(self, paper_id: str) -> Optional[EvidenceEntry]:
        return self._pool.get(paper_id)

    def get_all_papers(self) -> List[EvidenceEntry]:
        return list(self._pool.values())

    @property
    def size(self) -> int:
        return len(self._pool)

    # ── 查询与过滤 ──

    def query(self, topic: str = None, level: int = None, modality: str = None,
              disease: str = None, task: str = None, min_relevance: float = 0.0,
              limit: int = 20) -> List[EvidenceEntry]:
        """
        按条件查询证据池

        Args:
            topic: 主题关键词（模糊匹配标题/摘要/关键词）
            level: 证据等级上限（如 level=2 表示只返回 1-2 级）
            modality: 影像模态
            disease: 疾病
            task: 研究任务类型
            min_relevance: 最低相关度
            limit: 最大返回数量
        """
        results = []
        topic_lower = topic.lower() if topic else None

        for entry in self._pool.values():
            # 证据等级过滤
            if level is not None and entry.evidence_level > level:
                continue

            # 影像模态过滤
            if modality and modality.lower() not in entry.modality.lower():
                continue

            # 疾病过滤
            if disease and disease.lower() not in entry.disease.lower():
                continue

            # 任务过滤
            if task and task.lower() not in entry.task.lower():
                continue

            # 相关度过滤
            if entry.relevance_score < min_relevance:
                continue

            # 主题关键词模糊匹配
            if topic_lower:
                searchable = f"{entry.title} {entry.abstract} {' '.join(entry.keywords)} {' '.join(entry.mesh_terms)}".lower()
                if topic_lower not in searchable:
                    continue

            results.append(entry)

        # 按证据等级优先、相关度次之排序
        results.sort(key=lambda e: (e.evidence_level, -e.relevance_score))
        return results[:limit]

    def get_high_quality_evidence(self, limit: int = 10) -> List[EvidenceEntry]:
        """获取高质量证据（1-2级）"""
        return self.query(level=2, limit=limit)

    def get_evidence_summary(self) -> Dict:
        """获取证据池统计摘要"""
        if not self._pool:
            return {"total": 0, "levels": {}, "modalities": {}, "diseases": {}}

        levels = {}
        modalities = {}
        diseases = {}
        for entry in self._pool.values():
            lvl = entry.evidence_level
            levels[lvl] = levels.get(lvl, 0) + 1
            if entry.modality:
                modalities[entry.modality] = modalities.get(entry.modality, 0) + 1
            if entry.disease:
                diseases[entry.disease] = diseases.get(entry.disease, 0) + 1

        return {
            "total": len(self._pool),
            "levels": levels,
            "modalities": modalities,
            "diseases": diseases,
            "high_quality_count": sum(1 for e in self._pool.values() if e.evidence_level <= 2),
        }

    # ── 订阅/推送机制 ──

    def subscribe(self, agent_name: str, topic: str, callback: Callable = None):
        """Agent 订阅某个主题的证据"""
        sub = Subscription(agent_name=agent_name, topic=topic, callback=callback)
        self._subscriptions.append(sub)
        logger.info(f"[EvidencePool] {agent_name} 订阅主题: {topic}")

    def _notify_subscribers(self, entry: EvidenceEntry):
        """当有新文献入库时，通知相关订阅者"""
        for sub in self._subscriptions:
            topic_lower = sub.topic.lower()
            searchable = f"{entry.title} {entry.abstract} {' '.join(entry.keywords)}".lower()
            if topic_lower in searchable:
                if sub.callback:
                    try:
                        sub.callback(entry)
                    except Exception as e:
                        logger.warning(f"[EvidencePool] 推送通知失败 ({sub.agent_name}): {e}")

    # ── 文献冲突检测 ──

    def detect_conflicts(self, topic: str = None) -> List[Dict]:
        """
        检测证据池中的文献冲突

        策略：对同一主题的主要结论进行语义相似度比较，
        识别相互矛盾的结论。
        """
        papers = self.query(topic=topic, limit=50) if topic else list(self._pool.values())
        conflicts = []

        for i in range(len(papers)):
            for j in range(i + 1, len(papers)):
                p1, p2 = papers[i], papers[j]
                # 只比较同主题文献
                if not self._same_topic(p1, p2):
                    continue
                # 检测结论是否矛盾
                conflict = self._check_conclusion_conflict(p1, p2)
                if conflict:
                    conflicts.append(conflict)

        self._conflict_reports.extend(conflicts)
        if conflicts:
            logger.warning(f"[EvidencePool] 检测到 {len(conflicts)} 组文献冲突")
        return conflicts

    def _same_topic(self, p1: EvidenceEntry, p2: EvidenceEntry) -> bool:
        """判断两篇文献是否讨论同一主题"""
        # 疾病 + 任务 + 模态 三者有两个相同即认为同主题
        matches = sum([
            bool(p1.disease and p2.disease and p1.disease == p2.disease),
            bool(p1.task and p2.task and p1.task == p2.task),
            bool(p1.modality and p2.modality and p1.modality == p2.modality),
        ])
        return matches >= 2

    def _check_conclusion_conflict(self, p1: EvidenceEntry, p2: EvidenceEntry) -> Optional[Dict]:
        """检查两篇文献的结论是否矛盾（基于关键词启发式）"""
        if not p1.main_conclusion or not p2.main_conclusion:
            return None

        # 简单的矛盾检测：结论中是否包含相反的判断词
        positive_indicators = ['优于', '更好', '显著提高', 'superior', 'better', 'improve', 'outperform']
        negative_indicators = ['劣于', '不如', '无显著差异', 'inferior', 'worse', 'no significant', 'equivalent']

        p1_text = p1.main_conclusion.lower()
        p2_text = p2.main_conclusion.lower()

        p1_positive = any(w in p1_text for w in positive_indicators)
        p1_negative = any(w in p1_text for w in negative_indicators)
        p2_positive = any(w in p2_text for w in positive_indicators)
        p2_negative = any(w in p2_text for w in negative_indicators)

        # 一个正面一个负面 → 矛盾
        if (p1_positive and p2_negative) or (p1_negative and p2_positive):
            return {
                "type": "conclusion_conflict",
                "paper_1": {"id": p1.paper_id, "title": p1.title, "conclusion": p1.main_conclusion},
                "paper_2": {"id": p2.paper_id, "title": p2.title, "conclusion": p2.main_conclusion},
                "detected_at": datetime.now().isoformat(),
            }
        return None

    # ── 研究空白自动发现 ──

    def discover_research_gaps(self) -> Dict[str, List[str]]:
        """
        分析证据池，自动发现研究空白

        策略：
        1. 方法学空白：A领域的方法从未被应用到B领域
        2. 数据空白：某疾病的某影像模态研究不足
        3. 矛盾空白：不同文献结论存在冲突
        """
        gaps = {
            "methodological_gaps": [],
            "data_gaps": [],
            "conflict_gaps": [],
        }

        papers = list(self._pool.values())
        if len(papers) < 3:
            return gaps

        # ── 1. 方法学空白检测 ──
        # 统计各疾病-模态组合使用的方法
        disease_modality_methods: Dict[str, Set[str]] = {}
        for p in papers:
            if p.disease and p.modality and p.method:
                key = f"{p.disease}_{p.modality}"
                disease_modality_methods.setdefault(key, set()).add(p.method)

        # 统计各方法被用于哪些疾病-模态
        method_applications: Dict[str, Set[str]] = {}
        for key, methods in disease_modality_methods.items():
            for method in methods:
                method_applications.setdefault(method, set()).add(key)

        # 如果某方法被广泛用于 A 疾病但未用于 B 疾病（两者使用相同模态），则为空白
        all_keys = list(disease_modality_methods.keys())
        common_modalities = set()
        for key in all_keys:
            parts = key.split("_", 1)
            if len(parts) == 2:
                common_modalities.add(parts[1])

        for method, applications in method_applications.items():
            if len(applications) < 2:
                continue
            for key in all_keys:
                if key not in applications:
                    parts = key.split("_", 1)
                    if len(parts) == 2:
                        disease, modality = parts
                        # 检查该方法是否在该模态的其他疾病中使用过
                        same_mod_applications = [a for a in applications if modality in a]
                        if same_mod_applications:
                            gap_desc = f"{method} 已被用于 {modality} 的 {len(same_mod_applications)} 个疾病领域，但尚未应用于 {disease}"
                            if gap_desc not in gaps["methodological_gaps"]:
                                gaps["methodological_gaps"].append(gap_desc)

        # ── 2. 数据空白检测 ──
        # 统计各疾病-模态组合的文献数量
        disease_modality_counts: Dict[str, int] = {}
        for p in papers:
            if p.disease and p.modality:
                key = f"{p.disease}_{p.modality}"
                disease_modality_counts[key] = disease_modality_counts.get(key, 0) + 1

        avg_count = sum(disease_modality_counts.values()) / max(len(disease_modality_counts), 1)
        for key, count in disease_modality_counts.items():
            if count < avg_count * 0.3:  # 少于平均值的30%
                parts = key.split("_", 1)
                if len(parts) == 2:
                    gaps["data_gaps"].append(f"{parts[1]} 在 {parts[0]} 中的研究文献较少（仅 {count} 篇），存在数据空白")

        # ── 3. 矛盾空白 ──
        conflicts = self.detect_conflicts()
        for conflict in conflicts:
            gaps["conflict_gaps"].append(
                f"文献冲突: {conflict['paper_1']['title'][:40]}... vs {conflict['paper_2']['title'][:40]}..."
            )

        logger.info(f"[EvidencePool] 研究空白发现: 方法学={len(gaps['methodological_gaps'])}, "
                    f"数据={len(gaps['data_gaps'])}, 矛盾={len(gaps['conflict_gaps'])}")
        return gaps

    # ── 结构化辅助 ──

    def _structure_paper(self, raw: Dict, retrieved_by: str) -> EvidenceEntry:
        """将原始文献字典结构化为 EvidenceEntry"""
        # 提取样本量
        sample_size = 0
        abstract = raw.get("abstract", "") or ""
        sample_match = re.search(r'(\d+)\s*(?:例|个|份|张|病例|样本|患者|图像|patients|subjects|cases)', abstract + raw.get("title", ""))
        if sample_match:
            sample_size = int(sample_match.group(1))

        # 提取影像模态
        modality = ""
        text = f"{raw.get('title', '')} {abstract}".lower()
        for m in ['ct', 'mri', 'x-ray', 'x线', '超声', 'ultrasound', 'pet', '钼靶', 'mammography', 'dsa']:
            if m in text:
                modality = m.upper()
                break

        return EvidenceEntry(
            paper_id=raw.get("pmid", "") or raw.get("arxiv_id", "") or raw.get("title", ""),
            title=raw.get("title", ""),
            authors=raw.get("authors", [])[:5],
            abstract=abstract,
            journal=raw.get("journal", "") or raw.get("source", ""),
            pubdate=raw.get("pubdate", "") or raw.get("published", ""),
            article_type=raw.get("article_type", ""),
            doi=raw.get("doi", ""),
            url=raw.get("pubmed_url", "") or raw.get("arxiv_url", ""),
            source=raw.get("source", "pubmed"),
            study_design=raw.get("study_design", ""),
            sample_size=sample_size,
            modality=modality,
            disease=raw.get("disease", ""),
            task=raw.get("task", ""),
            method=raw.get("method", ""),
            main_conclusion=raw.get("main_conclusion", ""),
            limitations=raw.get("limitations", ""),
            key_quotes=raw.get("key_quotes", []),
            mesh_terms=raw.get("mesh_terms", []),
            keywords=raw.get("keywords", []),
            relevance_score=raw.get("relevance_score", 0),
            categories=raw.get("categories", []),
            retrieved_by=retrieved_by,
        )

    # ── LLM 消费接口 ──

    def to_llm_context(self, topic: str = None, max_papers: int = 8) -> str:
        """
        将证据池内容格式化为 LLM 可消费的上下文文本
        """
        papers = self.query(topic=topic, limit=max_papers) if topic else list(self._pool.values())[:max_papers]
        if not papers:
            return "（证据池中暂无相关文献）"

        summary = self.get_evidence_summary()
        lines = [
            f"## 证据池摘要（共 {summary['total']} 篇文献）",
            f"高质量证据（1-2级）: {summary.get('high_quality_count', 0)} 篇",
            "",
        ]

        for i, paper in enumerate(papers):
            lines.append(paper.to_llm_text(i + 1))
            lines.append("")

        return "\n".join(lines)

    def to_citation_list(self, topic: str = None, max_papers: int = 15) -> List[Dict]:
        """输出引用列表（供方案生成时插入参考文献标注）"""
        papers = self.query(topic=topic, limit=max_papers) if topic else list(self._pool.values())[:max_papers]
        return [
            {
                "id": i + 1,
                "pmid": p.paper_id,
                "title": p.title,
                "journal": p.journal,
                "year": p.pubdate,
                "evidence_level": p.evidence_level,
            }
            for i, p in enumerate(papers)
        ]


# 全局单例
evidence_pool = EvidencePool()
