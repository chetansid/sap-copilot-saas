export const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const getToken = () => localStorage.getItem('token');

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {};
  if (getToken()) headers.Authorization = `Bearer ${getToken()}`;
  if (body) headers['Content-Type'] = 'application/json';
  const res = await fetch(API + path, { method, headers, body: body ? JSON.stringify(body) : form });
  if (res.status === 401) { localStorage.removeItem('token'); window.location = '/login'; }
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    throw new Error(typeof e.detail === 'string' ? e.detail : 'Request failed');
  }
  return res.json();
}