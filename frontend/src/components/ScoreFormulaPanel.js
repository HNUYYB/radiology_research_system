import React, { useState } from 'react';
import { Card, Badge, Table, Button, Collapse } from 'react-bootstrap';
import { BiChevronDown, BiChevronUp, BiCalculator, BiBookOpen } from 'react-icons/bi';

/**
 * 评分公式说明面板
 *
 * 以可折叠面板形式展示文献推荐系统的完整评分体系说明，
 * 帮助用户理解推荐结果的排序依据。
 */
function ScoreFormulaPanel() {
  const [open, setOpen] = useState(false);

  return (
    <Card className="border-0 shadow-sm mt-4">
      <Card.Body className="p-0">
        {/* 折叠触发器 */}
        <button
          className="btn w-100 d-flex align-items-center justify-content-between p-3 text-start"
          onClick={() => setOpen(!open)}
          style={{ background: 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)' }}
        >
          <div className="d-flex align-items-center gap-2">
            <BiCalculator className="text-primary" size={18} />
            <span className="fw-semibold">📐 评分公式说明</span>
            <Badge bg="primary" pill>如何计算推荐分数？</Badge>
          </div>
          {open ? <BiChevronUp size={20} /> : <BiChevronDown size={20} />}
        </button>

        <Collapse in={open}>
          <div className="p-4">
            {/* 总览 */}
            <div className="alert alert-primary d-flex align-items-start gap-2 mb-4" style={{ fontSize: '0.9rem' }}>
              <BiBookOpen size={18} className="flex-shrink-0 mt-0.5" />
              <div>
                本系统使用 <strong>两套评分机制</strong> 为文献打分：
                <strong>检索评分</strong>（搜索阶段，基于关键词匹配）和
                <strong>个性化评分</strong>（推荐阶段，基于用户画像）。
                最终排序以个性化评分为准。
              </div>
            </div>

            {/* ═══ 第一套：检索评分 ═══ */}
            <h5 className="fw-bold mb-3">
              🔍 第一套：检索相关性评分
              <Badge bg="info" className="ms-2 fw-normal">literature_search.py</Badge>
            </h5>

            <div className="bg-light p-3 rounded-3 mb-3">
              <div className="fw-semibold mb-2">总分 = Σ (子项得分 × 权重) + 加分项</div>
              <Table bordered size="sm" className="bg-white mb-0">
                <thead className="table-light">
                  <tr>
                    <th>维度</th>
                    <th>权重</th>
                    <th>评分规则</th>
                    <th>满分</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>标题语义匹配</strong></td>
                    <td><Badge bg="primary">25%</Badge></td>
                    <td className="small text-muted">
                      完整 query 在标题中 → 90~100；关键词覆盖度 × 80；连续词组额外加分
                    </td>
                    <td>100</td>
                  </tr>
                  <tr>
                    <td><strong>摘要语义匹配</strong></td>
                    <td><Badge bg="primary">25%</Badge></td>
                    <td className="small text-muted">
                      关键词覆盖度 × 100；关键位置（首句/末句）加权
                    </td>
                    <td>100</td>
                  </tr>
                  <tr>
                    <td><strong>MeSH/关键词匹配</strong></td>
                    <td><Badge bg="info">15%</Badge></td>
                    <td className="small text-muted">
                      医学主题词 (MeSH) 精确匹配；作者关键词匹配
                    </td>
                    <td>100</td>
                  </tr>
                  <tr>
                    <td><strong>时效性</strong></td>
                    <td><Badge bg="info">15%</Badge></td>
                    <td className="small text-muted font-monospace">
                      100 × e<sup>(-0.15 × 年差)</sup> — 指数衰减
                    </td>
                    <td>100</td>
                  </tr>
                  <tr>
                    <td><strong>期刊质量</strong></td>
                    <td><Badge bg="secondary">10%</Badge></td>
                    <td className="small text-muted">
                      高影响期刊 (Radiology/Lancet/NEJM 等) → 100；中等 → 70；其他 → 50
                    </td>
                    <td>100</td>
                  </tr>
                  <tr>
                    <td><strong>引用影响力</strong></td>
                    <td><Badge bg="secondary">10%</Badge></td>
                    <td className="small text-muted">
                      ≥200次 → 100；≥100 → 85；≥50 → 70；≥20 → 50；≥5 → 30
                    </td>
                    <td>100</td>
                  </tr>
                  <tr className="table-success">
                    <td><strong>加分项</strong></td>
                    <td>—</td>
                    <td className="small text-muted">
                      开放获取 (OA) / PMC 来源 <strong>+3</strong>；策略匹配额外加分
                    </td>
                    <td>—</td>
                  </tr>
                </tbody>
              </Table>
            </div>

            {/* ═══ 第二套：个性化评分 ═══ */}
            <h5 className="fw-bold mb-3 mt-4">
              📊 第二套：个性化推荐评分
              <Badge bg="warning" text="dark" className="ms-2 fw-normal">pubmed_recommendation_system.py</Badge>
            </h5>

            <div className="bg-light p-3 rounded-3 mb-3">
              <div className="fw-semibold mb-2">
                总分 = 质量得分 × 40% + 专业相关 × 30% + 学术匹配 × 20% + 技术匹配 × 10%
              </div>

              {/* 维度 1 */}
              <div className="bg-white border rounded-3 p-3 mb-3">
                <div className="d-flex align-items-center gap-2 mb-2">
                  <Badge bg="primary" pill>× 40%</Badge>
                  <strong>📋 基础质量得分</strong>
                </div>
                <Table borderless size="sm" className="mb-0 small">
                  <tbody>
                    <tr><td className="text-muted" style={{ width: '30%' }}>影响因子</td><td>≥10 → +40 | ≥5 → +30 | ≥3 → +20 | ≥1 → +10</td></tr>
                    <tr><td className="text-muted">期刊质量</td><td>高影响期刊列表匹配 → +20</td></tr>
                    <tr><td className="text-muted">引用次数</td><td>≥100 → +20 | ≥50 → +15 | ≥20 → +10 | ≥5 → +5</td></tr>
                    <tr><td className="text-muted">时效性</td><td>2年内 → +15 | 5年内 → +10 | 10年内 → +5</td></tr>
                    <tr><td className="text-muted">研究类型</td><td>RCT +15 | Meta/系统综述 +12 | 临床试验 +10 | 综述 +8 | 病例 +3</td></tr>
                  </tbody>
                </Table>
              </div>

              {/* 维度 2 */}
              <div className="bg-white border rounded-3 p-3 mb-3">
                <div className="d-flex align-items-center gap-2 mb-2">
                  <Badge bg="info" pill>× 30%</Badge>
                  <strong>🎯 专业相关性得分</strong>
                </div>
                <div className="small text-muted mb-2">
                  根据用户专业（胸部/腹部/神经/骨关节/心血管影像），匹配预定义关键词库
                </div>
                <Table borderless size="sm" className="mb-0 small">
                  <tbody>
                    <tr><td className="text-muted" style={{ width: '30%' }}>标题关键词</td><td>+15 / 个</td></tr>
                    <tr><td className="text-muted">摘要关键词</td><td>+10 / 个</td></tr>
                    <tr><td className="text-muted">专业名称（标题）</td><td>+20</td></tr>
                    <tr><td className="text-muted">专业名称（摘要）</td><td>+15</td></tr>
                    <tr><td className="text-muted">未设置专业</td><td>默认 50 分</td></tr>
                  </tbody>
                </Table>
              </div>

              {/* 维度 3 */}
              <div className="bg-white border rounded-3 p-3 mb-3">
                <div className="d-flex align-items-center gap-2 mb-2">
                  <Badge bg="warning" text="dark" pill>× 20%</Badge>
                  <strong>🎓 学术水平匹配得分</strong>
                  <span className="text-muted small ms-auto">基础分 50</span>
                </div>
                <Table borderless size="sm" className="mb-0 small">
                  <thead className="table-light">
                    <tr>
                      <th>学历</th>
                      <th>加分</th>
                      <th>惩罚</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>本科生</td>
                      <td className="text-success">综述 +20, 病例 +15, 临床试验 +10</td>
                      <td className="text-danger">ML -10, DL -15</td>
                    </tr>
                    <tr>
                      <td>研究生</td>
                      <td className="text-success">RCT +20, 临床试验 +15, ML +10</td>
                      <td>—</td>
                    </tr>
                    <tr>
                      <td>博士</td>
                      <td className="text-success">DL +20, AI +20, ML +15</td>
                      <td>—</td>
                    </tr>
                  </tbody>
                </Table>
              </div>

              {/* 维度 4 */}
              <div className="bg-white border rounded-3 p-3 mb-2">
                <div className="d-flex align-items-center gap-2 mb-2">
                  <Badge bg="secondary" pill>× 10%</Badge>
                  <strong>💻 技术背景匹配得分</strong>
                  <span className="text-muted small ms-auto">基础分 50</span>
                </div>
                <Table borderless size="sm" className="mb-0 small">
                  <thead className="table-light">
                    <tr>
                      <th>背景</th>
                      <th>加分</th>
                      <th>惩罚</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>统计基础</td>
                      <td className="text-success">基础统计 +10</td>
                      <td className="text-danger">多元回归 -10</td>
                    </tr>
                    <tr>
                      <td>统计高级</td>
                      <td className="text-success">多元回归 +15, ML +10</td>
                      <td>—</td>
                    </tr>
                    <tr>
                      <td>AI 基础</td>
                      <td className="text-success">ML +10</td>
                      <td className="text-danger">DL -5</td>
                    </tr>
                    <tr>
                      <td>AI 熟悉/掌握</td>
                      <td className="text-success">DL +20, ML +15, 神经网络 +15</td>
                      <td>—</td>
                    </tr>
                  </tbody>
                </Table>
              </div>
            </div>

            {/* ═══ 高质量文献判定 ═══ */}
            <h5 className="fw-bold mb-3 mt-4">✅ 高质量文献判定标准</h5>
            <div className="bg-success bg-opacity-10 p-3 rounded-3 border mb-4">
              <div className="small">
                满足以下任一条件即为高质量文献：
                <ul className="mt-2 mb-0 ps-3">
                  <li>影响因子 ≥ 3.0</li>
                  <li>期刊在高影响期刊列表中（Radiology, Lancet, NEJM 等）</li>
                  <li>引用次数 ≥ 50</li>
                  <li>近 3 年发表且影响因子 ≥ 2.0</li>
                </ul>
              </div>
            </div>

            {/* ═══ 设计注意事项 ═══ */}
            <h5 className="fw-bold mb-3">⚠️ 设计注意事项</h5>
            <div className="bg-warning bg-opacity-10 p-3 rounded-3 border">
              <div className="small">
                <ul className="mb-0 ps-3">
                  <li><strong>本科生惩罚分：</strong>学术水平匹配中，本科生遇到 ML/DL 文献会被惩罚（-10/-15），
                    这是为了避免推荐过于复杂的方法学文献。但如果用户正在做 AI 相关研究，此惩罚可能与专业相关性得分冲突。</li>
                  <li><strong>估算值：</strong>前端展示的个性化评分子维度为前端估算，可能与后端实际值有偏差。
                    精确值以后端返回的 <code>personalized_score</code> 为准。</li>
                  <li><strong>关键词匹配局限：</strong>专业相关性基于预定义关键词库，未覆盖的研究方向可能得分偏低。</li>
                </ul>
              </div>
            </div>
          </div>
        </Collapse>
      </Card.Body>
    </Card>
  );
}

export default ScoreFormulaPanel;
