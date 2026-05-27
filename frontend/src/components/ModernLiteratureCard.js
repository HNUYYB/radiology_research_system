import React, { useState } from 'react';
import { Card, Badge, Button, Form } from 'react-bootstrap';
import { BiUser, BiBook, BiFile, BiLinkExternal, BiCalendar, BiChevronDown, BiChevronUp } from 'react-icons/bi';
import ScoreBreakdown from './ScoreBreakdown';

function ModernLiteratureCard({ paper, index, viewMode = 'card', onSelect, isSelected = false }) {
  const [abstractExpanded, setAbstractExpanded] = useState(false);
  const [fullTextExpanded, setFullTextExpanded] = useState(false);

  const ABSTRACT_PREVIEW_LEN = 150;

  const renderAbstract = (abstract) => {
    if (!abstract) return null;
    const isLong = abstract.length > ABSTRACT_PREVIEW_LEN;
    const previewText = isLong ? abstract.substring(0, ABSTRACT_PREVIEW_LEN) + '...' : abstract;

    return (
      <div className="bg-light p-3 rounded-3 border-start border-4 border-primary">
        <div className="d-flex align-items-center mb-2">
          <BiFile className="text-primary me-2" size={14} />
          <strong className="text-primary small">摘要</strong>
        </div>
        <p className="mb-0 text-dark small lh-base">
          {abstractExpanded ? abstract : previewText}
        </p>
        {isLong && (
          <button
            className="btn btn-link btn-sm p-0 mt-2 text-decoration-none d-flex align-items-center gap-1"
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setAbstractExpanded(!abstractExpanded); }}
            style={{ fontSize: '0.8rem' }}
          >
            {abstractExpanded ? <><BiChevronUp size={14} /> 收起摘要</> : <><BiChevronDown size={14} /> 展开摘要</>}
          </button>
        )}
      </div>
    );
  };

  const renderFullText = () => {
    if (!fullTextExpanded) return null;
    return (
      <div className="mt-3 p-3 rounded-3 border" style={{ backgroundColor: '#fafafa' }}>
        <h6 className="mb-2 fw-semibold" style={{ fontSize: '0.9rem' }}>📄 论文详情</h6>
        {paper.abstract && (
          <div className="mb-3">
            <strong className="small text-muted">摘要：</strong>
            <p className="mb-0 mt-1 small lh-base text-dark">{paper.abstract}</p>
          </div>
        )}
        {paper.authors && (
          <p className="mb-1 small"><strong>作者：</strong>{Array.isArray(paper.authors) ? paper.authors.join(', ') : paper.authors}</p>
        )}
        {paper.journal && (
          <p className="mb-1 small"><strong>期刊：</strong>{paper.journal}</p>
        )}
        {paper.pubdate && (
          <p className="mb-1 small"><strong>发表日期：</strong>{paper.pubdate}</p>
        )}
        {paper.doi && (
          <p className="mb-1 small"><strong>DOI：</strong>{paper.doi}</p>
        )}
        {paper.pmid && (
          <p className="mb-0 small"><strong>PMID：</strong>{paper.pmid}</p>
        )}
        {paper.article_type && (
          <p className="mb-0 small"><strong>文章类型：</strong>{paper.article_type}</p>
        )}
      </div>
    );
  };

  const handleTitleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setFullTextExpanded(!fullTextExpanded);
  };

  const getJournalColor = (journal) => {
    if (!journal) return 'secondary';
    const high = ['Nature', 'Science', 'Cell', 'Lancet', 'NEJM', 'JAMA', 'BMJ'];
    const mid = ['Radiology', 'European Radiology', 'AJR', 'Investigative Radiology'];
    if (high.some(j => journal.includes(j))) return 'danger';
    if (mid.some(j => journal.includes(j))) return 'warning';
    return 'primary';
  };

  const formatDate = (dateString) => {
    if (!dateString) return '日期未知';
    return dateString;
  };

  // 列表视图
  if (viewMode === 'list') {
    return (
      <Card className={`border-0 shadow-sm mb-3 ${isSelected ? 'border border-primary border-2' : ''}`}>
        <Card.Body className="p-4">
          <div className="d-flex align-items-start">
            {onSelect && (
              <Form.Check
                type="checkbox"
                checked={isSelected}
                onChange={() => onSelect && onSelect(index)}
                className="me-3 mt-1"
              />
            )}
            <span className="fw-bold text-muted me-3 mt-1" style={{ minWidth: '28px', textAlign: 'right' }}>
              {index + 1}
            </span>
            <div className="flex-grow-1">
              <h5 className="mb-2 lh-base" style={{ fontSize: '1.05rem' }}>
                <a href={paper.pubmed_url} target="_blank" rel="noopener noreferrer"
                   className="text-decoration-none text-dark fw-semibold">
                  {paper.title}
                </a>
              </h5>

              <div className="mb-2 text-muted small">
                <BiUser className="me-1" size={14} />
                {Array.isArray(paper.authors) ? paper.authors.join(', ') : paper.authors || '未知作者'}
              </div>

              <div className="mb-2 text-muted small">
                <BiBook className="me-1" size={14} />
                <Badge bg={getJournalColor(paper.journal)} className="me-1 fw-normal" style={{ fontSize: '0.75rem' }}>
                  {paper.journal}
                </Badge>
                <BiCalendar className="ms-2 me-1" size={14} />
                {formatDate(paper.pubdate)}
              </div>

              {renderAbstract(paper.abstract)}

              {renderFullText()}

              <div className="d-flex justify-content-between align-items-center pt-3 mt-3 border-top">
                <div className="d-flex align-items-center gap-2">
                  <small className="text-muted">PMID: {paper.pmid}</small>
                  {paper.relevance_score != null && (
                    <Badge bg={paper.relevance_score >= 65 ? 'success' : paper.relevance_score >= 35 ? 'warning' : 'secondary'} className="small fw-normal" style={{ fontSize: '0.75rem' }}>
                      检索: {paper.relevance_score}
                    </Badge>
                  )}
                  {paper.personalized_score != null && (
                    <Badge bg={paper.personalized_score >= 65 ? 'success' : paper.personalized_score >= 35 ? 'warning' : 'secondary'} className="small fw-normal" style={{ fontSize: '0.75rem' }}>
                      推荐: {paper.personalized_score.toFixed(1)}
                    </Badge>
                  )}
                  <ScoreBreakdown paper={paper} />
                  <button
                    className="btn btn-link btn-sm p-0 text-decoration-none d-flex align-items-center gap-1"
                    onClick={handleTitleClick}
                    style={{ fontSize: '0.8rem' }}
                  >
                    {fullTextExpanded ? <><BiChevronUp size={14} /> 收起详情</> : <><BiChevronDown size={14} /> 展开全文</>}
                  </button>
                </div>
                <Button variant="primary" size="sm" href={paper.pubmed_url} target="_blank">
                  <BiLinkExternal size={14} className="me-2" />
                  查看原文
                </Button>
              </div>
            </div>
          </div>
        </Card.Body>
      </Card>
    );
  }

  // 卡片视图
  return (
    <Card className={`border-0 shadow-sm h-100 overflow-hidden ${isSelected ? 'border border-primary border-2' : ''}`}
          style={{ borderRadius: '1rem' }}>
      {onSelect && (
        <div className="position-absolute" style={{ top: '10px', right: '10px', zIndex: 10 }}>
          <Form.Check type="checkbox" checked={isSelected} onChange={() => onSelect(index)} className="bg-white rounded" />
        </div>
      )}

      <Card.Body className="p-4">
        <div className="d-flex align-items-start mb-3">
          <span className="fw-bold text-primary me-2" style={{ fontSize: '1.1rem', minWidth: '28px' }}>
            {index + 1}
          </span>
          <h6 className="card-title mb-0 lh-base fw-semibold flex-grow-1" style={{ fontSize: '0.95rem' }}>
            <a href="#" onClick={handleTitleClick}
               className="text-decoration-none text-dark">
              {paper.title}
            </a>
          </h6>
        </div>

        {/* 作者 */}
        <div className="mb-2 text-muted small d-flex align-items-center">
          <BiUser size={14} className="me-2 flex-shrink-0" />
          <span>{Array.isArray(paper.authors) ? paper.authors.slice(0, 3).join(', ') + (paper.authors.length > 3 ? ' 等' : '') : paper.authors || '未知作者'}</span>
        </div>

        {/* 期刊 + 日期 + 相关度 */}
        <div className="mb-3 d-flex align-items-center flex-wrap gap-2">
          <Badge bg={getJournalColor(paper.journal)} className="small fw-normal" style={{ fontSize: '0.7rem' }}>
            {paper.journal}
          </Badge>
          <small className="text-muted d-flex align-items-center">
            <BiCalendar size={12} className="me-1" />
            {formatDate(paper.pubdate)}
          </small>
          {paper.relevance_score != null && (
            <Badge bg={paper.relevance_score >= 65 ? 'success' : paper.relevance_score >= 35 ? 'warning' : 'secondary'} className="small fw-normal" style={{ fontSize: '0.7rem' }}>
              相关度: {paper.relevance_score}
            </Badge>
          )}
        </div>

        {/* 摘要 — 可展开/收起 */}
        {paper.abstract ? (
          <div className="mb-3">{renderAbstract(paper.abstract)}</div>
        ) : (
          <div className="bg-light p-3 rounded-3 mb-3">
            <p className="mb-0 text-muted small fst-italic">暂无摘要</p>
          </div>
        )}

        {/* 全文详情展开区 */}
        {renderFullText()}

        {/* 底部 */}
        <div className="pt-3 border-top">
          <div className="d-flex align-items-center gap-2 mb-2 flex-wrap">
            <small className="text-muted">PMID: {paper.pmid}</small>
            {paper.relevance_score != null && (
              <Badge bg={paper.relevance_score >= 65 ? 'success' : paper.relevance_score >= 35 ? 'warning' : 'secondary'} className="small fw-normal" style={{ fontSize: '0.65rem' }}>
                检索: {paper.relevance_score}
              </Badge>
            )}
            {paper.personalized_score != null && (
              <Badge bg={paper.personalized_score >= 65 ? 'success' : paper.personalized_score >= 35 ? 'warning' : 'secondary'} className="small fw-normal" style={{ fontSize: '0.65rem' }}>
                推荐: {paper.personalized_score.toFixed(1)}
              </Badge>
            )}
            <ScoreBreakdown paper={paper} />
          </div>
          <div className="d-flex justify-content-end">
            <Button variant="outline-primary" size="sm" href={paper.pubmed_url} target="_blank" className="px-3 py-1">
              <BiLinkExternal size={12} className="me-1" />
              查看原文
            </Button>
          </div>
        </div>
      </Card.Body>
    </Card>
  );
}

export default ModernLiteratureCard;
