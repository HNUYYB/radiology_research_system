import React, { useState, useRef, useEffect } from 'react';
import { Modal, Button, Form, Spinner, Alert, Badge } from 'react-bootstrap';
import apiClient from '../config';

const fieldNames = {
  title: '研究题目', background: '研究背景', clinical_problem: '临床问题',
  scientific_problem: '科学问题', hypothesis: '研究假设', objectives: '研究目标',
  study_design: '研究设计', subjects_criteria: '纳排标准',
  variables_endpoints: '变量与终点', statistical_analysis: '统计分析',
  innovation: '创新点', risks_alternatives: '风险与备选', timeline: '时间表'
};

// 截断长文本用于预览
const truncate = (text, maxLen = 120) => {
  if (!text) return '';
  const s = text.toString().trim();
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
};

const ChatOptimizer = ({ show, onHide, plan, onOptimize }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [optimizedPlan, setOptimizedPlan] = useState(null);
  const [lastDiff, setLastDiff] = useState(null); // { key, name, oldVal, newVal }[]
  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (show && plan) {
      setMessages([{
        role: 'assistant',
        content: `你好！我是你的研究方案优化助手。当前方案是「${plan.title || '未命名'}」。\n\n你可以告诉我你想怎么优化，比如：\n• "创新点不够突出，帮我加强"\n• "样本量计算有问题，重新设计"\n• "研究设计改成前瞻性队列"\n• "帮我精简背景部分"\n\n请描述你的修改需求：`
      }]);
      setOptimizedPlan(null);
      setLastDiff(null);
      setInput('');
    }
  }, [show, plan]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 生成 diff 数据
  const computeDiff = (oldContent, newContent) => {
    const diffs = [];
    for (const [key, name] of Object.entries(fieldNames)) {
      const oldVal = (oldContent[key] || '').toString().trim();
      const newVal = (newContent[key] || '').toString().trim();
      if (oldVal !== newVal && newVal) {
        diffs.push({ key, name, oldVal, newVal });
      }
    }
    return diffs;
  };

  // 渲染单条 diff 对比
  const renderDiffItem = (diff) => (
    <div key={diff.key} className="mb-3 border rounded overflow-hidden">
      <div className="bg-light px-3 py-1 border-bottom d-flex align-items-center gap-2">
        <Badge bg="primary" pill>{diff.name}</Badge>
        <small className="text-muted">已修改</small>
      </div>
      <div className="row g-0">
        <div className="col-6 border-end">
          <div className="px-2 py-1 bg-danger bg-opacity-10 border-bottom">
            <small className="text-danger fw-semibold">修改前</small>
          </div>
          <div className="p-2" style={{ whiteSpace: 'pre-wrap', fontSize: '0.85rem', lineHeight: '1.5', maxHeight: '120px', overflowY: 'auto' }}>
            {truncate(diff.oldVal, 200) || <span className="text-muted fst-italic">（空）</span>}
          </div>
        </div>
        <div className="col-6">
          <div className="px-2 py-1 bg-success bg-opacity-10 border-bottom">
            <small className="text-success fw-semibold">修改后</small>
          </div>
          <div className="p-2" style={{ whiteSpace: 'pre-wrap', fontSize: '0.85rem', lineHeight: '1.5', maxHeight: '120px', overflowY: 'auto' }}>
            {truncate(diff.newVal, 200)}
          </div>
        </div>
      </div>
    </div>
  );

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const currentContent = typeof plan.content === 'string' ? JSON.parse(plan.content) : plan.content;

      const response = await apiClient.post('/api/research/edit-and-regenerate', {
        user_id: plan.user_id,
        plan_id: plan.id,
        user_edits: {},
        optimization_focus: userMsg,
      }, { timeout: 600000 });

      if (response.data.success) {
        const newPlan = response.data.optimized_plan;
        setOptimizedPlan(newPlan);

        const diffs = computeDiff(currentContent, newPlan);
        setLastDiff(diffs);

        if (diffs.length > 0) {
          // 构建带 diff 对比的消息
          const summaryText = `✅ 优化完成！以下 ${diffs.length} 个部分已修改：`;
          setMessages(prev => [
            ...prev,
            { role: 'assistant', content: summaryText, diffs },
            { role: 'assistant', content: '你可以点击「应用优化」将修改应用到方案中，或者继续对话进一步优化。' }
          ]);
        } else {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `已根据你的要求「${userMsg}」进行了优化调整，但没有字段发生变化。你可以尝试更具体地描述需要修改的内容。`
          }]);
        }
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: '优化失败：' + (response.data.error || '未知错误') }]);
      }
    } catch (err) {
      let errorMsg = '抱歉，优化过程中出现出现错误。';
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMsg = '⏱️ 优化请求超时（AI 生成时间过长）。建议：\n• 简化你的优化需求，一次只改一个方面\n• 或者使用「✏️ 编辑优化」功能直接修改具体内容';
      } else if (err.response?.data?.error) {
        errorMsg = `优化失败：${err.response.data.error}`;
      } else if (err.message) {
        errorMsg = `网络错误：${err.message}`;
      }
      setMessages(prev => [...prev, { role: 'assistant', content: errorMsg }]);
    } finally {
      setLoading(false);
    }
  };

  const handleApply = () => {
    if (optimizedPlan) {
      onOptimize(optimizedPlan);
      onHide();
    }
  };

  // 渲染单条消息（支持 diff 对比）
  const renderMessage = (msg, i) => {
    if (msg.diffs && msg.diffs.length > 0) {
      // 带 diff 对比的消息
      return (
        <div key={i} className="mb-3">
          <div className="d-flex justify-content-start mb-2">
            <div className="p-2 rounded-3 bg-light" style={{ maxWidth: '85%' }}>
              <span className="me-1">🤖</span>{msg.content}
            </div>
          </div>
          <div className="ms-3">
            {msg.diffs.map(renderDiffItem)}
          </div>
        </div>
      );
    }
    // 普通消息
    return (
      <div key={i} className={`d-flex mb-3 ${msg.role === 'user' ? 'justify-content-end' : 'justify-content-start'}`}>
        <div className={`p-3 rounded-3 ${msg.role === 'user' ? 'bg-primary text-white' : 'bg-light'}`}
          style={{ maxWidth: '80%', whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>
          {msg.role === 'assistant' && <span className="me-1">🤖</span>}
          {msg.content}
        </div>
      </div>
    );
  };

  return (
    <Modal show={show} onHide={onHide} size="lg" centered>
      <Modal.Header closeButton>
        <Modal.Title>💬 对话式优化</Modal.Title>
      </Modal.Header>
      <Modal.Body style={{ maxHeight: '65vh', overflowY: 'auto' }}>
        {messages.map(renderMessage)}
        {loading && (
          <div className="d-flex justify-content-start mb-3">
            <div className="p-3 rounded-3 bg-light">
              <Spinner animation="border" size="sm" className="me-2" />正在思考优化方案...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </Modal.Body>
      <Modal.Footer className="d-flex gap-2">
        <div className="flex-grow-1">
          <Form onSubmit={(e) => { e.preventDefault(); handleSend(); }}>
            <Form.Control
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="描述你的优化需求..."
              disabled={loading}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            />
          </Form>
        </div>
        <Button variant="primary" onClick={handleSend} disabled={loading || !input.trim()}>
          发送
        </Button>
        {optimizedPlan && lastDiff && lastDiff.length > 0 && (
          <Button variant="success" onClick={handleApply}>
            ✓ 应用优化
          </Button>
        )}
        <Button variant="secondary" onClick={onHide}>关闭</Button>
      </Modal.Footer>
    </Modal>
  );
};

export default ChatOptimizer;
