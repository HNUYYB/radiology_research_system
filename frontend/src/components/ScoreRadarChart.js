import React, { useRef, useEffect } from 'react';
import { Card, Row, Col, Badge, ProgressBar } from 'react-bootstrap';

const ScoreRadarChart = ({ critique }) => {
  const canvasRef = useRef(null);

  // ── 从 critique 数据提取各维度评分（统一为 0-5 分制）──
  const extractScores = () => {
    if (!critique) return null;

    // AI 返回的 overall_assessment.score 是 0-100，转为 0-5
    const to5 = (score100) => Math.min(5, Math.max(0, Number(score100) / 20));

    // 文字描述 → 分数映射
    const textToScore = (text) => {
      if (!text) return null;
      const s = String(text);
      if (s.includes('优秀') || s.includes('高') || s.includes('强') || s.includes('充分')) return 4;
      if (s.includes('良好') || s.includes('中等') || s.includes('基本')) return 3;
      if (s.includes('不足') || s.includes('弱') || s.includes('低') || s.includes('缺乏')) return 1.5;
      if (s.includes('需要改进') || s.includes('较差')) return 1;
      return null;
    };

    // boolean → 分数
    const boolToScore = (val) => {
      if (val === true) return 4;
      if (val === false) return 1.5;
      return null;
    };

    const scores = [];

    // 1. 综合评分：直接从 overall_assessment.score（0-100）转换
    const overallScore = critique?.overall_assessment?.score;
    if (overallScore !== undefined && overallScore !== null) {
      scores.push({ label: '综合评分', score: to5(overallScore), max: 5 });
    }

    // 2. 可行性：从 feasibility_analysis 各子项综合
    const fa = critique?.feasibility_analysis;
    if (fa) {
      const feasVals = [
        textToScore(fa.technical_feasibility),
        textToScore(fa.resource_feasibility),
        textToScore(fa.time_feasibility),
        textToScore(fa.ethical_feasibility),
      ].filter(v => v !== null);
      if (feasVals.length > 0) {
        scores.push({ label: '可行性', score: feasVals.reduce((a, b) => a + b, 0) / feasVals.length, max: 5 });
      }
    }

    // 3. 创新性：从 innovation_assessment 综合
    const ia = critique?.innovation_assessment;
    if (ia) {
      const innoVals = [
        textToScore(ia.novelty_level),
        boolToScore(ia.innovation_authentic),
        textToScore(ia.clinical_value),
        textToScore(ia.technical_advancement),
      ].filter(v => v !== null);
      if (innoVals.length > 0) {
        scores.push({ label: '创新性', score: innoVals.reduce((a, b) => a + b, 0) / innoVals.length, max: 5 });
      }
    }

    // 4. 方法学：从 methodology_evaluation 综合
    const me = critique?.methodology_evaluation;
    if (me) {
      const methVals = [
        textToScore(me.study_design_adequacy),
        textToScore(me.sample_size_rationale),
        textToScore(me.statistical_appropriateness),
        textToScore(me.bias_control),
        textToScore(me.statistical_closure),
      ].filter(v => v !== null);
      if (methVals.length > 0) {
        scores.push({ label: '方法学', score: methVals.reduce((a, b) => a + b, 0) / methVals.length, max: 5 });
      }
    }

    // 5. 终点清晰度：从 endpoint_clarity 综合
    const ec = critique?.endpoint_clarity;
    if (ec) {
      const endVals = [
        boolToScore(ec.primary_endpoint_clear),
        boolToScore(ec.secondary_endpoints_clear),
        boolToScore(ec.endpoint_measurable),
        boolToScore(ec.endpoint_hypothesis_aligned),
      ].filter(v => v !== null);
      if (endVals.length > 0) {
        scores.push({ label: '终点清晰度', score: endVals.reduce((a, b) => a + b, 0) / endVals.length, max: 5 });
      }
    }

    // 6. 逻辑链：从 logical_chain_complete
    const lc = critique?.logical_chain_complete;
    if (lc !== undefined) {
      scores.push({ label: '逻辑链', score: boolToScore(lc), max: 5 });
    }

    if (scores.length === 0) return null;

    const average = (scores.reduce((a, s) => a + s.score, 0) / scores.length).toFixed(1);
    return { scores, average };
  };

  const data = extractScores();

  // 绘制雷达图
  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const size = 320;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    ctx.scale(dpr, dpr);

    const cx = size / 2, cy = size / 2, r = 110;
    const n = data.scores.length;
    if (n < 3) return; // 至少需要3个维度才能画雷达图
    const angleStep = (2 * Math.PI) / n;

    // 背景网格
    for (let level = 1; level <= 5; level++) {
      const lr = (r * level) / 5;
      ctx.beginPath();
      ctx.strokeStyle = level === 5 ? '#cccccc' : '#e8e8e8';
      ctx.lineWidth = 1;
      for (let i = 0; i <= n; i++) {
        const angle = i * angleStep - Math.PI / 2;
        const x = cx + lr * Math.cos(angle);
        const y = cy + lr * Math.sin(angle);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }

    // 轴线和标签
    ctx.font = '12px -apple-system, "Microsoft YaHei", sans-serif';
    ctx.textAlign = 'center';
    data.scores.forEach((s, i) => {
      const angle = i * angleStep - Math.PI / 2;
      ctx.beginPath();
      ctx.strokeStyle = '#dddddd';
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + r * Math.cos(angle), cy + r * Math.sin(angle));
      ctx.stroke();
      // 标签
      const labelR = r + 22;
      const lx = cx + labelR * Math.cos(angle);
      const ly = cy + labelR * Math.sin(angle);
      ctx.fillStyle = '#333333';
      ctx.fillText(s.label, lx, ly + 4);
      // 分数
      const scoreR = (r * s.score) / 5;
      const sx = cx + scoreR * Math.cos(angle);
      const sy = cy + scoreR * Math.sin(angle);
      ctx.fillStyle = '#16213e';
      ctx.font = 'bold 11px -apple-system, "Microsoft YaHei", sans-serif';
      ctx.fillText(s.score.toFixed(1), sx, sy - 8);
      ctx.font = '12px -apple-system, "Microsoft YaHei", sans-serif';
    });

    // 数据多边形
    ctx.beginPath();
    ctx.fillStyle = 'rgba(22, 33, 62, 0.15)';
    ctx.strokeStyle = '#16213e';
    ctx.lineWidth = 2;
    data.scores.forEach((s, i) => {
      const angle = i * angleStep - Math.PI / 2;
      const sr = (r * s.score) / 5;
      const x = cx + sr * Math.cos(angle);
      const y = cy + sr * Math.sin(angle);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // 数据点
    data.scores.forEach((s, i) => {
      const angle = i * angleStep - Math.PI / 2;
      const sr = (r * s.score) / 5;
      const x = cx + sr * Math.cos(angle);
      const y = cy + sr * Math.sin(angle);
      ctx.beginPath();
      ctx.fillStyle = '#e94560';
      ctx.arc(x, y, 4, 0, 2 * Math.PI);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  }, [data]);

  if (!data) {
    return (
      <div className="text-center py-5">
        <div className="text-muted mb-3" style={{ fontSize: '3rem' }}>📊</div>
        <h6 className="text-muted">暂无评分数据</h6>
        <p className="text-muted small">重新生成方案后，系统会自动进行批判评估并展示评分</p>
      </div>
    );
  }

  const getScoreColor = (score) => {
    if (score >= 4) return 'success';
    if (score >= 2.5) return 'warning';
    return 'danger';
  };

  const getScoreLabel = (score) => {
    if (score >= 4.5) return '优秀';
    if (score >= 3.5) return '良好';
    if (score >= 2.5) return '中等';
    if (score >= 1.5) return '较弱';
    return '需改进';
  };

  return (
    <Row>
      <Col md={7}>
        <div className="d-flex justify-content-center">
          <canvas ref={canvasRef} style={{ maxWidth: '100%', height: 'auto' }} />
        </div>
      </Col>
      <Col md={5}>
        <div className="d-flex flex-column justify-content-center h-100">
          {data.average && (
            <div className="text-center mb-4">
              <div className="display-4 fw-bold text-primary">{data.average}</div>
              <div className="text-muted">综合评分（满分5分）</div>
              <Badge bg={getScoreColor(Number(data.average))} className="mt-1">{getScoreLabel(Number(data.average))}</Badge>
            </div>
          )}
          <div className="mt-2">
            {data.scores.map((s, i) => (
              <div key={i} className="mb-3">
                <div className="d-flex justify-content-between align-items-center mb-1">
                  <span className="small fw-medium">{s.label}</span>
                  <Badge bg={getScoreColor(s.score)} pill>{s.score.toFixed(1)}</Badge>
                </div>
                <ProgressBar now={(s.score / 5) * 100} variant={getScoreColor(s.score)} style={{ height: '6px' }} />
              </div>
            ))}
          </div>
          {critique?.major_concerns?.length > 0 && (
            <div className="mt-3 p-3 bg-warning bg-opacity-10 rounded">
              <h6 className="text-warning">⚠️ 主要问题</h6>
              <ul className="small mb-0 ps-3">
                {critique.major_concerns.map((c, i) => (<li key={i}>{c}</li>))}
              </ul>
            </div>
          )}
          {critique?.improvement_suggestions?.length > 0 && (
            <div className="mt-3 p-3 bg-info bg-opacity-10 rounded">
              <h6 className="text-info">💡 改进建议</h6>
              <ul className="small mb-0 ps-3">
                {critique.improvement_suggestions.map((s, i) => (<li key={i}>{s}</li>))}
              </ul>
            </div>
          )}
        </div>
      </Col>
    </Row>
  );
};

export default ScoreRadarChart;
