import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const AuthContext = createContext();

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 检查本地存储中的用户信息和 token
    const storedUser = localStorage.getItem('user');
    const accessToken = localStorage.getItem('access_token');
    if (storedUser && accessToken) {
      setUser(JSON.parse(storedUser));
    }
    setLoading(false);
  }, []);

  const login = async (username, password) => {
    try {
      const response = await axios.post('/api/auth/login', {
        username,
        password
      });

      if (response.data.success) {
        const { access_token, refresh_token, user: userData } = response.data;
        localStorage.setItem('access_token', access_token);
        if (refresh_token) {
          localStorage.setItem('refresh_token', refresh_token);
        }
        localStorage.setItem('user', JSON.stringify(userData));
        setUser(userData);
        return { success: true, message: response.data.message };
      }
      return { success: false, message: response.data.error };
    } catch (error) {
      return {
        success: false,
        message: error.response?.data?.error || '登录失败'
      };
    }
  };

  const register = async (userData) => {
    try {
      const response = await axios.post('/api/auth/register', userData);

      if (response.data.success) {
        // 如果注册返回了 token，直接登录
        if (response.data.access_token) {
          const { access_token, refresh_token, user: respUser } = response.data;
          localStorage.setItem('access_token', access_token);
          if (refresh_token) {
            localStorage.setItem('refresh_token', refresh_token);
          }
          localStorage.setItem('user', JSON.stringify(respUser));
          setUser(respUser);
        }
        return { success: true, message: '注册成功' };
      }
      return { success: false, message: response.data.error };
    } catch (error) {
      return {
        success: false,
        message: error.response?.data?.error || '注册失败'
      };
    }
  };

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem('user');
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }, []);

  const updateUser = (updatedUser) => {
    setUser(updatedUser);
    localStorage.setItem('user', JSON.stringify(updatedUser));
  };

  const refreshToken = async () => {
    try {
      const refreshTokenValue = localStorage.getItem('refresh_token');
      if (!refreshTokenValue) {
        return false;
      }

      const response = await axios.post('/api/auth/refresh', {}, {
        headers: { Authorization: `Bearer ${refreshTokenValue}` }
      });

      if (response.data.access_token) {
        localStorage.setItem('access_token', response.data.access_token);
        return true;
      }
      return false;
    } catch (error) {
      logout();
      return false;
    }
  };

  const value = {
    user,
    login,
    register,
    logout,
    updateUser,
    refreshToken,
    loading,
    isAuthenticated: !!user && !!localStorage.getItem('access_token'),
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}
