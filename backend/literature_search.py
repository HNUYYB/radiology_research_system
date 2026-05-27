"""
多源医学文献检索系统
整合多个API源，提供稳定可靠的文献检索服务
"""

import requests
import json
import time
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import sqlite3
import os

logger = logging.getLogger(__name__)

# 搜索策略配置
SEARCH_STRATEGIES = {
    'core_papers': {
        'name': '核心文献 (高影响力期刊)',
        'query_modifiers': 'AND ("Nature"[Journal] OR "Science"[Journal] OR "Cell"[Journal] OR "Lancet"[Journal] OR "NEJM"[Journal] OR "JAMA"[Journal] OR "BMJ"[Journal] OR "Nature Medicine"[Journal] OR "Nature Biotechnology"[Journal])',
        'sort': 'relevance',
        'max_results': 5,
        'description': '高影响力期刊的核心研究论文'
    },
    'recent_advances': {
        'name': '最新进展 (近2年)',
        'query_modifiers': 'AND ("2024/01/01"[Date - Publication] : "2026/12/31"[Date - Publication])',
        'sort': 'pub_date',
        'max_results': 8,
        'description': '最新的研究进展和突破'
    },
    'methodological_papers': {
        'name': '方法学文献',
        'query_modifiers': 'AND ("methods"[Title/Abstract] OR "methodology"[Title/Abstract] OR "technique"[Title/Abstract] OR "algorithm"[Title/Abstract] OR "protocol"[Title/Abstract] OR "framework"[Title/Abstract])',
        'sort': 'relevance',
        'max_results': 6,
        'description': '方法学和技术创新相关文献'
    },
    'clinical_applications': {
        'name': '临床应用文献',
        'query_modifiers': 'AND ("clinical"[Title/Abstract] OR "patient"[Title/Abstract] OR "diagnosis"[Title/Abstract] OR "treatment"[Title/Abstract] OR "clinical application"[Title/Abstract] OR "clinical practice"[Title/Abstract])',
        'sort': 'relevance',
        'max_results': 7,
        'description': '临床应用和实践相关文献'
    },
    'review_papers': {
        'name': '综述文献',
        'query_modifiers': 'AND ("review"[Publication Type] OR "review"[Title/Abstract] OR "systematic review"[Title/Abstract] OR "meta-analysis"[Title/Abstract] OR "literature review"[Title/Abstract])',
        'sort': 'relevance',
        'max_results': 4,
        'description': '系统性综述和meta分析'
    }
}

# 期刊影响因子数据库 (示例数据，实际应用中应从权威来源获取)
JOURNAL_IMPACT_FACTORS = {
    'Nature': 64.8,
    'Science': 56.9,
    'Cell': 66.9,
    'The Lancet': 168.9,
    'New England Journal of Medicine': 176.1,
    'JAMA': 120.7,
    'BMJ': 105.7,
    'Nature Medicine': 87.2,
    'Nature Biotechnology': 68.2,
    'Nature Reviews Disease Primers': 105.0,
    'Radiology': 29.2,
    'European Radiology': 7.4,
    'American Journal of Roentgenology': 4.8,
    'Investigative Radiology': 7.8,
    'Medical Image Analysis': 11.1,
    'IEEE Transactions on Medical Imaging': 11.4,
    'NeuroImage': 7.4,
    'Clinical Radiology': 2.9,
    'Academic Radiology': 3.9,
    'Journal of Computer Assisted Tomography': 1.8,
    'British Journal of Radiology': 2.7
}

# 放射学亚专业领域映射
RADIOLOGY_SPECIALTIES = {
    'chest_radiology': ['chest', 'thoracic', 'lung', 'pulmonary', 'cardiac', 'cardiovascular'],
    'neuro_radiology': ['brain', 'neurological', 'neuroimaging', 'stroke', 'cerebral', 'spine'],
    'musculoskeletal_radiology': ['musculoskeletal', 'bone', 'joint', 'orthopedic', 'rheumatology'],
    'abdominal_radiology': ['abdominal', 'gastrointestinal', 'liver', 'pancreas', 'kidney', 'renal'],
    'pediatric_radiology': ['pediatric', 'children', 'child', 'neonatal'],
    'interventional_radiology': ['interventional', 'catheter', 'embolization', 'ablation'],
    'breast_radiology': ['breast', 'mammography', 'mammogram'],
    'nuclear_radiology': ['nuclear', 'PET', 'SPECT', 'radionuclide'],
    'emergency_radiology': ['emergency', 'trauma', 'acute']
}

# 研究类型和证据等级映射
STUDY_TYPE_MAPPING = {
    'randomized_controlled_trial': {'evidence_level': 'I', 'keywords': ['randomized', 'RCT', 'randomised controlled']},
    'systematic_review': {'evidence_level': 'I', 'keywords': ['systematic review', 'meta-analysis']},
    'cohort_study': {'evidence_level': 'II', 'keywords': ['cohort', 'prospective', 'longitudinal']},
    'case_control': {'evidence_level': 'III', 'keywords': ['case-control', 'case control']},
    'cross_sectional': {'evidence_level': 'III', 'keywords': ['cross-sectional', 'prevalence']},
    'case_series': {'evidence_level': 'IV', 'keywords': ['case series', 'case report']},
    'expert_opinion': {'evidence_level': 'V', 'keywords': ['expert opinion', 'commentary', 'editorial']}
}

@dataclass
class LiteratureItem:
    """文献数据类 - 增强版包含完整元数据"""
    title: str
    authors: List[str]
    abstract: str
    journal: str
    pubdate: str
    doi: str
    pmid: str
    url: str
    relevance_score: float
    source: str  # semantic_scholar, crossref, core, local_cache

    # 新增元数据字段
    impact_factor: float = 0.0
    citation_count: int = 0
    study_type: str = ""  # original_research, review, meta_analysis, case_report, etc.
    evidence_level: str = ""  # I, II, III, IV, V
    specialty_area: str = ""  # chest_radiology, neuro_radiology, etc.
    mesh_terms: List[str] = None
    keywords: List[str] = None
    open_access: bool = False
    publication_type: str = ""

    def __post_init__(self):
        if self.mesh_terms is None:
            self.mesh_terms = []
        if self.keywords is None:
            self.keywords = []

class LiteratureSearchEngine(ABC):
    """文献检索引擎抽象基类"""

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[LiteratureItem]:
        pass

    @abstractmethod
    def get_name(self) -> str:
        pass

class SemanticScholarEngine(LiteratureSearchEngine):
    """Semantic Scholar API引擎"""

    def __init__(self):
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.timeout = 10
        self.rate_limit = 10  # 每秒最多10个请求
        self.last_request = 0

    def get_name(self) -> str:
        return "semantic_scholar"

    def _rate_limit(self):
        """速率限制"""
        current_time = time.time()
        time_since_last = current_time - self.last_request
        min_interval = 1.0 / self.rate_limit
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)
        self.last_request = time.time()

    def search(self, query: str, max_results: int = 10) -> List[LiteratureItem]:
        """搜索文献"""
        try:
            self._rate_limit()

            # 构建搜索URL
            search_url = f"{self.base_url}/paper/search"
            params = {
                'query': query,
                'limit': min(max_results, 100),
                'fields': 'title,authors,abstract,venue,year,doi,corpusId,citationCount'
            }

            response = requests.get(search_url, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            papers = data.get('data', [])

            results = []
            for paper in papers[:max_results]:
                # 处理作者信息
                authors = [author.get('name', '') for author in paper.get('authors', [])]

                # 计算相关性分数
                relevance_score = self._calculate_relevance_score(paper, query)

                item = LiteratureItem(
                    title=paper.get('title', ''),
                    authors=authors,
                    abstract=paper.get('abstract', ''),
                    journal=paper.get('venue', ''),
                    pubdate=str(paper.get('year', '')),
                    doi=paper.get('doi', ''),
                    pmid='',  # Semantic Scholar不提供PMID
                    url=f"https://semanticscholar.org/paper/{paper.get('corpusId', '')}",
                    relevance_score=relevance_score,
                    source=self.get_name()
                )
                results.append(item)

            return results

        except Exception as e:
            logger.error(f"Semantic Scholar搜索失败: {str(e)}")
            return []

    def _calculate_relevance_score(self, paper: Dict, query: str) -> float:
        """计算文献相关性分数"""
        score = 0.0
        query_lower = query.lower()

        # 标题匹配权重最高
        title = paper.get('title', '').lower()
        if query_lower in title:
            score += 50

        # 摘要匹配
        abstract = paper.get('abstract', '').lower()
        if query_lower in abstract:
            score += 30

        # 引用数加分
        citation_count = paper.get('citationCount', 0)
        score += min(citation_count * 0.1, 20)  # 最多加20分

        # 年份加分（近三年加分）
        year = paper.get('year', 0)
        current_year = datetime.now().year
        if current_year - year <= 3:
            score += 15
        elif current_year - year <= 5:
            score += 10

        return min(score, 100.0)

class CrossRefEngine(LiteratureSearchEngine):
    """CrossRef API引擎"""

    def __init__(self):
        self.base_url = "https://api.crossref.org/works"
        self.timeout = 10

    def get_name(self) -> str:
        return "crossref"

    def search(self, query: str, max_results: int = 10) -> List[LiteratureItem]:
        """搜索文献"""
        try:
            params = {
                'query': query,
                'rows': min(max_results, 100),
                'sort': 'score',
                'order': 'desc'
            }

            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            items = data.get('message', {}).get('items', [])

            results = []
            for item in items[:max_results]:
                # 处理作者信息
                authors = []
                for author in item.get('author', []):
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if given and family:
                        authors.append(f"{given} {family}")
                    elif family:
                        authors.append(family)

                # 获取期刊信息
                journal = ''
                if item.get('container-title'):
                    journal = item['container-title'][0] if isinstance(item['container-title'], list) else item['container-title']

                # 计算相关性分数
                relevance_score = self._calculate_relevance_score(item, query)

                literature_item = LiteratureItem(
                    title=item.get('title', [''])[0] if item.get('title') else '',
                    authors=authors,
                    abstract='',  # CrossRef通常不提供摘要
                    journal=journal,
                    pubdate=self._extract_year(item.get('published-print', {})),
                    doi=item.get('DOI', ''),
                    pmid='',
                    url=item.get('URL', ''),
                    relevance_score=relevance_score,
                    source=self.get_name()
                )
                results.append(literature_item)

            return results

        except Exception as e:
            logger.error(f"CrossRef搜索失败: {str(e)}")
            return []

    def _extract_year(self, published_data: Dict) -> str:
        """提取出版年份"""
        try:
            if published_data and 'date-parts' in published_data:
                date_parts = published_data['date-parts'][0]
                if date_parts:
                    return str(date_parts[0])
        except:
            pass
        return ''

    def _calculate_relevance_score(self, item: Dict, query: str) -> float:
        """计算相关性分数"""
        score = 0.0
        query_lower = query.lower()

        # 标题匹配
        title = item.get('title', [''])[0].lower() if item.get('title') else ''
        if query_lower in title:
            score += 60

        # 关键词匹配
        if item.get('subject'):
            subjects = ' '.join(item['subject']).lower()
            if query_lower in subjects:
                score += 20

        # 引用数加分
        if item.get('is-referenced-by-count'):
            citation_count = item['is-referenced-by-count']
            score += min(citation_count * 0.05, 15)

        return min(score, 100.0)

class COREEngine(LiteratureSearchEngine):
    """CORE API引擎 - 开放获取论文"""

    def __init__(self, api_key: str = None):
        self.base_url = "https://api.core.ac.uk/v3"
        self.api_key = api_key  # 可选的API密钥
        self.timeout = 10

    def get_name(self) -> str:
        return "core"

    def search(self, query: str, max_results: int = 10) -> List[LiteratureItem]:
        """搜索文献"""
        try:
            headers = {}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            search_url = f"{self.base_url}/search/works"
            params = {
                'q': query,
                'limit': min(max_results, 100)
            }

            response = requests.get(search_url, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            results_data = data.get('results', [])

            results = []
            for item in results_data[:max_results]:
                # 处理作者信息
                authors = []
                for author in item.get('authors', []):
                    name = author.get('name', '')
                    if name:
                        authors.append(name)

                # 计算相关性分数
                relevance_score = self._calculate_relevance_score(item, query)

                literature_item = LiteratureItem(
                    title=item.get('title', ''),
                    authors=authors,
                    abstract=item.get('abstract', ''),
                    journal=item.get('publisher', ''),
                    pubdate=str(item.get('publishedDate', '')).split('T')[0] if item.get('publishedDate') else '',
                    doi=item.get('doi', ''),
                    pmid='',
                    url=item.get('downloadUrl', ''),
                    relevance_score=relevance_score,
                    source=self.get_name()
                )
                results.append(literature_item)

            return results

        except Exception as e:
            logger.error(f"CORE搜索失败: {str(e)}")
            return []

    def _calculate_relevance_score(self, item: Dict, query: str) -> float:
        """计算相关性分数"""
        score = 0.0
        query_lower = query.lower()

        # 标题匹配
        title = item.get('title', '').lower()
        if query_lower in title:
            score += 50

        # 摘要匹配
        abstract = item.get('abstract', '').lower()
        if query_lower in abstract:
            score += 30

        # 开放获取加分
        score += 10

        return min(score, 100.0)

class EnhancedPubMedEngine(LiteratureSearchEngine):
    """增强版PubMed eUtility API引擎 - 综合搜索PubMed和PubMed Central"""

    def __init__(self, api_key: str = None):
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.api_key = api_key
        self.timeout = 10
        self.rate_limit = 3  # NCBI要求每秒不超过3个请求
        self.last_request = 0

    def get_name(self) -> str:
        return "enhanced_pubmed"

    def _rate_limit(self):
        """NCBI API速率限制"""
        current_time = time.time()
        time_since_last = current_time - self.last_request
        min_interval = 1.0 / self.rate_limit
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)
        self.last_request = time.time()

    def search(self, query: str, max_results: int = 10, strategy: str = None, filters: Dict = None) -> List[LiteratureItem]:
        """搜索PubMed文献（包括PubMed Central）- 支持策略和过滤"""
        try:
            # 应用搜索策略
            if strategy and strategy in SEARCH_STRATEGIES:
                return self._search_with_strategy(query, max_results, strategy, filters)

            # 应用过滤器
            if filters:
                query = self._apply_filters_to_query(query, filters)

            # 首先搜索PubMed获取最相关的文献
            pubmed_results = self._search_pubmed(query, max_results)

            # 然后搜索PubMed Central获取开放获取文献
            pmc_results = self._search_pubmed_central(query, max_results)

            # 合并结果并去重
            all_results = self._merge_results(pubmed_results, pmc_results)

            # 按相关性排序并限制数量
            all_results.sort(key=lambda x: x.relevance_score, reverse=True)

            return all_results[:max_results]

        except Exception as e:
            logger.error(f"增强版PubMed搜索失败: {str(e)}")
            return []

    def _search_with_strategy(self, query: str, max_results: int, strategy: str, filters: Dict = None) -> List[LiteratureItem]:
        """使用特定策略搜索文献"""
        strategy_config = SEARCH_STRATEGIES[strategy]

        # 构建策略查询
        strategy_query = f"({query}) {strategy_config['query_modifiers']}"

        # 应用额外过滤器
        if filters:
            strategy_query = self._apply_filters_to_query(strategy_query, filters)

        # 执行搜索
        pubmed_results = self._search_pubmed(strategy_query, max_results)
        pmc_results = self._search_pubmed_central(strategy_query, max_results)

        # 合并结果
        all_results = self._merge_results(pubmed_results, pmc_results)

        # 按策略特定的排序方式排序
        if strategy_config['sort'] == 'pub_date':
            all_results.sort(key=lambda x: x.pubdate, reverse=True)
        else:
            all_results.sort(key=lambda x: x.relevance_score, reverse=True)

        return all_results[:strategy_config['max_results']]

    def _apply_filters_to_query(self, query: str, filters: Dict) -> str:
        """应用过滤器到查询"""
        enhanced_query = query

        # 日期范围过滤
        if 'date_range' in filters:
            start_year, end_year = filters['date_range']
            enhanced_query += f' AND ("{start_year}/01/01"[Date - Publication] : "{end_year}/12/31"[Date - Publication])'

        # 文献类型过滤
        if 'publication_types' in filters:
            pub_types = filters['publication_types']
            if pub_types:
                pub_type_query = ' OR '.join([f'"{pt}"[Publication Type]' for pt in pub_types])
                enhanced_query += f' AND ({pub_type_query})'

        # 亚专业过滤
        if 'specialty' in filters and filters['specialty']:
            specialty_terms = RADIOLOGY_SPECIALTIES.get(filters['specialty'], [])
            if specialty_terms:
                specialty_query = ' OR '.join([f'"{term}"[Title/Abstract]' for term in specialty_terms])
                enhanced_query += f' AND ({specialty_query})'

        return enhanced_query

    def _search_pubmed(self, query: str, max_results: int) -> List[LiteratureItem]:
        """搜索PubMed数据库"""
        try:
            self._rate_limit()

            # 构建高级搜索查询
            advanced_query = self._build_advanced_query(query)

            # 搜索PubMed
            search_url = f"{self.base_url}/esearch.fcgi"
            search_params = {
                'db': 'pubmed',
                'term': advanced_query,
                'retmode': 'json',
                'retmax': max_results * 2,  # 获取更多结果以便筛选
                'sort': 'relevance',
                'api_key': self.api_key
            }

            search_response = requests.get(search_url, params=search_params, timeout=self.timeout)
            search_response.raise_for_status()
            search_data = search_response.json()

            if 'esearchresult' not in search_data or 'idlist' not in search_data['esearchresult']:
                return []

            pubmed_ids = search_data['esearchresult']['idlist']

            if not pubmed_ids:
                return []

            # 获取详细信息
            return self._fetch_pubmed_details(pubmed_ids[:max_results], query)

        except Exception as e:
            logger.error(f"PubMed搜索失败: {str(e)}")
            return []

    def _search_pubmed_central(self, query: str, max_results: int) -> List[LiteratureItem]:
        """搜索PubMed Central数据库"""
        try:
            self._rate_limit()

            # 搜索PubMed Central
            search_url = f"{self.base_url}/esearch.fcgi"
            search_params = {
                'db': 'pmc',
                'term': query,
                'retmode': 'json',
                'retmax': max_results,
                'sort': 'relevance',
                'api_key': self.api_key
            }

            search_response = requests.get(search_url, params=search_params, timeout=self.timeout)
            search_response.raise_for_status()
            search_data = search_response.json()

            if 'esearchresult' not in search_data or 'idlist' not in search_data['esearchresult']:
                return []

            pmc_ids = search_data['esearchresult']['idlist']

            if not pmc_ids:
                return []

            # 获取详细信息
            return self._fetch_pmc_details(pmc_ids[:max_results], query)

        except Exception as e:
            logger.error(f"PubMed Central搜索失败: {str(e)}")
            return []

    def _build_advanced_query(self, query: str) -> str:
        """
        构建高级搜索查询 v2 — 更精准的PubMed检索式

        改进：
        1. 更丰富的MeSH映射（覆盖常见放射学场景）
        2. 同时使用 [Title/Abstract] 和 [Mesh] 字段
        3. 扩展到近7年（重要论文可能稍旧）
        4. 更精准的文献类型过滤
        """
        # 提取MeSH术语
        mesh_terms = self._extract_mesh_terms(query)

        # 构建复合查询
        advanced_query = f"({query})"

        if mesh_terms:
            mesh_query = ' OR '.join([f'"{mt}"[Mesh]' for mt in mesh_terms[:4]])
            advanced_query += f" AND ({mesh_query})"

        # 时间限制（最近7年，覆盖更多高质量论文）
        from datetime import datetime
        current_year = datetime.now().year
        advanced_query += f' AND ("{current_year-7}/01/01"[Date - Publication] : "{current_year}/12/31"[Date - Publication])'

        # 文献类型：优先原创研究和综述，排除社论/信件
        advanced_query += ' AND ("Journal Article"[pt] OR "Review"[pt] OR "Meta-Analysis"[pt] OR "Systematic Review"[pt])'
        advanced_query += ' NOT ("Editorial"[pt] OR "Letter"[pt] OR "Comment"[pt])'

        # 限定人类研究
        advanced_query += ' AND ("Humans"[Mesh] OR "Humans"[Filter])'

        return advanced_query

    def _extract_mesh_terms(self, query: str) -> List[str]:
        """提取可能的MeSH主题词 — 扩展版，覆盖常见放射学场景"""
        mesh_mapping = {
            # ── 疾病/解剖 ──
            '肺结节': ['Solitary Pulmonary Nodule', 'Lung Neoplasms', 'Nodule'],
            '肺癌': ['Lung Neoplasms', 'Carcinoma, Non-Small-Cell Lung'],
            '脑卒中': ['Stroke', 'Cerebrovascular Disorders', 'Infarction, Middle Cerebral Artery'],
            '乳腺癌': ['Breast Neoplasms', 'Breast Carcinoma', 'Mammography'],
            '肝癌': ['Liver Neoplasms', 'Carcinoma, Hepatocellular', 'Liver Neoplasms'],
            '结结肠癌': ['Colorectal Neoplasms', 'Colonic Neoplasms'],
            '前列腺癌': ['Prostatic Neoplasms'],
            '骨折': ['Fractures, Bone', 'Bone Diseases'],
            '心血管': ['Cardiovascular Diseases', 'Heart Diseases', 'Coronary Artery Disease'],
            '冠心病': ['Coronary Artery Disease', 'Coronary Disease'],
            '主动脉': ['Aortic Diseases', 'Aneurysm, Dissecting'],
            '肺栓塞': ['Pulmonary Embolism'],
            '胰腺癌': ['Pancreatic Neoplasms'],
            '肾癌': ['Carcinoma, Renal Cell', 'Kidney Neoplasms'],
            '骨转移': ['Neoplasm Metastasis', 'Bone Neoplasms'],
            '脑肿瘤': ['Brain Neoplasms', 'Glioma', 'Meningioma'],
            '胶质瘤': ['Glioma', 'Astrocytoma'],
            '垂体瘤': ['Pituitary Neoplasms'],
            '脊髓': ['Spinal Cord Diseases', 'Spinal Cord Compression'],
            '关节': ['Joint Diseases', 'Arthritis, Rheumatoid'],
            '半月波': ['Meniscus', 'Anterior Cruciate Ligament'],
            '椎间盘': ['Intervertebral Disc Degeneration', 'Intervertebral Disc Displacement'],
            '脑出血': ['Cerebral Hemorrhage', 'Intracranial Hemorrhages'],
            '脑梗塞': ['Brain Infarction', 'Cerebral Infarction'],
            '痴呆': ['Alzheimer Disease', 'Dementia, Vascular', 'Cognitive Dysfunction'],
            '帕金森': ['Parkinson Disease'],
            '癫痫': ['Epilepsy'],
            '多发性硬化': ['Multiple Sclerosis'],
            '视网膜': ['Retinal Diseases', 'Diabetic Retinopathy'],
            '眼眶': ['Orbital Diseases', 'Graves Ophthalmopathy'],
            '甲状腺': ['Thyroid Nodules', 'Thyroid Neoplasms'],
            '颈部淋巴结': ['Lymph Nodes', 'Lymphatic Metastasis'],

            # ── 影像模态 ──
            'CT': ['Tomography, X-Ray Computed'],
            'MRI': ['Magnetic Resonance Imaging'],
            '磁共振': ['Magnetic Resonance Imaging'],
            '超声': ['Ultrasonography', 'Ultrasonography, Doppler'],
            'X线': ['Radiography'],
            'PET': ['Positron-Emission Tomography'],
            'PET-CT': ['Positron-Emission Tomography', 'Tomography, X-Ray Computed'],
            'DSA': ['Angiography, Digital Subtraction'],
            '造影': ['Contrast Media'],
            '钼靶': ['Mammography'],
            '核医学': ['Nuclear Medicine', 'Radiopharmaceuticals'],
            'SPECT': ['Tomography, Emission-Computed, Single-Photon'],
            '功能MRI': ['Magnetic Resonance Imaging', 'Functional Neuroimaging'],
            '弥散': ['Diffusion Magnetic Resonance Imaging', 'Diffusion Tensor Imaging'],
            '灌注': ['Perfusion Imaging', 'Perfusion'],
            '波谱': ['Magnetic Resonance Spectroscopy'],

            # ── AI/技术 ──
            '影像组学': ['Radiomics', 'Machine Learning'],
            '人工智能': ['Artificial Intelligence', 'Deep Learning', 'Machine Learning'],
            '深度学习': ['Deep Learning', 'Neural Networks, Computer'],
            '机器学习': ['Machine Learning', 'Artificial Intelligence'],
            '卷积神经网络': ['Neural Networks, Computer', 'Deep Learning'],
            'Transformer': ['Deep Learning', 'Neural Networks, Computer'],
            '分割': ['Image Processing, Computer-Assisted', 'Deep Learning'],
            '检测': ['Diagnosis, Computer-Assisted', 'Deep Learning'],
            '分类': ['Diagnosis, Computer-Assisted'],
            '辅助诊断': ['Diagnosis, Computer-Assisted', 'Artificial Intelligence'],
            '自然语言处理': ['Natural Language Processing'],
            '大语言模型': ['Deep Learning', 'Natural Language Processing'],
            '联邦学习': ['Machine Learning', 'Deep Learning'],
            '自监督': ['Deep Learning', 'Unsupervised Machine Learning'],
            '弱监督': ['Deep Learning', 'Supervised Machine Learning'],
            '可解释': ['Artificial Intelligence', 'Machine Learning'],
            '生成对抗': ['Deep Learning', 'Neural Networks, Computer'],
            'U-Net': ['Neural Networks, Computer', 'Deep Learning'],
            'ResNet': ['Neural Networks, Computer', 'Deep Learning'],
            'ViT': ['Neural Networks, Computer', 'Deep Learning'],
            '预训练': ['Deep Learning', 'Transfer Learning'],
            '迁移学习': ['Transfer Learning', 'Deep Learning'],
            '少样本': ['Deep Learning', 'Machine Learning'],
            '数据增强': ['Image Processing, Computer-Assisted'],
            '特征提取': ['Image Processing, Computer-Assisted'],
            '组学': ['Radiomics', 'Genomics'],
            '多模态': ['Multimodal Imaging'],
            '预后预测': ['Prognosis', 'Machine Learning'],
            '生存分析': ['Survival Analysis', 'Prognosis'],

            # ── 临床任务 ──
            '筛查': ['Mass Screening', 'Early Detection of Cancer'],
            '诊断': ['Diagnosis', 'Diagnosis, Computer-Assisted'],
            '分期': ['Neoplasm Staging'],
            '疗效评估': ['Treatment Outcome', 'Patient Outcome Assessment'],
            '复发预测': ['Neoplasm Recurrence, Local', 'Prognosis'],
            '风险预测': ['Risk Assessment', 'Risk Factors'],
            '预后': ['Prognosis', 'Survival Analysis'],
            '生物标志物': ['Biomarkers', 'Biomarkers, Tumor'],
            '精准医学': ['Precision Medicine'],
        }

        mesh_terms = []
        query_lower = query.lower()

        for chinese_term, english_terms in mesh_mapping.items():
            if chinese_term.lower() in query_lower:
                mesh_terms.extend(english_terms)

        return mesh_terms

    def _fetch_pubmed_details(self, pubmed_ids: List[str], original_query: str) -> List[LiteratureItem]:
        """获取PubMed文献详细信息"""
        try:
            self._rate_limit()

            # 获取摘要信息
            fetch_url = f"{self.base_url}/efetch.fcgi"
            fetch_params = {
                'db': 'pubmed',
                'id': ','.join(pubmed_ids),
                'retmode': 'xml',
                'api_key': self.api_key
            }

            response = requests.get(fetch_url, params=fetch_params, timeout=self.timeout)
            response.raise_for_status()

            # 解析XML
            root = ET.fromstring(response.content)

            results = []
            for article in root.findall('.//PubmedArticle'):
                article_data = self._parse_pubmed_article(article, original_query)
                if article_data:
                    results.append(article_data)

            return results

        except Exception as e:
            logger.error(f"获取PubMed详情失败: {str(e)}")
            return []

    def _fetch_pmc_details(self, pmc_ids: List[str], original_query: str) -> List[LiteratureItem]:
        """获取PubMed Central文献详细信息"""
        try:
            self._rate_limit()

            # 获取详细信息
            fetch_url = f"{self.base_url}/efetch.fcgi"
            fetch_params = {
                'db': 'pmc',
                'id': ','.join(pmc_ids),
                'retmode': 'xml',
                'api_key': self.api_key
            }

            response = requests.get(fetch_url, params=fetch_params, timeout=self.timeout)
            response.raise_for_status()

            # 解析XML
            root = ET.fromstring(response.content)

            results = []
            for article in root.findall('.//article'):
                article_data = self._parse_pmc_article(article, original_query)
                if article_data:
                    results.append(article_data)

            return results

        except Exception as e:
            logger.error(f"获取PubMed Central详情失败: {str(e)}")
            return []

    def _parse_pubmed_article(self, article_elem, original_query: str) -> Optional[LiteratureItem]:
        """解析PubMed文章XML"""
        try:
            # 获取PMID
            pmid_elem = article_elem.find('.//PMID')
            if pmid_elem is None:
                return None
            pmid = pmid_elem.text

            # 获取标题
            title_elem = article_elem.find('.//ArticleTitle')
            title = title_elem.text if title_elem is not None else ""
            if title_elem is not None and title_elem.text is None:
                # 处理带子标题的情况
                subtitle_elem = title_elem.find('.//Subtitle')
                title = subtitle_elem.text if subtitle_elem is not None else ""

            # 获取作者
            authors = []
            author_list = article_elem.find('.//AuthorList')
            if author_list is not None:
                for author in author_list.findall('.//Author'):
                    last_name = author.find('.//LastName')
                    fore_name = author.find('.//ForeName')
                    if last_name is not None and fore_name is not None:
                        authors.append(f"{fore_name.text} {last_name.text}")
                    elif last_name is not None:
                        authors.append(last_name.text)

            # 获取期刊信息
            journal_elem = article_elem.find('.//Journal')
            journal = ""
            if journal_elem is not None:
                journal_title = journal_elem.find('.//Title')
                if journal_title is not None:
                    journal = journal_title.text

            # 获取发表日期
            pubdate = ""
            pubdate_elem = article_elem.find('.//PubDate')
            if pubdate_elem is not None:
                year_elem = pubdate_elem.find('.//Year')
                month_elem = pubdate_elem.find('.//Month')
                if year_elem is not None:
                    pubdate = year_elem.text
                    if month_elem is not None:
                        pubdate += f"-{month_elem.text}"

            # 获取摘要
            abstract = ""
            abstract_elem = article_elem.find('.//Abstract/AbstractText')
            if abstract_elem is not None and abstract_elem.text:
                abstract = abstract_elem.text
            else:
                # 处理多个AbstractText的情况
                abstract_parts = article_elem.findall('.//AbstractText')
                if abstract_parts:
                    abstract = ' '.join([part.text for part in abstract_parts if part.text])

            # 获取DOI
            doi = ""
            doi_elem = article_elem.find('.//ArticleId[@IdType="doi"]')
            if doi_elem is not None:
                doi = doi_elem.text

            # 获取MeSH术语
            mesh_terms = []
            mesh_list = article_elem.find('.//MeshHeadingList')
            if mesh_list is not None:
                for mesh in mesh_list.findall('.//DescriptorName'):
                    if mesh.text:
                        mesh_terms.append(mesh.text)

            # 获取关键词
            keywords = []
            keyword_list = article_elem.find('.//KeywordList')
            if keyword_list is not None:
                for keyword in keyword_list.findall('.//Keyword'):
                    if keyword.text:
                        keywords.append(keyword.text)

            # 获取文献类型
            publication_types = []
            pub_type_list = article_elem.find('.//PublicationTypeList')
            if pub_type_list is not None:
                for pub_type in pub_type_list.findall('.//PublicationType'):
                    if pub_type.text:
                        publication_types.append(pub_type.text)

            # 获取引用次数（需要额外API调用，这里设为0）
            citation_count = 0

            # 判断是否开放获取
            pmc_elem = article_elem.find('.//ArticleIdList/ArticleId[@IdType="pmc"]')
            open_access = pmc_elem is not None and 'PMC' in str(pmc_elem.text)

            # 判断研究类型和证据等级
            study_type, evidence_level = self._determine_study_type_and_evidence(title, abstract, publication_types)

            # 判断放射学亚专业领域
            specialty_area = self._determine_specialty_area(title, abstract, keywords)

            # 获取期刊影响因子
            impact_factor = self._get_journal_impact_factor(journal)

            # 计算相关性分数
            relevance_score = self._calculate_relevance_score({
                'title': title,
                'abstract': abstract,
                'pubdate': pubdate,
                'journal': journal,
                'citation_count': citation_count,
                'mesh_terms': mesh_terms,
                'open_access': open_access
            }, original_query)

            # 构建URL
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            return LiteratureItem(
                title=title,
                authors=authors,
                abstract=abstract[:2000] if abstract else "摘要暂不可用",  # 限制长度
                journal=journal,
                pubdate=pubdate,
                doi=doi,
                pmid=pmid,
                url=url,
                relevance_score=relevance_score,
                source=self.get_name() + "_pubmed",
                impact_factor=impact_factor,
                citation_count=citation_count,
                study_type=study_type,
                evidence_level=evidence_level,
                specialty_area=specialty_area,
                mesh_terms=mesh_terms,
                keywords=keywords,
                open_access=open_access,
                publication_type=', '.join(publication_types)
            )

        except Exception as e:
            logger.error(f"解析PubMed文章失败: {str(e)}")
            return None

    def _parse_pmc_article(self, article_elem, original_query: str) -> Optional[LiteratureItem]:
        """解析PubMed Central文章XML"""
        try:
            # 获取PMC ID
            pmc_id = ""
            article_id_elems = article_elem.findall('.//article-id')
            for elem in article_id_elems:
                if elem.get('pub-id-type') == 'pmc':
                    pmc_id = elem.text
                    break

            if not pmc_id:
                return None

            # 获取PMID
            pmid = ""
            for elem in article_id_elems:
                if elem.get('pub-id-type') == 'pmid':
                    pmid = elem.text
                    break

            # 获取标题
            title = ""
            title_elem = article_elem.find('.//article-title')
            if title_elem is not None:
                title = ' '.join(title_elem.itertext()).strip()

            # 获取作者
            authors = []
            contrib_group = article_elem.find('.//contrib-group')
            if contrib_group is not None:
                for contrib in contrib_group.findall('.//contrib'):
                    if contrib.get('contrib-type') == 'author':
                        name_elem = contrib.find('.//name')
                        if name_elem is not None:
                            surname = name_elem.find('.//surname')
                            given_names = name_elem.find('.//given-names')
                            if surname is not None and given_names is not None:
                                authors.append(f"{given_names.text} {surname.text}")
                            elif surname is not None:
                                authors.append(surname.text)

            # 获取期刊信息
            journal = ""
            journal_elem = article_elem.find('.//journal-title')
            if journal_elem is not None:
                journal = journal_elem.text

            # 获取发表日期
            pubdate = ""
            pub_date_elems = article_elem.findall('.//pub-date')
            for pub_date in pub_date_elems:
                if pub_date.get('pub-type') == 'epub':
                    year_elem = pub_date.find('.//year')
                    month_elem = pub_date.find('.//month')
                    if year_elem is not None:
                        pubdate = year_elem.text
                        if month_elem is not None:
                            pubdate += f"-{month_elem.text}"
                    break

            # 获取摘要
            abstract = ""
            abstract_elem = article_elem.find('.//abstract')
            if abstract_elem is not None:
                abstract = ' '.join(abstract_elem.itertext()).strip()

            # 获取DOI
            doi = ""
            for elem in article_id_elems:
                if elem.get('pub-id-type') == 'doi':
                    doi = elem.text
                    break

            # 计算相关性分数
            relevance_score = self._calculate_relevance_score({
                'title': title,
                'abstract': abstract,
                'pubdate': pubdate,
                'journal': journal
            }, original_query)

            # 构建URL
            url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"

            return LiteratureItem(
                title=title,
                authors=authors,
                abstract=abstract[:2000] if abstract else "摘要暂不可用",  # 限制长度
                journal=journal,
                pubdate=pubdate,
                doi=doi,
                pmid=pmid,
                url=url,
                relevance_score=relevance_score + 5,  # PubMed Central文献加分
                source=self.get_name() + "_pmc"
            )

        except Exception as e:
            logger.error(f"解析PubMed Central文章失败: {str(e)}")
            return None

    def _calculate_relevance_score(self, article: Dict, query: str, strategy: str = None) -> float:
        """
        多因素相关性评分算法 v2 — 改进版

        评分维度（总分100）：
        1. 标题语义匹配 (25%)  — 关键词覆盖度 + 词序邻近度
        2. 摘要语义匹配 (25%)  — 关键词覆盖度 + 关键位置加权
        3. MeSH/关键词匹配 (15%) — 医学主题词精确匹配
        4. 时效性       (15%)  — 指数衰减模型
        5. 期刊质量     (10%)  — 影响因子归一化
        6. 引用影响力   (10%)  — 对数尺度引用分

        加分项（不封顶百分比）：
        + 开放获取 +3
        + 高影响力期刊额外加分
        + 策略匹配加分
        """
        score = 0.0
        query_lower = query.lower().strip()
        query_words = [w for w in query_lower.split() if len(w) > 1]

        if not query_words:
            return 0.0

        # ── 1. 标题语义匹配 (25%) ──
        title_score = self._calc_title_relevance(
            article.get('title', ''), query_lower, query_words
        )
        score += title_score * 0.25

        # ── 2. 摘要语义匹配 (25%) ──
        abstract_score = self._calc_abstract_relevance(
            article.get('abstract', ''), query_lower, query_words
        )
        score += abstract_score * 0.25

        # ── 3. MeSH/关键词匹配 (15%) ──
        mesh_score = self._calc_mesh_relevance(
            article.get('mesh_terms', []),
            article.get('keywords', []),
            query_lower, query_words
        )
        score += mesh_score * 0.15

        # ── 4. 时效性 (15%) ──
        recency_score = self._calc_recency(article.get('pubdate', ''))
        score += recency_score * 0.15

        # ── 5. 期刊质量 (10%) ──
        journal_score = self._calc_journal_quality(article.get('journal', ''))
        score += journal_score * 0.10

        # ── 6. 引用影响力 (10%) ──
        citation_score = self._calc_citation_impact(article.get('citation_count', 0))
        score += citation_score * 0.10

        # ── 加分项 ──
        # 开放获取
        if article.get('open_access', False) or 'PMC' in str(article.get('source', '')):
            score += 3

        # 策略匹配
        if strategy:
            score += self._calculate_strategy_bonus(article, strategy)

        return min(round(score, 1), 100.0)

    def _calc_title_relevance(self, title: str, query_lower: str, query_words: List[str]) -> float:
        """
        标题相关性评分（0-100）
        - 完整query在标题中：90-100
        - 关键词覆盖度：按匹配比例 0-80
        - 关键词位置加权：标题前半部分匹配加分
        - 连续词组匹配：额外加分
        """
        if not title or not query_words:
            return 0.0

        title_lower = title.lower()
        title_words = title_lower.split()
        if not title_words:
            return 0.0

        score = 0.0

        # 完整query短语匹配（最高优先级）
        if query_lower in title_lower:
            score = 90.0
            # 标题越短越精准，额外加分
            if len(title_words) <= 15:
                score = 100.0
            elif len(title_words) <= 25:
                score = 95.0
        else:
            # 关键词覆盖度（匹配的query词 / 总query词）
            matched_words = set()
            for qw in query_words:
                if qw in title_lower:
                    matched_words.add(qw)

            coverage = len(matched_words) / len(query_words)
            score = coverage * 70.0

            # 位置加权：关键词出现在标题前半部分
            if matched_words:
                half_len = len(title_words) // 2
                for qw in matched_words:
                    # 找所有出现位置
                    for idx, tw in enumerate(title_words):
                        if qw in tw:
                            if idx < half_len:
                                score += 5.0
                            break

            # 连续词组匹配加分（相邻的query词在标题中也相邻）
            for i in range(len(query_words) - 1):
                bigram = f"{query_words[i]} {query_words[i+1]}"
                if bigram in title_lower:
                    score += 8.0

        return min(score, 100.0)

    def _calc_abstract_relevance(self, abstract: str, query_lower: str, query_words: List[str]) -> float:
        """
        摘要相关性评分（0-100）
        - 关键词覆盖度：40%
        - 关键词频次/密度：30%
        - 关键位置加权（首句/末句匹配）：20%
        - 邻近度：10%
        """
        if not abstract or not query_words:
            return 0.0

        abstract_lower = abstract.lower()
        abstract_words = abstract_lower.split()
        total_words = len(abstract_words)
        if total_words == 0:
            return 0.0

        score = 0.0

        # 1. 关键词覆盖度（最高40分）
        matched_words = set()
        for qw in query_words:
            if qw in abstract_lower:
                matched_words.add(qw)
        coverage = len(matched_words) / len(query_words)
        score += coverage * 40.0

        # 2. 关键词频次加权（最高30分）
        # 使用TF-style scoring: 词频 / 文档长度，归一化到30分
        tf_score = 0.0
        for qw in matched_words:
            count = abstract_lower.count(qw)
            # 对数TF: 1 + log(count)
            import math
            tf = 1 + math.log(count) if count > 0 else 0
            tf_score += tf
        # 归一化：假设理想情况是所有query词各出现3次
        ideal_tf = len(query_words) * (1 + math.log(3))
        tf_normalized = min(tf_score / ideal_tf, 1.0) if ideal_tf > 0 else 0
        score += tf_normalized * 30.0

        # 3. 关键位置加权（最高20分）
        # 摘要首句（背景/目的）和末句（结论）匹配权重更高
        first_sentence = ''
        last_sentence = ''
        # 简单按句号分句
        sentences = abstract.split('.')
        if sentences:
            first_sentence = sentences[0].lower()[:200]
            last_sentence = sentences[-1].lower()[-200:] if len(sentences) > 1 else ''

        position_matches = 0
        for qw in matched_words:
            if qw in first_sentence:
                position_matches += 2  # 首句权重x2
            if last_sentence and qw in last_sentence:
                position_matches += 1.5  # 末句权重x1.5
        # 归一化到20分
        ideal_position = len(matched_words) * 3.5
        if ideal_position > 0:
            score += min(position_matches / ideal_position, 1.0) * 20.0

        # 4. 邻近度（最高10分）
        # 匹配词之间的距离越近，说明主题越集中
        if len(matched_words) >= 2:
            positions = []
            for qw in matched_words:
                pos = abstract_lower.find(qw)
                if pos >= 0:
                    positions.append(pos)
            if len(positions) >= 2:
                positions.sort()
                avg_gap = sum(positions[i+1] - positions[i] for i in range(len(positions)-1)) / (len(positions)-1)
                # 理想情况：所有词在100字符内
                proximity = max(0, 1 - avg_gap / 500)
                score += proximity * 10.0

        return min(score, 100.0)

    def _calc_mesh_relevance(self, mesh_terms: List[str], keywords: List[str],
                              query_lower: str, query_words: List[str]) -> float:
        """
        MeSH术语 + 作者关键词相关性评分（0-100）
        - MeSH精确匹配：每个匹配 +25分
        - 关键词匹配：每个匹配 +15分
        - query完整短语在MeSH中：额外 +20分
        """
        if not mesh_terms and not keywords:
            return 0.0

        score = 0.0
        mesh_lower = [m.lower() for m in (mesh_terms or [])]
        kw_lower = [k.lower() for k in (keywords or [])]

        # query完整短语匹配
        for m in mesh_lower:
            if query_lower in m:
                score += 25.0
                break

        for k in kw_lower:
            if query_lower in k:
                score += 20.0
                break

        # 单个query词匹配，MeSH权重更高
        mesh_matched = set()
        kw_matched = set()
        for qw in query_words:
            for m in mesh_lower:
                if qw in m:
                    mesh_matched.add(qw)
                    break
        for qw in query_words:
            for k in kw_lower:
                if qw in k:
                    kw_matched.add(qw)
                    break

        score += min(len(mesh_matched) * 12.0, 60.0)
        score += min(len(kw_matched) * 8.0, 40.0)

        return min(score, 100.0)

    def _calc_recency(self, pubdate: str) -> float:
        """
        时效性评分（0-100）— 指数衰减模型
        当年=100, 去年=90, 2年=78, 3年=67, 5年=45, 10年=20
        """
        if not pubdate:
            return 30.0  # 未知年份给基础分

        try:
            pub_year = int(str(pubdate)[:4])
            current_year = datetime.now().year
            years_diff = current_year - pub_year

            if years_diff < 0:
                return 50.0  # 未来日期（预印本）
            if years_diff == 0:
                return 100.0

            # 指数衰减: score = 100 * e^(-0.15 * years)
            import math
            score = 100.0 * math.exp(-0.15 * years_diff)
            return max(score, 10.0)
        except (ValueError, TypeError):
            return 30.0

    def _calc_journal_quality(self, journal: str) -> float:
        """
        期刊质量评分（0-100）
        - 影响因子映射到0-100，使用对数尺度
        - Radiology-level (IF~30) ≈ 85分
        - 顶级期刊 (IF~50+) ≈ 100分
        - 低影响因子 (IF~1) ≈ 20分
        """
        import math
        if not journal:
            return 20.0

        impact_factor = self._get_journal_impact_factor(journal)
        if impact_factor <= 0:
            return 20.0

        # 对数尺度: score = 20 + 80 * log(1 + IF) / log(1 + 100)
        score = 20.0 + 80.0 * math.log(1 + impact_factor) / math.log(101)
        return min(score, 100.0)

    def _calc_citation_impact(self, citation_count: int) -> float:
        """
        引用影响力评分（0-100）— 对数尺度
        - 0引用 = 10分（基础分）
        - 10引用 ≈ 40分
        - 100引用 ≈ 65分
        - 1000引用 ≈ 90分
        """
        import math
        if not citation_count or citation_count <= 0:
            return 10.0

        # 对数尺度: score = 10 + 90 * log(1 + citations) / log(1 + 5000)
        score = 10.0 + 90.0 * math.log(1 + citation_count) / math.log(5001)
        return min(score, 100.0)

    def _determine_study_type_and_evidence(self, title: str, abstract: str, publication_types: List[str]) -> tuple:
        """确定研究类型和证据等级"""
        text_to_analyze = f"{title} {abstract}".lower()

        # 检查文献类型
        for pub_type in publication_types:
            pub_type_lower = pub_type.lower()
            if 'review' in pub_type_lower or 'systematic review' in pub_type_lower:
                return 'systematic_review', 'I'
            elif 'meta-analysis' in pub_type_lower or 'metaanalysis' in pub_type_lower:
                return 'meta_analysis', 'I'
            elif 'randomized controlled trial' in pub_type_lower or 'rct' in pub_type_lower:
                return 'randomized_controlled_trial', 'I'

        # 基于内容的判断
        for study_type, info in STUDY_TYPE_MAPPING.items():
            keywords = info['keywords']
            if any(keyword.lower() in text_to_analyze for keyword in keywords):
                return study_type, info['evidence_level']

        # 默认值
        return 'original_research', 'III'

    def _determine_specialty_area(self, title: str, abstract: str, keywords: List[str]) -> str:
        """确定放射学亚专业领域"""
        text_to_analyze = f"{title} {abstract} {' '.join(keywords)}".lower()

        specialty_scores = {}
        for specialty, terms in RADIOLOGY_SPECIALTIES.items():
            score = sum(1 for term in terms if term in text_to_analyze)
            if score > 0:
                specialty_scores[specialty] = score

        if specialty_scores:
            # 返回得分最高的亚专业
            return max(specialty_scores, key=specialty_scores.get)

        return 'general_radiology'

    def _calculate_strategy_bonus(self, article: Dict, strategy: str) -> float:
        """计算策略特定加分"""
        bonus = 0.0

        if strategy == 'core_papers':
            # 高影响力期刊加分
            journal = article.get('journal', '')
            if any(high_impact in journal for high_impact in ['Nature', 'Science', 'Cell', 'Lancet', 'NEJM', 'JAMA']):
                bonus += 15
        elif strategy == 'recent_advances':
            # 近期发表加分
            pubdate = article.get('pubdate', '')
            try:
                pub_year = int(pubdate[:4])
                current_year = datetime.now().year
                if current_year - pub_year <= 2:
                    bonus += 10
            except:
                pass
        elif strategy == 'methodological_papers':
            # 方法学相关加分
            title = article.get('title', '').lower()
            abstract = article.get('abstract', '').lower()
            method_keywords = ['method', 'algorithm', 'technique', 'framework', 'protocol']
            if any(keyword in title or keyword in abstract for keyword in method_keywords):
                bonus += 10
        elif strategy == 'clinical_applications':
            # 临床应用相关加分
            title = article.get('title', '').lower()
            abstract = article.get('abstract', '').lower()
            clinical_keywords = ['clinical', 'patient', 'diagnosis', 'treatment', 'therapy']
            if any(keyword in title or keyword in abstract for keyword in clinical_keywords):
                bonus += 10

        return bonus

    def _get_journal_impact_factor(self, journal: str) -> float:
        """获取期刊影响因子"""
        if not journal:
            return 1.0

        # 在影响因子数据库中查找
        for journal_name, impact_factor in JOURNAL_IMPACT_FACTORS.items():
            if journal_name.lower() in journal.lower():
                return impact_factor

        # 默认影响因子
        return 1.0

    def _merge_results(self, pubmed_results: List[LiteratureItem], pmc_results: List[LiteratureItem]) -> List[LiteratureItem]:
        """合并PubMed和PubMed Central结果，去重"""
        all_results = []
        seen_titles = set()
        seen_dois = set()

        # 首先添加PubMed Central结果（开放获取优先）
        for result in pmc_results:
            title_key = result.title.lower().strip()
            if result.doi:
                if title_key not in seen_titles and result.doi not in seen_dois:
                    all_results.append(result)
                    seen_titles.add(title_key)
                    seen_dois.add(result.doi)
            else:
                if title_key not in seen_titles:
                    all_results.append(result)
                    seen_titles.add(title_key)

        # 然后添加PubMed结果，避免重复
        for result in pubmed_results:
            title_key = result.title.lower().strip()
            if result.doi:
                if title_key not in seen_titles and result.doi not in seen_dois:
                    all_results.append(result)
                    seen_titles.add(title_key)
                    seen_dois.add(result.doi)
            else:
                if title_key not in seen_titles:
                    all_results.append(result)
                    seen_titles.add(title_key)

        return all_results


class PubMedCentralEngine(LiteratureSearchEngine):
    """PubMed Central API引擎 - 完全免费的生物医学文献（保留旧版本）"""

    def __init__(self):
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.timeout = 10

    def get_name(self) -> str:
        return "pubmed_central"

    def search(self, query: str, max_results: int = 10) -> List[LiteratureItem]:
        """搜索PubMed Central文献"""
        try:
            # 第一步：搜索获取PMID列表
            search_url = f"{self.base_url}/esearch.fcgi"
            search_params = {
                'db': 'pmc',
                'term': query,
                'retmode': 'json',
                'retmax': max_results,
                'sort': 'relevance'
            }

            search_response = requests.get(search_url, params=search_params, timeout=self.timeout)
            search_data = search_response.json()

            if 'esearchresult' not in search_data or 'idlist' not in search_data['esearchresult']:
                return []

            pmc_ids = search_data['esearchresult']['idlist'][:max_results]

            if not pmc_ids:
                return []

            # 第二步：获取详细信息
            fetch_url = f"{self.base_url}/esummary.fcgi"
            fetch_params = {
                'db': 'pmc',
                'id': ','.join(pmc_ids),
                'retmode': 'json'
            }

            fetch_response = requests.get(fetch_url, params=fetch_params, timeout=self.timeout)
            fetch_data = fetch_response.json()

            results = []
            if 'result' in fetch_data:
                for pmc_id in pmc_ids:
                    if pmc_id in fetch_data['result']:
                        article = fetch_data['result'][pmc_id]

                        # 获取文章详细信息
                        title = article.get('title', '')
                        authors = [author.get('name', '') for author in article.get('authors', [])]
                        pubdate = article.get('pubdate', '')
                        journal = article.get('source', '')

                        # 获取摘要（需要额外调用efetch）
                        abstract = self._get_abstract(pmc_id)

                        # 计算相关性分数（PubMed Central专用算法）
                        relevance_score = self._calculate_relevance_score({
                            'title': title,
                            'abstract': abstract,
                            'pubdate': pubdate
                        }, query)

                        # PubMed Central文章的免费访问URL
                        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/"

                        item = LiteratureItem(
                            title=title,
                            authors=authors,
                            abstract=abstract,
                            journal=journal,
                            pubdate=pubdate,
                            doi=article.get('elocationid', ''),
                            pmid=pmc_id,
                            url=url,
                            relevance_score=relevance_score,
                            source=self.get_name()
                        )
                        results.append(item)

            return results

        except Exception as e:
            logger.error(f"PubMed Central搜索失败: {str(e)}")
            return []

    def _get_abstract(self, pmc_id: str) -> str:
        """获取文章摘要"""
        try:
            fetch_url = f"{self.base_url}/efetch.fcgi"
            params = {
                'db': 'pmc',
                'id': pmc_id,
                'retmode': 'xml'
            }

            response = requests.get(fetch_url, params=params, timeout=self.timeout)

            # 解析XML获取摘要
            root = ET.fromstring(response.content)
            abstract_elem = root.find('.//abstract')

            if abstract_elem is not None:
                # 提取所有文本内容
                abstract_text = ' '.join(abstract_elem.itertext()).strip()
                return abstract_text[:1000]  # 限制长度

            return "摘要暂不可用"

        except Exception as e:
            logger.error(f"获取摘要失败 PMC{pmc_id}: {str(e)}")
            return "摘要获取失败"

    def _calculate_relevance_score(self, article: Dict, query: str) -> float:
        """PubMed Central专用的相关性评分算法"""
        score = 0.0
        query_lower = query.lower()

        # 标题匹配（权重最高）
        title = article.get('title', '').lower()
        title_words = query_lower.split()
        title_matches = sum(1 for word in title_words if word in title)
        score += (title_matches / len(title_words)) * 40 if title_words else 0

        # 摘要匹配
        abstract = article.get('abstract', '').lower()
        if query_lower in abstract:
            score += 35
        else:
            abstract_matches = sum(1 for word in title_words if word in abstract)
            score += (abstract_matches / len(title_words)) * 25 if title_words else 0

        # 发表时间加分
        pubdate = article.get('pubdate', '')
        try:
            pub_year = int(pubdate.split()[0]) if pubdate else 0
            current_year = datetime.now().year
            if current_year - pub_year <= 2:
                score += 15
            elif current_year - pub_year <= 5:
                score += 10
            elif current_year - pub_year <= 10:
                score += 5
        except:
            pass  # 如果日期解析失败，不加分

        # 开放获取加分（PubMed Central都是开放获取）
        score += 10

        return min(score, 100.0)

class LocalCacheEngine(LiteratureSearchEngine):
    """本地缓存引擎"""

    def __init__(self, cache_db_path: str = "./data/literature_cache.db"):
        self.cache_db_path = cache_db_path
        self._init_cache_db()

    def get_name(self) -> str:
        return "local_cache"

    def _init_cache_db(self):
        """初始化缓存数据库"""
        os.makedirs(os.path.dirname(self.cache_db_path), exist_ok=True)

        conn = sqlite3.connect(self.cache_db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS literature_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_hash TEXT,
                title TEXT,
                authors TEXT,
                abstract TEXT,
                journal TEXT,
                pubdate TEXT,
                doi TEXT,
                pmid TEXT,
                url TEXT,
                relevance_score REAL,
                source TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_query_hash ON literature_cache(query_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cached_at ON literature_cache(cached_at)')

        conn.commit()
        conn.close()

    def _get_query_hash(self, query: str) -> str:
        """生成查询哈希"""
        import hashlib
        return hashlib.md5(query.lower().strip().encode()).hexdigest()

    def _is_cache_valid(self, cached_at: str) -> bool:
        """检查缓存是否有效（7天内）"""
        try:
            cache_time = datetime.strptime(cached_at, '%Y-%m-%d %H:%M:%S')
            return datetime.now() - cache_time < timedelta(days=7)
        except:
            return False

    def search(self, query: str, max_results: int = 10) -> List[LiteratureItem]:
        """从缓存搜索文献"""
        try:
            query_hash = self._get_query_hash(query)

            conn = sqlite3.connect(self.cache_db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT title, authors, abstract, journal, pubdate, doi, pmid, url,
                       relevance_score, source, cached_at
                FROM literature_cache
                WHERE query_hash = ? AND cached_at > datetime('now', '-7 days')
                ORDER BY relevance_score DESC
                LIMIT ?
            ''', (query_hash, max_results))

            rows = cursor.fetchall()
            conn.close()

            results = []
            for row in rows:
                literature_item = LiteratureItem(
                    title=row[0],
                    authors=json.loads(row[1]) if row[1] else [],
                    abstract=row[2],
                    journal=row[3],
                    pubdate=row[4],
                    doi=row[5],
                    pmid=row[6],
                    url=row[7],
                    relevance_score=row[8],
                    source=row[9]
                )
                results.append(literature_item)

            return results

        except Exception as e:
            logger.error(f"本地缓存搜索失败: {str(e)}")
            return []

    def cache_results(self, query: str, results: List[LiteratureItem]):
        """缓存搜索结果"""
        try:
            query_hash = self._get_query_hash(query)

            conn = sqlite3.connect(self.cache_db_path)
            cursor = conn.cursor()

            for item in results:
                cursor.execute('''
                    INSERT INTO literature_cache
                    (query_hash, title, authors, abstract, journal, pubdate, doi, pmid, url, relevance_score, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    query_hash, item.title, json.dumps(item.authors), item.abstract,
                    item.journal, item.pubdate, item.doi, item.pmid, item.url,
                    item.relevance_score, item.source
                ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"缓存结果失败: {str(e)}")

class MultiSourceLiteratureSearch:
    """多源文献检索系统"""

    def __init__(self, pubmed_api_key: str = None):
        self.engines = [
            EnhancedPubMedEngine(pubmed_api_key),  # 优先使用增强版PubMed（最权威的生物医学文献）
            PubMedCentralEngine(),    # 备用PubMed Central
            SemanticScholarEngine(),
            CrossRefEngine(),
            COREEngine(),
            LocalCacheEngine()
        ]

    def search(self, query: str, max_results: int = 10,
               preferred_sources: List[str] = None, strategy: str = None,
               filters: Dict = None) -> List[LiteratureItem]:
        """多源搜索文献 - 支持策略和过滤"""
        all_results = []

        # 如果指定了策略，优先使用增强版PubMed引擎
        if strategy and strategy in SEARCH_STRATEGIES:
            enhanced_pubmed = None
            for engine in self.engines:
                if engine.get_name() == "enhanced_pubmed":
                    enhanced_pubmed = engine
                    break

            if enhanced_pubmed:
                try:
                    strategy_results = enhanced_pubmed.search(query, max_results, strategy, filters)
                    logger.info(f"策略 '{strategy}' 获取到 {len(strategy_results)} 篇文献")
                    all_results.extend(strategy_results)
                    return all_results[:max_results]
                except Exception as e:
                    logger.error(f"策略搜索失败: {str(e)}")

        # 首先尝试本地缓存
        cache_engine = None
        for engine in self.engines:
            if engine.get_name() == "local_cache":
                cache_engine = engine
                break

        if cache_engine:
            cache_results = cache_engine.search(query, max_results)
            if cache_results:
                logger.info(f"从缓存获取到 {len(cache_results)} 篇文献")
                all_results.extend(cache_results)

        # 如果缓存结果不足，从在线API获取
        if len(all_results) < max_results:
            needed_results = max_results - len(all_results)

            for i, engine in enumerate(self.engines):
                # 跳过缓存引擎
                if engine.get_name() == "local_cache":
                    continue

                if preferred_sources and engine.get_name() not in preferred_sources:
                    continue

                try:
                    # 传递策略和过滤器参数
                    if hasattr(engine, 'search') and engine.get_name() == "enhanced_pubmed":
                        results = engine.search(query, needed_results, strategy, filters)
                    else:
                        results = engine.search(query, needed_results)

                    logger.info(f"{engine.get_name()} 获取到 {len(results)} 篇文献")

                    # 应用过滤器
                    if filters:
                        results = self._apply_filters_to_results(results, filters)

                    # 去重
                    new_results = []
                    for result in results:
                        if not self._is_duplicate(result, all_results):
                            new_results.append(result)
                            all_results.append(result)

                    logger.info(f"{engine.get_name()} 新增 {len(new_results)} 篇不重复文献")

                    if len(all_results) >= max_results:
                        break

                except Exception as e:
                    logger.error(f"{engine.get_name()} 搜索失败: {str(e)}")
                    continue

        # 按相关性排序
        all_results.sort(key=lambda x: x.relevance_score, reverse=True)

        # 缓存结果（仅在线API的结果）
        if cache_engine and len(all_results) > len(cache_results if 'cache_results' in locals() else []):
            online_results = all_results[len(cache_results if 'cache_results' in locals() else []):]
            cache_engine.cache_results(query, online_results)

        return all_results[:max_results]

    def get_literature_context(self, research_topic: str, specialty: str = "") -> Dict[str, Any]:
        """获取文献上下文信息 - 用于研究方案生成的文献支持"""
        try:
            # 构建专业特定的检索查询
            if specialty:
                specialty_mapping = {
                    '胸部影像': 'chest_radiology',
                    '神经影像': 'neuro_radiology',
                    '腹部影像': 'abdominal_radiology',
                    '骨肌影像': 'musculoskeletal_radiology',
                    '儿科影像': 'pediatric_radiology',
                    '介入放射学': 'interventional_radiology',
                    '乳腺影像': 'breast_radiology',
                    '核医学': 'nuclear_radiology'
                }
                specialty_term = specialty_mapping.get(specialty, '')

                # 设置过滤器
                filters = {
                    'specialty': specialty_term,
                    'date_range': (2019, 2024),  # 近5年
                    'publication_types': ['Journal Article', 'Clinical Trial', 'Randomized Controlled Trial']
                }

                # 执行检索
                literature_results = self.search(
                    research_topic,
                    max_results=15,
                    strategy='core_papers',
                    filters=filters
                )
            else:
                # 无专业过滤的通用检索
                literature_results = self.search(
                    research_topic,
                    max_results=10,
                    strategy='core_papers'
                )

            if not literature_results:
                return {
                    'total_results': 0,
                    'high_quality_count': 0,
                    'recommended_papers': [],
                    'key_findings': [],
                    'methodological_trends': [],
                    'research_gaps': ['暂无相关文献，建议扩大检索范围'],
                    'keywords': []
                }

            # 筛选高质量文献（影响因子≥3.0或来自高质量期刊）
            high_quality_papers = []
            for paper in literature_results:
                if (hasattr(paper, 'impact_factor') and paper.impact_factor >= 3.0) or \
                   (hasattr(paper, 'journal') and paper.journal in JOURNAL_IMPACT_FACTORS and JOURNAL_IMPACT_FACTORS[paper.journal] >= 3.0):
                    high_quality_papers.append({
                        'title': paper.title,
                        'authors': paper.authors,
                        'journal': paper.journal,
                        'publication_date': paper.pubdate,
                        'pmid': getattr(paper, 'pmid', ''),
                        'doi': getattr(paper, 'doi', ''),
                        'abstract': getattr(paper, 'abstract', ''),
                        'impact_factor': getattr(paper, 'impact_factor', 0.0)
                    })

            # 提取关键发现
            key_findings = self._extract_key_findings(literature_results)

            # 识别方法学趋势
            methodological_trends = self._identify_methodological_trends(literature_results)

            # 识别研究空白
            research_gaps = self._identify_research_gaps(literature_results, research_topic)

            # 提取关键词
            keywords = self._extract_keywords(literature_results)

            return {
                'total_results': len(literature_results),
                'high_quality_count': len(high_quality_papers),
                'recommended_papers': high_quality_papers[:5],  # 前5篇
                'key_findings': key_findings,
                'methodological_trends': methodological_trends,
                'research_gaps': research_gaps,
                'keywords': keywords
            }

        except Exception as e:
            logger.error(f"获取文献上下文失败: {str(e)}")
            return {
                'total_results': 0,
                'high_quality_count': 0,
                'recommended_papers': [],
                'key_findings': [],
                'methodological_trends': [],
                'research_gaps': ['文献检索失败，请检查网络连接'],
                'keywords': []
            }

    def _extract_key_findings(self, papers: List[LiteratureItem]) -> List[str]:
        """从文献中提取关键发现"""
        findings = []

        for paper in papers[:5]:  # 分析前5篇
            if hasattr(paper, 'abstract') and paper.abstract:
                # 简单的关键句子提取
                sentences = paper.abstract.split('. ')
                for sentence in sentences:
                    if any(keyword in sentence.lower() for keyword in
                          ['significant', 'result', 'found', 'demonstrate', 'show', 'conclude']):
                        if len(sentence.strip()) > 50:  # 确保句子有意义
                            findings.append(sentence.strip())
                            break

        return findings[:5]

    def _identify_methodological_trends(self, papers: List[LiteratureItem]) -> List[str]:
        """从文献中识别方法学趋势"""
        trends = set()

        methodology_keywords = {
            'deep learning': '深度学习应用',
            'machine learning': '机器学习方法',
            'radiomics': '影像组学分析',
            'multicenter': '多中心研究',
            'prospective': '前瞻性研究',
            'retrospective': '回顾性研究',
            'validation': '验证研究',
            'ai': '人工智能技术',
            'neural network': '神经网络模型'
        }

        for paper in papers:
            text = f"{paper.title} {getattr(paper, 'abstract', '')}".lower()
            for keyword, trend in methodology_keywords.items():
                if keyword in text:
                    trends.add(trend)

        return list(trends)[:5]

    def _identify_research_gaps(self, papers: List[LiteratureItem], research_topic: str) -> List[str]:
        """从文献中识别研究空白"""
        gaps = []

        # 基于文献内容分析
        all_texts = ' '.join([f"{paper.title} {getattr(paper, 'abstract', '')}" for paper in papers]).lower()

        # 检查常见的研究空白
        if 'prospective' not in all_texts:
            gaps.append("缺乏前瞻性研究设计")

        if 'multicenter' not in all_texts:
            gaps.append("缺乏多中心验证研究")

        if 'validation' not in all_texts:
            gaps.append("缺乏独立验证队列")

        if 'deep learning' not in all_texts and 'ai' not in all_texts:
            gaps.append("缺乏先进AI技术应用")

        if 'clinical' not in all_texts:
            gaps.append("缺乏临床应用验证")

        # 如果文献数量很少，添加相应提示
        if len(papers) < 3:
            gaps.append("相关文献较少，可能存在研究空白")

        return gaps[:5]

    def _extract_keywords(self, papers: List[LiteratureItem]) -> List[str]:
        """从文献中提取关键词"""
        keywords = set()

        for paper in papers:
            # 从标题和摘要中提取
            text = f"{paper.title} {getattr(paper, 'abstract', '')}".lower()
            words = text.split()

            # 简单的关键词提取
            for word in words:
                if len(word) > 4 and word.isalpha() and word not in [
                    'study', 'research', 'analysis', 'method', 'result', 'conclusion'
                ]:
                    keywords.add(word)

        return list(keywords)[:15]

    def _apply_filters_to_results(self, results: List[LiteratureItem], filters: Dict) -> List[LiteratureItem]:
        """应用过滤器到结果"""
        filtered_results = results

        # 研究类型过滤
        if 'study_type' in filters and filters['study_type']:
            filtered_results = [r for r in filtered_results if r.study_type == filters['study_type']]

        # 证据等级过滤
        if 'evidence_level' in filters and filters['evidence_level']:
            filtered_results = [r for r in filtered_results if r.evidence_level == filters['evidence_level']]

        # 亚专业领域过滤
        if 'specialty' in filters and filters['specialty']:
            filtered_results = [r for r in filtered_results if r.specialty_area == filters['specialty']]

        # 影响因子范围过滤
        if 'min_impact_factor' in filters:
            min_if = filters['min_impact_factor']
            filtered_results = [r for r in filtered_results if r.impact_factor >= min_if]

        # 开放获取过滤
        if 'open_access_only' in filters and filters['open_access_only']:
            filtered_results = [r for r in filtered_results if r.open_access]

        # 发表年份过滤
        if 'year_range' in filters:
            start_year, end_year = filters['year_range']
            filtered_results = [r for r in filtered_results
                              if r.pubdate and start_year <= int(r.pubdate[:4]) <= end_year]

        return filtered_results

    def _is_duplicate(self, item: LiteratureItem, existing_items: List[LiteratureItem]) -> bool:
        """检查是否为重复文献"""
        for existing in existing_items:
            # 基于标题相似度判断
            if self._title_similarity(item.title, existing.title) > 0.8:
                return True
            # 基于DOI判断
            if item.doi and existing.doi and item.doi == existing.doi:
                return True
        return False

    def _title_similarity(self, title1: str, title2: str) -> float:
        """计算标题相似度"""
        if not title1 or not title2:
            return 0.0

        # 简单的Jaccard相似度计算
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

# 全局检索实例
literature_search = MultiSourceLiteratureSearch(pubmed_api_key=None)  # 可以从环境变量配置API key

# 工具函数
def search_radiology_literature(query: str, max_results: int = 10, strategy: str = None, filters: Dict = None) -> Dict:
    """搜索放射学相关文献 - 主要接口函数（增强版）"""
    try:
        # 构建放射学相关的搜索查询
        radiology_query = f"({query}) AND (radiology OR imaging OR radiological OR \"medical imaging\" OR radiomics OR \"artificial intelligence\" OR \"machine learning\")"

        # 优先使用增强版PubMed引擎，支持策略和过滤
        results = literature_search.search(radiology_query, max_results,
                                        preferred_sources=['enhanced_pubmed'],
                                        strategy=strategy, filters=filters)

        # 转换为字典格式（包含所有增强的元数据）
        literature_data = []
        for item in results:
            # 构建PubMed URL（如果PMID存在）
            pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{item.pmid}/" if item.pmid and item.pmid.isdigit() else item.url

            # 处理作者信息
            authors_str = '; '.join(item.authors) if item.authors else '作者信息暂不可用'

            # 处理摘要信息
            abstract = item.abstract if item.abstract else '摘要暂不可用'
            if len(abstract) > 1000:  # 限制摘要长度
                abstract = abstract[:997] + '...'

            literature_data.append({
                'title': item.title if item.title else '标题暂不可用',
                'authors': authors_str,
                'abstract': abstract,
                'journal': item.journal if item.journal else '期刊信息暂不可用',
                'pubdate': item.pubdate if item.pubdate else '发表日期暂不可用',
                'doi': item.doi if item.doi else '',
                'pmid': item.pmid if item.pmid else '',
                'url': item.url if item.url else '',
                'pubmed_url': pubmed_url,  # 添加pubmed_url字段以兼容前端组件
                'relevance_score': round(item.relevance_score, 2),
                'source': item.source,
                # 新增元数据字段
                'impact_factor': round(item.impact_factor, 2) if item.impact_factor else 0.0,
                'citation_count': item.citation_count if item.citation_count else 0,
                'study_type': item.study_type if item.study_type else 'original_research',
                'evidence_level': item.evidence_level if item.evidence_level else 'III',
                'specialty_area': item.specialty_area if item.specialty_area else 'general_radiology',
                'mesh_terms': item.mesh_terms if item.mesh_terms else [],
                'keywords': item.keywords if item.keywords else [],
                'open_access': item.open_access if item.open_access else False,
                'publication_type': item.publication_type if item.publication_type else ''
            })

        # 生成搜索总结
        source_stats = {}
        for item in results:
            source = item.source
            source_stats[source] = source_stats.get(source, 0) + 1

        summary_parts = [f"基于增强版PubMed eUtility API，为您找到 {len(literature_data)} 篇高质量放射学文献"]
        if source_stats:
            summary_parts.append(f"（来源分布：{', '.join([f'{k}: {v}篇' for k, v in source_stats.items()])}）")

        return {
            'search_query': radiology_query,
            'total_results': len(literature_data),
            'recommended_papers': literature_data,
            'search_summary': ' '.join(summary_parts)
        }

    except Exception as e:
        logger.error(f"放射学文献搜索失败: {str(e)}")
        return {
            'search_query': query,
            'total_results': 0,
            'recommended_papers': [],
            'search_summary': '文献搜索失败，请稍后重试'
        }


def search_clinical_literature(query: str, max_results: int = 10) -> Dict:
    """搜索临床医学相关文献 - 扩展接口函数"""
    try:
        # 构建临床医学相关的搜索查询
        clinical_query = f"({query}) AND (clinical OR \"clinical trial\" OR \"cohort study\" OR \"case-control\" OR prognosis OR diagnosis)"

        # 优先使用增强版PubMed引擎
        results = literature_search.search(clinical_query, max_results, preferred_sources=['enhanced_pubmed'])

        # 转换为字典格式
        literature_data = []
        for item in results:
            pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{item.pmid}/" if item.pmid and item.pmid.isdigit() else item.url

            literature_data.append({
                'title': item.title if item.title else '标题暂不可用',
                'authors': '; '.join(item.authors) if item.authors else '作者信息暂不可用',
                'abstract': item.abstract if item.abstract else '摘要暂不可用',
                'journal': item.journal if item.journal else '期刊信息暂不可用',
                'pubdate': item.pubdate if item.pubdate else '发表日期暂不可用',
                'doi': item.doi if item.doi else '',
                'pmid': item.pmid if item.pmid else '',
                'url': item.url if item.url else '',
                'pubmed_url': pubmed_url,
                'relevance_score': round(item.relevance_score, 2),
                'source': item.source
            })

        return {
            'search_query': clinical_query,
            'total_results': len(literature_data),
            'recommended_papers': literature_data,
            'search_summary': f"基于增强版PubMed eUtility API，为您找到 {len(literature_data)} 篇临床医学相关文献"
        }

    except Exception as e:
        logger.error(f"临床医学文献搜索失败: {str(e)}")
        return {
            'search_query': query,
            'total_results': 0,
            'recommended_papers': [],
            'search_summary': '文献搜索失败，请稍后重试'
        }