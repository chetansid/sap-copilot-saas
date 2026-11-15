import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';

export default function Dashboard() {
  const [projects, setProjects] = useState([]);
  const [f, setF] = useState({ name: '', client_name: '' });
  const [err, setErr] = useState('');

  const load = () => api('/projects').then(setProjects).catch(e => setErr(e.message));
  useEffect(() => { load(); }, []);

  const create = async e => {
    e.preventDefault();
    await api('/projects', { method: 'POST', body: f });
    setF({ name: '', client_name: '' });
    load();
  };
  const remove = async id => {
    if (!confirm('Delete this project?')) return;
    await api(`/projects/${id}`, { method: 'DELETE' });
    load();
  };

  return (
    <div className="page">
      <h2>Projects</h2>
      {err && <p className="err">{err}</p>}
      <form className="row" onSubmit={create}>
        <input placeholder="Project name" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required />
        <input placeholder="Client" value={f.client_name} onChange={e => setF({ ...f, client_name: e.target.value })} required />
        <button>Create</button>
      </form>
      {projects.map(p => (
        <div className="card row" key={p.id}>
          <Link to={`/project/${p.id}`}><b>{p.name}</b> · {p.client_name}</Link>
          <button className="ghost" onClick={() => remove(p.id)}>Delete</button>
        </div>
      ))}
    </div>
  );
}