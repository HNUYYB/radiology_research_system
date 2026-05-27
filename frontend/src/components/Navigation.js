import React from 'react';
import { Navbar, Nav, Container, Button } from 'react-bootstrap';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

function Navigation() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <Navbar bg="light" expand="lg" className="shadow-sm">
      <Container>
        <Navbar.Brand as={Link} to="/">
          <i className="fas fa-x-ray me-2"></i>
          放射学研究方案生成系统
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="basic-navbar-nav" />
        <Navbar.Collapse id="basic-navbar-nav">
          <Nav className="me-auto">
            {user && (
              <>
                <Nav.Link as={Link} to="/">
                  仪表板
                </Nav.Link>
                <Nav.Link as={Link} to="/research-input">
                  研究方案生成
                </Nav.Link>
                <Nav.Link as={Link} to="/literature-demo">
                  📚 文献推荐
                </Nav.Link>
                {user.user_type === 'expert' && (
                  <Nav.Link as={Link} to="/expert-review">
                    专家评审
                  </Nav.Link>
                )}
                {user.user_type === 'admin' && (
                  <Nav.Link as={Link} to="/admin">
                    系统管理
                  </Nav.Link>
                )}
              </>
            )}
          </Nav>
          <Nav>
            {user ? (
              <>
                <Nav.Link as={Link} to="/api-settings">
                  ⚙️ API 设置
                </Nav.Link>
                <Nav.Link as={Link} to="/profile-setup">
                  个人设置
                </Nav.Link>
                <Button variant="outline-danger" size="sm" onClick={handleLogout}>
                  退出登录
                </Button>
              </>
            ) : (
              <>
                <Nav.Link as={Link} to="/login">
                  登录
                </Nav.Link>
                <Nav.Link as={Link} to="/register">
                  注册
                </Nav.Link>
              </>
            )}
          </Nav>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}

export default Navigation;