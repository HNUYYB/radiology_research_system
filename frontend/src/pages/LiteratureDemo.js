import React, { useState, useEffect, useRef } from 'react';
import apiClient from '../config';
import LiteratureRecommendation from '../components/LiteratureRecommendation';

function LiteratureDemo() {
  const [literature, setLiterature] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState('');
  const hasLoadedDefault = useRef(false);

  const doSearch = async (query) => {
    if (!query.trim()) return;
    try {
      setLoading(true);
      setError('');
      setLiterature(null);
      const response = await apiClient.post(
        '/api/pubmed/recommendations/search',
        { query: query.trim(), max_results: 30 },
        { timeout: 60000 }
      );

      if (response.data && response.data.success && response.data.data) {
        setLiterature(response.data.data);
      } else {
        setError(response.data?.error || '搜索失败，请重试');
      }
    } catch (err) {
      setError(err.response?.data?.error || '搜索失败，请检查网络后重试');
    } finally {
      setLoading(false);
    }
  };

  // 默认加载一批文献
  useEffect(() => {
    if (!hasLoadedDefault.current) {
      hasLoadedDefault.current = true;
      doSearch('radiology artificial intelligence');
    }
  }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    doSearch(searchQuery);
  };

  return (
    <div className="container-fluid py-4">
      <div className="row justify-content-center">
        <div className="col-xxl-10">
          <div className="text-center mb-4">
            <h1 className="display-5 fw-bold mb-2">📚 PubMed 文献检索</h1>
            <p className="lead text-muted">基于 Biopython + PubMed API 的自动化文献检索</p>
          </div>

          {/* 搜索框 */}
          <div className="row justify-content-center mb-4">
            <div className="col-lg-8">
              <form onSubmit={handleSearch}>
                <div className="input-group input-group-lg shadow-sm">
                  <span className="input-group-text bg-white border-end-0">🔍</span>
                  <input
                    type="text"
                    className="form-control border-start-0"
                    placeholder="输入英文关键词，如：lung nodule radiomics、MRI brain tumor..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                  <button
                    type="submit"
                    className="btn btn-primary px-4 fw-semibold"
                    disabled={loading || !searchQuery.trim()}
                  >
                    {loading ? '检索中...' : '检索'}
                  </button>
                </div>
              </form>
              <div className="form-text text-center mt-1">
                建议使用英文关键词，PubMed 对英文检索支持更好
              </div>
            </div>
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="alert alert-warning text-center" role="alert">
              ⚠️ {error}
            </div>
          )}

          {/* 文献结果 */}
          <LiteratureRecommendation literature={literature} loading={loading} />

          {/* 空状态提示 */}
          {!loading && !literature && !error && (
            <div className="text-center py-5 text-muted">
              <div className="display-1 mb-3">📖</div>
              <h5>正在加载文献...</h5>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default LiteratureDemo;
