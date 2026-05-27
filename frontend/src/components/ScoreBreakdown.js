import React, { useState } from 'react';
import { Modal, ProgressBar, Badge, Button, Table } from 'react-bootstrap';
import { BiCalculator, BiInfoCircle, BiX } from 'react-icons/bi';

/**
 * 文献评分详情弹窗
 *
 * 展示后端 _calculate_personalized_score 的 4 个维度：
 *   1. 基础质量得分 (40%)  — 影响因子 + 期刊 + 引用 + 时效 + 研究类型
 *   2. 专业相关性得分 (30%) — 专业关键词匹配
 *   3. 学术水平匹配得分 (20%) — 学历与文献难度匹配
 *   4. 技术背景匹配得分 (10%) — 统计/AI背景匹配
 *
 * 同时展示文献检索阶段的 relevance_score（标题/摘要/MeSH/时效/期刊/引用）
 */
function ScoreBreakdown({ paper, userProfile }) {
  const [show, setShow] = useState(false);
  const [activeTab, setActiveTab] = useState('personalized');

  if (!paper) return null;

  const personalizedScore = paper.personalized_score;
  const relevanceScore = paper.relevance_score;

  // ── 个性化评分维度（来自后端 _calculate_personalized_score）──
  // 这些子分数目前后端没有单独返回，这里根据 paper 字段做前端估算展示
  const estimateQualityScore = () => {
    let score = 0;
    const breakdown = [];

    // 影响因子
    const impactFactor = paper.impact_factor || 0;
    let impactPoints = 0;
    if (impactFactor >= 10) impactPoints = 40;
    else if (impactFactor >= 5) impactPoints = 30;
    else if (impactFactor >= 3) impactPoints = 20;
    else if (impactFactor >= 1) impactPoints = 10;
    score += impactPoints;
    breakdown.push({ label: '影响因子', detail: impactFactor > 0 ? `IF = ${impactFactor}` : '未知', points: impactPoints, max: 40 });

    // 期刊质量
    const highImpactJournals = ['Radiology', 'European Radiology', 'AJR', 'Investigative Radiology', 'Nature Medicine', 'Lancet', 'NEJM', 'JAMA'];
    const isHighImpact = highImpactJournals.some(j => (paper.journal || '').includes(j));
    const journalPoints = isHighImpact ? 20 : 0;
    score += journalPoints;
    breakdown.push({ label: '期刊质量', detail: isHighImpact ? `${paper.journal} (高影响)` : (paper.journal || '未知'), points: journalPoints, max: 20 });

    // 引用次数
    const citations = paper.citations || 0;
    let citePoints = 0;
    if (citations >= 100) citePoints = 20;
    else if (citations >= 50) citePoints = 15;
    else if (citations >= 20) citePoints = 10;
    else if (citations >= 5) citePoints = 5;
    score += citePoints;
    breakdown.push({ label: '引用次数', detail: citations > 0 ? `${citations} 次` : '未知', points: citePoints, max: 20 });

    // 时效性
    const pubYear = parseInt((paper.pubdate || '').substring(0, 4));
    const currentYear = new Date().getFullYear();
    let recencyPoints = 0;
    if (pubYear) {
      const diff = currentYear - pubYear;
      if (diff <= 2) recencyPoints = 15;
      else if (diff <= 5) recencyPoints = 10;
      else if (diff <= 10) recencyPoints = 5;
    }
    score += recencyPoints;
    breakdown.push({ label: '时效性', detail: pubYear ? `${pubYear}年 (距今${pubYear ? currentYear - pubYear : '?'}年)` : '未知', points: recencyPoints, max: 15 });

    // 研究类型
    const articleType = (paper.article_type || '').toLowerCase();
    let typePoints = 0;
    let typeLabel = paper.article_type || '未知';
    if (articleType.includes('randomized controlled trial')) { typePoints = 15; typeLabel = 'RCT'; }
    else if (articleType.includes('meta-analysis') || articleType.includes('systematic review')) { typePoints = 12; typeLabel = 'Meta/综述'; }
    else if (articleType.includes('clinical trial')) { typePoints = 10; typeLabel = '临床试验'; }
    else if (articleType.includes('review')) { typePoints = 8; typeLabel = '综述'; }
    else if (articleType.includes('case report')) { typePoints = 3; typeLabel = '病例报告'; }
    score += typePoints;
    breakdown.push({ label: '研究类型', detail: typeLabel, points: typePoints, max: 15 });

    return { total: Math.min(score, 100), breakdown };
  };

  const qualityEstimate = estimateQualityScore();

  // ── 检索评分维度（来自后端 _calculate_relevance_score）──
  const getRelevanceDimensions = () => {
    const query = (paper.search_query || '').toLowerCase();
    const queryWords = query.split(/\s+/).filter(w => w.length > 1);
    const title = (paper.title || '').toLowerCase();
    const abstract = (paper.abstract || '').toLowerCase();

    // 标题匹配
    const titleMatches = queryWords.filter(w => title.includes(w));
    const titleCoverage = queryWords.length > 0 ? titleMatches.length / queryWords.length : 0;
    const titleScore = Math.min(titleCoverage * 80 + (title.includes(query) ? 20 : 0), 100);

    // 摘要匹配
    const abstractMatches = queryWords.filter(w => abstract.includes(w));
    const abstractCoverage = queryWords.length > 0 ? abstractMatches.length / queryWords.length : 0;
    const abstractScore = Math.min(abstractCoverage * 100, 100);

    // 时效性
    const pubYear = parseInt((paper.pubdate || '').substring(0, 4));
    const currentYear = new Date().getFullYear();
    const yearDiff = pubYear ? Math.max(0, currentYear - pubYear) : 10;
    const recencyScore = Math.min(100 * Math.exp(-0.15 * yearDiff), 100);

    // 期刊质量
    const highImpactJournals = ['Radiology', 'European Radiology', 'AJR', 'Investigative Radiology', 'Nature Medicine', 'Lancet', 'NEJM', 'JAMA'];
    const midJournals = ['Academic Radiology', 'Clinical Radiology', 'European Journal of Radiology'];
    let journalScore = 30;
    if (highImpactJournals.some(j => (paper.journal || '').includes(j))) journalScore = 100;
    else if (midJournals.some(j => (paper.journal || '').includes(j))) journalScore = 70;
    else if (paper.journal) journalScore = 50;

    // 引用影响力
    const citations = paper.citations || 0;
    let citationScore = 0;
    if (citations >= 200) citationScore = 100;
    else if (citations >= 100) citationScore = 85;
    else if (citations >= 50) citationScore = 70;
    else if (citations >= 20) citationScore = 50;
    else if (citations >= 5) citationScore = 30;
    else if (citations > 0) citationScore = 15;

    return [
      { label: '标题语义匹配', weight: '25%', score: titleScore, detail: `匹配 ${titleMatches.length}/${queryWords.length} 个关键词`, color: '#4361ee' },
      { label: '摘要语义匹配', weight: '25%', score: abstractScore, detail: `匹配 ${abstractMatches.length}/${queryWords.length} 个关键词`, color: '#3a86ff' },
      { label: 'MeSH/关键词匹配', weight: '15%', score: null, detail: '需后端返回 MeSH 数据', color: '#4cc9f0' },
      { label: '时效性', weight: '15%', score: recencyScore, detail: pubYear ? `e^(-0.15 × ${yearDiff}) × 100 = ${recencyScore.toFixed(1)}` : '未知', color: '#f72585' },
      { label: '期刊质量', weight: '10%', score: journalScore, detail: paper.journal || '未知', color: '#7209b7' },
      { label: '引用影响力', weight: '10%', score: citationScore, detail: citations > 0 ? `${citations} 次引用` : '未知', color: '#c9184a' },
    ];
  };

  const relevanceDimensions = getRelevanceDimensions();

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
        <BiCalculator size={14} />
        <BiInfoCircle size={14} />
      </Button>

      <Modal show={show} onHide={() => setShow(false)} size="lg" centered>
        <Modal.Header className="border-bottom">
          <div className="d-flex align-items-center gap-2">
            <BiCalculator className="text-primary" size={20} />
            <Modal.Title className="fs-5">评分详情</Modal.Title>
          </div>
          <Button variant="light" className="border-0" onClick={() => setShow(false)}>
            <BiX size={22} />
          </Button>
        </Modal.Header>

        <Modal.Body className="p-0">
          {/* 顶部总分展示 */}
          <div className="bg-light p-4 border-bottom">
            <div className="row align-items-center">
              <div className="col-md-6 text-center border-end">
                <div className="text-muted small mb-1">个性化推荐总分</div>
                <div className="display-5 fw-bold" style={{ color: getScoreColor(personalizedScore || 0) }}>
                  {personalizedScore != null ? personalizedScore.toFixed(1) : '—'}
                </div>
                <div className="text-muted small mt-1">满分 100</div>
              </div>
              <div className="col-md-6 text-center">
                <div className="text-muted small mb-1">检索相关性得分</div>
                <div className="display-5 fw-bold" style={{ color: getScoreColor(relevanceScore || 0) }}>
                  {relevanceScore != null ? relevanceScore.toFixed(1) : '—'}
                </div>
                <div className="text-muted small mt-1">满分 100</div>
              </div>
            </div>
          </div>

          {/* Tab 切换 */}
          <div className="border-bottom">
            <div className="d-flex">
              <button
                className={`btn btn-link text-decoration-none flex-fill py-3 fw-semibold ${activeTab === 'personalized' ? 'text-primary border-bottom border-3 border-primary' : 'text-muted'}`}
                onClick={() => setActiveTab('personalized')}
              >
                📊 个性化评分 (4 维加权)
              </button>
              <button
                className={`btn btn-link text-decoration-none flex-fill py-3 fw-semibold ${activeTab === 'relevance' ? 'text-primary border-bottom border-3 border-primary' : 'text-muted'}`}
                onClick={() => setActiveTab('relevance')}
              >
                🔍 检索评分 (6 维加权)
              </button>
            </div>
          </div>

          <div className="p-4">
            {activeTab === 'personalized' && (
              <div>
                {/* 个性化评分公式 */}
                <div className="alert alert-primary d-flex align-items-start gap-2 py-2 mb-4" style={{ fontSize: '0.85rem' }}>
                  <BiInfoCircle size={16} className="flex-shrink-0 mt-0.5" />
                  <div>
                    <strong>计算公式：</strong>
                    总分 = 质量得分 × 40% + 专业相关 × 30% + 学术匹配 × 20% + 技术匹配 × 10%
                  </div>
                </div>

                {/* 维度 1: 基础质量 */}
                <div className="mb-4">
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <span className="fw-semibold">📋 基础质量得分</span>
                    <Badge bg="primary">权重 40%</Badge>
                  </div>
                  <div className="bg-white border rounded-3 p-3">
                    {qualityEstimate.breakdown.map((item, i) => (
                      <div key={i} className="mb-2">
                        <div className="d-flex justify-content-between small mb-1">
                          <span className="text-muted">{item.label} <span className="text-muted">— {item.detail}</span></span>
                          <span className="fw-medium" style={{ color: getScoreColor(item.points / item.max * 100) }}>
                            +{item.points}/{item.max}
                          </span>
                        </div>
                        <ProgressBar
                          now={(item.points / item.max) * 100}
                          variant={getBarVariant((item.points / item.max) * 100)}
                          style={{ height: '4px' }}
                        />
                      </div>
                    ))}
                    <div className="border-top pt-2 mt-2 d-flex justify-content-between">
                      <span className="fw-semibold small">质量得分小计</span>
                      <span className="fw-bold" style={{ color: getScoreColor(qualityEstimate.total) }}>
                        {qualityEstimate.total.toFixed(1)} / 100
                      </span>
                    </div>
                    <div className="text-muted small mt-1">
                      → 加权后: {(qualityEstimate.total * 0.4).toFixed(1)} 分 (× 0.4)
                    </div>
                  </div>
                </div>

                {/* 维度 2: 专业相关性 */}
                <div className="mb-4">
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <span className="fw-semibold">🎯 专业相关性得分</span>
                    <Badge bg="info">权重 30%</Badge>
                  </div>
                  <div className="bg-white border rounded-3 p-3">
                    <Table borderless size="sm" className="mb-2">
                      <tbody>
                        <tr>
                          <td className="text-muted" style={{ width: '40%' }}>标题关键词匹配</td>
                          <td>+15 / 个</td>
                          <td className="text-muted" style={{ width: '40%' }}>摘要关键词匹配</td>
                          <td>+10 / 个</td>
                        </tr>
                        <tr>
                          <td className="text-muted">专业名称直接匹配（标题）</td>
                          <td>+20</td>
                          <td className="text-muted">专业名称直接匹配（摘要）</td>
                          <td>+15</td>
                        </tr>
                      </tbody>
                    </Table>
                    <div className="text-muted small">
                      预定义专业方向：胸部影像、腹部影像、神经影像、骨关节影像、心血管影像
                    </div>
                    <div className="mt-2 p-2 bg-light rounded small">
                      <strong>当前专业：</strong>{userProfile?.specialty || '未设置'}
                      {userProfile?.specialty ? (
                        <span className="text-muted ms-2">→ 关键词库已匹配</span>
                      ) : (
                        <span className="text-warning ms-2">→ 未设置专业，默认 50 分</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* 维度 3: 学术水平 */}
                <div className="mb-4">
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <span className="fw-semibold">🎓 学术水平匹配得分</span>
                    <Badge bg="warning">权重 20%</Badge>
                  </div>
                  <div className="bg-white border rounded-3 p-3">
                    <Table borderless size="sm" className="mb-0">
                      <thead className="table-light">
                        <tr>
                          <th>学历</th>
                          <th>偏好加分</th>
                          <th>惩罚减分</th>
                        </tr>
                      </thead>
                      <tbody className="small">
                        <tr>
                          <td>本科生</td>
                          <td className="text-success">综述 +20, 病例 +15</td>
                          <td className="text-danger">ML -10, DL -15</td>
                        </tr>
                        <tr>
                          <td>研究生</td>
                          <td className="text-success">RCT +20, 临床试验 +15, ML +10</td>
                          <td className="text-muted">—</td>
                        </tr>
                        <tr>
                          <td>博士</td>
                          <td className="text-success">DL +20, AI +20, ML +15</td>
                          <td className="text-muted">—</td>
                        </tr>
                      </tbody>
                    </Table>
                    <div className="mt-2 p-2 bg-light rounded small">
                      <strong>当前学历：</strong>{userProfile?.academic_level || '未设置'}
                      <span className="text-muted ms-2">基础分 50 分</span>
                    </div>
                  </div>
                </div>

                {/* 维度 4: 技术背景 */}
                <div className="mb-2">
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <span className="fw-semibold">💻 技术背景匹配得分</span>
                    <Badge bg="secondary">权重 10%</Badge>
                  </div>
                  <div className="bg-white border rounded-3 p-3">
                    <Table borderless size="sm" className="mb-0">
                      <thead className="table-light">
                        <tr>
                          <th>背景</th>
                          <th>加分项</th>
                          <th>减分项</th>
                        </tr>
                      </thead>
                      <tbody className="small">
                        <tr>
                          <td>统计基础</td>
                          <td className="text-success">基础统计 +10</td>
                          <td className="text-danger">多元回归 -10</td>
                        </tr>
                        <tr>
                          <td>统计高级</td>
                          <td className="text-success">多元回归 +15, ML +10</td>
                          <td className="text-muted">—</td>
                        </tr>
                        <tr>
                          <td>AI 基础</td>
                          <td className="text-success">ML +10</td>
                          <td className="text-danger">DL -5</td>
                        </tr>
                        <tr>
                          <td>AI 熟悉/掌握</td>
                          <td className="text-success">DL +20, ML +15, NN +15</td>
                          <td className="text-muted">—</td>
                        </tr>
                      </tbody>
                    </Table>
                    <div className="mt-2 p-2 bg-light rounded small">
                      <strong>当前背景：</strong>
                      统计 {userProfile?.stats_background || '未设置'} / AI {userProfile?.ai_background || '未设置'}
                      <span className="text-muted ms-2">基础分 50 分</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'relevance' && (
              <div>
                {/* 检索评分公式 */}
                <div className="alert alert-info d-flex align-items-start gap-2 py-2 mb-4" style={{ fontSize: '0.85rem' }}>
                  <BiInfoCircle size={16} className="flex-shrink-0 mt-0.5" />
                  <div>
                    <strong>计算公式（literature_search.py v2）：</strong>
                    总分 = 标题匹配 × 25% + 摘要匹配 × 25% + MeSH匹配 × 15% + 时效性 × 15% + 期刊质量 × 10% + 引用影响 × 10% + 加分项
                  </div>
                </div>

                {relevanceDimensions.map((dim, i) => (
                  <div key={i} className="mb-3">
                    <div className="d-flex justify-content-between align-items-center mb-1">
                      <span className="fw-medium small">{dim.label}</span>
                      <div className="d-flex align-items-center gap-2">
                        <Badge bg="light" text="dark" className="fw-normal">{dim.weight}</Badge>
                        {dim.score !== null ? (
                          <span className="fw-bold" style={{ color: getScoreColor(dim.score) }}>
                            {dim.score.toFixed(1)}
                          </span>
                        ) : (
                          <span className="text-muted small">N/A</span>
                        )}
                      </div>
                    </div>
                    {dim.score !== null && (
                      <ProgressBar
                        now={dim.score}
                        variant={getBarVariant(dim.score)}
                        style={{ height: '6px' }}
                      />
                    )}
                    <div className="text-muted" style={{ fontSize: '0.75rem' }}>{dim.detail}</div>
                  </div>
                ))}

                {/* 加分项说明 */}
                <div className="mt-3 p-3 bg-success bg-opacity-10 rounded-3 border">
                  <h6 className="fw-semibold mb-2">✨ 加分项</h6>
                  <ul className="small mb-0 ps-3">
                    <li>开放获取 (OA) / PMC 来源：<strong>+3 分</strong></li>
                    <li>策略匹配（核心文献/最新进展/方法学等）：额外加分</li>
                  </ul>
                </div>

                {/* 时效性衰减公式 */}
                <div className="mt-3 p-3 bg-warning bg-opacity-10 rounded-3 border">
                  <h6 className="fw-semibold mb-2">📅 时效性衰减公式</h6>
                  <div className="small font-monospace bg-white p-2 rounded border">
                    score = 100 × e<sup>(-0.15 × 年差)</sup>
                  </div>
                  <div className="small text-muted mt-2">
                    发表越近得分越高。1年前 ≈ 86分，3年前 ≈ 64分，5年前 ≈ 47分，10年前 ≈ 22分
                  </div>
                </div>
              </div>
            )}
          </div>
        </Modal.Body>

        <Modal.Footer className="border-top">
          <small className="text-muted me-auto">
            评分由后端 pubmed_recommendation_system.py 和 literature_search.py 计算
          </small>
          <Button variant="secondary" size="sm" onClick={() => setShow(false)}>
            关闭
          </Button>
        </Modal.Footer>
      </Modal>
    </>
  );
}

export default ScoreBreakdown;
