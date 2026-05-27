/* eslint-disable no-undef */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import './RealtimeDebugConsole.css';

const MIN_WIDTH = 320;
const MIN_HEIGHT = 200;
const MAX_WIDTH = 1200;
const MAX_HEIGHT = 900;

const RealtimeDebugConsole = ({ isVisible, onToggle }) => {
  const [logs, setLogs] = useState([]);
  const [socket, setSocket] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedLevel, setSelectedLevel] = useState('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const logsEndRef = useRef(null);

  // 窗口位置和尺寸状态
  const [position, setPosition] = useState({ x: null, y: null });  // null = 默认右下角
  const [size, setSize] = useState({ width: 600, height: 500 });

  // 拖拽 / 缩放状态（不触发重渲染）
  const dragRef = useRef({ dragging: false, startX: 0, startY: 0, origX: 0, origY: 0 });
  const resizeRef = useRef({ resizing: false, startX: 0, startY: 0, origW: 0, origH: 0, edge: '' });
  const consoleElRef = useRef(null);

  // ── 拖动：鼠标按下标题栏 ──
  const handleDragStart = useCallback((e) => {
    // 避免点击按钮时触发拖拽
    if (e.target.closest('button') || e.target.closest('select') || e.target.closest('input')) return;
    e.preventDefault();
    const rect = consoleElRef.current.getBoundingClientRect();
    dragRef.current = {
      dragging: true,
      startX: e.clientX,
      startY: e.clientY,
      origX: rect.left,
      origY: rect.top,
    };
    setPosition({}); // 触发从 fixed → absolute 切换
  }, []);

  // ── 缩放：鼠标按下某条边 / 角落 ──
  const handleResizeStart = useCallback((e, edge) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = consoleElRef.current.getBoundingClientRect();
    resizeRef.current = {
      resizing: true,
      startX: e.clientX,
      startY: e.clientY,
      origW: rect.width,
      origH: rect.height,
      origX: rect.left,
      origY: rect.top,
      edge,
    };
    setPosition({});
  }, []);

  // 全局 mousemove / mouseup
  useEffect(() => {
    const handleMouseMove = (e) => {
      const d = dragRef.current;
      if (d.dragging) {
        const dx = e.clientX - d.startX;
        const dy = e.clientY - d.startY;
        setPosition({ x: d.origX + dx, y: d.origY + dy });
      }
      const r = resizeRef.current;
      if (r.resizing) {
        const dx = e.clientX - r.startX;
        const dy = e.clientY - r.startY;
        let newW = r.origW;
        let newH = r.origH;
        let newX = r.origX;
        let newY = r.origY;

        if (r.edge.includes('e')) newW = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, r.origW + dx));
        if (r.edge.includes('w')) {
          newW = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, r.origW - dx));
          if (newW !== r.origW) newX = r.origX + dx;
        }
        if (r.edge.includes('s')) newH = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, r.origH + dy));
        if (r.edge.includes('n')) {
          newH = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, r.origH - dy));
          if (newH !== r.origH) newY = r.origY + dy;
        }

        setSize({ width: newW, height: newH });
        setPosition({ x: newX, y: newY });
      }
    };

    const handleMouseUp = () => {
      dragRef.current.dragging = false;
      resizeRef.current.resizing = false;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // 连接WebSocket
  useEffect(() => {
    if (!isVisible) return;

    // 直连后端 Socket.IO 服务（React proxy 不转发 WebSocket）
    const socketUrl = process.env.REACT_APP_SOCKET_URL || 'http://localhost:5002';
    const newSocket = io(socketUrl, {
      transports: ['polling', 'websocket'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 5
    });

    newSocket.on('connect', () => {
      console.log('已连接到调试日志系统');
      setIsConnected(true);
      newSocket.emit('subscribe_logs');
      newSocket.emit('get_logs', { limit: 50 });
    });

    newSocket.on('disconnect', () => {
      console.log('已断开连接');
      setIsConnected(false);
    });

    newSocket.on('new_log', (logEntry) => {
      setLogs(prev => [...prev, logEntry].slice(-200));
    });

    newSocket.on('logs_history', (data) => {
      setLogs(data.logs || []);
    });

    newSocket.on('connection_response', (data) => {
      console.log(data.data);
    });

    setSocket(newSocket);

    return () => {
      newSocket.disconnect();
    };
  }, [isVisible]);

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const filteredLogs = logs.filter(log => {
    const categoryMatch = selectedCategory === 'all' || log.category === selectedCategory;
    const levelMatch = selectedLevel === 'all' || log.level === selectedLevel;
    return categoryMatch && levelMatch;
  });

  const categories = ['all', ...new Set(logs.map(log => log.category))];
  const levels = ['all', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'API_CALL', 'AI_RESPONSE', 'AGENT_ACTION', 'LITERATURE_SEARCH', 'PLAN_GENERATION'];

  const getLogColor = (level) => {
    switch (level) {
      case 'ERROR': return '#ff6b6b';
      case 'WARNING': return '#ffa500';
      case 'API_CALL': return '#4ecdc4';
      case 'AI_RESPONSE': return '#95e1d3';
      case 'AGENT_ACTION': return '#a8dadc';
      case 'LITERATURE_SEARCH': return '#7c3aed';
      case 'PLAN_GENERATION': return '#2563eb';
      case 'CRITIQUE': return '#d97706';
      case 'REVISION': return '#059669';
      case 'DEBUG': return '#888888';
      default: return '#ffffff';
    }
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', { hour12: false });
  };

  const clearLogs = () => {
    if (socket) {
      socket.emit('clear_logs');
      setLogs([]);
    }
  };

  // 双击标题栏重置到默认位置和大小
  const handleHeaderDoubleClick = () => {
    setPosition({ x: null, y: null });
    setSize({ width: 600, height: 500 });
  };

  // 计算样式
  const isPositioned = position.x !== null && position.y !== null;
  const consoleStyle = isPositioned
    ? {
        position: 'fixed',
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
      }
    : {};

  if (!isVisible) {
    return (
      <div className="debug-console-toggle">
        <button onClick={onToggle} className="debug-console-btn">
          📊 实时日志
        </button>
      </div>
    );
  }

  return (
    <div
      ref={consoleElRef}
      className="realtime-debug-console"
      style={consoleStyle}
    >
      {/* ── 拖动区域：标题栏 ── */}
      <div
        className="console-header console-drag-handle"
        onMouseDown={handleDragStart}
        onDoubleClick={handleHeaderDoubleClick}
      >
        <div className="console-title">
          <h3>📊 实时调试日志</h3>
          <span className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? '● 已连接' : '● 已断开'}
          </span>
          <span className="drag-hint">✥ 拖动 · 双击重置</span>
        </div>
        <button onClick={onToggle} className="console-close-btn">
          ✕
        </button>
      </div>

      <div className="console-controls">
        <div className="control-group">
          <label>分类:</label>
          <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)}>
            {categories.map(cat => (
              <option key={cat} value={cat}>
                {cat === 'all' ? '全部' : cat}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>级别:</label>
          <select value={selectedLevel} onChange={(e) => setSelectedLevel(e.target.value)}>
            {levels.map(level => (
              <option key={level} value={level}>
                {level === 'all' ? '全部' : level}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            自动滚动
          </label>
        </div>

        <button onClick={clearLogs} className="clear-logs-btn">
          🗑️ 清空日志
        </button>

        <span className="log-count">
          显示: {filteredLogs.length} / 总计: {logs.length}
        </span>
      </div>

      <div className="console-logs">
        {filteredLogs.length === 0 ? (
          <div className="no-logs">暂无日志</div>
        ) : (
          filteredLogs.map((log, index) => (
            <div key={index} className="log-entry" style={{ borderLeftColor: getLogColor(log.level) }}>
              <div className="log-header">
                <span className="log-time">{formatTimestamp(log.timestamp)}</span>
                <span className="log-level" style={{ color: getLogColor(log.level) }}>
                  [{log.level}]
                </span>
                <span className="log-category">[{log.category}]</span>
              </div>
              <div className="log-message">{log.message}</div>
              {log.data && Object.keys(log.data).length > 0 && (
                <details className="log-data">
                  <summary>查看详细数据</summary>
                  <pre>{JSON.stringify(log.data, null, 2)}</pre>
                </details>
              )}
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>

      {/* ── 8 个方向的调整大小手柄 ── */}
      <div className="resize-handle resize-n"  onMouseDown={(e) => handleResizeStart(e, 'n')}  />
      <div className="resize-handle resize-s"  onMouseDown={(e) => handleResizeStart(e, 's')}  />
      <div className="resize-handle resize-e"  onMouseDown={(e) => handleResizeStart(e, 'e')}  />
      <div className="resize-handle resize-w"  onMouseDown={(e) => handleResizeStart(e, 'w')}  />
      <div className="resize-handle resize-ne" onMouseDown={(e) => handleResizeStart(e, 'ne')} />
      <div className="resize-handle resize-nw" onMouseDown={(e) => handleResizeStart(e, 'nw')} />
      <div className="resize-handle resize-se" onMouseDown={(e) => handleResizeStart(e, 'se')} />
      <div className="resize-handle resize-sw" onMouseDown={(e) => handleResizeStart(e, 'sw')} />
    </div>
  );
};

export default RealtimeDebugConsole;
