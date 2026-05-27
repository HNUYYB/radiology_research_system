import React from 'react';
import { Card, Badge, Row, Col, Button, Table } from 'react-bootstrap';
import { BiBook, BiSearch, BiCheckCircle, BiBulb, BiBrain, BiBullseye, BiTestTube, BiLinkExternal } from 'react-icons/bi';
import PlanScoreBreakdown from './PlanScoreBreakdown';

function ModernEvidenceDisplay({ evidenceData, loading = false }) {
  if (loading) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">加载中...</span>
        </div>
        <p className="mt-3 text-muted">正在检索文献并生成证据综述...</p>
      </div>
    );
  }

  if (!evidenceData) {
    return (
      <Card className="border-0 shadow-sm">
        <Card.Body className="text-center py-5">
          <BiBook size={48} className="text-muted mb-3" />
          <h5 className="text-muted">暂无证据综述</h5>
          <p className="text-muted small">系统正在为您生成证据综述，请稍后再试</p>
        </Card.Body>
      </Card>
    );
  }

  // 解析数据（可能是 JSON 字符串或对象）
  let data;
  try {
    data = typeof evidenceData === 'string' ? JSON.parse(evidenceData) : evidenceData;
  } catch (e) {
    return (
      <Card className="border-0 shadow-sm">
        <Card.Body className="text-center py-5">
          <h5 className="text-danger">数据解析失败</h5>
          <p className="text-muted small">{String(evidenceData).slice(0, 200)}</p>
        </Card.Body>
      </Card>
    );
  }

  // 兼容新旧两种数据结构
  const literature = data.recommended_literature || data.literature_results || {};
  const papers = literature.recommended_papers || [];
  const evidenceSummary = data.evidence_summary || {};
  const keyFindings = evidenceSummary.key_findings || data.key_findings || [];
  const researchGaps = data.research_gaps || {};
  const methodologicalInsights = data.methodological_insights || [];
  const keywords = data.keywords || [];
  const searchStrategy = data.search_strategy || {};
  const sources = literature.sources || [];

  // 渲染研究空白
  const renderResearchGaps = () => {
    if (!researchGaps || Object.keys(researchGaps).length === 0) return null;

    const gapLabels = {
      methodological_gaps: '方法学空白',
      technical_gaps: '技术空白',
      clinical_gaps: '临床空白',
      research_gaps: '总体研究空白',
    };

    return (
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Header className="bg-gradient bg-warning text-dark border-0">
          <div className="d-flex align-items-center">
            <BiBullseye size={20} />
            <h5 className="mb-0 ms-2">🔍 研究空白</h5>
          </div>
        </Card.Header>
        <Card.Body>
          {Object.entries(researchGaps).map(([key, value]) => {
            const label = gapLabels[key] || key;
            const items = Array.isArray(value) ? value : (typeof value === 'string' && value.trim() ? [value] : []);
            if (items.length === 0) return null;
            return (
              <div key={key} className="mb-3">
                <h6 className="text-warning fw-bold">{label}</h6>
                <ul className="list-unstyled ms-3">
                  {items.map((item, i) => (
                    <li key={i} className="mb-1">• {item}</li>
                  ))}
                </ul>
              </div>
            );
          })}
        </Card.Body>
      </Card>
    );
  };

  // 渲染方法学洞察
  const renderMethodologicalInsights = () => {
    if (!methodologicalInsights || methodologicalInsights.length === 0) return null;

    return (
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Header className="bg-gradient bg-secondary text-white border-0">
          <div className="d-flex align-items-center">
            <BiTestTube size={20} />
            <h5 className="mb-0 ms-2">🧪 方法学洞察</h5>
          </div>
        </Card.Header>
        <Card.Body>
          {methodologicalInsights.map((insight, index) => (
            <div key={index} className="mb-3 p-3 bg-light rounded">
              <h6 className="fw-bold text-secondary">{insight.method || `方法 ${index + 1}`}</h6>
              <p className="mb-1 text-muted small">{insight.description || ''}</p>
              {insight.source_paper && (
                <p className="mb-1 text-muted small"><strong>来源:</strong> {insight.source_paper}</p>
              )}
              {insight.applicability && (
                <p className="mb-0 text-muted small"><strong>适用性:</strong> {insight.applicability}</p>
              )}
            </div>
          ))}
        </Card.Body>
      </Card>
    );
  };

  return (
    <div className="modern-evidence-display">
      {/* 概览卡片 */}
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Body className="bg-gradient bg-light">
          <div className="d-flex align-items-center mb-3">
            <BiBrain size={32} className="text-primary me-3" />
            <div>
              <h4 className="mb-1 fw-bold">🧠 智能证据综述</h4>
              <p className="text-muted mb-0 small">
                AI驱动的双源文献检索与分析系统
              </p>
            </div>
          </div>
          {/* 数据源标签 */}
          <div className="d-flex gap-2 flex-wrap">
            {sources.includes('pubmed') && <Badge bg="primary">PubMed</Badge>}
            {sources.includes('arxiv') && <Badge bg="dark">arXiv</Badge>}
            <Badge bg="info">{papers.length} 篇精选文献</Badge>
            {keywords.length > 0 && <Badge bg="secondary">{keywords.length} 个关键词</Badge>}
          </div>
        </Card.Body>
      </Card>

      {/* 搜索策略 */}
      {literature.search_query && (
        <Card className="border-0 shadow-sm mb-4 modern-card">
          <Card.Header className="bg-gradient bg-info text-white border-0">
            <div className="d-flex align-items-center">
              <BiSearch size={20} />
              <h5 className="mb-0 ms-2">🔍 检索策略</h5>
            </div>
          </Card.Header>
          <Card.Body>
            <p className="text-muted small mb-2">系统基于您的研究方向自动构建的专业检索式：</p>
            <div className="font-monospace bg-light p-2 rounded" style={{ fontSize: '0.8rem', wordBreak: 'break-all' }}>
              {literature.search_query}
            </div>
            {literature.search_summary && (
              <p className="mt-2 mb-0 text-muted small"><strong>📊</strong> {literature.search_summary}</p>
            )}
          </Card.Body>
        </Card>
      )}

      {/* 关键发现 */}
      {keyFindings && keyFindings.length > 0 && (
        <Card className="border-0 shadow-sm mb-4 modern-card">
          <Card.Header className="bg-gradient bg-info text-white border-0">
            <div className="d-flex align-items-center">
              <BiCheckCircle size={20} />
              <h5 className="mb-0 ms-2">💡 关键发现</h5>
            </div>
          </Card.Header>
          <Card.Body>
            <Row>
              {keyFindings.map((finding, index) => (
                <Col md={6} key={index} className="mb-3">
                  <div className="d-flex align-items-start">
                    <Badge bg="info" className="me-2 mt-1 flex-shrink-0">
                      {index + 1}
                    </Badge>
                    <span className="text-dark">{finding}</span>
                  </div>
                </Col>
              ))}
            </Row>
          </Card.Body>
        </Card>
      )}

      {/* 证据综述总览 */}
      {evidenceSummary.summary && (
        <Card className="border-0 shadow-sm mb-4 modern-card">
          <Card.Header className="bg-gradient bg-primary text-white border-0">
            <div className="d-flex align-items-center">
              <BiBook size={20} />
              <h5 className="mb-0 ms-2">📖 证据综述</h5>
            </div>
          </Card.Header>
          <Card.Body>
            <p className="mb-3" style={{ lineHeight: '1.8' }}>{evidenceSummary.summary}</p>
            {evidenceSummary.supporting_evidence && (
              <p className="mb-2"><strong>支撑程度:</strong> {evidenceSummary.supporting_evidence}</p>
            )}
            {evidenceSummary.contradictory_evidence && (
              <p className="mb-0"><strong>矛盾证据:</strong> {evidenceSummary.contradictory_evidence}</p>
            )}
          </Card.Body>
        </Card>
      )}

      {/* 研究空白 */}
      {renderResearchGaps()}

      {/* 方法学洞察 */}
      {renderMethodologicalInsights()}

      {/* 推荐文献 */}
      {papers && papers.length > 0 && (
        <Card className="border-0 shadow-sm mb-4 modern-card">
          <Card.Header className="bg-gradient bg-success text-white border-0">
            <div className="d-flex align-items-center">
              <BiSearch size={20} />
              <h5 className="mb-0 ms-2">📚 推荐文献</h5>
              <Badge bg="light" text="success" className="ms-2">
                {papers.length} 篇
              </Badge>
            </div>
          </Card.Header>
          <Card.Body>
            <div className="space-y-3">
              {papers.map((paper, index) => {
                const fused = paper.relevance_score;
                const algo = paper._algo_score;
                const llm = paper._llm_score;
                const hasScore = fused != null || algo != null || llm != null;

                return (
                  <Card key={paper.pmid || paper.arxiv_id || index} className="border hover-lift">
                    <Card.Body className="p-3">
                      {/* 标题行 */}
                      <div className="d-flex justify-content-between align-items-start mb-2">
                        <h6 className="mb-1 text-primary" style={{ fontSize: '0.95rem' }}>
                          {paper.title}
                        </h6>
                        <div className="d-flex gap-1 flex-shrink-0 ms-2 align-items-center">
                          {fused != null && (
                            <Badge bg={fused >= 65 ? 'success' : fused >= 35 ? 'warning' : 'secondary'}>
                              {fused.toFixed(1)}分
                            </Badge>
                          )}
                          {paper.source === 'arxiv' && <Badge bg="dark">arXiv</Badge>}
                          {paper.source === 'pubmed' && <Badge bg="primary">PubMed</Badge>}
                          <PlanScoreBreakdown paper={paper} />
                        </div>
                      </div>

                      {/* 作者 / 期刊 / 时间 */}
                      <p className="text-muted mb-2" style={{ fontSize: '0.85rem' }}>
                        <strong>作者:</strong> {(paper.authors || []).slice(0, 3).join(', ')}
                        {(paper.authors || []).length > 3 ? ' 等' : ''}
                        {paper.journal && <> | <strong>期刊:</strong> {paper.journal}</>}
                        {paper.pubdate && <> | <strong>时间:</strong> {paper.pubdate}</>}
                      </p>

                      {/* 子分数条（紧凑展示） */}
                      {hasScore && (
                        <div className="mb-2 p-2 bg-light rounded-2">
                          <div className="d-flex align-items-center gap-3 flex-wrap" style={{ fontSize: '0.75rem' }}>
                            {fused != null && (
                              <div className="d-flex align-items-center gap-1">
                                <span className="text-muted">融合:</span>
                                <Badge bg={fused >= 65 ? 'success' : fused >= 35 ? 'warning' : 'secondary'} pill>
                                  {fused.toFixed(1)}
                                </Badge>
                              </div>
                            )}
                            {algo != null && (
                              <div className="d-flex align-items-center gap-1">
                                <span className="text-muted">算法:</span>
                                <Badge bg="info" bg-opacity-25 text-dark pill>{algo.toFixed(1)}</Badge>
                              </div>
                            )}
                            {llm != null && (
                              <div className="d-flex align-items-center gap-1">
                                <span className="text-muted">LLM:</span>
                                <Badge bg="warning" bg-opacity-25 text-dark pill>{llm.toFixed(1)}</Badge>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* 摘要 */}
                      {paper.abstract && (
                        <p className="text-muted small mb-2" style={{ lineHeight: '1.6' }}>
                          {paper.abstract.length > 300 ? paper.abstract.slice(0, 300) + '...' : paper.abstract}
                        </p>
                      )}

                      {/* 关键发现 */}
                      {paper.key_insight && (
                        <p className="text-info small mb-2">
                          <BiBulb size={14} /> <strong>关键发现:</strong> {paper.key_insight}
                        </p>
                      )}

                      {/* 相关性说明 */}
                      {paper.relevance_reason && (
                        <p className="text-muted small mb-2">
                          <strong>相关性:</strong> {paper.relevance_reason}
                        </p>
                      )}

                      {/* 查看原文 */}
                      <div className="text-end">
                        {(paper.pubmed_url || paper.url) && (
                          <Button
                            variant="outline-primary"
                            size="sm"
                            href={paper.pubmed_url || paper.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <BiLinkExternal size={14} className="me-1" />
                            查看原文
                          </Button>
                        )}
                      </div>
                    </Card.Body>
                  </Card>
                );
              })}
            </div>
          </Card.Body>
        </Card>
      )}

      {/* 无文献提示 */}
      {(!papers || papers.length === 0) && (
        <Card className="border-0 shadow-sm mb-4">
          <Card.Body className="text-center py-4">
            <BiBook size={32} className="text-muted mb-2" />
            <p className="text-muted">未检索到匹配的文献，请尝试调整研究关键词</p>
          </Card.Body>
        </Card>
      )}
    </div>
  );
}

export default ModernEvidenceDisplay;
