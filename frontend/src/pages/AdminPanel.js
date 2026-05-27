import React, { useState, useEffect } from 'react';
import { Card, Table, Button, Alert, Container, Row, Col, Spinner, Tabs, Tab } from 'react-bootstrap';
import apiClient from '../config';

function AdminPanel() {
  const [systemStats, setSystemStats] = useState({});
  const [systemLogs, setSystemLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);

  useEffect(() => {
    fetchSystemData();
  }, []);

  const fetchSystemData = async () => {
    try {
      await Promise.all([
        fetchSystemStats(),
        fetchSystemLogs()
      ]);
    } catch (err) {
      setError('获取系统数据失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchSystemStats = async () => {
    try {
      const response = await apiClient.get('/api/system/stats');
      if (response.data.success) {
        setSystemStats(response.data.statistics);
      }
    } catch (err) {
      console.error('获取系统统计失败:', err);
    }
  };

  const fetchSystemLogs = async () => {
    try {
      const response = await apiClient.get('/api/system/logs?days=7');
      if (response.data.success) {
        setSystemLogs(response.data.logs);
      }
    } catch (err) {
      console.error('获取系统日志失败:', err);
    }
  };

  const performMaintenance = async (action) => {
    setMaintenanceLoading(true);
    setError('');

    try {
      const response = await apiClient.post('/api/system/maintenance', { action });
      if (response.data.success) {
        alert(response.data.message);
        fetchSystemData();
      }
    } catch (err) {
      setError(err.response?.data?.error || '维护操作失败');
    } finally {
      setMaintenanceLoading(false);
    }
  };

  const exportData = () => {
    // 使用 apiClient 获取数据（带 token），然后下载
    apiClient.get('/api/system/export-data')
      .then(response => {
        const dataStr = JSON.stringify(response.data.data, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `system_export_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch(err => {
        setError('导出数据失败');
      });
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
        <Col>
          <h2>系统管理面板</h2>
        </Col>
      </Row>

      {error && (
        <Row className="mb-3">
          <Col>
            <Alert variant="danger">{error}</Alert>
          </Col>
        </Row>
      )}

      <Row className="mb-4">
        <Col md={3}>
          <Card className="text-center">
            <Card.Body>
              <h3 className="text-primary">{systemStats.total_users || 0}</h3>
              <p className="text-muted mb-0">总用户数</p>
            </Card.Body>
          </Card>
        </Col>
        <Col md={3}>
          <Card className="text-center">
            <Card.Body>
              <h3 className="text-success">{systemStats.student_users || 0}</h3>
              <p className="text-muted mb-0">研究生用户</p>
            </Card.Body>
          </Card>
        </Col>
        <Col md={3}>
          <Card className="text-center">
            <Card.Body>
              <h3 className="text-info">{systemStats.expert_users || 0}</h3>
              <p className="text-muted mb-0">专家用户</p>
            </Card.Body>
          </Card>
        </Col>
        <Col md={3}>
          <Card className="text-center">
            <Card.Body>
              <h3 className="text-warning">{systemStats.active_users_7days || 0}</h3>
              <p className="text-muted mb-0">7天活跃用户</p>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row>
        <Col>
          <Card>
            <Card.Header>
              <h5>系统管理</h5>
            </Card.Header>
            <Card.Body>
              <Row>
                <Col md={4}>
                  <Button
                    variant="outline-primary"
                    className="w-100 mb-2"
                    onClick={exportData}
                  >
                    导出系统数据
                  </Button>
                </Col>
                <Col md={4}>
                  <Button
                    variant="outline-warning"
                    className="w-100 mb-2"
                    onClick={() => performMaintenance('cleanup_logs')}
                    disabled={maintenanceLoading}
                  >
                    清理系统日志
                  </Button>
                </Col>
                <Col md={4}>
                  <Button
                    variant="outline-info"
                    className="w-100 mb-2"
                    onClick={() => performMaintenance('backup_database')}
                    disabled={maintenanceLoading}
                  >
                    数据库备份
                  </Button>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Row className="mt-4">
        <Col>
          <Card>
            <Card.Header>
              <h5>系统详情</h5>
            </Card.Header>
            <Card.Body>
              <Tabs defaultActiveKey="stats" className="mb-3">
                <Tab eventKey="stats" title="使用统计">
                  <Row>
                    <Col>
                      <h6>模块使用情况（7天内）</h6>
                      {systemStats.module_usage && Object.keys(systemStats.module_usage).length > 0 ? (
                        <Table responsive>
                          <thead>
                            <tr>
                              <th>模块</th>
                              <th>使用次数</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(systemStats.module_usage).map(([module, count]) => (
                              <tr key={module}>
                                <td>{module}</td>
                                <td>{count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </Table>
                      ) : (
                        <p className="text-muted">暂无使用数据</p>
                      )}
                    </Col>
                  </Row>
                </Tab>

                <Tab eventKey="logs" title="系统日志">
                  <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                    <Table responsive hover size="sm">
                      <thead>
                        <tr>
                          <th>时间</th>
                          <th>用户</th>
                          <th>模块</th>
                          <th>操作</th>
                          <th>详情</th>
                        </tr>
                      </thead>
                      <tbody>
                        {systemLogs.map((log) => (
                          <tr key={log.id}>
                            <td>
                              {new Date(log.created_at).toLocaleString('zh-CN')}
                            </td>
                            <td>{log.username}</td>
                            <td>{log.module}</td>
                            <td>{log.action}</td>
                            <td>
                              <small>{log.details}</small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </Tab>
              </Tabs>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default AdminPanel;
