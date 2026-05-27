import React, { useState, useEffect } from 'react';
import { Card, Button, Form, Alert, Row, Col, Badge, Spinner, InputGroup } from 'react-bootstrap';
import { BiKey, BiServer, BiChip, BiCheckCircle, BiXCircle, BiLoaderAlt, BiShow, BiHide, BiRefresh } from 'react-icons/bi';
import apiClient from '../config';

/**
 * API 设置页面 — 支持切换 LLM 模型提供商（LongCat / DeepSeek / OpenAI）
 */
function ApiSettings() {
  const [presets, setPresets] = useState({});
  const [activeProvider, setActiveProvider] = useState('longcat');
  const [activeConfig, setActiveConfig] = useState(null);

  // 表单状态
  const [selectedProvider, setSelectedProvider] = useState('longcat');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [model, setModel] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);

  // UI 状态
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState(null); // { type: 'success'|'danger'|'info', text: '...' }
  const [testResult, setTestResult] = useState(null);

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
        setActiveProvider(res.data.active_provider || 'longcat');
        setActiveConfig(res.data.active_config || null);

        // 初始化表单为当前激活的配置
        const provider = res.data.active_provider || 'longcat';
        setSelectedProvider(provider);
        const preset = res.data.presets?.[provider] || {};
        setBaseUrl(preset.base_url || '');
        setModel(preset.model || '');
        // API Key 不预填（安全）
        setApiKey('');
      }
    } catch (err) {
      setMessage({ type: 'danger', text: '加载配置失败: ' + (err.response?.data?.error || err.message) });
    } finally {
      setLoading(false);
    }
  };

  // 切换选中的 provider 时更新表单
  const handleProviderChange = (provider) => {
    setSelectedProvider(provider);
    const preset = presets[provider] || {};
    setBaseUrl(preset.base_url || '');
    setModel(preset.model || '');
    setApiKey('');
    setTestResult(null);
    setMessage(null);
  };

  // 保存并切换
  const handleSave = async (e) => {
    e.preventDefault();
    if (!apiKey.trim()) {
      setMessage({ type: 'danger', text: '请输入 API Key' });
      return;
    }
    setSaving(true);
    setMessage(null);
    setTestResult(null);

    try {
      const res = await apiClient.post('/api/settings/llm/switch', {
        provider: selectedProvider,
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
        save_to_env: true,
      });

      if (res.data.success) {
        setActiveProvider(res.data.active.provider);
        setActiveConfig(res.data.active);
        setMessage({ type: 'success', text: res.data.message + ' 配置已保存到 .env 文件' });
        // 刷新完整配置
        await fetchSettings();
      } else {
        setMessage({ type: 'danger', text: res.data.error || '切换失败' });
      }
    } catch (err) {
      setMessage({ type: 'danger', text: '切换失败: ' + (err.response?.data?.error || err.message) });
    } finally {
      setSaving(false);
    }
  };

  // 测试连接
  const handleTest = async () => {
    if (!apiKey.trim()) {
      setMessage({ type: 'danger', text: '请先输入 API Key' });
      return;
    }
    setTesting(true);
    setTestResult(null);
    setMessage(null);

    try {
      const res = await apiClient.post('/api/settings/llm/test', {
        provider: selectedProvider,
        api_key: apiKey.trim(),
        base_url: baseUrl.trim(),
        model: model.trim(),
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
  const isActive = activeProvider === selectedProvider;

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
                    const active = activeProvider === key;
                    const selected = selectedProvider === key;
                    return (
                      <button
                        key={key}
                        className={`btn w-100 text-start d-flex align-items-center gap-3 p-3 border-0 border-bottom rounded-0 ${
                          selected ? 'bg-primary bg-opacity-10' : 'bg-white'
                        }`}
                        onClick={() => handleProviderChange(key)}
                      >
                        <span style={{ fontSize: '1.5rem' }}>{preset.icon}</span>
                        <div className="flex-grow-1">
                          <div className="d-flex align-items-center gap-2">
                            <span className="fw-semibold">{preset.label}</span>
                            {active && <Badge bg="success" pill>当前使用</Badge>}
                            {preset.has_key && (
                              <Badge bg="info" pill>
                                <BiKey size={10} /> 已配置
                              </Badge>
                            )}
                          </div>
                          <div className="text-muted small mt-0.5">{preset.description}</div>
                        </div>
                        {selected && <BiCheckCircle className="text-primary" size={20} />}
                      </button>
                    );
                  })}
                </Card.Body>
              </Card>

              {/* 当前激活信息 */}
              {activeConfig && (
                <Card className="border-0 shadow-sm">
                  <Card.Header className="bg-white">
                    <h6 className="mb-0">当前激活配置</h6>
                  </Card.Header>
                  <Card.Body>
                    <div className="small">
                      <div className="d-flex justify-content-between mb-2">
                        <span className="text-muted">提供商</span>
                        <span className="fw-medium">{presets[activeProvider]?.icon} {activeConfig.label}</span>
                      </div>
                      <div className="d-flex justify-content-between mb-2">
                        <span className="text-muted">模型</span>
                        <code className="small">{activeConfig.model}</code>
                      </div>
                      <div className="d-flex justify-content-between mb-2">
                        <span className="text-muted">API Key</span>
                        <span className={activeConfig.has_key ? 'text-success' : 'text-danger'}>
                          {activeConfig.has_key ? '已配置' : '未配置'}
                        </span>
                      </div>
                      <div className="d-flex justify-content-between">
                        <span className="text-muted">API Key 变量</span>
                        <code className="small">{activeConfig.api_key_env}</code>
                      </div>
                    </div>
                  </Card.Body>
                </Card>
              )}
            </Col>

            {/* 右侧：配置表单 */}
            <Col lg={8}>
              <Card className="border-0 shadow-sm">
                <Card.Header className="bg-white d-flex align-items-center gap-2">
                  <span style={{ fontSize: '1.3rem' }}>{currentPreset.icon}</span>
                  <h5 className="mb-0">{currentPreset.label} 配置</h5>
                  {isActive && <Badge bg="success">当前使用中</Badge>}
                </Card.Header>
                <Card.Body>
                  <Form onSubmit={handleSave}>
                    {/* API Key */}
                    <Form.Group className="mb-4">
                      <Form.Label className="fw-semibold d-flex align-items-center gap-2">
                        <BiKey className="text-warning" />
                        {currentPreset.api_key_label || 'API Key'}
                        <span className="text-danger">*</span>
                      </Form.Label>
                      <InputGroup>
                        <Form.Control
                          type={showApiKey ? 'text' : 'password'}
                          placeholder={currentPreset.api_key_placeholder || '输入 API Key'}
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
                        输入你的 {currentPreset.label} API Key。留空则使用 .env 文件中已有的配置。
                      </Form.Text>
                    </Form.Group>

                    {/* Base URL */}
                    <Form.Group className="mb-4">
                      <Form.Label className="fw-semibold d-flex align-items-center gap-2">
                        <BiServer className="text-info" />
                        Base URL
                      </Form.Label>
                      <Form.Control
                        type="text"
                        placeholder="https://api.example.com"
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                        className="font-monospace small"
                      />
                      <Form.Text className="text-muted">
                        API 服务地址，使用默认值即可。如需自定义代理请修改此字段。
                      </Form.Text>
                    </Form.Group>

                    {/* Model */}
                    <Form.Group className="mb-4">
                      <Form.Label className="fw-semibold d-flex align-items-center gap-2">
                        <BiChip className="text-primary" />
                        模型名称
                      </Form.Label>
                      <Form.Control
                        type="text"
                        placeholder="model-name"
                        value={model}
                        onChange={(e) => setModel(e.target.value)}
                        className="font-monospace small"
                      />
                      <Form.Text className="text-muted">
                        推荐：LongCat → <code>LongCat-2.0-Preview</code>，DeepSeek → <code>deepseek-chat</code>，OpenAI → <code>gpt-4o</code>
                      </Form.Text>
                    </Form.Group>

                    {/* 操作按钮 */}
                    <div className="d-flex gap-3">
                      <Button
                        variant="primary"
                        type="submit"
                        disabled={saving}
                        className="d-flex align-items-center gap-2"
                      >
                        {saving ? (
                          <><BiLoaderAlt className="spin" /> 保存中...</>
                        ) : (
                          <><BiCheckCircle /> 保存并切换</>
                        )}
                      </Button>
                      <Button
                        variant="outline-info"
                        onClick={handleTest}
                        disabled={testing || !apiKey.trim()}
                        className="d-flex align-items-center gap-2"
                      >
                        {testing ? (
                          <><BiLoaderAlt className="spin" /> 测试中...</>
                        ) : (
                          <><BiChip /> 测试连接</>
                        )}
                      </Button>
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
                  </Form>
                </Card.Body>
              </Card>

              {/* 预设参考表 */}
              <Card className="border-0 shadow-sm mt-4">
                <Card.Header className="bg-white">
                  <h6 className="mb-0">📋 模型预设参考</h6>
                </Card.Header>
                <Card.Body className="p-0">
                  <table className="table table-sm table-hover mb-0">
                    <thead className="table-light">
                      <tr>
                        <th>提供商</th>
                        <th>默认 Base URL</th>
                        <th>默认模型</th>
                        <th>API Key 环境变量</th>
                      </tr>
                    </thead>
                    <tbody className="small">
                      {Object.entries(presets).map(([key, preset]) => (
                        <tr key={key} className={key === activeProvider ? 'table-success' : ''}>
                          <td>{preset.icon} {preset.label}</td>
                          <td><code className="small">{preset.base_url}</code></td>
                          <td><code className="small">{preset.model}</code></td>
                          <td><code className="small">{preset.api_key_env || '—'}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card.Body>
              </Card>

              {/* 环境变量说明 */}
              <Card className="border-0 shadow-sm mt-4">
                <Card.Header className="bg-white">
                  <h6 className="mb-0">💡 配置说明</h6>
                </Card.Header>
                <Card.Body className="small text-muted">
                  <ul className="mb-0 ps-3">
                    <li>切换模型后，配置会自动保存到项目根目录的 <code>.env</code> 文件中</li>
                    <li>重启后端服务后，新配置会自动生效</li>
                    <li>API Key 仅保存在 <code>.env</code> 中，不会发送到前端显示</li>
                    <li>LongCat 使用 Anthropic 兼容格式；DeepSeek 和 OpenAI 使用 OpenAI Chat Completions 格式</li>
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
