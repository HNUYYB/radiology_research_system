import React, { useState, useEffect } from 'react';
import { Card, Button, Badge, Row, Col, Form, Pagination, Spinner, Alert } from 'react-bootstrap';
import { BiCalculator, BiCalendar, BiUser, BiBook, BiFile, BiLinkExternal, BiSearch, BiFilter } from 'react-icons/bi';
import ModernLiteratureCard from './ModernLiteratureCard';
import ScoreFormulaPanel from './ScoreFormulaPanel';

function LiteratureRecommendation({ literature, loading = false, onSearch, availableStrategies = [] }) {
  const [sortBy, setSortBy] = useState('relevance');
  const [filterYear, setFilterYear] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [viewMode, setViewMode] = useState('card'); // 'card' or 'list'
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [studyTypeFilter, setStudyTypeFilter] = useState('');
  const [evidenceLevelFilter, setEvidenceLevelFilter] = useState('');
  const [specialtyFilter, setSpecialtyFilter] = useState('');
  const [selectedPapers, setSelectedPapers] = useState(new Set());
  const papersPerPage = 9;

  // 文献处理逻辑
  const processPapers = (papers) => {
    if (!papers) return [];

    let processed = [...papers];

    // 搜索过滤
    if (searchTerm) {
      processed = processed.filter(paper =>
        paper.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (Array.isArray(paper.authors) ? paper.authors.join(' ').toLowerCase() : paper.authors?.toLowerCase() || '').includes(searchTerm.toLowerCase()) ||
        paper.journal?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        paper.abstract?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        paper.keywords?.some(keyword => keyword.toLowerCase().includes(searchTerm.toLowerCase()))
      );
    }

    // 年份过滤
    if (filterYear !== 'all') {
      const currentYear = new Date().getFullYear();
      const yearThreshold = currentYear - parseInt(filterYear);
      processed = processed.filter(paper => {
        const paperYear = parseInt(paper.pubdate?.substring(0, 4)) || 0;
        return paperYear >= yearThreshold;
      });
    }

    // 研究类型过滤
    if (studyTypeFilter) {
      processed = processed.filter(paper => paper.study_type === studyTypeFilter);
    }

    // 证据等级过滤
    if (evidenceLevelFilter) {
      processed = processed.filter(paper => paper.evidence_level === evidenceLevelFilter);
    }

    // 亚专业过滤
    if (specialtyFilter) {
      processed = processed.filter(paper => paper.specialty_area === specialtyFilter);
    }

    // 排序
    processed.sort((a, b) => {
      switch (sortBy) {
        case 'relevance':
          return (b.relevance_score ?? 0) - (a.relevance_score ?? 0);
        case 'date':
          const yearA = parseInt(a.pubdate?.substring(0, 4)) || 0;
          const yearB = parseInt(b.pubdate?.substring(0, 4)) || 0;
          return yearB - yearA;
        case 'journal':
          return (a.journal || '').localeCompare(b.journal || '');
        case 'title':
          return (a.title || '').localeCompare(b.title || '');
        default:
          return 0;
      }
    });

    return processed;
  };

  // 分页逻辑
  const processedPapers = processPapers(literature?.recommended_papers || []);
  const totalPages = Math.ceil(processedPapers.length / papersPerPage);
  const startIndex = (currentPage - 1) * papersPerPage;
  const currentPapers = processedPapers.slice(startIndex, startIndex + papersPerPage);

  // 重置页码当过滤条件改变时
  useEffect(() => {
    setCurrentPage(1);
  }, [sortBy, filterYear, searchTerm, studyTypeFilter, evidenceLevelFilter, specialtyFilter]);

  // 处理文献选择
  const handlePaperSelect = (paperId) => {
    setSelectedPapers(prev => {
      const newSet = new Set(prev);
      if (newSet.has(paperId)) {
        newSet.delete(paperId);
      } else {
        newSet.add(paperId);
      }
      return newSet;
    });
  };

  // 全选/取消全选当前页
  const toggleSelectAll = () => {
    const currentPagePaperIds = currentPapers.map((_, index) => startIndex + index);
    setSelectedPapers(prev => {
      const newSet = new Set(prev);
      const allSelected = currentPagePaperIds.every(id => newSet.has(id));

      if (allSelected) {
        // 取消全选
        currentPagePaperIds.forEach(id => newSet.delete(id));
      } else {
        // 全选
        currentPagePaperIds.forEach(id => newSet.add(id));
      }
      return newSet;
    });
  };

  // 导出选中的文献
  const exportSelectedPapers = () => {
    const selectedPapersData = processedPapers.filter((_, index) =>
      selectedPapers.has(index)
    );

    if (selectedPapersData.length === 0) {
      alert('请先选择要导出的文献');
      return;
    }

    // 创建BibTeX格式
    const bibtexContent = selectedPapersData.map((paper, index) => {
      const citeKey = `paper_${paper.pmid || index}_${Date.now()}`;
      const authors = Array.isArray(paper.authors) ? paper.authors.join(' and ') : paper.authors || 'Unknown authors';
      return `@article{${citeKey},
  title={${paper.title}},
  author={${authors}},
  journal={${paper.journal}},
  year={${paper.pubdate?.substring(0, 4) || 'Unknown'}},
  doi={${paper.doi}},
  pmid={${paper.pmid}}
}`;
    }).join('\n\n');

    // 下载文件
    const blob = new Blob([bibtexContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `literature_export_${new Date().toISOString().split('T')[0]}.bib`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    // 清空选择
    setSelectedPapers(new Set());
  };


  if (loading) {
    return (
      <div className="text-center py-5">
        <Spinner animation="border" variant="primary" className="mb-3" />
        <h6 className="text-muted">正在搜索相关文献...</h6>
        <small className="text-muted">这可能需要几分钟时间，请耐心等待</small>
      </div>
    );
  }

  if (!literature || !literature.recommended_papers || literature.recommended_papers.length === 0) {
    return (
      <Card className="border-0 shadow-sm">
        <Card.Body className="text-center py-5">
          <div className="display-1 mb-3 text-muted">📚</div>
          <h5 className="text-muted mb-2">暂无相关文献推荐</h5>
          <p className="text-muted small mb-4">系统正在为您搜索相关学术文献，请稍后再试</p>
          <Button variant="outline-primary" size="sm">
            <BiSearch className="me-2" />
            重新搜索
          </Button>
        </Card.Body>
      </Card>
    );
  }

  return (
    <div className="literature-recommendation">
      {/* 顶部概览区域 */}
      <Card className="border-0 shadow-sm mb-4">
        <Card.Body className="bg-gradient bg-light">
          <Row className="align-items-center">
            <Col lg={8}>
              <div className="d-flex align-items-center mb-3 mb-lg-0">
                <div className="bg-primary text-white rounded-circle d-flex align-items-center justify-content-center me-3"
                     style={{ width: '48px', height: '48px' }}>
                  <BiFile size={24} />
                </div>
                <div>
                  <h4 className="mb-1 fw-bold">文献推荐</h4>
                  <p className="text-muted mb-0 small">
                    关键词：<strong>"{literature.search_query || literature.search_summary || '您的研究方向'}"</strong>
                    ，共找到 <Badge bg="primary" className="fs-6">{processedPapers.length}</Badge> 篇相关文献
                  </p>
                </div>
              </div>
            </Col>

            <Col lg={4}>
              <div className="d-flex gap-2 justify-content-lg-end">
                {/* 批量操作 */}
                {selectedPapers.size > 0 && (
                  <Button
                    variant="outline-success"
                    size="sm"
                    onClick={() => exportSelectedPapers()}
                  >
                    导出选中 ({selectedPapers.size})
                  </Button>
                )}

                {/* 视图模式切换 */}
                <Button
                  variant={viewMode === 'card' ? 'primary' : 'outline-primary'}
                  size="sm"
                  onClick={() => setViewMode('card')}
                  title="卡片视图"
                >
                  卡片
                </Button>
                <Button
                  variant={viewMode === 'list' ? 'primary' : 'outline-primary'}
                  size="sm"
                  onClick={() => setViewMode('list')}
                  title="列表视图"
                >
                  列表
                </Button>
              </div>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {/* 搜索和筛选控制 */}
      <Card className="border-0 shadow-sm mb-4">
        <Card.Body>
          <Row className="g-3">
            <Col md={6} lg={4}>
              <Form.Group>
                <Form.Label className="small text-muted mb-1">
                  <BiSearch className="me-1" />
                  搜索文献
                </Form.Label>
                <Form.Control
                  type="text"
                  placeholder="搜索标题、作者、期刊或摘要..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  size="sm"
                />
              </Form.Group>
            </Col>

            <Col md={3} lg={2}>
              <Form.Group>
                <Form.Label className="small text-muted mb-1">
                  <BiFilter className="me-1" />
                  排序方式
                </Form.Label>
                <Form.Select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  size="sm"
                >
                  <option value="relevance">相关度</option>
                  <option value="date">最新发表</option>
                  <option value="journal">期刊名称</option>
                  <option value="title">文献标题</option>
                </Form.Select>
              </Form.Group>
            </Col>

            <Col md={3} lg={2}>
              <Form.Group>
                <Form.Label className="small text-muted mb-1">发表年份</Form.Label>
                <Form.Select
                  value={filterYear}
                  onChange={(e) => setFilterYear(e.target.value)}
                  size="sm"
                >
                  <option value="all">全部年份</option>
                  <option value="1">近1年</option>
                  <option value="3">近3年</option>
                  <option value="5">近5年</option>
                  <option value="10">近10年</option>
                </Form.Select>
              </Form.Group>
            </Col>

            <Col md={12} lg={4} className="d-flex align-items-end">
              <div className="small text-muted">
                显示第 <strong>{startIndex + 1}</strong> - <strong>{Math.min(startIndex + papersPerPage, processedPapers.length)}</strong> 篇，
                共 <strong>{processedPapers.length}</strong> 篇
              </div>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      {/* 高级过滤器 */}
      <Card className="border-0 shadow-sm mb-4">
        <Card.Body>
          <h6 className="mb-3">
            <BiFilter className="me-2" />
            高级过滤
          </h6>
          <Row className="g-3">
            <Col md={6} lg={3}>
              <Form.Group>
                <Form.Label className="small text-muted mb-1">搜索策略</Form.Label>
                <Form.Select
                  value={selectedStrategy}
                  onChange={(e) => {
                    setSelectedStrategy(e.target.value);
                    if (onSearch && e.target.value) {
                      onSearch({ strategy: e.target.value });
                    }
                  }}
                  size="sm"
                >
                  <option value="">默认搜索</option>
                  <option value="core_papers">核心文献 (高影响力期刊)</option>
                  <option value="recent_advances">最新进展 (近2年)</option>
                  <option value="methodological_papers">方法学文献</option>
                  <option value="clinical_applications">临床应用文献</option>
                  <option value="review_papers">综述文献</option>
                </Form.Select>
              </Form.Group>
            </Col>

            <Col md={6} lg={2}>
              <Form.Group>
                <Form.Label className="small text-muted mb-1">研究类型</Form.Label>
                <Form.Select
                  value={studyTypeFilter}
                  onChange={(e) => setStudyTypeFilter(e.target.value)}
                  size="sm"
                >
                  <option value="">全部类型</option>
                  <option value="randomized_controlled_trial">随机对照试验</option>
                  <option value="systematic_review">系统综述</option>
                  <option value="meta_analysis">Meta分析</option>
                  <option value="cohort_study">队列研究</option>
                  <option value="case_control">病例对照</option>
                  <option value="original_research">原创研究</option>
                </Form.Select>
              </Form.Group>
            </Col>

            <Col md={6} lg={2}>
              <Form.Group>
                <Form.Label className="small text-muted mb-1">证据等级</Form.Label>
                <Form.Select
                  value={evidenceLevelFilter}
                  onChange={(e) => setEvidenceLevelFilter(e.target.value)}
                  size="sm"
                >
                  <option value="">全部等级</option>
                  <option value="I">I级证据</option>
                  <option value="II">II级证据</option>
                  <option value="III">III级证据</option>
                  <option value="IV">IV级证据</option>
                  <option value="V">V级证据</option>
                </Form.Select>
              </Form.Group>
            </Col>

            <Col md={6} lg={2}>
              <Form.Group>
                <Form.Label className="small text-muted mb-1">亚专业</Form.Label>
                <Form.Select
                  value={specialtyFilter}
                  onChange={(e) => setSpecialtyFilter(e.target.value)}
                  size="sm"
                >
                  <option value="">全部专业</option>
                  <option value="chest_radiology">胸部影像</option>
                  <option value="neuro_radiology">神经影像</option>
                  <option value="musculoskeletal_radiology">骨肌影像</option>
                  <option value="abdominal_radiology">腹部影像</option>
                  <option value="interventional_radiology">介入放射</option>
                  <option value="breast_radiology">乳腺影像</option>
                </Form.Select>
              </Form.Group>
            </Col>

            <Col md={6} lg={3} />
          </Row>
        </Card.Body>
      </Card>

      {/* 文献列表 */}
      <Card className="border-0 shadow-sm mb-4">
        <Card.Body className="p-3">
          {/* 全选控制 */}
          {currentPapers.length > 0 && (
            <div className="mb-3 pb-2 border-bottom">
              <Form.Check
                type="checkbox"
                label={`全选当前页 (${currentPapers.length} 篇文献)`}
                checked={currentPapers.length > 0 && currentPapers.every((_, index) =>
                  selectedPapers.has(startIndex + index)
                )}
                onChange={toggleSelectAll}
                className="fw-semibold"
              />
            </div>
          )}

          {viewMode === 'card' ? (
            <Row className="g-4">
              {currentPapers.map((paper, index) => (
                <Col key={paper.pmid || index} xs={12} lg={6} xl={4}>
                  <ModernLiteratureCard
                    paper={paper}
                    index={startIndex + index}
                    viewMode="card"
                    onSelect={handlePaperSelect}
                    isSelected={selectedPapers.has(startIndex + index)}
                  />
                </Col>
              ))}
            </Row>
          ) : (
            <div className="d-flex flex-column gap-3">
              {currentPapers.map((paper, index) => (
                <ModernLiteratureCard
                  key={paper.pmid || index}
                  paper={paper}
                  index={startIndex + index}
                  viewMode="list"
                  onSelect={handlePaperSelect}
                  isSelected={selectedPapers.has(startIndex + index)}
                />
              ))}
            </div>
          )}
        </Card.Body>
      </Card>

      {/* 分页 */}
      {totalPages > 1 && (
        <Card className="border-0 shadow-sm mt-4">
          <Card.Body className="d-flex justify-content-center">
            <Pagination className="mb-0">
              <Pagination.First
                onClick={() => setCurrentPage(1)}
                disabled={currentPage === 1}
              />
              <Pagination.Prev
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
              />

              {[...Array(Math.min(5, totalPages))].map((_, i) => {
                let pageNum;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else {
                  if (currentPage <= 3) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }
                }

                return (
                  <Pagination.Item
                    key={pageNum}
                    active={pageNum === currentPage}
                    onClick={() => setCurrentPage(pageNum)}
                  >
                    {pageNum}
                  </Pagination.Item>
                );
              })}

              <Pagination.Next
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
              />
              <Pagination.Last
                onClick={() => setCurrentPage(totalPages)}
                disabled={currentPage === totalPages}
              />
            </Pagination>
          </Card.Body>
        </Card>
      )}

      {/* 使用提示 */}
      <Alert variant="info" className="mt-4 mb-0">
        <div className="d-flex align-items-start">
          <BiFile className="text-info me-2 mt-1" size={20} />
          <div className="small">
            <strong>使用提示:</strong>
            文献默认按个性化推荐分排序（0-100分）。每篇文献卡片上的 <strong>检索分</strong> 反映关键词匹配程度，
            <strong>推荐分</strong> 综合了您的专业、学历和技术背景。点击 <BiCalculator size={12} className="mx-1" /> 按钮可查看评分详情。
          </div>
        </div>
      </Alert>

      {/* 评分公式说明面板 */}
      <ScoreFormulaPanel />
    </div>
  );
}

export default LiteratureRecommendation;