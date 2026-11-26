const BASE = import.meta.env.VITE_API_URL || ''

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || body.error || `Request failed (${res.status})`)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  meta: () => req('/api/meta'),
  employees: () => req('/api/employees'),
  addEmployee: (d) => req('/api/employees', { method: 'POST', body: JSON.stringify(d) }),
  updateEmployee: (id, d) => req(`/api/employees/${id}`, { method: 'PUT', body: JSON.stringify(d) }),
  deleteEmployee: (id) => req(`/api/employees/${id}`, { method: 'DELETE' }),
  schedule: () => req('/api/schedules'),
  generate: () => req('/api/schedules/generate', { method: 'POST', body: JSON.stringify({}) }),
  analytics: () => req('/api/analytics'),
  conflicts: () => req('/api/conflicts'),
  constraints: () => req('/api/constraints'),
  deleteConstraint: (id) => req(`/api/constraints/${id}`, { method: 'DELETE' }),
  parse: (text) => req('/api/assistant/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  resetDemo: () => req('/api/demo/reset', { method: 'POST' }),
  exportUrl: (kind) => `${BASE}/api/export/${kind}`,
}
