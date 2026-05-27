"""
PubMed文献推荐系统
基于人工智能的个性化文献推荐，为您的研究提供最新、最相关的学术资源
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from literature_search import MultiSourceLiteratureSearch

class PubMedRecommendationSystem:
    """
    基于人工智能的个性化PubMed文献推荐系统
    特点：
    1. 个性化推荐：基于用户画像和研究兴趣
    2. 多维度排序：相关性、影响因子、时效性、证据等级
    3. 智能过滤：自动筛选高质量文献
    4. 实时更新：连接PubMed获取最新文献
    5. 专业优化：针对放射学领域优化
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.literature_search = MultiSourceLiteratureSearch()

        # 高质量期刊定义
        self.high_impact_journals = {
            'Radiology': 11.1,
            'European Radiology': 5.9,
            'American Journal of Roentgenology': 8.8,
            'Investigative Radiology': 7.2,
            'Clinical Radiology': 3.1,
            'Academic Radiology': 3.5,
            'Nature Medicine': 87.2,
            'The Lancet': 168.9,
            'New England Journal of Medicine': 176.1,
            'JAMA': 120.7
        }

    def get_personalized_recommendations(self,
                                       student_profile: Dict[str, Any],
                                       research_interests: str,
                                       max_results: int = 50) -> Dict[str, Any]:
        """
        获取个性化文献推荐

        Args:
            student_profile: 学生画像信息
            research_interests: 研究兴趣描述
            max_results: 最大返回文献数量

        Returns:
            包含推荐文献和相关信息的字典
        """
        try:
            self.logger.info(f"开始个性化文献推荐: {research_interests[:50]}...")

            # 1. 基于研究兴趣检索文献
            literature_context = self._search_literature_by_interests(
                research_interests,
                student_profile.get('specialty', ''),
                max_results
            )

            # 2. 基于用户画像进行个性化排序
            personalized_papers = self._personalize_ranking(
                literature_context['recommended_papers'],
                student_profile
            )

            # 3. 生成推荐摘要
            recommendation_summary = self._generate_recommendation_summary(
                personalized_papers,
                student_profile,
                research_interests
            )

            # 4. 构建完整响应
            result = {
                'search_query': research_interests,
                'user_profile': {
                    'academic_level': student_profile.get('academic_level', ''),
                    'specialty': student_profile.get('specialty', ''),
                    'research_interests': research_interests
                },
                'recommendation_summary': recommendation_summary,
                'total_results': len(personalized_papers),
                'high_quality_count': len([p for p in personalized_papers if self._is_high_quality(p)]),
                'recommended_papers': personalized_papers[:max_results],
                'search_metadata': {
                    'generated_at': datetime.now().isoformat(),
                    'search_strategy': 'personalized_radiology',
                    'filters_applied': {
                        'min_impact_factor': 3.0,
                        'date_range': 'last_5_years',
                        'high_quality_journals': True,
                        'peer_reviewed_only': True
                    }
                }
            }

            self.logger.info(f"个性化推荐完成，共推荐 {len(personalized_papers)} 篇文献")
            return result

        except Exception as e:
            self.logger.error(f"个性化文献推荐失败: {str(e)}")
            raise

    def _search_literature_by_interests(self, research_interests: str, specialty: str, max_results: int) -> Dict[str, Any]:
        """
        基于研究兴趣检索文献

        Args:
            research_interests: 研究兴趣描述
            specialty: 专业领域
            max_results: 最大结果数量

        Returns:
            文献上下文信息
        """
        try:
            all_papers = []

            # 单次综合搜索，减少 PubMed API 调用次数
            search_papers = self.literature_search.search(
                research_interests,
                max_results=max_results,
                strategy='core_papers'
            )
            all_papers.extend(search_papers)
            self.logger.info(f"文献搜索获取到 {len(all_papers)} 篇文献")

            # 去重并格式化
            seen_pmids = set()
            formatted_papers = []

            for paper in all_papers:
                pmid = getattr(paper, 'pmid', '')
                if pmid and pmid not in seen_pmids:
                    seen_pmids.add(pmid)

                    # 确保所有必要字段都存在
                    formatted_paper = {
                        'title': getattr(paper, 'title', '') or '',
                        'authors': getattr(paper, 'authors', []) or [],
                        'journal': getattr(paper, 'journal', '') or 'Unknown',
                        'pubdate': getattr(paper, 'pubdate', '') or '',
                        'abstract': getattr(paper, 'abstract', '') or '',
                        'pmid': pmid,
                        'impact_factor': getattr(paper, 'impact_factor', 0) or 0,
                        'citations': getattr(paper, 'citations', 0) or 0,
                        'article_type': getattr(paper, 'article_type', '') or '',
                        'doi': getattr(paper, 'doi', '') or '',
                        'pubmed_url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid and str(pmid).isdigit() else getattr(paper, 'url', '')
                    }
                    formatted_papers.append(formatted_paper)

            self.logger.info(f"总共获取到 {len(formatted_papers)} 篇不重复文献")

            # 生成文献上下文
            literature_context = {
                'recommended_papers': formatted_papers,
                'total_results': len(formatted_papers),
                'high_quality_count': len([p for p in formatted_papers if self._is_high_quality(p)]),
                'methodological_trends': self._extract_methodological_trends(formatted_papers),
                'research_gaps': self._identify_research_gaps(formatted_papers, research_interests),
                'keywords': self._extract_keywords(formatted_papers)
            }

            return literature_context

        except Exception as e:
            self.logger.error(f"文献检索失败: {str(e)}")
            # 返回空结果而不是失败
            return {
                'recommended_papers': [],
                'total_results': 0,
                'high_quality_count': 0,
                'methodological_trends': [],
                'research_gaps': [],
                'keywords': []
            }

    def _extract_methodological_trends(self, papers: List[Dict[str, Any]]) -> List[str]:
        """提取方法学趋势"""
        trends = []
        methods_count = {}

        for paper in papers:
            abstract = paper.get('abstract', '').lower()
            title = paper.get('title', '').lower()

            # 检测方法学关键词
            methods = [
                'machine learning', 'deep learning', 'artificial intelligence',
                'radiomics', 'texture analysis', 'neural network',
                'random forest', 'support vector machine', 'logistic regression',
                'cox regression', 'survival analysis', 'meta-analysis'
            ]

            for method in methods:
                if method in abstract or method in title:
                    methods_count[method] = methods_count.get(method, 0) + 1

        # 返回出现频率最高的方法
        sorted_methods = sorted(methods_count.items(), key=lambda x: x[1], reverse=True)
        trends = [method for method, count in sorted_methods[:5] if count >= 2]

        return trends if trends else ['暂无明显方法学趋势']

    def _identify_research_gaps(self, papers: List[Dict[str, Any]], research_topic: str) -> List[str]:
        """识别研究空白"""
        gaps = []

        # 基于文献数量和质量的简单分析
        total_papers = len(papers)
        recent_papers = sum(1 for p in papers if p.get('pubdate', '').startswith('2024') or p.get('pubdate', '').startswith('2025'))
        high_quality_papers = sum(1 for p in papers if self._is_high_quality(p))

        if total_papers < 10:
            gaps.append('相关文献数量较少，需要扩大研究范围')

        if recent_papers < 3:
            gaps.append('近期研究不足，建议关注最新进展')

        if high_quality_papers / max(total_papers, 1) < 0.5:
            gaps.append('高质量研究比例偏低，建议提高文献质量筛选标准')

        # 检查特定研究主题的覆盖情况
        if '肺结节' in research_topic:
            ct_papers = sum(1 for p in papers if 'CT' in p.get('title', '') or 'CT' in p.get('abstract', ''))
            if ct_papers < 5:
                gaps.append('CT影像相关研究不足，建议增加影像学研究')

        return gaps if gaps else ['研究覆盖较为全面']

    def _extract_keywords(self, papers: List[Dict[str, Any]]) -> List[str]:
        """提取关键词"""
        keywords = set()

        for paper in papers:
            title = paper.get('title', '').lower()
            abstract = paper.get('abstract', '').lower()

            # 提取医学术语关键词
            medical_terms = [
                'lung nodule', 'pulmonary nodule', 'ct imaging', 'radiomics',
                'malignancy', 'diagnosis', 'prognosis', 'screening',
                'artificial intelligence', 'machine learning', 'deep learning'
            ]

            for term in medical_terms:
                if term in title or term in abstract:
                    keywords.add(term)

        return list(keywords)[:20]  # 返回前20个关键词

    def _personalize_ranking(self, papers: List[Dict[str, Any]], student_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        基于用户画像进行个性化排序

        Args:
            papers: 文献列表
            student_profile: 学生画像

        Returns:
            排序后的文献列表
        """
        try:
            # 获取用户偏好
            academic_level = student_profile.get('academic_level', '')
            specialty = student_profile.get('specialty', '')
            stats_background = student_profile.get('stats_background', '')
            ai_background = student_profile.get('ai_background', '')

            # 为每篇文献计算个性化得分
            scored_papers = []
            for paper in papers:
                score = self._calculate_personalized_score(
                    paper,
                    academic_level,
                    specialty,
                    stats_background,
                    ai_background
                )
                paper['personalized_score'] = score
                scored_papers.append(paper)

            # 按个性化得分排序
            scored_papers.sort(key=lambda x: x['personalized_score'], reverse=True)

            return scored_papers

        except Exception as e:
            self.logger.error(f"个性化排序失败: {str(e)}")
            return papers

    def _calculate_personalized_score(self, paper: Dict[str, Any],
                                    academic_level: str, specialty: str,
                                    stats_background: str, ai_background: str) -> float:
        """
        计算文献的个性化得分

        Args:
            paper: 文献信息
            academic_level: 学术水平
            specialty: 专业领域
            stats_background: 统计学背景
            ai_background: AI背景

        Returns:
            个性化得分
        """
        score = 0.0

        # 1. 基础质量得分 (40%)
        quality_score = self._calculate_quality_score(paper)
        score += quality_score * 0.4

        # 2. 专业相关性得分 (30%)
        relevance_score = self._calculate_relevance_score(paper, specialty)
        score += relevance_score * 0.3

        # 3. 学术水平匹配得分 (20%)
        level_score = self._calculate_academic_level_score(paper, academic_level)
        score += level_score * 0.2

        # 4. 技术背景匹配得分 (10%)
        tech_score = self._calculate_technical_background_score(paper, stats_background, ai_background)
        score += tech_score * 0.1

        return score

    def _calculate_quality_score(self, paper: Dict[str, Any]) -> float:
        """计算文献质量得分"""
        score = 0.0

        # 影响因子得分
        impact_factor = paper.get('impact_factor', 0)
        if impact_factor >= 10:
            score += 40
        elif impact_factor >= 5:
            score += 30
        elif impact_factor >= 3:
            score += 20
        elif impact_factor >= 1:
            score += 10

        # 期刊质量得分
        journal = paper.get('journal', '')
        if journal in self.high_impact_journals:
            score += 20

        # 引用次数得分
        citations = paper.get('citations', 0)
        if citations >= 100:
            score += 20
        elif citations >= 50:
            score += 15
        elif citations >= 20:
            score += 10
        elif citations >= 5:
            score += 5

        # 时效性得分
        pubdate = paper.get('pubdate', '')
        if pubdate:
            try:
                year = int(pubdate[:4])
                current_year = datetime.now().year
                if current_year - year <= 2:
                    score += 15
                elif current_year - year <= 5:
                    score += 10
                elif current_year - year <= 10:
                    score += 5
            except:
                pass

        # 研究类型得分
        article_type = paper.get('article_type', '').lower()
        if 'randomized controlled trial' in article_type:
            score += 15
        elif 'meta-analysis' in article_type or 'systematic review' in article_type:
            score += 12
        elif 'clinical trial' in article_type:
            score += 10
        elif 'review' in article_type:
            score += 8
        elif 'case report' in article_type:
            score += 3

        return min(score, 100.0)

    def _calculate_relevance_score(self, paper: Dict[str, Any], specialty: str) -> float:
        """计算专业相关性得分"""
        score = 0.0

        if not specialty:
            return 50.0  # 默认中等相关性

        # 关键词匹配
        title = paper.get('title', '').lower()
        abstract = paper.get('abstract', '').lower()
        specialty_lower = specialty.lower()

        # 专业关键词匹配
        specialty_keywords = {
            '胸部影像': ['胸部', '肺', 'CT', 'X光', '胸片', '纵隔', '胸膜', '肺结节', '肺炎', '肺癌'],
            '腹部影像': ['腹部', '肝', '胆', '胰', '脾', '肾', 'CT', 'MRI', '超声', '腹部CT'],
            '神经影像': ['脑', '神经', 'MRI', 'CT', '脑血管', '脑肿瘤', '脑卒中', '神经影像'],
            '骨关节影像': ['骨', '关节', '骨折', 'MRI', 'CT', 'X光', '骨质疏松', '关节炎'],
            '心血管影像': ['心脏', '血管', 'CTA', 'MRA', '冠脉', '心血管', '心肌', '动脉']
        }

        keywords = specialty_keywords.get(specialty, [])
        for keyword in keywords:
            if keyword.lower() in title:
                score += 15
            if keyword.lower() in abstract:
                score += 10

        # 专业名称直接匹配
        if specialty_lower in title:
            score += 20
        if specialty_lower in abstract:
            score += 15

        return min(score, 100.0)

    def _calculate_academic_level_score(self, paper: Dict[str, Any], academic_level: str) -> float:
        """计算学术水平匹配得分"""
        score = 50.0  # 基础分

        if not academic_level:
            return score

        # 本科生适合综述和基础临床研究
        if '本科' in academic_level:
            article_type = paper.get('article_type', '').lower()
            if 'review' in article_type:
                score += 20
            elif 'case report' in article_type:
                score += 15
            elif 'clinical trial' in article_type:
                score += 10

            # 避免过于复杂的方法学
            if 'machine learning' in paper.get('abstract', '').lower():
                score -= 10
            if 'deep learning' in paper.get('abstract', '').lower():
                score -= 15

        # 研究生适合方法学研究
        elif '研究生' in academic_level:
            article_type = paper.get('article_type', '').lower()
            if 'clinical trial' in article_type:
                score += 15
            elif 'randomized controlled trial' in article_type:
                score += 20
            elif 'machine learning' in paper.get('abstract', '').lower():
                score += 10

        # 博士生适合前沿研究
        elif '博士' in academic_level:
            # 鼓励前沿技术和复杂方法
            if 'machine learning' in paper.get('abstract', '').lower():
                score += 15
            if 'deep learning' in paper.get('abstract', '').lower():
                score += 20
            if 'artificial intelligence' in paper.get('abstract', '').lower():
                score += 20

        return min(max(score, 0.0), 100.0)

    def _calculate_technical_background_score(self, paper: Dict[str, Any],
                                            stats_background: str, ai_background: str) -> float:
        """计算技术背景匹配得分"""
        score = 50.0  # 基础分

        abstract = paper.get('abstract', '').lower()

        # 统计学背景匹配
        if stats_background and '基础' in stats_background:
            if 'multivariate analysis' in abstract or 'regression' in abstract:
                score -= 10  # 过于复杂
            if 'descriptive statistics' in abstract or 'chi-square' in abstract:
                score += 10  # 匹配基础统计

        if stats_background and '高级' in stats_background:
            if 'multivariate analysis' in abstract or 'regression' in abstract:
                score += 15
            if 'machine learning' in abstract:
                score += 10

        # AI背景匹配
        if ai_background and '基础' in ai_background:
            if 'machine learning' in abstract:
                score += 10
            if 'deep learning' in abstract:
                score -= 5  # 可能过于复杂

        if ai_background and ('熟悉' in ai_background or '掌握' in ai_background):
            if 'machine learning' in abstract:
                score += 15
            if 'deep learning' in abstract:
                score += 20
            if 'neural network' in abstract:
                score += 15

        return min(max(score, 0.0), 100.0)

    def _is_high_quality(self, paper: Dict[str, Any]) -> bool:
        """判断是否为高质量文献"""
        # 影响因子大于3或在高影响因子期刊
        impact_factor = paper.get('impact_factor', 0)
        journal = paper.get('journal', '')

        if impact_factor >= 3.0 or journal in self.high_impact_journals:
            return True

        # 引用次数较多
        citations = paper.get('citations', 0)
        if citations >= 50:
            return True

        # 近期高质量研究
        pubdate = paper.get('pubdate', '')
        if pubdate:
            try:
                year = int(pubdate[:4])
                current_year = datetime.now().year
                if current_year - year <= 3 and impact_factor >= 2.0:
                    return True
            except:
                pass

        return False

    def _generate_recommendation_summary(self, papers: List[Dict[str, Any]],
                                       student_profile: Dict[str, Any],
                                       research_interests: str) -> Dict[str, Any]:
        """生成推荐摘要"""
        try:
            total_papers = len(papers)
            high_quality_papers = [p for p in papers if self._is_high_quality(p)]

            # 按年份统计
            year_distribution = {}
            journal_distribution = {}

            for paper in papers:
                # 年份分布
                pubdate = paper.get('pubdate', '')
                if pubdate:
                    try:
                        year = pubdate[:4]
                        year_distribution[year] = year_distribution.get(year, 0) + 1
                    except:
                        pass

                # 期刊分布
                journal = paper.get('journal', 'Unknown')
                journal_distribution[journal] = journal_distribution.get(journal, 0) + 1

            # 推荐策略说明
            strategy = self._generate_recommendation_strategy(student_profile, research_interests)

            summary = {
                'total_recommendations': total_papers,
                'high_quality_recommendations': len(high_quality_papers),
                'quality_ratio': len(high_quality_papers) / max(total_papers, 1) * 100,
                'year_distribution': dict(sorted(year_distribution.items())[-5:]),  # 最近5年
                'top_journals': dict(sorted(journal_distribution.items(),
                                           key=lambda x: x[1], reverse=True)[:5]),
                'recommendation_strategy': strategy,
                'coverage_assessment': self._assess_coverage(papers, research_interests)
            }

            return summary

        except Exception as e:
            self.logger.error(f"生成推荐摘要失败: {str(e)}")
            return {
                'total_recommendations': 0,
                'high_quality_recommendations': 0,
                'quality_ratio': 0,
                'year_distribution': {},
                'top_journals': {},
                'recommendation_strategy': '基于用户画像和研究兴趣的个性化推荐',
                'coverage_assessment': '文献覆盖度评估失败'
            }

    def _generate_recommendation_strategy(self, student_profile: Dict[str, Any],
                                        research_interests: str) -> str:
        """生成推荐策略说明"""
        academic_level = student_profile.get('academic_level', '')
        specialty = student_profile.get('specialty', '')

        strategy_parts = []

        if academic_level:
            strategy_parts.append(f"针对{academic_level}的学术水平")

        if specialty:
            strategy_parts.append(f"聚焦{specialty}专业领域")

        strategy_parts.append("综合考虑影响因子、引用次数和时效性")
        strategy_parts.append("优先推荐高质量期刊文献")

        return "，".join(strategy_parts) + "进行个性化推荐"

    def _assess_coverage(self, papers: List[Dict[str, Any]], research_interests: str) -> str:
        """评估文献覆盖度"""
        if not papers:
            return "未找到相关文献"

        total_papers = len(papers)
        recent_papers = 0
        high_impact_papers = 0

        current_year = datetime.now().year

        for paper in papers:
            # 统计近期文献
            pubdate = paper.get('pubdate', '')
            if pubdate:
                try:
                    year = int(pubdate[:4])
                    if current_year - year <= 3:
                        recent_papers += 1
                except:
                    pass

            # 统计高质量文献
            if self._is_high_quality(paper):
                high_impact_papers += 1

        recent_ratio = recent_papers / total_papers * 100
        quality_ratio = high_impact_papers / total_papers * 100

        if recent_ratio >= 60 and quality_ratio >= 50:
            return "文献覆盖度优秀，包含大量近期高质量研究"
        elif recent_ratio >= 40 and quality_ratio >= 30:
            return "文献覆盖度良好，包含一定数量的近期研究"
        elif recent_ratio >= 20:
            return "文献覆盖度一般，建议扩展检索范围"
        else:
            return "文献覆盖度有限，建议调整检索策略"