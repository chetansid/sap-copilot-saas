import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../api';

export default function Auth({ mode }) {
  const [f, setF] = useState({ email: '', password: '', full_name: '' });
  const [err, setErr] = useState('');
  const nav = useNavigate();
  const set = k => e => setF({ ...f, [k]: e.target.value });

  const submit = async e => {
    e.preventDefault();
    try {
      const d = await api(`/auth/${mode}`, { method: 'POST', body: f });
      localStorage.setItem('token', d.token);
      nav('/dashboard');
    } catch (x) { setErr(x.message); }
  };

  return (
    <form className="card narrow" onSubmit={submit}>
      <h2>{mode === 'signup' ? 'Start your 7-day free trial' : 'Log in'}</h2>
      {mode === 'signup' && <input placeholder="Full name" value={f.full_name} onChange={set('full_name')} required />}
      <input type="email" placeholder="Email" value={f.email} onChange={set('email')} required />
      <input type="password" placeholder="Password" value={f.password} onChange={set('password')} required />
      {err && <p className="err">{err}</p>}
      <button>{mode === 'signup' ? 'Sign up' : 'Log in'}</button>
      <p>{mode === 'signup' ? <Link to="/login">Have an account? Log in</Link> : <Link to="/signup">New here? Sign up</Link>}</p>
    </form>
  );
}