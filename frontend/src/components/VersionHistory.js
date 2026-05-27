import React, { useState, useEffect } from 'react';
import { Modal, Button, ListGroup, Badge, Alert, Spinner } from 'react-bootstrap';
import apiClient from '../config';

const VersionHistory = ({ show, onHide, planId, onRestore }) => {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(null);

  useEffect(() => {
    if (show && planId) fetchVersions();
  }, [show, planId]);

  const fetchVersions = async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/research/plan/${planId}/versions`);
      if (res.data.success) setVersions(res.data.versions);
    } catch (err) { console.error('获取版本失败:', err); }
    finally { setLoading(false); }
  };

  const handleRestore = async (versionId) => {
    if (!window.confirm('确定要回退到此版本？当前版本会自动备份。')) return;
    setRestoring(versionId);
    try {
      const res = await apiClient.post(`/api/research/plan/${planId}/versions/${versionId}/restore`);
      if (res.data.success) {
        onRestore(res.data.plan.content);
      }
    } catch (err) { alert('回退失败'); }
    finally { setRestoring(null); }
  };

  return (
    <Modal show={show} onHide={onHide} size="lg">
      <Modal.Header closeButton><Modal.Title>📋 版本历史</Modal.Title></Modal.Header>
      <Modal.Body>
        {loading ? (
          <div className="text-center py-4"><Spinner animation="border" /><p className="mt-2 text-muted">加载中...</p></div>
        ) : versions.length === 0 ? (
          <div className="text-center py-4">
            <div className="text-muted mb-2" style={{ fontSize: '2rem' }}>📝</div>
            <p className="text-muted">暂无历史版本</p>
            <small className="text-muted">每次编辑优化后会自动保存版本快照</small>
          </div>
        ) : (
          <ListGroup>
            {versions.map((v) => (
              <ListGroup.Item key={v.id} className="d-flex justify-content-between align-items-start">
                <div className="me-3">
                  <div className="d-flex align-items-center gap-2 mb-1">
                    <Badge bg="primary">v{v.version_num}</Badge>
                    <small className="text-muted">{new Date(v.created_at).toLocaleString('zh-CN')}</small>
                  </div>
                  {v.change_summary && <p className="small text-secondary mb-0">{v.change_summary}</p>}
                </div>
                <Button variant="outline-warning" size="sm" disabled={restoring === v.id}
                  onClick={() => handleRestore(v.id)}>
                  {restoring === v.id ? '回退中...' : '⏪ 回退'}
                </Button>
              </ListGroup.Item>
            ))}
          </ListGroup>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>关闭</Button>
      </Modal.Footer>
    </Modal>
  );
};

export default VersionHistory;
