import React, { useState } from 'react';
import { Card, Badge, Row, Col, Button } from 'react-bootstrap';
import { BiBook, BiSearch, BiTrendingUp, BiCheckCircle, BiBulb, BiChevronDown, BiChevronUp } from 'react-icons/bi';

function LiteratureReviewCard({ reviewData, loading = false }) {
  if (loading) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">加载中...</span>
        </div>
        <p className="mt-3 text-muted">正在加载文献综述...</p>
      </div>
    );
  }

  if (!reviewData) {
    return (
      <Card className="border-0 shadow-sm">
        <Card.Body className="text-center py-5">
          <BiBook size={48} className="text-muted mb-3" />
          <h5 className="text-muted">暂无文献综述</h5>
          <p className="text-muted small">系统正在为您生成文献综述，请稍后再试</p>
        </Card.Body>
      </Card>
    );
  }

  // 渲染文献综述内容
  const renderReviewSection = (content, title, icon, color = 'primary') => {
    if (!content || typeof content !== 'string') return null;

    return (
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Header className={`bg-gradient bg-${color} text-white border-0`}>
          <div className="d-flex align-items-center">
            {icon}
            <h5 className="mb-0 ms-2">{title}</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <div className="literature-content">
            <p className="mb-0" style={{
              lineHeight: '1.8',
              fontFamily: 'inherit',
              fontSize: '0.95rem',
              color: '#495057'
            }}>
              {content}
            </p>
          </div>
        </Card.Body>
      </Card>
    );
  };

  // 渲染研究空白
  const renderResearchGaps = (gaps) => {
    // 处理对象格式的研究空白
    if (typeof gaps === 'object' && gaps !== null && !Array.isArray(gaps)) {
      const gapTypes = [
        { key: 'methodological_gaps', label: '方法学空白' },
        { key: 'clinical_gaps', label: '临床空白' },
        { key: 'technical_gaps', label: '技术空白' }
      ];

      const gapItems = [];
      gapTypes.forEach(gapType => {
        const value = gaps[gapType.key];
        if (value && typeof value === 'string' && value.trim()) {
          gapItems.push(`${gapType.label}: ${value}`);
        }
      });

      if (gapItems.length === 0) return null;

      return (
        <Card className="border-0 shadow-sm mb-4 modern-card">
          <Card.Header className="bg-gradient bg-warning text-dark border-0">
            <div className="d-flex align-items-center">
              <BiBulb size={20} />
              <h5 className="mb-0 ms-2">研究空白与机会</h5>
            </div>
          </Card.Header>
          <Card.Body>
            <div className="bg-light p-3 rounded">
              {gapItems.map((item, index) => (
                <p key={index} className="mb-2" style={{ lineHeight: '1.8' }}>{item}</p>
              ))}
            </div>
          </Card.Body>
        </Card>
      );
    }

    // 处理字符串格式（向后兼容）
    if (!gaps || typeof gaps !== 'string') return null;

    return (
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Header className="bg-gradient bg-warning text-dark border-0">
          <div className="d-flex align-items-center">
            <BiBulb size={20} />
            <h5 className="mb-0 ms-2">研究空白与机会</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <div className="bg-light p-3 rounded">
            <p className="mb-0" style={{ lineHeight: '1.8' }}>{gaps}</p>
          </div>
        </Card.Body>
      </Card>
    );
  };

  // 渲染方法学证据
  const renderMethodologicalEvidence = (evidence) => {
    if (!evidence || typeof evidence !== 'string') return null;

    return (
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Header className="bg-gradient bg-info text-white border-0">
          <div className="d-flex align-items-center">
            <BiCheckCircle size={20} />
            <h5 className="mb-0 ms-2">方法学证据支持</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <div className="bg-light p-3 rounded">
            <p className="mb-0" style={{ lineHeight: '1.8' }}>{evidence}</p>
          </div>
        </Card.Body>
      </Card>
    );
  };

  // 渲染推荐文献
  const renderRecommendedLiterature = (literature) => {
    if (!literature || !literature.recommended_papers) return null;

    return (
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Header className="bg-gradient bg-success text-white border-0">
          <div className="d-flex align-items-center">
            <BiSearch size={20} />
            <h5 className="mb-0 ms-2">推荐文献</h5>
            <Badge bg="light" text="success" className="ms-2">
              {literature.total_results} 篇
            </Badge>
          </div>
        </Card.Header>
        <Card.Body>
          {/* 搜索查询信息 */}
          {literature.search_query && (
            <div className="mb-4 p-3 bg-light rounded">
              <small className="text-muted">
                <strong>搜索策略:</strong>
                <div className="mt-2 font-monospace" style={{ fontSize: '0.8rem' }}>
                  {literature.search_query}
                </div>
              </small>
            </div>
          )}

          {/* 文献列表 */}
          {literature.recommended_papers.map((paper, index) => (
            <PaperItem key={paper.pmid || index} paper={paper} index={index} />
          ))}

          {/* 搜索总结 */}
          {literature.search_summary && (
            <div className="mt-4 p-3 bg-light rounded">
              <small className="text-muted">
                <strong>搜索总结:</strong> {literature.search_summary}
              </small>
            </div>
          )}
        </Card.Body>
      </Card>
    );
  };

  // 单篇文献组件 — 摘要可展开/收起，标题点击展开全文详情
  const PaperItem = ({ paper, index }) => {
    const [expanded, setExpanded] = useState(false);
    const [abstractExpanded, setAbstractExpanded] = useState(false);

    const authorsStr = Array.isArray(paper.authors) ? paper.authors.join(', ') : (paper.authors || '');
    const ABSTRACT_PREVIEW = 200;
    const isAbstractLong = paper.abstract && paper.abstract.length > ABSTRACT_PREVIEW;

    return (
      <div className="border rounded-3 mb-3 overflow-hidden">
        {/* 标题栏 — 点击展开全文 */}
        <div
          className="p-3 d-flex justify-content-between align-items-start"
          style={{ cursor: 'pointer', backgroundColor: '#f8f9fa' }}
          onClick={() => setExpanded(!expanded)}
        >
          <div className="flex-grow-1 me-3">
            <h6 className="mb-1 fw-semibold" style={{ fontSize: '0.95rem' }}>
              <span className="text-success me-2">#{index + 1}</span>
              {paper.title}
            </h6>
            <small className="text-muted">
              {authorsStr} | {paper.journal} | {paper.pubdate}
            </small>
          </div>
          <div className="d-flex align-items-center gap-2 flex-shrink-0">
            {paper.relevance_score != null && (
              <Badge bg={paper.relevance_score >= 65 ? 'success' : paper.relevance_score >= 35 ? 'warning' : 'secondary'}>
                相关度: {paper.relevance_score}
              </Badge>
            )}
            {expanded ? <BiChevronUp size={18} /> : <BiChevronDown size={18} />}
          </div>
        </div>

        {/* 展开的详情区 */}
        {expanded && (
          <div className="p-3 border-top">
            {/* 基本信息 */}
            <Row className="mb-3">
              <Col md={8}>
                {paper.pmid && <p className="mb-1 small"><strong>PMID:</strong> {paper.pmid}</p>}
                {paper.doi && <p className="mb-1 small"><strong>DOI:</strong> {paper.doi}</p>}
                {paper.article_type && <p className="mb-0 small"><strong>文章类型:</strong> {paper.article_type}</p>}
              </Col>
              <Col md={4} className="text-md-end">
                <Button
                  variant="outline-primary"
                  size="sm"
                  href={paper.pubmed_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  PubMed 原文 ↗
                </Button>
              </Col>
            </Row>

            {/* 摘要 — 可展开/收起 */}
            {paper.abstract ? (
              <div className="bg-light p-3 rounded-3 border-start border-4 border-success">
                <strong className="small text-success">摘要：</strong>
                <p className="mb-0 mt-1 small lh-base text-dark">
                  {abstractExpanded ? paper.abstract : (isAbstractLong ? paper.abstract.substring(0, ABSTRACT_PREVIEW) + '...' : paper.abstract)}
                </p>
                {isAbstractLong && (
                  <button
                    className="btn btn-link btn-sm p-0 mt-2 text-decoration-none d-flex align-items-center gap-1"
                    onClick={(e) => { e.stopPropagation(); setAbstractExpanded(!abstractExpanded); }}
                    style={{ fontSize: '0.8rem' }}
                  >
                    {abstractExpanded ? <><BiChevronUp size={14} /> 收起摘要</> : <><BiChevronDown size={14} /> 展开摘要</>}
                  </button>
                )}
              </div>
            ) : (
              <div className="bg-light p-3 rounded-3">
                <p className="mb-0 text-muted small fst-italic">暂无摘要</p>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="literature-review">
      {/* 概览卡片 */}
      <Card className="border-0 shadow-sm mb-4 modern-card">
        <Card.Body className="bg-gradient bg-light">
          <div className="d-flex align-items-center mb-3">
            <BiTrendingUp size={32} className="text-primary me-3" />
            <div>
              <h4 className="mb-1 fw-bold">📚 智能文献综述</h4>
              <p className="text-muted mb-0 small">
                基于AI分析和最新研究文献的综合评估
              </p>
            </div>
          </div>
        </Card.Body>
      </Card>

      {/* 主要内容 */}
      {reviewData.literature_review &&
        renderReviewSection(
          reviewData.literature_review,
          '文献综述',
          <BiBook size={20} />
        )
      }

      {reviewData.research_gaps &&
        renderResearchGaps(reviewData.research_gaps)
      }

      {reviewData.methodological_evidence &&
        renderMethodologicalEvidence(reviewData.methodological_evidence)
      }

      {reviewData.recommended_literature &&
        renderRecommendedLiterature(reviewData.recommended_literature)
      }
    </div>
  );
}

export default LiteratureReviewCard;