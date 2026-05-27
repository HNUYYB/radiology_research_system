import React, { useState } from 'react';
import { Col, Modal, ProgressBar, Row, Badge, Button } from 'react-bootstrap';
import { BiBrain, BiCalculator, BiChip, BiInfoCircle, BiShuffle, BiX } from 'react-icons/bi';

/**
 * 方案生成 — 文献评分详情弹窗
 *
 * 展示后端 agents.py _ai_screen_papers 计算的融合分构成：
 *   - 算法分 (_algo_score)：标题匹配 + 摘要匹配 + 时效性 + 期刊质量
 *   - LLM分 (_llm_score)：LLM 语义评分（0/1/2/3 → 0/45/72/100）
 *   - 融合分 (relevance_score)：algo × 0.3 + llm × 0.7（有信号时）
 *
 * 同时展示 relevance_reason（LLM 给出的相关性说明）
 * 和 key_insight（关键发现）
 */
function PlanScoreBreakdown({ paper }) {
  const [show, setShow] = useState(false);

  if (!paper) return null;

  const fused = paper.relevance_score;
  const algo = paper._algo_score;
  const llm = paper._llm_score;

  // 没有分数时不显示按钮
  if (fused == null && algo == null && llm == null) return null;

  const getScoreColor = (score) => {
    if (score >= 70) return '#198754';
    if (score >= 40) return '#ffc107';
    return '#dc3545';
  };

  const getBarVariant = (score) => {
    if (score >= 70) return 'success';
    if (score >= 40) return 'warning';
    return 'danger';
  };

  const getLlmLabel = (score) => {
    // LLM 原始分映射：0→0, 1→45, 2→72, 3→100
    if (score >= 90) return '3分 — 高度相关';
    if (score >= 65) return '2分 — 中度相关';
    if (score >= 30) return '1分 — 低相关';
    return '0分 — 不相关';
  };

  const getFusedLabel = (score) => {
    if (score >= 70) return '高度相关';
    if (score >= 40) return '中度相关';
    if (score >= 20) return '低相关';
    return '不相关';
  };

  return (
    <>
      {/* 触发按钮 */}
      <Button
        variant="outline-info"
        size="sm"
        onClick={() => setShow(true)}
        className="d-flex align-items-center gap-1"
        title="查看评分详情"
      >
        <BiCalculator size={13} />
        <BiInfoCircle size={13} />
      </Button>

      <Modal show={show} onHide={() => setShow(false)} size="md" centered>
        <Modal.Header className="border-bottom py-2 px-3">
          <div className="d-flex align-items-center gap-2">
            <BiCalculator className="text-primary" size={18} />
            <Modal.Title className="fs-6">评分详情</Modal.Title>
          </div>
          <Button variant="light" className="border-0 p-1" onClick={() => setShow(false)}>
            <BiX size={20} />
          </Button>
        </Modal.Header>

        <Modal.Body className="p-3">
          {/* 融合总分 — 突出显示 */}
          {fused != null && (
            <div className="text-center p-3 bg-light rounded-3 mb-3">
              <div className="text-muted small mb-1">融合总分</div>
              <div className="display-4 fw-bold" style={{ color: getScoreColor(fused), lineHeight: 1.2 }}>
                {fused.toFixed(1)}
              </div>
              <Badge bg={getBarVariant(fused)} className="mt-1">{getFusedLabel(fused)}</Badge>
            </div>
          )}

          {/* 融合公式说明 */}
          <div className="alert alert-primary d-flex align-items-start gap-2 py-2 mb-3" style={{ fontSize: '0.8rem' }}>
            <BiInfoCircle size={14} className="flex-shrink-0 mt-0.5" />
            <div>
              <strong>融合公式：</strong>
              当算法分 &gt; 10 时，融合分 = 算法分 × 30% + LLM分 × 70%；否则直接使用 LLM 分。
            </div>
          </div>

          {/* 子分数 */}
          <div className="row g-3 mb-3">
            {/* 算法分 */}
            <Col md={6}>
              <div className="border rounded-3 p-3 h-100">
                <div className="d-flex align-items-center gap-2 mb-2">
                  <BiChip className="text-info" size={16} />
                  <span className="fw-semibold small">算法分</span>
                  <Badge bg="info" pill className="ms-auto">权重 30%</Badge>
                </div>
                {algo != null ? (
                  <>
                    <div className="display-6 fw-bold text-center" style={{ color: getScoreColor(algo) }}>
                      {algo.toFixed(1)}
                    </div>
                    <ProgressBar now={algo} variant={getBarVariant(algo)} style={{ height: '6px' }} className="mt-2" />
                  </>
                ) : (
                  <div className="text-muted text-center small">未计算</div>
                )}
                <div className="text-muted mt-2" style={{ fontSize: '0.7rem' }}>
                  标题匹配 + 摘要关键词 + 时效性 + 期刊质量
                </div>
              </div>
            </Col>

            {/* LLM分 */}
            <Col md={6}>
              <div className="border rounded-3 p-3 h-100">
                <div className="d-flex align-items-center gap-2 mb-2">
                  <BiBrain className="text-warning" size={16} />
                  <span className="fw-semibold small">LLM 分</span>
                  <Badge bg="warning" text="dark" pill className="ms-auto">权重 70%</Badge>
                </div>
                {llm != null ? (
                  <>
                    <div className="display-6 fw-bold text-center" style={{ color: getScoreColor(llm) }}>
                      {llm.toFixed(1)}
                    </div>
                    <ProgressBar now={llm} variant={getBarVariant(llm)} style={{ height: '6px' }} className="mt-2" />
                  </>
                ) : (
                  <div className="text-muted text-center small">未计算</div>
                )}
                <div className="text-muted mt-2" style={{ fontSize: '0.7rem' }}>
                  {llm != null ? getLlmLabel(llm) : 'LLM 语义评分'}
                </div>
              </div>
            </Col>
          </div>

          {/* 融合过程可视化 */}
          {algo != null && llm != null && (
            <div className="border rounded-3 p-3 mb-3 bg-light">
              <div className="d-flex align-items-center gap-2 mb-2">
                <BiShuffle className="text-primary" size={16} />
                <span className="fw-semibold small">融合计算过程</span>
              </div>
              <div className="d-flex align-items-center justify-content-center gap-2 flex-wrap" style={{ fontSize: '0.85rem' }}>
                <span className="badge bg-info bg-opacity-25 text-dark">
                  {algo.toFixed(1)} × 0.3 = {(algo * 0.3).toFixed(1)}
                </span>
                <span className="text-muted">+</span>
                <span className="badge bg-warning bg-opacity-25 text-dark">
                  {llm.toFixed(1)} × 0.7 = {(llm * 0.7).toFixed(1)}
                </span>
                <span className="text-muted">=</span>
                <span className="badge bg-success bg-opacity-25 text-dark fw-bold">
                  {(algo * 0.3 + llm * 0.7).toFixed(1)}
                </span>
              </div>
            </div>
          )}

          {/* LLM 给出的相关性说明 */}
          {paper.relevance_reason && (
            <div className="alert alert-success d-flex align-items-start gap-2 py-2 mb-2" style={{ fontSize: '0.85rem' }}>
              <BiBrain size={16} className="flex-shrink-0 mt-0.5" />
              <div>
                <strong>LLM 评估：</strong>{paper.relevance_reason}
              </div>
            </div>
          )}

          {/* 关键发现 */}
          {paper.key_insight && (
            <div className="alert alert-info d-flex align-items-start gap-2 py-2 mb-0" style={{ fontSize: '0.85rem' }}>
              <BiInfoCircle size={16} className="flex-shrink-0 mt-0.5" />
              <div>
                <strong>关键发现：</strong>{paper.key_insight}
              </div>
            </div>
          )}
        </Modal.Body>

        <Modal.Footer className="border-top py-2 px-3">
          <small className="text-muted me-auto">
            评分由 agents.py _ai_screen_papers 计算
          </small>
          <Button variant="secondary" size="sm" onClick={() => setShow(false)}>关闭</Button>
        </Modal.Footer>
      </Modal>
    </>
  );
}

export default PlanScoreBreakdown;
