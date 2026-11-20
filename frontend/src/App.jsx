import { BrowserRouter, Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom';

import { getToken } from './api';
import Auth from './pages/Auth';
import Dashboard from './pages/Dashboard';
import Project from './pages/Project';
import Settings from './pages/Settings';
import './App.css';

const Protected = ({ children }) => getToken() ? children : <Navigate to="/login" />;

function Nav() {
  useLocation();            // re-renders Nav on every route change, so the token check stays current
  const nav = useNavigate();
  if (!getToken()) return null;
  const logout = () => { localStorage.removeItem('token'); nav('/login'); };
  return (
    <nav>
      <b>SAP Copilot</b>
      <Link to="/dashboard">Projects</Link>
      <Link to="/settings">Billing</Link>
      <button onClick={logout}>Log out</button>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/login" element={<Auth mode="login" />} />
        <Route path="/signup" element={<Auth mode="signup" />} />
        <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
        <Route path="/project/:id" element={<Protected><Project /></Protected>} />
        <Route path="/settings" element={<Protected><Settings /></Protected>} />
        <Route path="*" element={<Navigate to="/dashboard" />} />
      </Routes>
    </BrowserRouter>
  );
}