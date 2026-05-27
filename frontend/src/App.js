import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Container } from 'react-bootstrap';
import Navigation from './components/Navigation';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import ProfileSetup from './pages/ProfileSetup';
import ResearchInput from './pages/ResearchInput';
import PlanViewer from './pages/PlanViewer';
import ExpertReview from './pages/ExpertReview';
import AdminPanel from './pages/AdminPanel';
import LiteratureDemo from './pages/LiteratureDemo';
import ShareView from './pages/ShareView';
import ApiSettings from './pages/ApiSettings';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import './App.css';

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="App">
          <Navigation />
          <Container fluid className="main-container">
            <Routes>
              <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/profile-setup" element={<ProtectedRoute><ProfileSetup /></ProtectedRoute>} />
              <Route path="/research-input" element={<ProtectedRoute><ResearchInput /></ProtectedRoute>} />
              <Route path="/plan/:planId" element={<ProtectedRoute><PlanViewer /></ProtectedRoute>} />
              <Route path="/expert-review" element={<ProtectedRoute requiredRole="expert"><ExpertReview /></ProtectedRoute>} />
              <Route path="/admin" element={<ProtectedRoute requiredRole="admin"><AdminPanel /></ProtectedRoute>} />
              <Route path="/literature-demo" element={<LiteratureDemo />} />
              <Route path="/api-settings" element={<ProtectedRoute><ApiSettings /></ProtectedRoute>} />
              <Route path="/share/:shareCode" element={<ShareView />} />
            </Routes>
          </Container>
        </div>
      </Router>
    </AuthProvider>
  );
}

// 受保护的路由组件
function ProtectedRoute({ children, requiredRole }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="text-center mt-5">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">加载中...</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && user.user_type !== requiredRole) {
    return <Navigate to="/" replace />;
  }

  return children;
}

export default App;