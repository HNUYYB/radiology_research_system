import React from 'react';
import { Card, Badge, Row, Col } from 'react-bootstrap';
import { BiFile, BiTrendingUp, BiCheckCircle, BiError, BiBook, BiBulb } from 'react-icons/bi';

function EvidenceSummary({ evidenceData, loading = false }) {
  if (loading) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">加载中...</span>
        </div>
        <p className="mt-3 text-muted">正在加载证据综述...</p>
      </div>
    );
  }

  if (!evidenceData) {
    return (
      <Card className="border-0 shadow-sm">
        <Card.Body className="text-center py-5">
          <BiFile size={48} className="text-muted mb-3" />
          <h5 className="text-muted">暂无证据综述</h5>
          <p className="text-muted small">系统正在为您生成证据综述，请稍后再试</p>
        </Card.Body>
      </Card>
    );
  }

  // 解析证据数据
  const evidenceContent = typeof evidenceData === 'string'
    ? JSON.parse(evidenceData)
    : evidenceData;

  // 渲染证据章节
  const renderEvidenceSection = (section, title, icon, color = 'primary') => {
    if (!section || typeof section !== 'string') return null;

    return (
      <Card className="border-0 shadow-sm mb-4">
        <Card.Header className={`bg-${color} text-white border-0`}>
          <div className="d-flex align-items-center">
            {icon}
            <h5 className="mb-0 ms-2">{title}</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <div className="evidence-content">
            <pre className="mb-0" style={{
              whiteSpace: 'pre-wrap',
              lineHeight: '1.8',
              fontFamily: 'inherit',
              fontSize: '0.95rem',
              color: '#495057'
            }}>
              {section}
            </pre>
          </div>
        </Card.Body>
      </Card>
    );
  };

  // 渲染关键点
  const renderKeyPoints = (points) => {
    if (!Array.isArray(points) || points.length === 0) return null;

    return (
      <Card className="border-0 shadow-sm mb-4">
        <Card.Header className="bg-success text-white border-0">
          <div className="d-flex align-items-center">
            <BiCheckCircle size={20} />
            <h5 className="mb-0 ms-2">关键发现</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <ul className="list-unstyled">
            {points.map((point, index) => (
              <li key={index} className="mb-3 d-flex align-items-start">
                <Badge bg="success" className="me-3 mt-1 flex-shrink-0">
                  {index + 1}
                </Badge>
                <span className="text-dark">{point}</span>
              </li>
            ))}
          </ul>
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
        <Card className="border-0 shadow-sm mb-4">
          <Card.Header className="bg-warning text-dark border-0">
            <div className="d-flex align-items-center">
              <BiError size={20} />
              <h5 className="mb-0 ms-2">研究空白</h5>
            </div>
          </Card.Header>
          <Card.Body>
            <ul className="list-unstyled">
              {gapItems.map((gap, index) => (
                <li key={index} className="mb-3 d-flex align-items-start">
                  <Badge bg="warning" text="dark" className="me-3 mt-1 flex-shrink-0">
                    {index + 1}
                  </Badge>
                  <span className="text-dark">{gap}</span>
                </li>
              ))}
            </ul>
          </Card.Body>
        </Card>
      );
    }

    // 处理数组格式的研究空白（向后兼容）
    if (!Array.isArray(gaps) || gaps.length === 0) return null;

    return (
      <Card className="border-0 shadow-sm mb-4">
        <Card.Header className="bg-warning text-dark border-0">
          <div className="d-flex align-items-center">
            <BiError size={20} />
            <h5 className="mb-0 ms-2">研究空白</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <ul className="list-unstyled">
            {gaps.map((gap, index) => (
              <li key={index} className="mb-3 d-flex align-items-start">
                <Badge bg="warning" text="dark" className="me-3 mt-1 flex-shrink-0">
                  {index + 1}
                </Badge>
                <span className="text-dark">{gap}</span>
              </li>
            ))}
          </ul>
        </Card.Body>
      </Card>
    );
  };

  // 渲染临床意义
  const renderClinicalImplications = (implications) => {
    if (!Array.isArray(implications) || implications.length === 0) return null;

    return (
      <Card className="border-0 shadow-sm mb-4">
        <Card.Header className="bg-info text-white border-0">
          <div className="d-flex align-items-center">
            <BiBulb size={20} />
            <h5 className="mb-0 ms-2">临床意义</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <ul className="list-unstyled">
            {implications.map((implication, index) => (
              <li key={index} className="mb-3 d-flex align-items-start">
                <Badge bg="info" className="me-3 mt-1 flex-shrink-0">
                  {index + 1}
                </Badge>
                <span className="text-dark">{implication}</span>
              </li>
            ))}
          </ul>
        </Card.Body>
      </Card>
    );
  };

  // 渲染证据强度
  const renderEvidenceStrength = (strength) => {
    if (!strength) return null;

    const getStrengthColor = (level) => {
      switch (level?.toLowerCase()) {
        case 'high': return 'success';
        case 'medium': return 'warning';
        case 'low': return 'danger';
        default: return 'secondary';
      }
    };

    const getStrengthText = (level) => {
      switch (level?.toLowerCase()) {
        case 'high': return '高质量';
        case 'medium': return '中等质量';
        case 'low': return '低质量';
        default: return '待评估';
      }
    };

    return (
      <Card className="border-0 shadow-sm mb-4">
        <Card.Header className="bg-primary text-white border-0">
          <div className="d-flex align-items-center">
            <BiTrendingUp size={20} />
            <h5 className="mb-0 ms-2">证据强度评估</h5>
          </div>
        </Card.Header>
        <Card.Body>
          <Row>
            <Col md={6}>
              <div className="d-flex align-items-center mb-3">
                <strong className="me-3">总体强度:</strong>
                <Badge bg={getStrengthColor(strength.overall)} className="fs-6">
                  {getStrengthText(strength.overall)}
                </Badge>
              </div>
            </Col>
            {strength.rationale && (
              <Col md={12}>
                <div className="bg-light p-3 rounded">
                  <strong className="text-primary">评估依据:</strong>
                  <p className="mb-0 mt-2">{strength.rationale}</p>
                </div>
              </Col>
            )}
          </Row>
        </Card.Body>
      </Card>
    );
  };

  return (
    <div className="evidence-summary">
      {/* 概览卡片 */}
      <Card className="border-0 shadow-sm mb-4">
        <Card.Body className="bg-gradient bg-light">
          <div className="d-flex align-items-center mb-3">
            <BiBook size={32} className="text-primary me-3" />
            <div>
              <h4 className="mb-1 fw-bold">📊 证据综述</h4>
              <p className="text-muted mb-0 small">
                AI基于最新文献生成的智能分析和评估
              </p>
            </div>
          </div>
        </Card.Body>
      </Card>

      {/* 主要内容 */}
      {evidenceContent.key_findings &&
        renderKeyPoints(evidenceContent.key_findings)
      }

      {/* 如果数据结构简单，直接显示 */}
      {!evidenceContent.key_findings && typeof evidenceData === 'string' && (
        <Card className="border-0 shadow-sm">
          <Card.Body>
            <div className="evidence-content">
              <pre className="mb-0" style={{
                whiteSpace: 'pre-wrap',
                lineHeight: '1.8',
                fontFamily: 'inherit',
                fontSize: '0.95rem',
                color: '#495057'
              }}>
                {evidenceData}
              </pre>
            </div>
          </Card.Body>
        </Card>
      )}
    </div>
  );
}

export default EvidenceSummary;