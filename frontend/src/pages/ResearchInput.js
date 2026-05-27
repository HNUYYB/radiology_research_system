import React, { useState, useEffect } from 'react';
import { Card, Form, Button, Alert, Container, Row, Col, ProgressBar, Spinner, Modal } from 'react-bootstrap';
import { useAuth } from '../contexts/AuthContext';
import apiClient from '../config';
import { useNavigate } from 'react-router-dom';
import RealtimeDebugConsole from '../components/RealtimeDebugConsole';

// ── 默认选项（与后端 /api/profile/options 保持一致，防止异步加载前渲染空白） ──
const DEFAULT_OPTIONS = {
  grades: ['研一', '研二', '研三', '博一', '博二', '博三', '博四及以上'],
  specialties: [
    '胸部', '神经', '乳腺', '腹部', '骨肌', '介入',
    '心血管', '儿科', '头颈', '泌尿', '妇科', '急诊',
    '功能影像', '分子影像', '核医学', '超声', '病理影像',
    '放射治疗', '核磁共振', 'CT专项', 'X线专项', '其他'
  ],
  case_scales: ['小型(<50例)', '中型(50-200例)', '大型(200-500例)', '超大型(>500例)'],
  statistical_backgrounds: ['基础', '中等', '熟练'],
  ai_backgrounds: ['无基础', '基础', '中等', '熟练'],
  time_constraints: ['6个月以内', '6-12个月', '12-24个月', '24个月以上'],
  target_journal_levels: ['核心期刊', 'SCI一般', 'SCI中等', 'SCI高分'],
};

/**
 * 智能匹配：把数据库中可能存在的旧值/自由文本映射到标准选项
 */
function matchOption(value, options) {
  if (!value) return '';
  if (options.includes(value)) return value;
  const lower = value.toLowerCase();
  for (const opt of options) {
    if (lower.includes(opt.toLowerCase()) || opt.toLowerCase().includes(lower)) {
      return opt;
    }
  }
  if (lower.includes('无') || lower.includes('没') || lower.includes('零基础')) {
    const found = options.find(o => o.includes('无'));
    if (found) return found;
  }
  if (lower.includes('熟练') || lower.includes('精通') || lower.includes('强') || lower.includes('非常')) {
    const found = options.find(o => o.includes('熟练'));
    if (found) return found;
  }
  if (lower.includes('中等') || lower.includes('一般') || lower.includes('还行') || lower.includes('还可以')) {
    const found = options.find(o => o.includes('中等'));
    if (found) return found;
  }
  if (lower.includes('基础') || lower.includes('初学') || lower.includes('入门') || lower.includes('薄弱')) {
    const found = options.find(o => o.includes('基础'));
    if (found) return found;
  }
  return '';
}

function ResearchInput() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState({
    student_input: '',
    grade: '',
    specialty: '',
    available_resources: {},
    case_scale: '',
    follow_up_available: false,
    gold_standard_available: false,
    statistical_background: '',
    ai_background: '',
    time_constraint: '',
    target_journal_level: '',
  });
  const [profileOptions, setProfileOptions] = useState(DEFAULT_OPTIONS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showProgress, setShowProgress] = useState(false);
  const [progressInfo, setProgressInfo] = useState('');
  const [progressPercent, setProgressPercent] = useState(0);
  const [showRealtimeConsole, setShowRealtimeConsole] = useState(false);

  useEffect(() => {
    fetchProfileOptions();
    loadUserProfile();
  }, []);

  const fetchProfileOptions = async () => {
    try {
      const response = await apiClient.get('/api/profile/options');
      if (response.data.success) {
        setProfileOptions(response.data.options);
      }
    } catch (err) {
      console.error('获取选项失败:', err);
    }
  };

  const loadUserProfile = async () => {
    try {
      const response = await apiClient.get(`/api/profile/student/${user.id}`);
      if (response.data.success) {
        const profile = response.data.profile;
        const opts = profileOptions;
        const matchedStatsBg = matchOption(profile.statistical_background, opts.statistical_backgrounds || DEFAULT_OPTIONS.statistical_backgrounds);
        const matchedAiBg = matchOption(profile.ai_background, opts.ai_backgrounds || DEFAULT_OPTIONS.ai_backgrounds);
        const matchedJournal = matchOption(profile.target_journal_level, opts.target_journal_levels || DEFAULT_OPTIONS.target_journal_levels);
        const matchedTime = matchOption(profile.time_constraint, opts.time_constraints || DEFAULT_OPTIONS.time_constraints);
        const matchedGrade = matchOption(profile.grade, opts.grades || DEFAULT_OPTIONS.grades);
        const matchedSpecialty = matchOption(profile.specialty, opts.specialties || DEFAULT_OPTIONS.specialties);

        setFormData(prev => ({
          ...prev,
          grade: matchedGrade || profile.grade || '',
          specialty: matchedSpecialty || profile.specialty || '',
          case_scale: profile.case_scale || '',
          follow_up_available: profile.follow_up_available || false,
          gold_standard_available: profile.gold_standard_available || false,
          time_constraint: matchedTime || profile.time_constraint || '',
          statistical_background: matchedStatsBg,
          ai_background: matchedAiBg,
          target_journal_level: matchedJournal,
          available_resources: profile.available_resources || {},
          student_input: ''
        }));
      } else {
        setFormData(prev => ({
          ...prev,
          statistical_background: '',
          ai_background: '',
          target_journal_level: '',
          available_resources: {},
          student_input: ''
        }));
      }
    } catch (err) {
      console.error('加载用户画像失败:', err);
      setFormData(prev => ({
        ...prev,
        statistical_background: '',
        ai_background: '',
        target_journal_level: '',
        available_resources: {},
        student_input: ''
      }));
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleResourceChange = (resourceType, value) => {
    setFormData(prev => ({
      ...prev,
      available_resources: {
        ...prev.available_resources,
        [resourceType]: value
      }
    }));
  };

  const nextStep = () => {
    if (loading) return;
    if (currentStep >= 3) return;

    if (currentStep === 1) {
      if (!formData.student_input || formData.student_input.trim().length < 10) {
        setError('请输入详细的研究需求（至少10个字符）');
        return;
      }
    } else if (currentStep === 2) {
      if (!formData.grade || !formData.specialty) {
        setError('请填写年级和专业方向');
        return;
      }
      if (formData.specialty === '其他' && (!formData.customSpecialty || formData.customSpecialty.trim().length < 2)) {
        setError('请选择专业方向，如果选择"其他"，请填写自定义专业方向（至少2个字符）');
        return;
      }
    }

    setError('');
    const nextStepNumber = currentStep + 1;
    if (nextStepNumber <= 3) {
      setCurrentStep(nextStepNumber);
    }
  };

  const prevStep = () => {
    setCurrentStep(prev => Math.max(prev - 1, 1));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (currentStep !== 3) {
      setError('请完成所有步骤后再提交');
      return;
    }

    if (!formData.statistical_background) {
      setError('请选择统计学基础水平');
      return;
    }
    if (!formData.ai_background) {
      setError('请选择AI基础水平');
      return;
    }
    if (!formData.target_journal_level) {
      setError('请选择目标期刊层级');
      return;
    }

    setError('');
    setSuccess('');
    setLoading(true);
    setShowProgress(true);

    try {
      // 第一步：保存或更新学生画像
      setProgressInfo('正在保存学生画像...');
      await saveStudentProfile();

      // 第二步：启动异步生成任务
      setProgressInfo('正在启动方案生成任务...');
      const startResponse = await apiClient.post('/api/multi-agent/generate-plan', {
        user_id: user.id,
        student_input: formData.student_input,
      }, { timeout: 15000 });

      if (!startResponse.data.success) {
        setError(startResponse.data.error || '启动生成任务失败');
        setLoading(false);
        setShowProgress(false);
        return;
      }

      const taskId = startResponse.data.task_id;
      console.log('Async task started, task_id:', taskId);

      // 第三步：轮询任务进度
      const pollInterval = 3000;
      let pollCount = 0;
      let hasShownLongWaitMsg = false;

      const pollTimer = setInterval(async () => {
        pollCount++;
        try {
          const taskResponse = await apiClient.get(`/api/multi-agent/task/${taskId}`);
          const task = taskResponse.data.task;

          if (!task || !task.status) {
            clearInterval(pollTimer);
            setError('任务不存在或已过期');
            setLoading(false);
            setShowProgress(false);
            return;
          }

          const progress = task.progress || 0;
          const step = task.step || '处理中';

          // 超过10分钟仍在运行，提示用户可在历史方案中查看
          if (pollCount > 200 && !hasShownLongWaitMsg) {
            hasShownLongWaitMsg = true;
            setProgressInfo(`${step} (${progress}%) — 生成时间较长，完成后可在历史方案列表中查看`);
          } else {
            setProgressInfo(`${step} (${progress}%)`);
          }
          setProgressPercent(progress);

          if (task.status === 'done') {
            clearInterval(pollTimer);
            const planId = task.result?.plan_id;
            if (planId) {
              setSuccess('研究方案生成成功！正在跳转...');
              setTimeout(() => {
                navigate(`/plan/${planId}`);
              }, 1500);
            } else {
              setError('生成完成但未获取到方案ID');
              setLoading(false);
              setShowProgress(false);
            }
          } else if (task.status === 'error') {
            clearInterval(pollTimer);
            setError(task.error || '方案生成失败');
            setLoading(false);
            setShowProgress(false);
          }
        } catch (pollErr) {
          console.error('轮询任务状态失败:', pollErr);
          // 网络错误不中断轮询，继续等待
        }
      }, pollInterval);

    } catch (err) {
      setError(err.response?.data?.error || '生成研究方案失败');
      setLoading(false);
      setShowProgress(false);
    }
  };

  const saveStudentProfile = async () => {
    try {
      const finalSpecialty = formData.specialty === '其他'
        ? formData.customSpecialty
        : formData.specialty;

      const profileData = {
        user_id: user.id,
        grade: formData.grade,
        specialty: finalSpecialty,
        available_resources: formData.available_resources,
        case_scale: formData.case_scale,
        follow_up_available: formData.follow_up_available,
        gold_standard_available: formData.gold_standard_available,
        statistical_background: formData.statistical_background,
        ai_background: formData.ai_background,
        time_constraint: formData.time_constraint,
        target_journal_level: formData.target_journal_level
      };

      const existingResponse = await apiClient.get(`/api/profile/student/${user.id}`);

      if (existingResponse.data.success) {
        await apiClient.put(`/api/profile/student/${user.id}`, profileData);
      } else {
        await apiClient.post('/api/profile/student', profileData);
      }
    } catch (err) {
      console.error('保存学生画像失败:', err);
      throw new Error('保存学生画像失败');
    }
  };

  const renderStep1 = () => (
    <div>
      <h5 className="mb-4">研究需求输入</h5>
      <Form.Group className="mb-3">
        <Form.Label>请描述您的研究想法或需求 *</Form.Label>
        <Form.Control
          as="textarea"
          rows={6}
          name="student_input"
          value={formData.student_input}
          onChange={handleChange}
          placeholder="请详细描述您的研究兴趣、想要解决的问题、已有的想法等..."
          required
        />
        <Form.Text className="text-muted">
          提示：描述越详细，生成的方案越贴合您的需求
        </Form.Text>
      </Form.Group>
    </div>
  );

  const renderStep2 = () => (
    <div>
      <h5 className="mb-4">基本信息</h5>
      <Row>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Label>年级 *</Form.Label>
            <Form.Select
              name="grade"
              value={formData.grade}
              onChange={handleChange}
              required
            >
              <option value="">请选择年级</option>
              {profileOptions.grades?.map(grade => (
                <option key={grade} value={grade}>{grade}</option>
              ))}
            </Form.Select>
          </Form.Group>
        </Col>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Label>亚专业方向 *</Form.Label>
            <Form.Select
              name="specialty"
              value={formData.specialty}
              onChange={handleChange}
              required
            >
              <option value="">请选择方向</option>
              {profileOptions.specialties?.map(specialty => (
                <option key={specialty} value={specialty}>{specialty}</option>
              ))}
            </Form.Select>
            {formData.specialty === '其他' && (
              <Form.Control
                type="text"
                placeholder="请填写您的专业方向"
                value={formData.customSpecialty || ''}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  customSpecialty: e.target.value
                }))}
                className="mt-2"
                required
              />
            )}
          </Form.Group>
        </Col>
      </Row>

      <Row>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Label>病例规模</Form.Label>
            <Form.Select
              name="case_scale"
              value={formData.case_scale}
              onChange={handleChange}
            >
              <option value="">请选择规模</option>
              {profileOptions.case_scales?.map(scale => (
                <option key={scale} value={scale}>{scale}</option>
              ))}
            </Form.Select>
          </Form.Group>
        </Col>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Label>时间限制</Form.Label>
            <Form.Select
              name="time_constraint"
              value={formData.time_constraint}
              onChange={handleChange}
            >
              <option value="">请选择时间</option>
              {profileOptions.time_constraints?.map(time => (
                <option key={time} value={time}>{time}</option>
              ))}
            </Form.Select>
          </Form.Group>
        </Col>
      </Row>

      <Row>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Check
              type="checkbox"
              label="可进行随访"
              name="follow_up_available"
              checked={formData.follow_up_available}
              onChange={handleChange}
            />
          </Form.Group>
        </Col>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Check
              type="checkbox"
              label="有金标准"
              name="gold_standard_available"
              checked={formData.gold_standard_available}
              onChange={handleChange}
            />
          </Form.Group>
        </Col>
      </Row>
    </div>
  );

  const renderStep3 = () => (
    <div>
      <h5 className="mb-4">技能基础与目标</h5>
      <div className="alert alert-warning mb-4">
        <small>
          <strong>步骤3：请完成最终设置</strong><br/>
          请根据您的实际情况选择统计学基础、AI基础和目标期刊层级。<br/>
          <strong>所有选项都必须选择完成后，才能点击"生成研究方案"按钮。</strong><br/>
          当前完成状态：{formData.statistical_background ? '✓' : '✗'} 统计学基础 | {formData.ai_background ? '✓' : '✗'} AI基础 | {formData.target_journal_level ? '✓' : '✗'} 目标期刊
        </small>
      </div>
      <Row>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Label>统计学基础</Form.Label>
            <Form.Select
              name="statistical_background"
              value={formData.statistical_background}
              onChange={handleChange}
            >
              <option value="">请选择水平</option>
              {profileOptions.statistical_backgrounds?.map(level => (
                <option key={level} value={level}>{level}</option>
              ))}
            </Form.Select>
          </Form.Group>
        </Col>
        <Col md={6}>
          <Form.Group className="mb-3">
            <Form.Label>AI基础</Form.Label>
            <Form.Select
              name="ai_background"
              value={formData.ai_background}
              onChange={handleChange}
            >
              <option value="">请选择水平</option>
              {profileOptions.ai_backgrounds?.map(level => (
                <option key={level} value={level}>{level}</option>
              ))}
            </Form.Select>
          </Form.Group>
        </Col>
      </Row>

      <Form.Group className="mb-3">
        <Form.Label>目标期刊层级</Form.Label>
        <Form.Select
          name="target_journal_level"
          value={formData.target_journal_level}
          onChange={handleChange}
        >
          <option value="">请选择目标</option>
          {profileOptions.target_journal_levels?.map(level => (
            <option key={level} value={level}>{level}</option>
          ))}
        </Form.Select>
      </Form.Group>

      <Form.Group className="mb-3">
        <Form.Label>可用资源</Form.Label>
        <Row>
          <Col md={4}>
            <Form.Check
              type="checkbox"
              label="影像设备"
              checked={formData.available_resources?.imaging_equipment || false}
              onChange={(e) => handleResourceChange('imaging_equipment', e.target.checked)}
            />
          </Col>
          <Col md={4}>
            <Form.Check
              type="checkbox"
              label="临床数据"
              checked={formData.available_resources?.clinical_data || false}
              onChange={(e) => handleResourceChange('clinical_data', e.target.checked)}
            />
          </Col>
          <Col md={4}>
            <Form.Check
              type="checkbox"
              label="统计软件"
              checked={formData.available_resources?.statistical_software || false}
              onChange={(e) => handleResourceChange('statistical_software', e.target.checked)}
            />
          </Col>
        </Row>
      </Form.Group>
    </div>
  );

  const isStep3Complete = formData.statistical_background && formData.ai_background && formData.target_journal_level;

  return (
    <div>
      <Container className="mt-4">
        <Row className="justify-content-center">
          <Col lg={8}>
            <Card>
              <Card.Header>
                <h4 className="mb-0">研究方案生成</h4>
              </Card.Header>
              <Card.Body>
                {error && <Alert variant="danger">{error}</Alert>}
                {success && <Alert variant="success">{success}</Alert>}

                <ProgressBar now={loading ? progressPercent : (currentStep / 3) * 100} className="mb-4">
                  <ProgressBar striped variant={loading ? "info" : "primary"} now={loading ? progressPercent : (currentStep / 3) * 100} key={1} />
                </ProgressBar>

                <div className="text-center mb-4">
                  <h5>步骤 {currentStep} / 3 - {currentStep === 1 ? '研究需求输入' : currentStep === 2 ? '基本信息' : '技能基础与目标'}</h5>
                </div>

                <div onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    e.stopPropagation();
                    return false;
                  }
                }}>
                  {currentStep === 1 && renderStep1()}
                  {currentStep === 2 && renderStep2()}
                  {currentStep === 3 && renderStep3()}

                  <div className="d-flex justify-content-between mt-4">
                    <div>
                      <Button
                        variant="outline-info"
                        onClick={() => setShowRealtimeConsole(!showRealtimeConsole)}
                        disabled={loading}
                      >
                        📊 {showRealtimeConsole ? '隐藏实时日志' : '查看实时日志'}
                      </Button>
                    </div>

                    <div>
                      <Button
                        variant="secondary"
                        onClick={prevStep}
                        disabled={currentStep === 1 || loading}
                        className="me-2"
                        type="button"
                      >
                        上一步
                      </Button>

                      {currentStep === 1 || currentStep === 2 ? (
                        <Button
                          variant="primary"
                          onClick={nextStep}
                          disabled={loading}
                          type="button"
                        >
                          下一步
                        </Button>
                      ) : (
                        <Button
                          variant="success"
                          type="button"
                          onClick={handleSubmit}
                          disabled={loading || !isStep3Complete}
                          size="lg"
                        >
                          {loading ? (
                            <React.Fragment>
                              <Spinner animation="border" size="sm" className="me-2" />
                              正在生成研究方案...
                            </React.Fragment>
                          ) : (
                            '🚀 生成研究方案'
                          )}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              </Card.Body>
            </Card>

            <RealtimeDebugConsole
              isVisible={showRealtimeConsole}
              onToggle={() => setShowRealtimeConsole(!showRealtimeConsole)}
            />
          </Col>
        </Row>
      </Container>
    </div>
  );
}

export default ResearchInput;
