import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, API, getToken } from '../api';

export default function Project() {
  const { id } = useParams();
  const [docs, setDocs] = useState([]);
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [docType, setDocType] = useState('ricefw');
  const [status, setStatus] = useState('');
  const bottom = useRef();

  const loadDocs = () => api(`/projects/${id}/documents`).then(setDocs);
  useEffect(() => {
    loadDocs();
    api(`/projects/${id}/messages`).then(setMsgs);
  }, [id]);
  useEffect(() => bottom.current?.scrollIntoView({ behavior: 'smooth' }), [msgs]);

  const upload = async e => {
    const file = e.target.files[0];
    if (!file) return;
    setStatus('Ingesting...');
    const form = new FormData();
    form.append('file', file);
    try {
      const d = await api(`/projects/${id}/upload?doc_type=${docType}`, { method: 'POST', form });
      setStatus(`✓ ${d.chunks} chunks`);
      loadDocs();
    } catch (x) { setStatus(x.message); }
    e.target.value = '';
  };

  const send = async () => {
    const question = q.trim();
    if (!question || busy) return;
    setQ(''); setBusy(true);
    setMsgs(m => [...m, { role: 'user', content: question }, { role: 'assistant', content: '' }]);

    const res = await fetch(`${API}/ask-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
      body: JSON.stringify({ question, project_id: Number(id) })
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      setMsgs(m => [...m.slice(0, -1), { role: 'assistant', content: e.detail || 'Request failed' }]);
      setBusy(false); return;
    }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '', text = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const events = buf.split('\n\n');
      buf = events.pop();
      for (const ev of events) {
        if (!ev.startsWith('data: ')) continue;
        const data = ev.slice(6);
        if (data === '[DONE]') continue;
        text += data;
        setMsgs(m => [...m.slice(0, -1), { role: 'assistant', content: text }]);
      }
    }
    setBusy(false);
  };

  return (
    <div className="workspace">
      <aside>
        <h3>Documents</h3>
        <select value={docType} onChange={e => setDocType(e.target.value)}>
          <option value="ricefw">RICEFW spec</option>
          <option value="note">Meeting / implementation notes</option>
          <option value="design">Technical design</option>
        </select>
        <input type="file" accept=".pdf" onChange={upload} />
        <small>{status}</small>
        {docs.map(d => <div key={d.id} className="doc"><span className="badge">{d.doc_type}</span> {d.filename}</div>)}
      </aside>
      <main>
        <div className="msgs">
          {msgs.length === 0 && <p className="hint">Upload a spec and notes, then ask: “Are there conflicts between the spec and the notes?”</p>}
          {msgs.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.content || '…'}</div>)}
          <div ref={bottom} />
        </div>
        <div className="row">
          <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} placeholder="Ask about your project..." />
          <button onClick={send} disabled={busy}>Send</button>
        </div>
      </main>
    </div>
  );
}