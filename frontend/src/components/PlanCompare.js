import React, { useState } from 'react';
import { Modal, Button, Table, Badge, Tabs, Tab, Row, Col, Card } from 'react-bootstrap';

const PlanCompare = ({ show, onHide, data }) => {
  const [viewMode, setViewMode] = useState('sideBySide'); // sideBySide | scores

  if (!data) return null;

  const { plans, fields, score_dimensions } = data;

  // 颜色方案
  const colors = ['#16213e', '#e94560', '#0f3460', '#533483'];

  return (
    <Modal show={show} onHide={onHide} size="xl" fullscreen="xl-down" centered>
      <Modal.Header closeButton>
        <Modal.Title>🔍 方案对比（{plans.length} 个方案）</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <Tabs activeKey={viewMode} onSelect={setViewMode} className="mb-3">
          <Tab eventKey="sideBySide" title="📊 并排对比" />
          <Tab eventKey="scores" title="📈 评分对比" />
        </Tabs>

        {viewMode === 'sideBySide' ? (
          <div className="table-responsive">
            <Table bordered hover className="align-middle">
              <thead>
                <tr className="table-light">
                  <th style={{ width: 150, minWidth: 150 }}>对比维度</th>
                  {plans.map((p, i) => (
                    <th key={p.id} style={{ minWidth: 250 }}>
                      <div className="d-flex align-items-center gap-2">
                        <span className="badge rounded-pill" style={{ backgroundColor: colors[i % colors.length] }}>{i + 1}</span>
                        <span className="text-truncate" style={{ maxWidth: 200 }} title={p.title}>{p.title || '未命名'}</span>
                      </div>
                      <small className="text-muted d-block mt-1">{new Date(p.created_at).toLocaleDateString('zh-CN')}</small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fields.map(([key, label]) => {
                  // 检查是否有任何方案有这个字段的内容
                  const hasContent = plans.some(p => {
                    const val = p.content?.[key];
                    return val && typeof val === 'string' && val.trim() !== '' && !val.includes('待补充');
                  });
                  if (!hasContent) return null;

                  return (
                    <tr key={key}>
                      <td className="fw-bold bg-light" style={{ position: 'sticky', left: 0, zIndex: 1 }}>
                        {label}
                      </td>
                      {plans.map((p, i) => {
                        const val = p.content?.[key];
                        const text = val && typeof val === 'string' ? val : '—';
                        const isLong = text.length > 80;
                        return (
                          <td key={p.id} style={{ borderLeft: `3px solid ${colors[i % colors.length]}` }}>
                            {isLong ? (
                              <div>
                                <p className="small mb-0" style={{ whiteSpace: 'pre-wrap', maxHeight: 80, overflow: 'hidden', position: 'relative' }}>
                                  {text.substring(0, 80)}...
                                </p>
                                <span className="text-muted small">（{text.length}字）</span>
                              </div>
                            ) : (
                              <p className="small mb-0" style={{ whiteSpace: 'pre-wrap' }}>{text}</p>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </div>
        ) : (
          <Row>
            {plans.map((p, i) => {
              const critique = p.critique || {};
              const feas = critique.feasibility_analysis?.overall || critique.feasibility_analysis?.score;
              const innov = critique.innovation_assessment?.novelty_level || critique.innovation_assessment?.score;
              const meth = critique.methodology_evaluation?.overall || critique.methodology_evaluation?.score;
              const endp = critique.endpoint_clarity?.overall || critique.endpoint_clarity?.score;
              const scores = [
                { label: '可行性', value: feas },
                { label: '创新性', value: innov },
                { label: '方法学', value: meth },
                { label: '终点清晰度', value: endp },
              ].filter(s => s.value !== undefined);

              return (
                <Col key={p.id} md={Math.max(4, Math.floor(12 / plans.length))}>
                  <Card className="h-100" style={{ borderTop: `4px solid ${colors[i % colors.length]}` }}>
                    <Card.Header className="bg-white">
                      <div className="d-flex align-items-center gap-2">
                        <span className="badge rounded-pill" style={{ backgroundColor: colors[i % colors.length] }}>{i + 1}</span>
                        <span className="fw-bold text-truncate" title={p.title}>{p.title || '未命名'}</span>
                      </div>
                    </Card.Header>
                    <Card.Body>
                      {scores.length > 0 ? (
                        <div>
                          {scores.map((s, si) => {
                            const numVal = typeof s.value === 'number' ? s.value : (typeof s.value === 'string' ? parseFloat(s.value) || 3 : 3);
                            const pct = Math.min(100, (numVal / 5) * 100);
                            const variant = pct >= 80 ? 'success' : pct >= 60 ? 'warning' : 'danger';
                            return (
                              <div key={si} className="mb-3">
                                <div className="d-flex justify-content-between mb-1">
                                  <small>{s.label}</small>
                                  <small className="fw-bold">{typeof s.value === 'number' ? s.value.toFixed(1) : s.value}</small>
                                </div>
                                <div className="progress" style={{ height: 6 }}>
                                  <div className={`progress-bar bg-${variant}`} style={{ width: `${pct}%` }} />
                                </div>
                              </div>
                            );
                          })}
                          {critique.major_concerns?.length > 0 && (
                            <div className="mt-3 p-2 bg-warning bg-opacity-10 rounded">
                              <small className="fw-bold text-warning">⚠️ 主要问题</small>
                              <ul className="small mb-0 ps-3 mt-1">
                                {critique.major_concerns.slice(0, 3).map((c, ci) => (<li key={ci}>{c}</li>))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="text-muted text-center small py-3">暂无评分数据</p>
                      )}
                    </Card.Body>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>关闭</Button>
      </Modal.Footer>
    </Modal>
  );
};

export default PlanCompare;
