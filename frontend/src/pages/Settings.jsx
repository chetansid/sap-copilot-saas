import { useEffect, useState } from 'react';
import { api } from '../api';

export default function Settings() {
  const [me, setMe] = useState(null);
  useEffect(() => { api('/auth/me').then(setMe); }, []);
  const go = async path => { const d = await api(path); window.location = d.url; };
  if (!me) return null;
  const s = me.subscription;
  return (
    <div className="page card narrow">
      <h2>Billing</h2>
      <p>{me.email}</p>
      <p>Status: <b>{s.status}</b>{s.status === 'trial' && ` (ends ${new Date(s.trial_ends_at).toLocaleDateString()})`}</p>
      {s.cancel_at_period_end && <p>Cancels on <b>{new Date(s.current_period_end).toLocaleDateString()}</b>. You keep access until then.</p>}
      {s.status !== 'active'
        ? <button onClick={() => go('/billing/checkout')}>Subscribe — $99/month</button>
        : <button onClick={() => go('/billing/portal')}>Manage subscription</button>}
    </div>
  );
}