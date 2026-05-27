import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Button, Table, Alert, Spinner, Modal, Badge, Form } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import apiClient from '../config';
import { saveAs } from 'file-saver';
import PlanCompare from '../components/PlanCompare';

function Dashboard() {
  const { user } = useAuth();
  const [researchPlans, setResearchPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedIds, setSelectedIds] = useState([]);
  const [showCompare, setShowCompare] = useState(false);
  const [compareData, setCompareData] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);

  useEffect(() => { fetchResearchPlans(); }, []);

  const fetchResearchPlans = async () => {
    try {
      const response = await apiClient.get(`/api/research/plans?user_id=${user.id}`);
      if (response.data.success) setResearchPlans(response.data.plans);
      else setError(response.data.error);
    } catch (err) { setError('获取研究方案失败'); }
    finally { setLoading(false); }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleCompare = async () => {
    if (selectedIds.length < 2) { alert('请至少选择2个方案'); return; }
    setCompareLoading(true);
    try {
      const res = await apiClient.post('/api/research/compare', { plan_ids: selectedIds });
      if (res.data.success) { setCompareData(res.data.comparison); setShowCompare(true); }
    } catch (err) { alert('对比失败'); }
    finally { setCompareLoading(false); }
  };

  const handleExportAll = async () => {
    if (researchPlans.length === 0) { alert('暂无方案可导出'); return; }
    try {
      const res = await apiClient.get('/api/research/export-all', { responseType: 'blob' });
      saveAs(new Blob([res.data], { type: 'application/zip' }), '研究方案合集.zip');
    } catch (err) { alert('批量导出失败'); }
  };

  if (loading) return (<div className="text-center mt-5"><Spinner animation="border" variant="primary" /><p className="mt-2">加载中...</p></div>);

  return (
    <div className="mt-4">
      <Row className="mb-4">
        <Col>
          <h2>欢迎回来，{user.username}！</h2>
          <p className="text-muted">
            {user.user_type === 'student' ? '研究生' : user.user_type === 'expert' ? '评审专家' : '管理员'} |
            {user.grade && ` ${user.grade}`}{user.specialty && ` | ${user.specialty}方向`}
          </p>
        </Col>
      </Row>

      <Row className="mb-4">
        <Col md={4}>
          <Card className="text-center">
            <Card.Body>
              <h3 className="text-success">{researchPlans.length}</h3>
              <p className="text-muted mb-0">智能体生成方案</p>
            </Card.Body>
          </Card>
        </Col>
        <Col md={4}>
          <Card className="text-center">
            <Card.Body>
              <div className="d-flex justify-content-center gap-2">
                <Button variant="outline-primary" size="sm" as={Link} to="/research-input">➕ 创建新方案</Button>
                <Button variant="outline-dark" size="sm" onClick={handleExportAll} disabled={researchPlans.length === 0}>📦 批量导出</Button>
              </div>
              <p className="text-muted small mb-0 mt-2">选中方案后可对比分析</p>
            </Card.Body>
          </Card>
        </Col>
        <Col md={4}>
          <Card className="text-center hover-lift">
            <Card.Body>
              <Link to="/literature-demo" className="text-decoration-none">
                <h3 className="text-info">📚</h3>
                <p className="text-muted mb-0">文献推荐</p>
              </Link>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {selectedIds.length > 0 && (
        <Row className="mb-3">
          <Col>
            <Card className="py-2 px-3 d-flex flex-row align-items-center justify-content-between">
              <span>已选择 <Badge bg="primary">{selectedIds.length}</Badge> 个方案</span>
              <div className="d-flex gap-2">
                <Button variant="outline-secondary" size="sm" onClick={() => setSelectedIds([])}>取消选择</Button>
                <Button variant="primary" size="sm" onClick={handleCompare} disabled={selectedIds.length < 2 || compareLoading}>
                  {compareLoading ? '对比中...' : '🔍 对比方案'}
                </Button>
              </div>
            </Card>
          </Col>
        </Row>
      )}

      <Row>
        <Col>
          <Card>
            <Card.Header className="d-flex justify-content-between align-items-center">
              <h5 className="mb-0">我的研究方案</h5>
              <Button as={Link} to="/research-input" variant="primary" size="sm">创建新方案</Button>
            </Card.Header>
            <Card.Body>
              {error && <Alert variant="danger">{error}</Alert>}
              {researchPlans.length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-muted">您还没有创建任何研究方案</p>
                  <Button as={Link} to="/research-input" variant="outline-primary">创建第一个研究方案</Button>
                </div>
              ) : (
                <Table responsive hover>
                  <thead><tr>
                    <th style={{ width: 40 }}></th>
                    <th>标题</th>
                    <th>类型</th>
                    <th>创建时间</th>
                    <th>操作</th>
                  </tr></thead>
                  <tbody>
                    {researchPlans.map((plan) => (
                      <tr key={plan.id} className={selectedIds.includes(plan.id) ? 'table-primary' : ''}>
                        <td>
                          <Form.Check type="checkbox" checked={selectedIds.includes(plan.id)}
                            onChange={() => toggleSelect(plan.id)} />
                        </td>
                        <td>{plan.title || '未命名方案'}</td>
                        <td><Badge bg="success">多智能体</Badge></td>
                        <td>{new Date(plan.created_at).toLocaleDateString('zh-CN')}</td>
                        <td>
                          <Button as={Link} to={`/plan/${plan.id}`} variant="outline-primary" size="sm">查看</Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      {user.user_type === 'student' && (
        <Row className="mt-4">
          <Col>
            <Card><Card.Header><h5>快速操作</h5></Card.Header>
              <Card.Body><Row>
                <Col md={3}><Button as={Link} to="/api-settings" variant="outline-dark" className="w-100 mb-2">⚙️ API 设置</Button></Col>
                <Col md={3}><Button as={Link} to="/profile-setup" variant="outline-secondary" className="w-100 mb-2">完善个人资料</Button></Col>
                <Col md={3}><Button as={Link} to="/research-input" variant="outline-primary" className="w-100 mb-2">生成研究方案</Button></Col>
                <Col md={3}><Button as={Link} to="/literature-demo" variant="outline-info" className="w-100 mb-2">📚 文献检索</Button></Col>
              </Row></Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      {/* 方案对比 Modal */}
      <PlanCompare show={showCompare} onHide={() => { setShowCompare(false); setSelectedIds([]); }} data={compareData} />
    </div>
  );
}

export default Dashboard;
