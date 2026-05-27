import React, { useState, useEffect, useRef } from 'react';
import { Card, Button, Alert, Container, Row, Col, Spinner, Tabs, Tab, Modal, Form, Badge, ListGroup } from 'react-bootstrap';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../config';
import { saveAs } from 'file-saver';
import { Document, Packer, Paragraph, TextRun, HeadingLevel } from 'docx';
import ModernEvidenceDisplay from '../components/ModernEvidenceDisplay';
// import ScoreRadarChart from '../components/ScoreRadarChart';
import VersionHistory from '../components/VersionHistory';
import ChatOptimizer from '../components/ChatOptimizer';

function PlanViewer() {
  const { planId } = useParams();
  const navigate = useNavigate();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);
  const [showRegenerateModal, setShowRegenerateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showVersionModal, setShowVersionModal] = useState(false);
  const [showChatModal, setShowChatModal] = useState(false);
  const [regenerateRequirements, setRegenerateRequirements] = useState('');
  const [editSection, setEditSection] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editRequirements, setEditRequirements] = useState('');
  const [sharePassword, setSharePassword] = useState('');
  const [shareDays, setShareDays] = useState(7);
  const [shareUrl, setShareUrl] = useState('');
  const [activeTab, setActiveTab] = useState('plan');

  useEffect(() => { fetchPlan(); }, [planId]);

  const fetchPlan = async () => {
    try {
      const response = await apiClient.get(`/api/research/plan/${planId}`);
      if (response.data.success) {
        setPlan(response.data.plan);
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      setError('获取研究方案失败');
    } finally {
      setLoading(false);
    }
  };

  // ── 导出 PDF（真正 PDF）──
  const exportToPDF = async () => {
    setExporting(true);
    try {
      const response = await apiClient.get(`/api/research/export-pdf/${planId}`, { responseType: 'blob' });
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const filename = `${plan.title || 'research_plan'}.pdf`.replace(/[<>:"/\\|?*]/g, '_');
      saveAs(blob, filename);
    } catch (err) {
      console.error('PDF导出失败:', err);
      alert(err.response?.data?.error || 'PDF导出失败');
    } finally {
      setExporting(false);
    }
  };

  // ── 导出 Word ──
  const exportToWord = async () => {
    setExporting(true);
    try {
      const planData = typeof plan.content === 'string' ? JSON.parse(plan.content) : plan.content;
      const literatureSection = [];
      if (plan.evidence_summary?.recommended_literature?.recommended_papers) {
        literatureSection.push(new Paragraph({ text: '推荐文献', heading: HeadingLevel.HEADING_2, spacing: { before: 400, after: 200 } }));
        plan.evidence_summary.recommended_literature.recommended_papers.forEach((paper, index) => {
          literatureSection.push(
            new Paragraph({ text: `${index + 1}. ${paper.title}`, spacing: { before: 100, after: 50 } }),
            new Paragraph({ children: [new TextRun({ text: `作者: ${paper.authors}\n`, break: 1 }), new TextRun({ text: `期刊: ${paper.journal} | 发表时间: ${paper.pubdate}\n`, break: 1 })], spacing: { after: 100 } })
          );
        });
      }
      const doc = new Document({ sections: [{ properties: {}, children: [
        new Paragraph({ text: plan.title || '研究方案', heading: HeadingLevel.HEADING_1, spacing: { after: 200 } }),
        ...Object.entries(planData).map(([key, value]) => {
          const fieldName = fieldNameMapping[key] || key;
          return [new Paragraph({ text: fieldName, heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 100 } }),
            new Paragraph({ children: [new TextRun({ text: value ? String(value) : '暂无内容', break: 1 })], spacing: { after: 200 } })];
        }).flat(),
        ...literatureSection,
      ]}]});
      const blob = await Packer.toBlob(doc);
      saveAs(blob, `${plan.title || '研究方案'}_含文献推荐.docx`);
    } catch (err) { console.error('Word导出失败:', err); alert('Word导出失败');
    } finally { setExporting(false); }
  };

  // ── 导出 LaTeX ──
  const exportToLatex = async () => {
    setExporting(true);
    try {
      const response = await apiClient.get(`/api/research/export-latex/${planId}`, { responseType: 'blob' });
      const blob = new Blob([response.data], { type: 'application/x-tex;charset=utf-8' });
      saveAs(blob, `${plan.title || 'research_plan'}.tex`.replace(/[<>:"/\\|?*]/g, '_'));
    } catch (err) { console.error('LaTeX导出失败:', err); alert('LaTeX导出失败');
    } finally { setExporting(false); }
  };

  // ── 导出 BibTeX ──
  const exportToBibTeX = async () => {
    setExporting(true);
    try {
      const response = await apiClient.get(`/api/research/export-bibtex/${planId}`, { responseType: 'blob' });
      const blob = new Blob([response.data], { type: 'application/x-bibtex;charset=utf-8' });
      saveAs(blob, `references_${planId}.bib`);
    } catch (err) {
      console.error('BibTeX导出失败:', err);
      alert(err.response?.data?.error || 'BibTeX导出失败');
    } finally { setExporting(false); }
  };

  // ── 创建分享链接 ──
  const handleCreateShare = async () => {
    try {
      const response = await apiClient.post(`/api/research/plan/${planId}/share`, {
        password: sharePassword || '',
        expire_days: parseInt(shareDays),
      });
      if (response.data.success) {
        setShareUrl(window.location.origin + response.data.share_url);
      }
    } catch (err) { alert('创建分享链接失败'); }
  };

  // ── 重新生成 ──
  const handleRegenerate = async () => {
    try {
      setLoading(true);
      setShowRegenerateModal(false);
      const response = await apiClient.post('/api/research/regenerate', {
        user_id: plan.user_id, plan_id: plan.id, modification_requirements: regenerateRequirements
      });
      if (response.data.success) {
        navigate(`/plan/${response.data.new_plan_id}`);
        alert('研究方案重新生成成功！');
      } else { alert(response.data.error || '重新生成失败'); }
    } catch (err) { alert('重新生成失败，请稍后重试');
    } finally { setLoading(false); setRegenerateRequirements(''); }
  };

  // ── 编辑优化 ──
  const handleEditAndRegenerate = async () => {
    try {
      setLoading(true);
      setShowEditModal(false);
      const response = await apiClient.post('/api/research/edit-and-regenerate', {
        user_id: plan.user_id, plan_id: plan.id,
        user_edits: { [editSection]: editContent },
        optimization_focus: editRequirements
      });
      if (response.data.success) {
        const newPlan = response.data.optimized_plan;
        setPlan(prev => ({
          ...prev,
          content: JSON.stringify(newPlan),
          title: newPlan.title || prev.title,
          updated_at: new Date().toISOString(),
        }));
        alert('研究方案编辑优化成功！');
      } else { alert(response.data.error || '编辑优化失败'); }
    } catch (err) { alert('编辑优化失败，请稍后重试');
    } finally { setLoading(false); setEditSection(''); setEditContent(''); setEditRequirements(''); }
  };

  // ── 对话式优化回调 ──
  const handleChatOptimize = (optimizedContent) => {
    setPlan(prev => ({
      ...prev,
      content: JSON.stringify(optimizedContent),
      title: optimizedContent.title || prev.title,
      updated_at: new Date().toISOString(),
    }));
    setActiveTab('plan');
  };

  const fieldNameMapping = {
    'user_input': '📝 我的研究需求', 'title': '研究题目', 'background': '研究背景',
    'clinical_problem': '临床问题', 'scientific_problem': '科学问题',
    'hypothesis': '研究假设', 'objectives': '研究目标',
    'study_design': '研究设计', 'subjects_criteria': '研究对象与纳排标准',
    'variables_endpoints': '变量与终点', 'statistical_analysis': '统计分析方案',
    'innovation': '创新点', 'risks_alternatives': '风险与备选方案', 'timeline': '实施时间表'
  };

  const renderPlanContent = (content) => {
    if (!content) return <p className="text-muted">暂无内容</p>;
    let planData;
    try {
      planData = typeof content === 'string' ? JSON.parse(content) : content;
      if (planData?.research_proposal && typeof planData.research_proposal === 'object') planData = planData.research_proposal;
    } catch (error) {
      return (<div className="alert alert-warning"><h6>内容显示异常</h6><pre style={{ whiteSpace: 'pre-wrap', maxHeight: '300px', overflow: 'auto' }}>{typeof content === 'string' ? content : JSON.stringify(content, null, 2)}</pre></div>);
    }
    const orderedKeys = [...(planData['user_input'] ? ['user_input'] : []), ...Object.keys(fieldNameMapping).filter(k => k !== 'user_input' && planData[k])];
    return (<div>
      {orderedKeys.map((key, index) => {
        const value = planData[key];
        if (!value || (typeof value === 'string' && value.trim() === '')) return null;
        const displayName = fieldNameMapping[key] || key;
        const isUserInput = key === 'user_input';
        return (<div key={key} className={`mb-4 ${isUserInput ? 'border-start border-4 border-info ps-3 bg-info bg-opacity-10 pe-3 py-2 rounded' : ''}`}>
          <h6 className={`${isUserInput ? 'text-info' : 'text-primary'} border-bottom pb-2`}><span>{displayName}</span></h6>
          <div className="ps-3">
            {typeof value === 'string' ? (<p style={{ whiteSpace: 'pre-wrap', lineHeight: '1.8' }}>{value}</p>) : (<pre className="bg-light p-3 rounded" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(value, null, 2)}</pre>)}
          </div>
        </div>);
      })}
    </div>);
  };

  if (loading) return (<div className="text-center mt-5"><Spinner animation="border" variant="primary" /><p className="mt-2">加载中...</p></div>);
  if (error) return (<Container className="mt-4"><Alert variant="danger">{error}</Alert><Button onClick={() => navigate('/')} variant="primary">返回首页</Button></Container>);

  // const critique = (() => { try { const c = plan.critique_feedback; return typeof c === 'string' ? JSON.parse(c) : (c || {}); } catch { return {}; } })();

  return (<>
    <Container className="mt-4">
      <Row><Col>
        <Card>
          <Card.Header className="d-flex justify-content-between align-items-center flex-wrap">
            <h4 className="mb-0 me-3">{plan.title || '研究方案'}</h4>
            <div className="d-flex flex-wrap gap-2">
              <Button variant="outline-primary" size="sm" onClick={exportToPDF} disabled={exporting}>{exporting ? '导出中...' : 'PDF'}</Button>
              <Button variant="outline-secondary" size="sm" onClick={exportToWord} disabled={exporting}>Word</Button>
              <Button variant="outline-dark" size="sm" onClick={exportToLatex} disabled={exporting}>LaTeX</Button>
              <Button variant="outline-info" size="sm" onClick={exportToBibTeX} disabled={exporting}>BibTeX</Button>
              <Button variant="outline-success" size="sm" onClick={() => setShowRegenerateModal(true)}>🔄 重新生成</Button>
              <Button variant="outline-warning" size="sm" onClick={() => setShowChatModal(true)}>💬 对话优化</Button>
              <Button variant="outline-info" size="sm" onClick={() => setShowEditModal(true)}>✏️ 编辑优化</Button>
              <Button variant="outline-secondary" size="sm" onClick={() => { setShareUrl(''); setShowShareModal(true); }}>🔗 分享</Button>
              <Button variant="outline-secondary" size="sm" onClick={() => setShowVersionModal(true)}>📋 版本历史</Button>
              <Button variant="secondary" size="sm" onClick={() => navigate('/')}>返回</Button>
            </div>
          </Card.Header>
          <Card.Body>
            <Tabs activeKey={activeTab} onSelect={setActiveTab} className="mb-3">
              <Tab eventKey="plan" title="研究方案">{renderPlanContent(plan.content)}</Tab>
              <Tab eventKey="evidence" title="证据综述"><ModernEvidenceDisplay evidenceData={plan.evidence_summary} loading={loading} /></Tab>
              {/* <Tab eventKey="scores" title="评分分析"><ScoreRadarChart critique={critique} /></Tab> */}
            </Tabs>
            <div className="mt-4 p-3 bg-light rounded">
              <small className="text-muted">
                <strong>创建时间:</strong> {new Date(plan.created_at).toLocaleString('zh-CN')} | <strong>方案类型:</strong> 多智能体生成 | <strong>最后更新:</strong> {new Date(plan.updated_at).toLocaleString('zh-CN')}
              </small>
            </div>
          </Card.Body>
        </Card>
      </Col></Row>
    </Container>

    {/* 重新生成 Modal */}
    <Modal show={showRegenerateModal} onHide={() => setShowRegenerateModal(false)} size="lg">
      <Modal.Header closeButton><Modal.Title>🔄 重新生成研究方案</Modal.Title></Modal.Header>
      <Modal.Body><Form><Form.Group className="mb-3">
        <Form.Label>修改要求</Form.Label>
        <Form.Control as="textarea" rows={4} value={regenerateRequirements} onChange={(e) => setRegenerateRequirements(e.target.value)} placeholder="请详细描述您希望修改的内容..." />
      </Form.Group></Form></Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={() => setShowRegenerateModal(false)}>取消</Button>
        <Button variant="primary" onClick={handleRegenerate} disabled={!regenerateRequirements.trim()}>开始重新生成</Button>
      </Modal.Footer>
    </Modal>

    {/* 编辑优化 Modal */}
    <Modal show={showEditModal} onHide={() => setShowEditModal(false)} size="lg">
      <Modal.Header closeButton><Modal.Title>✏️ 编辑优化研究方案</Modal.Title></Modal.Header>
      <Modal.Body><Form>
        <Form.Group className="mb-3">
          <Form.Label>选择要编辑的章节</Form.Label>
          <Form.Select value={editSection} onChange={(e) => { setEditSection(e.target.value); if (e.target.value) { const pd = typeof plan.content === 'string' ? JSON.parse(plan.content) : plan.content; setEditContent(pd[e.target.value] || ''); } }}>
            <option value="">请选择章节</option>
            {Object.keys(fieldNameMapping).map(key => (<option key={key} value={key}>{fieldNameMapping[key]}</option>))}
          </Form.Select>
        </Form.Group>
        {editSection && (<>
          <Form.Group className="mb-3"><Form.Label>当前内容</Form.Label><Form.Control as="textarea" rows={6} value={editContent} onChange={(e) => setEditContent(e.target.value)} /></Form.Group>
          <Form.Group className="mb-3"><Form.Label>优化要求</Form.Label><Form.Control as="textarea" rows={3} value={editRequirements} onChange={(e) => setEditRequirements(e.target.value)} placeholder="请描述您希望如何优化..." /></Form.Group>
        </>)}
      </Form></Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={() => setShowEditModal(false)}>取消</Button>
        <Button variant="primary" onClick={handleEditAndRegenerate} disabled={!editSection || !editContent.trim()}>应用修改</Button>
      </Modal.Footer>
    </Modal>

    {/* 分享 Modal */}
    <Modal show={showShareModal} onHide={() => setShowShareModal(false)}>
      <Modal.Header closeButton><Modal.Title>🔗 分享研究方案</Modal.Title></Modal.Header>
      <Modal.Body>
        {shareUrl ? (<>
          <Alert variant="success">分享链接已创建！</Alert>
          <Form.Group className="mb-3">
            <Form.Label>分享链接</Form.Label>
            <Form.Control value={shareUrl} readOnly onClick={(e) => e.target.select()} />
          </Form.Group>
          <Button variant="outline-primary" size="sm" onClick={() => { navigator.clipboard.writeText(shareUrl); alert('已复制到剪贴板'); }}>📋 复制链接</Button>
        </>) : (<>
          <Form.Group className="mb-3">
            <Form.Label>访问密码（可选）</Form.Label>
            <Form.Control type="text" value={sharePassword} onChange={(e) => setSharePassword(e.target.value)} placeholder="留空则无需密码" />
          </Form.Group>
          <Form.Group className="mb-3">
            <Form.Label>有效期</Form.Label>
            <Form.Select value={shareDays} onChange={(e) => setShareDays(e.target.value)}>
              <option value="1">1天</option><option value="3">3天</option>
              <option value="7">7天</option><option value="30">30天</option><option value="0">永久有效</option>
            </Form.Select>
          </Form.Group>
        </>)}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={() => setShowShareModal(false)}>关闭</Button>
        {!shareUrl && <Button variant="primary" onClick={handleCreateShare}>生成链接</Button>}
      </Modal.Footer>
    </Modal>

    {/* 版本历史 Modal */}
    <VersionHistory show={showVersionModal} onHide={() => setShowVersionModal(false)} planId={planId} onRestore={(newContent) => { setPlan(prev => ({ ...prev, content: JSON.stringify(newContent), title: newContent.title || prev.title, updated_at: new Date().toISOString() })); setShowVersionModal(false); setActiveTab('plan'); }} />

    {/* 对话式优化 Modal */}
    <ChatOptimizer show={showChatModal} onHide={() => setShowChatModal(false)} plan={plan} onOptimize={handleChatOptimize} />
  </>);
}

export default PlanViewer;
