import React, { useState, useEffect } from 'react';
import { Card, Button, Alert, Container, Spinner, Form } from 'react-bootstrap';
import { useParams } from 'react-router-dom';
import apiClient from '../config';

function ShareView() {
  const { shareCode } = useParams();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [requirePassword, setRequirePassword] = useState(false);
  const [password, setPassword] = useState('');
  const [viewCount, setViewCount] = useState(0);

  useEffect(() => { fetchSharedPlan(); }, [shareCode]);

  const fetchSharedPlan = async (pwd = '') => {
    try {
      setLoading(true);
      const method = pwd ? 'post' : 'get';
      const config = { method, url: `/api/share/${shareCode}` };
      if (pwd) config.data = { password: pwd };
      const res = await apiClient(config);
      if (res.data.success) {
        setPlan(res.data.plan);
        setViewCount(res.data.share_info?.view_count || 0);
        setRequirePassword(false);
      } else if (res.data.require_password) {
        setRequirePassword(true);
      }
    } catch (err) {
      if (err.response?.status === 401) {
        setRequirePassword(true);
        setError('密码错误');
      } else if (err.response?.status === 410) {
        setError('分享链接已过期');
      } else {
        setError(err.response?.data?.error || '无法访问该分享链接');
      }
    } finally { setLoading(false); }
  };

  const handlePasswordSubmit = (e) => {
    e.preventDefault();
    fetchSharedPlan(password);
  };

  const fieldNameMapping = {
    title: '研究题目', background: '研究背景', clinical_problem: '临床问题',
    scientific_problem: '科学问题', hypothesis: '研究假设', objectives: '研究目标',
    study_design: '研究设计', subjects_criteria: '研究对象与纳排标准',
    variables_endpoints: '变量与终点', statistical_analysis: '统计分析方案',
    innovation: '创新点', risks_alternatives: '风险与备选方案', timeline: '实施时间表'
  };

  if (loading) return (<Container className="mt-5 text-center"><Spinner animation="border" /><p className="mt-2">加载中...</p></Container>);

  if (requirePassword) return (
    <Container className="mt-5" style={{ maxWidth: 400 }}>
      <Card>
        <Card.Body>
          <h5 className="text-center mb-3">🔒 此分享需要密码</h5>
          {error && <Alert variant="danger">{error}</Alert>}
          <Form onSubmit={handlePasswordSubmit}>
            <Form.Group className="mb-3">
              <Form.Control type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="请输入访问密码" />
            </Form.Group>
            <Button variant="primary" type="submit" className="w-100">查看方案</Button>
          </Form>
        </Card.Body>
      </Card>
    </Container>
  );

  if (error) return (<Container className="mt-4"><Alert variant="danger">{error}</Alert></Container>);

  if (!plan) return null;

  const content = plan.content || {};

  return (
    <Container className="mt-4" style={{ maxWidth: 900 }}>
      <Card>
        <Card.Header className="d-flex justify-content-between align-items-center">
          <div>
            <h4 className="mb-0">{plan.title || '研究方案'}</h4>
            <small className="text-muted">分享浏览 | 已查看 {viewCount} 次</small>
          </div>
          <span className="badge bg-success">多智能体生成</span>
        </Card.Header>
        <Card.Body>
          {Object.entries(fieldNameMapping).map(([key, label]) => {
            const value = content[key];
            if (!value || typeof value !== 'string' || !value.trim() || value.includes('待补充')) return null;
            return (
              <div key={key} className="mb-4">
                <h6 className="text-primary border-bottom pb-2">{label}</h6>
                <p style={{ whiteSpace: 'pre-wrap', lineHeight: '1.8' }}>{value}</p>
              </div>
            );
          })}
        </Card.Body>
        <Card.Footer className="text-center text-muted small">
          本研究方案由放射学多智能体研究系统生成 | {new Date(plan.created_at).toLocaleDateString('zh-CN')}
        </Card.Footer>
      </Card>
    </Container>
  );
}

export default ShareView;
