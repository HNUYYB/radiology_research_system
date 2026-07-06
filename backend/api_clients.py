import logging
import os
import json
import re
import time
from config import Config
from debug_logger import debug_logger, LogLevel

logger = logging.getLogger(__name__)


class AnthropicClient:
    def __init__(self, api_key: str = None, provider: str = None, base_url: str = None, model: str = None):
        """
        参数化构造，不再依赖全局 Config。
        调用方传入用户自己的 api_key；provider/base_url/model 可从 Config.get_preset() 获取默认值。
        """
        from config import Config, DEFAULT_API_KEY, DEFAULT_PROVIDER
        self.api_key = api_key or DEFAULT_API_KEY
        self.provider = provider or DEFAULT_PROVIDER
        preset = Config.get_preset(self.provider)
        self.base_url = base_url or preset['base_url']
        self.model = model or preset['model']
        self.timeout = 600  # 10分钟超时，长文本生成需要更长时间
        self.max_retries = 5  # 连接断开时最多重试5次
        self.base_delay = 3  # 基础等待秒数

    def configure(self, api_key: str = None, provider: str = None, base_url: str = None, model: str = None):
        """动态重新配置（用于切换用户/提供商时复用同一个实例）"""
        from config import Config, DEFAULT_API_KEY, DEFAULT_PROVIDER
        if api_key is not None:
            self.api_key = api_key
        if provider is not None:
            self.provider = provider
        preset = Config.get_preset(self.provider)
        if base_url is not None:
            self.base_url = base_url
        else:
            self.base_url = preset['base_url']
        if model is not None:
            self.model = model
        else:
            self.model = preset['model']

    def _get_api_url(self):
        """根据 provider 返回正确的 API URL"""
        base = self.base_url.rstrip('/')
        if self.provider == 'longcat':
            return f"{base}/v1/messages"
        elif self.provider in ('deepseek', 'openai', 'gpt54'):
            return f"{base}/chat/completions"
        return f"{base}/v1/messages"

    def _build_payload(self, prompt, max_tokens, system_prompt=None):
        """根据 provider 构建请求体"""
        if self.provider == 'longcat':
            # Anthropic 格式
            if system_prompt is None:
                full_prompt = prompt
            else:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            return {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": full_prompt}],
                "temperature": 0.1,
            }
        else:
            # OpenAI / DeepSeek 格式
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            return {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": 0.1,
            }

    def _extract_response_text(self, result):
        """从响应 JSON 中提取文本"""
        if self.provider == 'longcat':
            return result.get("content", [{}])[0].get("text", "").strip()
        else:
            return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    def _call_openai_sdk(self, messages: list, max_tokens: int, temperature: float = 0.1) -> str:
        """使用 OpenAI Python SDK 调用 OpenAI 兼容 API（DeepSeek / GPT-54 等）"""
        from openai import OpenAI
        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def _call_anthropic_native(self, payload: dict) -> str:
        """使用 requests 调用 Anthropic 原生格式 API（LongCat）"""
        import requests
        api_url = self._get_api_url()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "anthropic-version": "2023-06-01",
        }
        response = requests.post(api_url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        return result.get("content", [{}])[0].get("text", "").strip()

    def _clean_response(self, ai_response: str) -> str:
        """清理markdown代码块标记"""
        if ai_response.startswith('```json'):
            ai_response = ai_response[7:]
        if ai_response.startswith('```'):
            ai_response = ai_response[3:]
        if ai_response.endswith('```'):
            ai_response = ai_response[:-3]
        return ai_response.strip()

    def _call_api_with_retry(self, payload: dict = None, prompt: str = "", max_tokens: int = None,
                              system_prompt: str = None, temperature: float = 0.1) -> str:
        """带指数退避重试的API调用（支持 LongCat / DeepSeek / OpenAI）"""
        from config import Config

        if payload is None:
            payload = self._build_payload(prompt, max_tokens or 1000, system_prompt)

        # 构建 messages（供 OpenAI SDK 使用）
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            preset = Config.get_preset(self.provider)
            provider_label = preset.get('label', self.provider)
        except Exception:
            provider_label = self.provider
        debug_logger.api_call(
            provider_label, 'POST', self.base_url,
            headers={'Authorization': 'Bearer ***'},
            payload={'model': self.model, 'max_tokens': max_tokens}
        )
        if prompt:
            debug_logger.prompt_sent(self.model, prompt, max_tokens)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                # 根据提供商选择调用方式
                if self.provider == 'longcat':
                    ai_response = self._call_anthropic_native(payload)
                else:
                    ai_response = self._call_openai_sdk(messages, max_tokens or 1000, temperature)

                ai_response = self._clean_response(ai_response)

                debug_logger.api_response(
                    provider_label, 200,
                    {'response_length': len(ai_response), 'model': self.model}
                )
                debug_logger.ai_response_received(self.model, ai_response)

                return ai_response

            except Exception as e:
                last_error = e
                # 检查是否是可重试的错误
                error_str = str(e).lower()
                is_retryable = any(kw in error_str for kw in [
                    '429', 'rate limit', '500', '502', '503', '504',
                    'timeout', 'connection', 'connectionerror', 'remotedisconnected',
                    'server disconnected', 'tryagain'
                ])
                if is_retryable:
                    wait = self.base_delay * (2 ** attempt)
                    logger.warning(f"API错误({type(e).__name__})，第{attempt+1}次重试，等待{wait:.1f}秒... 错误: {str(e)[:100]}")
                    print(f"[API Retry] {type(e).__name__}: {str(e)[:80]} — 等待 {wait:.1f}s (第{attempt+1}/{self.max_retries}次)")
                    time.sleep(wait)
                    continue
                raise

        raise Exception(f"API调用失败，已重试{self.max_retries}次。最后错误: {last_error}")

    def call_longcat_api(self, prompt: str, max_tokens: int = 1000, system_prompt: str = None) -> str:
        """调用当前激活的 LLM API

        Args:
            prompt: 用户提示词
            max_tokens: 最大生成长度
            system_prompt: 自定义系统提示词。为None时使用默认研究方案生成提示词。
        """
        if system_prompt is None:
            system_prompt = """
你是一名放射学科研专家。
请根据学生画像和需求，生成一份规范、可开题的研究方案，
并且**必须严格按照下面的 JSON 格式输出，只返回 JSON，不要额外文字**。

**重要要求：**
1. 所有字段值必须是**纯文本字符串**，不能是数组、对象或嵌套结构
2. 如果内容包含列表，请用换行符或分号分隔，转换为文本格式
3. 只返回JSON，不要任何额外文字、解释或格式化标记
4. 确保JSON格式有效，可以直接被json.loads()解析

输出字段如下：
{
  "title": "研究题目（简洁明确的标题）",
  "background": "研究背景（详细说明研究背景和意义）",
  "clinical_problem": "临床问题（描述需要解决的临床问题）",
  "scientific_problem": "科学问题（描述需要解决的科学问题）",
  "hypothesis": "研究假设（明确的研究假设）",
  "objectives": "研究目标（主要研究目标和次要目标，用分号或换行分隔）",
  "study_design": "研究设计（详细的研究设计方案）",
  "subjects_criteria": "纳排标准（纳入和排除标准，用分号或换行分隔）",
  "variables_endpoints": "变量与终点（研究变量和终点指标，用分号或换行分隔）",
  "statistical_analysis": "统计分析（统计分析方法）",
  "innovation": "创新点（研究的创新之处，用分号或换行分隔）",
  "risks_alternatives": "风险与备选方案（研究风险和应对方案，用分号或换行分隔）",
  "timeline": "研究时间表（研究时间安排，用分号或换行分隔）"
}
"""
            full_prompt = f"""{system_prompt}

用户输入：{prompt}

请严格按照上述JSON格式返回结果。所有字段值都必须是纯文本字符串，不要使用数组或对象。不要添加任何额外文字、解释或格式化标记。只返回可以被json.loads()直接解析的纯JSON字符串。"""
        else:
            full_prompt = prompt

        return self._call_api_with_retry(
            prompt=full_prompt,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )

    def call_tech_solution_api(self, prompt: str, max_tokens: int = 200) -> str:
        """调用当前激活的 LLM API 生成技术方案"""
        tech_system_prompt = """
你是一名医学影像AI技术专家。请提供创新的技术解决方案。
要求：
1. 返回纯文本，不要使用JSON格式
2. 提供具体、可行的技术创新思路
3. 避免套路化表述
4. 字数控制在100-200字内
"""

        return self._call_api_with_retry(
            prompt=prompt,
            max_tokens=max_tokens,
            system_prompt=tech_system_prompt,
            temperature=0.7,
        )


class PubMedClient:
    """PubMed API客户端"""

    def __init__(self):
        self.api_key = Config.PUBMED_API_KEY
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        self.rate_limit = 3
        self.last_request_time = 0
        import time
        import requests
        self.time = time
        self.requests = requests

    def _rate_limit(self):
        current_time = self.time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < 1.0 / self.rate_limit:
            self.time.sleep((1.0 / self.rate_limit) - time_since_last)
        self.last_request_time = current_time

    def search_literature(self, query: str, max_results: int = 20):
        try:
            self._rate_limit()
            search_url = f"{self.base_url}esearch.fcgi"
            params = {
                'db': 'pubmed', 'term': query, 'retmax': max_results,
                'retmode': 'json', 'api_key': self.api_key
            }
            response = self.requests.get(search_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            id_list = data.get('esearchresult', {}).get('idlist', [])
            if not id_list:
                return []
            return self._fetch_details(id_list[:10])
        except Exception as e:
            logger.error(f"PubMed搜索失败: {str(e)}")
            raise

    def _fetch_details(self, id_list):
        try:
            self._rate_limit()
            fetch_url = f"{self.base_url}esummary.fcgi"
            params = {
                'db': 'pubmed', 'id': ','.join(id_list),
                'retmode': 'json', 'api_key': self.api_key
            }
            response = self.requests.get(fetch_url, params=params, timeout=30)
            response.raise_for_status()
            summary_data = response.json()
            abstract_results = self._fetch_abstracts(id_list)
            results = []
            for uid, article_data in summary_data.get('result', {}).items():
                if uid == 'uids':
                    continue
                abstract_info = abstract_results.get(uid, {})
                result = {
                    'pmid': uid,
                    'title': article_data.get('title', ''),
                    'authors': article_data.get('authors', []),
                    'source': article_data.get('source', ''),
                    'pubdate': article_data.get('pubdate', ''),
                    'abstract': abstract_info.get('abstract', ''),
                    'doi': abstract_info.get('doi', ''),
                    'uid': uid
                }
                results.append(result)
            return results
        except Exception as e:
            logger.error(f"获取文献详情失败: {str(e)}")
            raise

    def _fetch_abstracts(self, id_list):
        try:
            self._rate_limit()
            abstract_url = f"{self.base_url}efetch.fcgi"
            params = {
                'db': 'pubmed', 'id': ','.join(id_list),
                'retmode': 'xml', 'api_key': self.api_key
            }
            response = self.requests.get(abstract_url, params=params, timeout=30)
            response.raise_for_status()
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            abstracts = {}
            for article in root.findall('.//PubmedArticle'):
                pmid_elem = article.find('.//PMID')
                if pmid_elem is not None:
                    pmid = pmid_elem.text
                    abstract_elem = article.find('.//Abstract/AbstractText')
                    abstract_text = abstract_elem.text if abstract_elem is not None else ''
                    doi_elem = article.find('.//ArticleId[@IdType="doi"]')
                    doi = doi_elem.text if doi_elem is not None else ''
                    abstracts[pmid] = {'abstract': abstract_text or '', 'doi': doi}
            return abstracts
        except Exception as e:
            logger.error(f"获取摘要失败: {str(e)}")
            raise


class ArXivClient:
    """文献检索客户端（arXiv 替代源）

    数据源：
    1. CrossRef API — 本 IP 可正常访问，返回 DOI 文献
    2. OpenAlex API — 本 IP 可正常访问，开放学术图谱
    3. Semantic Scholar API — 备用（当前 IP 被限速）

    结果格式与 PubMed 统一，source 标记为 "arxiv"
    """

    CROSSREF_URL = "https://api.crossref.org/works"
    OPENALEX_URL = "https://api.openalex.org/works"
    SS_BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self):
        import requests as _requests
        self._session = _requests.Session()
        self._session.headers.update({
            "User-Agent": "RadiologyResearchSystem/1.0 (mailto:79047879@qq.com)",
        })

    def search(self, query: str, max_results: int = 10, sort_by: str = "relevance") -> list:
        """
        多源检索文献（优先 CrossRef → OpenAlex → Semantic Scholar）

        Args:
            query: 搜索关键词（英文）
            max_results: 最大返回数量
            sort_by: relevance / year

        Returns:
            list[dict]: 文献列表，与 PubMed 格式统一，source 标记为 "arxiv"
        """
        import time as _time

        # 1. 尝试 CrossRef
        papers = self._search_crossref(query, max_results, sort_by)
        if papers:
            logger.info(f"  [arXiv/CrossRef] 检索完成: 返回 {len(papers)} 篇")
            return papers

        _time.sleep(1)

        # 2. 尝试 OpenAlex
        papers = self._search_openalex(query, max_results, sort_by)
        if papers:
            logger.info(f"  [arXiv/OpenAlex] 检索完成: 返回 {len(papers)} 篇")
            return papers

        _time.sleep(1)

        # 3. 尝试 Semantic Scholar（备用）
        papers = self._search_semantic_scholar(query, max_results, sort_by)
        if papers:
            logger.info(f"  [arXiv/SS] 检索完成: 返回 {len(papers)} 篇")
            return papers

        logger.warning(f"  [arXiv] 所有数据源均未返回结果")
        return []

    def _search_crossref(self, query: str, max_results: int, sort_by: str) -> list:
        """CrossRef API 检索"""
        import time as _time
        sort_param = "score" if sort_by == "relevance" else "published"
        params = {
            "query": query,
            "rows": min(max_results, 20),
            "sort": sort_param,
            "order": "desc",
            "select": "DOI,title,author,abstract,container-title,published-print,subject,link",
        }
        for attempt in range(3):
            try:
                resp = self._session.get(self.CROSSREF_URL, params=params, timeout=20)
                if resp.status_code == 429:
                    wait = 3 * (attempt + 1)
                    _time.sleep(wait)
                    continue
                resp.raise_for_status()
                items = resp.json().get("message", {}).get("items", [])
                papers = [self._normalize_crossref_paper(i) for i in items]
                papers = [p for p in papers if p]
                return papers
            except Exception as e:
                if attempt < 2:
                    _time.sleep(2 * (attempt + 1))
                    continue
                logger.error(f"  [arXiv/CrossRef] 失败: {e}")
                return []
        return []

    def _search_openalex(self, query: str, max_results: int, sort_by: str) -> list:
        """OpenAlex API 检索"""
        import time as _time
        sort_param = "relevance_score:desc" if sort_by == "relevance" else "publication_date:desc"
        params = {
            "search": query,
            "per-page": min(max_results, 20),
            "sort": sort_param,
            "select": "id,title,authorships,abstract_inverted_index,primary_location,publication_year,doi",
        }
        for attempt in range(3):
            try:
                resp = self._session.get(self.OPENALEX_URL, params=params, timeout=20)
                if resp.status_code == 429:
                    wait = 3 * (attempt + 1)
                    _time.sleep(wait)
                    continue
                resp.raise_for_status()
                items = resp.json().get("results", [])
                papers = [self._normalize_openalex_paper(i) for i in items]
                papers = [p for p in papers if p]
                return papers
            except Exception as e:
                if attempt < 2:
                    _time.sleep(2 * (attempt + 1))
                    continue
                logger.error(f"  [arXiv/OpenAlex] 失败: {e}")
                return []
        return []

    def _search_semantic_scholar(self, query: str, max_results: int, sort_by: str) -> list:
        """Semantic Scholar API 检索（备用）"""
        import time as _time
        fields = "title,authors,year,abstract,externalIds,openAccessPdf"
        params = {
            "query": query,
            "limit": max_results,
            "fields": fields,
        }
        if sort_by in ("year", "submittedDate", "lastUpdatedDate"):
            params["sort"] = "year:desc"
        for attempt in range(3):
            try:
                resp = self._session.get(
                    f"{self.SS_BASE_URL}/paper/search",
                    params=params, timeout=20
                )
                if resp.status_code == 429:
                    wait = 5 * (attempt + 1)
                    _time.sleep(wait)
                    continue
                resp.raise_for_status()
                papers_raw = resp.json().get("data", [])
                papers = [self._normalize_ss_paper(p) for p in papers_raw]
                papers = [p for p in papers if p]
                return papers
            except Exception as e:
                if attempt < 2:
                    _time.sleep(3 * (attempt + 1))
                    continue
                logger.error(f"  [arXiv/SS] 失败: {e}")
                return []
        return []

    @staticmethod
    def _normalize_crossref_paper(item: dict):
        """将 CrossRef 结果标准化为统一格式"""
        title_list = item.get("title") or []
        title = title_list[0].strip() if title_list else ""
        if not title:
            return None

        # 作者
        authors_raw = item.get("author") or []
        authors = []
        for a in authors_raw:
            given = a.get("given", "")
            family = a.get("family", "")
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)

        # 日期
        published = item.get("published-print") or item.get("published") or {}
        date_parts = published.get("date-parts", [[]])
        year = date_parts[0][0] if date_parts and date_parts[0] else ""
        pubdate = f"{year}-01-01" if year else ""

        # 期刊
        container = item.get("container-title") or []
        journal = container[0] if container else ""

        # DOI & URL
        doi = item.get("DOI", "")
        url = f"https://doi.org/{doi}" if doi else ""

        # 摘要（CrossRef 通常返回 HTML 摘要）
        abstract = item.get("abstract", "") or ""
        # 简单去除 HTML 标签
        import re
        abstract = re.sub(r'<[^>]+>', '', abstract).strip()

        return {
            "pmid": "",
            "arxiv_id": "",
            "title": title,
            "authors": authors[:5],
            "abstract": abstract,
            "journal": journal,
            "pubdate": pubdate,
            "doi": doi,
            "pubmed_url": url,
            "url": url,
            "article_type": "journal_article",
            "categories": item.get("subject", []),
            "mesh_terms": [],
            "keywords": [],
            "source": "arxiv",
        }

    @staticmethod
    def _normalize_openalex_paper(item: dict):
        """将 OpenAlex 结果标准化为统一格式"""
        title = (item.get("title") or "").strip()
        if not title:
            return None

        # 作者
        authors_raw = item.get("authorships") or []
        authors = []
        for a in authors_raw:
            name = a.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        # 日期
        year = item.get("publication_year", "")
        pubdate = f"{year}-01-01" if year else ""

        # 期刊/来源
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        journal = source.get("display_name", "")

        # DOI & URL
        doi = item.get("doi", "") or ""
        url = doi if doi.startswith("http") else (f"https://doi.org/{doi}" if doi else "")

        # 摘要（OpenAlex 使用 inverted index 格式）
        abstract_index = item.get("abstract_inverted_index") or {}
        abstract = ""
        if abstract_index:
            # 从 inverted index 还原文本
            word_positions = []
            for word, positions in abstract_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            abstract = " ".join(w for _, w in sorted(word_positions))

        return {
            "pmid": "",
            "arxiv_id": "",
            "title": title,
            "authors": authors[:5],
            "abstract": abstract,
            "journal": journal,
            "pubdate": pubdate,
            "doi": doi,
            "pubmed_url": url,
            "url": url,
            "article_type": "journal_article",
            "categories": [],
            "mesh_terms": [],
            "keywords": [],
            "source": "arxiv",
        }

    @staticmethod
    def _normalize_ss_paper(p: dict):
        """将 Semantic Scholar 结果标准化为统一格式"""
        title = (p.get("title") or "").strip()
        if not title:
            return None

        external_ids = p.get("externalIds") or {}
        arxiv_id = external_ids.get("ArXiv", "")
        if arxiv_id:
            arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
        else:
            oa_pdf = p.get("openAccessPdf") or {}
            arxiv_url = oa_pdf.get("url", "")

        year = p.get("year", "")
        pubdate = f"{year}-01-01" if year else ""

        authors_raw = p.get("authors") or []
        authors = [a.get("name", "") for a in authors_raw if a.get("name")]

        abstract = (p.get("abstract") or "").strip().replace("\n", " ")
        doi = external_ids.get("DOI", "")

        return {
            "pmid": "",
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors[:5],
            "abstract": abstract,
            "journal": "arXiv",
            "pubdate": pubdate,
            "doi": doi,
            "pubmed_url": arxiv_url,
            "url": arxiv_url,
            "article_type": "preprint",
            "categories": [],
            "mesh_terms": [],
            "keywords": [],
            "source": "arxiv",
        }


from literature_search import search_radiology_literature, literature_search

anthropic_client = AnthropicClient()
pubmed_client = PubMedClient()
arxiv_client = ArXivClient()
