import axios from 'axios';

// API配置 — 使用相对路径，由 setupProxy.js 代理到后端
export const API_CONFIG = {
  BASE_URL: '',
  TIMEOUT: 120000,
  ENDPOINTS: {
    // 认证相关
    REGISTER: '/api/auth/register',
    LOGIN: '/api/auth/login',
    REFRESH: '/api/auth/refresh',
    ME: '/api/auth/me',

    // 用户画像
    STUDENT_PROFILE: '/api/profile/student',
    PROFILE_OPTIONS: '/api/profile/options',

    // 研究方案
    RESEARCH_PLANS: '/api/research/plans',
    RESEARCH_PLAN: '/api/research/plan',
    MULTI_AGENT_GENERATE: '/api/multi-agent/generate-plan',
    MULTI_AGENT_TASK: '/api/multi-agent/task',
    EDIT_AND_REGENERATE: '/api/research/edit-and-regenerate',

    // 评审相关
    REVIEW_ASSIGNMENTS: '/api/review/assignments',
    REVIEW_SUBMIT: '/api/review/submit',
    REVIEW_PLAN: '/api/review/plan',
    REVIEW_MY_REVIEWS: '/api/review/my-reviews',
    REVIEW_STATISTICS: '/api/review/statistics',

    // 系统相关
    SYSTEM_HEALTH: '/api/health',
    SYSTEM_STATS: '/api/system/stats',
    SYSTEM_LOGS: '/api/system/logs',
    SYSTEM_EXPORT: '/api/system/export-data',
    SYSTEM_MAINTENANCE: '/api/system/maintenance',

    // PubMed
    PUBMED_SEARCH: '/api/pubmed/recommendations/search',
    PUBMED_RECOMMENDATIONS: '/api/pubmed/recommendations',
  }
};

// 创建axios实例
const apiClient = axios.create({
  baseURL: API_CONFIG.BASE_URL,
  timeout: API_CONFIG.TIMEOUT,
  headers: {
    'Content-Type': 'application/json'
  }
});

// 请求拦截器：自动附加 JWT Token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器：处理 401 未授权，尝试刷新 token
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // 如果 401 且不是刷新请求本身，尝试刷新 token
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest.url?.includes('/api/auth/refresh')) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('user');
          window.location.href = '/login';
          return Promise.reject(error);
        }

        const response = await axios.post('/api/auth/refresh', {}, {
          headers: { Authorization: `Bearer ${refreshToken}` }
        });

        if (response.data.access_token) {
          localStorage.setItem('access_token', response.data.access_token);
          originalRequest.headers.Authorization = `Bearer ${response.data.access_token}`;
          return apiClient(originalRequest);
        }
      } catch (refreshError) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
