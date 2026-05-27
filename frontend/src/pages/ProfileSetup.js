import React, { useState, useEffect } from 'react';
import { Card, Form, Button, Alert, Container, Row, Col } from 'react-bootstrap';
import { useAuth } from '../contexts/AuthContext';
import apiClient from '../config';
import { useNavigate } from 'react-router-dom';

function ProfileSetup() {
  const { user, updateUser } = useAuth();
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    grade: '',
    specialty: '',
    available_resources: {},
    case_scale: '',
    follow_up_available: false,
    gold_standard_available: false,
    statistical_background: '',
    ai_background: '',
    time_constraint: '',
    target_journal_level: ''
  });
  const [profileOptions, setProfileOptions] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

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
        setFormData({
          grade: profile.grade || '',
          specialty: profile.specialty || '',
          case_scale: profile.case_scale || '',
          follow_up_available: profile.follow_up_available || false,
          gold_standard_available: profile.gold_standard_available || false,
          statistical_background: profile.statistical_background || '',
          ai_background: profile.ai_background || '',
          time_constraint: profile.time_constraint || '',
          target_journal_level: profile.target_journal_level || '',
          available_resources: profile.available_resources || {}
        });
      }
    } catch (err) {
      if (err.response && err.response.status === 404) {
        console.log('用户尚未设置个人画像，将创建新的画像');
        setFormData(prev => ({
          ...prev,
          grade: user.grade || '',
          specialty: user.specialty || ''
        }));
      } else {
        console.error('加载用户画像失败:', err);
      }
    }
  };

  const handleChange = (e) => {
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      const profileData = {
        user_id: user.id,
        ...formData
      };

      try {
        const response = await apiClient.post('/api/profile/student', profileData);
        if (response.data.success) {
          setSuccess('个人资料创建成功！');
          updateUser({ ...user, grade: formData.grade, specialty: formData.specialty });
          setTimeout(() => {
            navigate('/');
          }, 2000);
        }
      } catch (createErr) {
        if (createErr.response && createErr.response.status === 409) {
          try {
            const response = await apiClient.put(`/api/profile/student/${user.id}`, profileData);
            if (response.data.success) {
              setSuccess('个人资料更新成功！');
              updateUser({ ...user, grade: formData.grade, specialty: formData.specialty });
              setTimeout(() => {
                navigate('/');
              }, 2000);
            }
          } catch (updateErr) {
            throw updateErr;
          }
        } else {
          throw createErr;
        }
      }
    } catch (err) {
      setError(err.response?.data?.error || '保存失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container className="mt-4">
      <Row className="justify-content-center">
        <Col lg={8}>
          <Card>
            <Card.Header>
              <h4>个人资料设置</h4>
            </Card.Header>
            <Card.Body>
              {error && <Alert variant="danger">{error}</Alert>}
              {success && <Alert variant="success">{success}</Alert>}

              <Form onSubmit={handleSubmit}>
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

                <Row className="mb-3">
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="可进行随访"
                      name="follow_up_available"
                      checked={formData.follow_up_available}
                      onChange={handleChange}
                    />
                  </Col>
                  <Col md={6}>
                    <Form.Check
                      type="checkbox"
                      label="有金标准"
                      name="gold_standard_available"
                      checked={formData.gold_standard_available}
                      onChange={handleChange}
                    />
                  </Col>
                </Row>

                <Form.Group className="mb-4">
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

                <Button
                  variant="primary"
                  type="submit"
                  className="w-100"
                  disabled={loading}
                >
                  {loading ? '保存中...' : '保存设置'}
                </Button>
              </Form>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
}

export default ProfileSetup;
