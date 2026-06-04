import React, { useState, useEffect } from 'react';
import { Card, Button, Form, Alert, Row, Col, Badge, Spinner, InputGroup } from 'react-bootstrap';
import { BiKey, BiChip, BiCheckCircle, BiXCircle, BiLoaderAlt, BiShow, BiHide, BiRefresh } from 'react-icons/bi';
import apiClient from '../config';

/**
 * API 设置页面 — 用户选择提供商 + 配置自己的 API Key
 * 提供商定义是系统预设的，API Key 是每个用户私有的
 */
function ApiSettings() {
  const [presets, setPresets] = useState({});

  // 表单状态
  const [selectedProvider, setSelectedProvider] = useState('longcat');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);

  // UI 状态
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [userProvider, setUserProvider] = useState('longcat');
  const [hasCustomKey, setHasCustomKey] = useState(false);

  // 加载当前配置
  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const res = await apiClient.get('/api/settings/llm');
      if (res.data.success) {
        setPresets(res.data.presets || {});
        setUserProvider(res.data.user_provider || 'longcat');
        setHasCustomKey(res.data.has_custom_key || false);
        setSelectedProvider(res.data.user_provider || 'longcat');
        setApiKey('');
      }
    } catch (err) {
      setMessage({ type: 'danger', text: '加载配置失败: ' + (err.response?.data?.error || err.message) });
    } finally {
      setLoading(false);
    }
  };

  // 切换提供商
  const handleProviderChange = (provider) => {
    setSelectedProvider(provider);
    setTestResult(null);
    setMessage(null);
  };

  // 保存 API Key
  const handleSaveKey = async () => {
    if (!apiKey.trim()) {
      setMessage({ type: 'danger', text: '请输入 API Key' });
      return;
    }
    setSaving(true);
    setMessage(null);
    setTestResult(null);

    try {
      const res = await apiClient.post('/api/settings/llm/key', {
        api_key: apiKey.trim(),
        provider: selectedProvider,
      });

      if (res.data.success) {
        setUserProvider(res.data.user_provider);
        setSelectedProvider(res.data.user_provider);
        setHasCustomKey(true);
        setMessage({ type: 'success', text: 'API Key 已保存，提供商已切换' });
        await fetchSettings();
      } else {
        setMessage({ type: 'danger', text: res.data.error || '保存失败' });
      }
    } catch (err) {
      setMessage({ type: 'danger', text: '保存失败: ' + (err.response?.data?.error || err.message) });
    } finally {
      setSaving(false);
    }
  };

  // 清除 API Key（恢复默认）
  const handleClearKey = async () => {
    try {
      const res = await apiClient.delete('/api/settings/llm/key');
      if (res.data.success) {
        setHasCustomKey(false);
        setUserProvider(res.data.user_provider);
        setSelectedProvider(res.data.user_provider);
        setApiKey('');
        setMessage({ type: 'success', text: '已恢复默认配置' });
        await fetchSettings();
      } else {
        setMessage({ type: 'danger', text: res.data.error || '操作失败' });
      }
    } catch (err) {
      setMessage({ type: 'danger', text: '操作失败: ' + (err.response?.data?.error || err.message) });
    }
  };

  // 测试连接
  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    setMessage(null);

    try {
      const res = await apiClient.post('/api/settings/llm/test', {
        provider: selectedProvider,
      });

      if (res.data.success) {
        setTestResult({ success: true, message: res.data.message });
      } else {
        setTestResult({ success: false, message: res.data.error || '连接失败' });
      }
    } catch (err) {
      setTestResult({ success: false, message: '测试失败: ' + (err.response?.data?.error || err.message) });
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="text-center py-5">
        <Spinner animation="border" variant="primary" />
        <p className="mt-2 text-muted">加载配置中...</p>
      </div>
    );
  }

  const currentPreset = presets[selectedProvider] || {};
  const isActive = userProvider === selectedProvider;

  return (
    <div className="container-fluid py-4">
      <div className="row justify-content-center">
        <div className="col-xl-10">
          {/* 页面标题 */}
          <div className="d-flex align-items-center justify-content-between mb-4">
            <div>
              <h2 className="fw-bold mb-1">⚙️ LLM 模型设置</h2>
              <p className="text-muted mb-0">切换 AI 模型提供商，支持 LongCat、DeepSeek、OpenAI</p>
            </div>
            <Button variant="outline-secondary" size="sm" onClick={fetchSettings} disabled={loading}>
              <BiRefresh className="me-1" /> 刷新
            </Button>
          </div>

          {/* 消息提示 */}
          {message && (
            <Alert variant={message.type} dismissible onClose={() => setMessage(null)} className="mb-4">
              {message.type === 'success' && <BiCheckCircle className="me-2" />}
              {message.type === 'danger' && <BiXCircle className="me-2" />}
              {message.text}
            </Alert>
          )}

          <Row>
            {/* 左侧：模型选择 */}
            <Col lg={4}>
              <Card className="border-0 shadow-sm mb-4">
                <Card.Header className="bg-white">
                  <h5 className="mb-0">选择模型提供商</h5>
                </Card.Header>
                <Card.Body className="p-0">
                  {Object.entries(presets).map(([key, preset]) => {
                    const isCurrent = userProvider === key;
                    return (
                      <button
                        key={key}
                        className={`btn w-100 text-start d-flex align-items-center gap-3 p-3 border-0 border-bottom rounded-0 ${
                          isCurrent ? 'bg-primary bg-opacity-10' : 'bg-white'
                        }`}
                        onClick={() => handleProviderChange(key)}
                      >
                        <span style={{ fontSize: '1.5rem' }}>{preset.icon}</span>
                        <div className="flex-grow-1">
                          <div className="d-flex align-items-center gap-2">
                            <span className="fw-semibold">{preset.label}</span>
                            {isCurrent && <Badge bg="success" pill>当前使用</Badge>}
                            {hasCustomKey && userProvider === key && (
                              <Badge bg="info" pill>
                                <BiKey size={10} /> 已配置
                              </Badge>
                            )}
                          </div>
                          <div className="text-muted small mt-0.5">{preset.description}</div>
                        </div>
                        {isCurrent && <BiCheckCircle className="text-primary" size={20} />}
                      </button>
                    );
                  })}
                </Card.Body>
              </Card>

              {/* 当前激活信息 */}
              <Card className="border-0 shadow-sm">
                <Card.Header className="bg-white">
                  <h6 className="mb-0">当前激活配置</h6>
                </Card.Header>
                <Card.Body>
                  <div className="small">
                    <div className="d-flex justify-content-between mb-2">
                      <span className="text-muted">提供商</span>
                      <span className="fw-medium">{presets[userProvider]?.icon} {presets[userProvider]?.label}</span>
                    </div>
                    <div className="d-flex justify-content-between mb-2">
                      <span className="text-muted">模型</span>
                      <code className="small">{presets[userProvider]?.model}</code>
                    </div>
                    <div className="d-flex justify-content-between mb-2">
                      <span className="text-muted">API Key</span>
                      <span className={hasCustomKey ? 'text-success' : 'text-warning'}>
                        {hasCustomKey ? '已配置' : '未配置（使用系统默认）'}
                      </span>
                    </div>
                    <div className="d-flex justify-content-between">
                      <span className="text-muted">Base URL</span>
                      <code className="small">{presets[userProvider]?.base_url}</code>
                    </div>
                  </div>
                </Card.Body>
              </Card>
            </Col>

            {/* 右侧：API Key 配置 */}
            <Col lg={8}>
              <Card className="border-0 shadow-sm">
                <Card.Header className="bg-white d-flex align-items-center gap-2">
                  <span style={{ fontSize: '1.3rem' }}>{currentPreset.icon}</span>
                  <h5 className="mb-0">{currentPreset.label}</h5>
                  {userProvider === selectedProvider && <Badge bg="success">当前使用</Badge>}
                </Card.Header>
                <Card.Body>
                  {/* 提供商信息（只读） */}
                  <div className="mb-4 p-3 bg-light rounded">
                    <Row>
                      <Col sm={4}><span className="text-muted small">提供商</span></Col>
                      <Col sm={8}><strong>{currentPreset.label}</strong></Col>
                    </Row>
                    <Row className="mt-1">
                      <Col sm={4}><span className="text-muted small">模型</span></Col>
                      <Col sm={8}><code className="small">{currentPreset.model}</code></Col>
                    </Row>
                    <Row className="mt-1">
                      <Col sm={4}><span className="text-muted small">Base URL</span></Col>
                      <Col sm={8}><code className="small">{currentPreset.base_url}</code></Col>
                    </Row>
                    <Row className="mt-1">
                      <Col sm={4}><span className="text-muted small">API Key</span></Col>
                      <Col sm={8}>
                        {hasCustomKey ? (
                          <span className="text-success">已配置</span>
                        ) : (
                          <span className="text-warning">未配置（使用系统默认）</span>
                        )}
                      </Col>
                    </Row>
                  </div>

                  {/* API Key 输入 */}
                  <Form.Group className="mb-4">
                    <Form.Label className="fw-semibold d-flex align-items-center gap-2">
                      <BiKey className="text-warning" />
                      API Key
                    </Form.Label>
                    <InputGroup>
                      <Form.Control
                        type={showApiKey ? 'text' : 'password'}
                        placeholder="输入你的 API Key（留空则使用系统默认）"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        className="font-monospace"
                      />
                      <Button
                        variant="outline-secondary"
                        onClick={() => setShowApiKey(!showApiKey)}
                        title={showApiKey ? '隐藏' : '显示'}
                      >
                        {showApiKey ? <BiHide /> : <BiShow />}
                      </Button>
                    </InputGroup>
                    <Form.Text className="text-muted">
                      你的 API Key 仅保存在你的账户中，不会泄露给其他用户。
                    </Form.Text>
                  </Form.Group>

                  {/* 操作按钮 */}
                  <div className="d-flex gap-3 flex-wrap">
                    <Button
                      variant="primary"
                      onClick={handleSaveKey}
                      disabled={saving}
                      className="d-flex align-items-center gap-2"
                    >
                      {saving ? (
                        <><BiLoaderAlt className="spin" /> 保存中...</>
                      ) : (
                        <><BiCheckCircle /> 保存 API Key 并切换</>
                      )}
                    </Button>
                    <Button
                      variant="outline-info"
                      onClick={handleTest}
                      disabled={testing}
                      className="d-flex align-items-center gap-2"
                    >
                      {testing ? (
                        <><BiLoaderAlt className="spin" /> 测试中...</>
                      ) : (
                        <><BiChip /> 测试连接</>
                      )}
                    </Button>
                    {hasCustomKey && (
                      <Button
                        variant="outline-danger"
                        onClick={handleClearKey}
                        className="d-flex align-items-center gap-2"
                      >
                        <BiXCircle /> 清除 Key（恢复默认）
                      </Button>
                    )}
                  </div>

                  {/* 测试结果 */}
                  {testResult && (
                    <Alert
                      variant={testResult.success ? 'success' : 'danger'}
                      className="mt-3 mb-0 d-flex align-items-center gap-2"
                    >
                      {testResult.success ? <BiCheckCircle size={18} /> : <BiXCircle size={18} />}
                      <span>{testResult.message}</span>
                    </Alert>
                  )}
                </Card.Body>
              </Card>

              {/* 所有可用提供商参考表 */}
              <Card className="border-0 shadow-sm mt-4">
                <Card.Header className="bg-white">
                  <h6 className="mb-0">📋 可用模型提供商</h6>
                </Card.Header>
                <Card.Body className="p-0">
                  <table className="table table-sm table-hover mb-0">
                    <thead className="table-light">
                      <tr>
                        <th>提供商</th>
                        <th>模型</th>
                        <th>格式</th>
                        <th>Base URL</th>
                      </tr>
                    </thead>
                    <tbody className="small">
                      {Object.entries(presets).map(([key, preset]) => (
                        <tr
                          key={key}
                          className={key === userProvider ? 'table-success' : ''}
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleProviderChange(key)}
                        >
                          <td>{preset.icon} {preset.label}</td>
                          <td><code className="small">{preset.model}</code></td>
                          <td><Badge bg="secondary" pill>{preset.format === 'anthropic' ? 'Anthropic' : 'OpenAI'}</Badge></td>
                          <td><code className="small">{preset.base_url}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card.Body>
              </Card>

              {/* 说明 */}
              <Card className="border-0 shadow-sm mt-4">
                <Card.Header className="bg-white">
                  <h6 className="mb-0">💡 说明</h6>
                </Card.Header>
                <Card.Body className="small text-muted">
                  <ul className="mb-0 ps-3">
                    <li>每个用户有自己的 API Key，互不影响</li>
                    <li>提供商配置是系统预设的，所有人共享同一套模型定义</li>
                    <li>API Key 仅保存在你的账户中，不会泄露给其他用户</li>
                    <li>如果不配置自己的 API Key，系统会使用默认配置</li>
                    <li>LongCat 使用 Anthropic 格式；DeepSeek 和 GPT-5.4 使用 OpenAI 格式</li>
                    <li>切换提供商后，建议先点击"测试连接"确认配置正确</li>
                  </ul>
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </div>
      </div>
    </div>
  );
}

export default ApiSettings;
