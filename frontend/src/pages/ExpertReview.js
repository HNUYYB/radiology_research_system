import React, { useState, useEffect } from 'react';
import { Card, Form, Button, Alert, Container, Row, Col, Spinner, Table } from 'react-bootstrap';
import { useAuth } from '../contexts/AuthContext';
import apiClient from '../config';

function ExpertReview() {
  const { user } = useAuth();
  const [assignments, setAssignments] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [reviewData, setReviewData] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    fetchAssignments();
  }, []);

  const fetchAssignments = async () => {
    try {
      const response = await apiClient.get(`/api/review/assignments?expert_id=${user.id}`);
      if (response.data.success) {
        setAssignments(response.data.assignments);
      }
    } catch (err) {
      setError('获取评审任务失败');
    } finally {
      setLoading(false);
    }
  };

  const selectPlan = async (planId) => {
    try {
      const response = await apiClient.get(`/api/review/plan/${planId}`);
      if (response.data.success) {
        setSelectedPlan(response.data.plan);
        setReviewData({});
        setError('');
        setSuccess('');
      }
    } catch (err) {
      setError('获取方案详情失败');
    }
  };

  const handleReviewChange = (field, value) => {
    setReviewData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const calculateTotalScore = () => {
    const scores = [
      reviewData.clinical_significance,
      reviewData.innovation,
      reviewData.relevance,
      reviewData.feasibility,
      reviewData.methodology,
      reviewData.publication_potential
    ];

    const validScores = scores.filter(score => score !== undefined && score !== null);
    if (validScores.length === 0) return null;

    return (validScores.reduce((sum, score) => sum + score, 0) / validScores.length).toFixed(1);
  };

  const submitReview = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    setSuccess('');

    try {
      const reviewSubmission = {
        plan_id: selectedPlan.id,
        expert_id: user.id,
        total_score: parseFloat(calculateTotalScore()),
        ...reviewData
      };

      const response = await apiClient.post('/api/review/submit', reviewSubmission);
      if (response.data.success) {
        setSuccess('评审提交成功！');
        setSelectedPlan(null);
        fetchAssignments();
      } else {
        setError(response.data.error);
      }
    } catch (err) {
      setError(err.response?.data?.error || '提交评审失败');
    } finally {
      setSubmitting(false);
    }
  };

  const renderPlanContent = (content) => {
    if (!content) return <p className="text-muted">暂无内容</p>;

    try {
      const planData = typeof content === 'string' ? JSON.parse(content) : content;
      return (
        <div>
          {Object.entries(planData).map(([key, value]) => (
            <div key={key} className="mb-3">
              <h6 className="text-primary">{key}</h6>
              <p style={{ whiteSpace: 'pre-wrap' }}>{value}</p>
            </div>
          ))}
        </div>
      );
    } catch (err) {
      return <pre>{content}</pre>;
    }
  };

  if (loading) {
    return (
      <div className="text-center mt-5">
        <Spinner animation="border" variant="primary" />
        <p className="mt-2">加载中...</p>
      </div>
    );
  }

  return (
    <Container className="mt-4">
      <Row>
        <Col lg={selectedPlan ? 6 : 12}>
          <Card>
            <Card.Header>
              <h4>评审任务列表</h4>
            </Card.Header>
            <Card.Body>
              {assignments.length === 0 ? (
                <p className="text-center text-muted">暂无评审任务</p>
              ) : (
                <Table responsive hover>
                  <thead>
                    <tr>
                      <th>方案标题</th>
                      <th>创建时间</th>
                      <th>状态</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assignments.map((assignment) => (
                      <tr key={assignment.plan_id}>
                        <td>{assignment.title}</td>
                        <td>
                          {new Date(assignment.created_at).toLocaleDateString('zh-CN')}
                        </td>
                        <td>
                          {assignment.has_reviewed ? (
                            <span className="badge bg-success">已评审</span>
                          ) : (
                            <span className="badge bg-warning">待评审</span>
                          )}
                        </td>
                        <td>
                          <Button
                            variant="outline-primary"
                            size="sm"
                            onClick={() => selectPlan(assignment.plan_id)}
                            disabled={assignment.has_reviewed}
                          >
                            {assignment.has_reviewed ? '查看' : '评审'}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Col>

        {selectedPlan && (
          <Col lg={6}>
            <Card>
              <Card.Header>
                <h4>方案评审</h4>
              </Card.Header>
              <Card.Body>
                {error && <Alert variant="danger">{error}</Alert>}
                {success && <Alert variant="success">{success}</Alert>}

                <div className="mb-4">
                  <h5>{selectedPlan.title}</h5>
                  <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    {renderPlanContent(selectedPlan.content)}
                  </div>
                </div>

                <Form onSubmit={submitReview}>
                  <Row>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>临床意义 (1-5分)</Form.Label>
                        <Form.Control
                          type="number"
                          min="1"
                          max="5"
                          step="0.1"
                          value={reviewData.clinical_significance || ''}
                          onChange={(e) => handleReviewChange('clinical_significance', parseFloat(e.target.value))}
                          required
                        />
                      </Form.Group>
                    </Col>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>创新性 (1-5分)</Form.Label>
                        <Form.Control
                          type="number"
                          min="1"
                          max="5"
                          step="0.1"
                          value={reviewData.innovation || ''}
                          onChange={(e) => handleReviewChange('innovation', parseFloat(e.target.value))}
                          required
                        />
                      </Form.Group>
                    </Col>
                  </Row>

                  <Row>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>针对性 (1-5分)</Form.Label>
                        <Form.Control
                          type="number"
                          min="1"
                          max="5"
                          step="0.1"
                          value={reviewData.relevance || ''}
                          onChange={(e) => handleReviewChange('relevance', parseFloat(e.target.value))}
                          required
                        />
                      </Form.Group>
                    </Col>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>可行性 (1-5分)</Form.Label>
                        <Form.Control
                          type="number"
                          min="1"
                          max="5"
                          step="0.1"
                          value={reviewData.feasibility || ''}
                          onChange={(e) => handleReviewChange('feasibility', parseFloat(e.target.value))}
                          required
                        />
                      </Form.Group>
                    </Col>
                  </Row>

                  <Row>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>方法学严谨性 (1-5分)</Form.Label>
                        <Form.Control
                          type="number"
                          min="1"
                          max="5"
                          step="0.1"
                          value={reviewData.methodology || ''}
                          onChange={(e) => handleReviewChange('methodology', parseFloat(e.target.value))}
                          required
                        />
                      </Form.Group>
                    </Col>
                    <Col md={6}>
                      <Form.Group className="mb-3">
                        <Form.Label>发表潜力 (1-5分)</Form.Label>
                        <Form.Control
                          type="number"
                          min="1"
                          max="5"
                          step="0.1"
                          value={reviewData.publication_potential || ''}
                          onChange={(e) => handleReviewChange('publication_potential', parseFloat(e.target.value))}
                          required
                        />
                      </Form.Group>
                    </Col>
                  </Row>

                  <Form.Group className="mb-3">
                    <Form.Label>总评分: {calculateTotalScore() || '待计算'}</Form.Label>
                  </Form.Group>

                  <Form.Group className="mb-3">
                    <Form.Label>评审意见</Form.Label>
                    <Form.Control
                      as="textarea"
                      rows={4}
                      value={reviewData.comments || ''}
                      onChange={(e) => handleReviewChange('comments', e.target.value)}
                      placeholder="请输入详细的评审意见..."
                    />
                  </Form.Group>

                  <Button
                    variant="primary"
                    type="submit"
                    className="w-100"
                    disabled={submitting || !calculateTotalScore()}
                  >
                    {submitting ? '提交中...' : '提交评审'}
                  </Button>
                </Form>
              </Card.Body>
            </Card>
          </Col>
        )}
      </Row>
    </Container>
  );
}

export default ExpertReview;
