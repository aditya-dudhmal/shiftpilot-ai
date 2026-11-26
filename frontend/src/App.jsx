import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from './api.js'

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const SHIFTS = ['Morning', 'Midday', 'Evening']
const ROLE_CLASS = { Cook: 'cook', Server: 'server', Cashier: 'cashier', Dishwasher: 'dishwasher', Supervisor: 'supervisor' }
const EXAMPLES = [
  'Give Alex fewer evening shifts next week',
  "Don't schedule Maya on Friday",
  'Cap Priya at 20 hours',
  'Jordan needs at least 16 hours',
]

export default function App() {
  const [tab, setTab] = useState('dashboard')
  const [theme, setTheme] = useState(() => localStorage.getItem('sp-theme') || 'light')
  const [employees, setEmployees] = useState([])
  const [schedule, setSchedule] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [constraints, setConstraints] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); localStorage.setItem('sp-theme', theme) }, [theme])

  async function load() {
    setLoading(true); setError('')
    try {
      const [emps, sched, an, cons] = await Promise.all([api.employees(), api.schedule(), api.analytics(), api.constraints()])
      setEmployees(emps); setSchedule(sched); setAnalytics(an); setConstraints(cons)
    } catch (e) {
      setError(`Could not reach the API at ${window.location.origin}. Start the backend first: cd backend && uvicorn app.main:app --reload --port 8000 — ${e.message}`)
    } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  async function generate() {
    setBusy(true); setError(''); setNotice('')
    try {
      const r = await api.generate()
      setNotice(`Schedule generated with ${r.solver} — coverage ${(r.coverage * 100).toFixed(0)}%, ${r.assignments.length} shifts. ${r.unfilled.length ? `${r.unfilled.length} slots unfilled — see Conflicts.` : 'All required slots filled.'}`)
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const conflicts = schedule?.conflicts || []
  const errors = conflicts.filter((c) => c.severity === 'error')
  const warnings = conflicts.filter((c) => c.severity === 'warning')

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><div className="logo">S</div><div><h1>ShiftPilot AI</h1><p>Intelligent workforce scheduling · Campus dining demo · Week of {schedule?.week_start || '2026-11-30'}</p></div></div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>{theme === 'light' ? '🌙 Dark mode' : '☀️ Light mode'}</button>
          <button className="btn" onClick={async () => { await api.resetDemo(); setNotice('Demo data reset to the 12-person synthetic roster.'); load() }}>Reset demo</button>
        </div>
      </header>

      <nav className="nav">
        {['dashboard', 'schedule', 'employees', 'assistant', 'analytics'].map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t[0].toUpperCase() + t.slice(1)}</button>
        ))}
      </nav>

      {error && <div className="error" role="alert">{error}</div>}
      {notice && <div className="success">{notice}</div>}
      {loading && <p className="muted">Loading schedule…</p>}

      {!loading && tab === 'dashboard' && (
        <>
          <div className="grid cols-3">
            <div className="card stat"><b>{employees.length}</b><span>Employees on roster</span></div>
            <div className="card stat"><b>{analytics ? `${analytics.coverage_pct}%` : '—'}</b><span>Staffing coverage · {analytics?.filled_slots || 0}/{analytics?.required_slots || 0} slots</span></div>
            <div className="card stat"><b>{analytics ? `${analytics.fairness_score}/100` : '—'}</b><span>Fairness score · mean {analytics?.mean_hours || 0}h / person</span></div>
          </div>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>This week at a glance</h2>
            <p className="muted">Generate an optimised week with OR-Tools, then ask the assistant to adjust it in plain English. No API key needed — demo mode parses instructions with built-in rules.</p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn primary" disabled={busy} onClick={generate}>{busy ? 'Generating…' : '✦ Generate optimised schedule'}</button>
              <a className="btn" href={api.exportUrl('csv')}>Download CSV</a>
              <a className="btn" href={api.exportUrl('excel')}>Download Excel</a>
              <button className="btn" onClick={() => setTab('assistant')}>Ask the assistant →</button>
            </div>
          </div>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Conflicts ({errors.length} errors · {warnings.length} warnings)</h3>
            {conflicts.length === 0 ? <p className="muted">No conflicts. Generate a schedule to check coverage.</p> : (
              <ul>{conflicts.slice(0, 8).map((c, i) => (
                <li key={i}><span className={`badge ${c.severity === 'error' ? 'error' : 'warn'}`}>{c.severity}</span> {c.message}</li>
              ))}</ul>
            )}
            {conflicts.length > 8 && <p className="muted">…and {conflicts.length - 8} more — see the Schedule tab.</p>}
          </div>
        </>
      )}

      {!loading && tab === 'schedule' && <ScheduleView schedule={schedule} onGenerate={generate} busy={busy} />}
      {!loading && tab === 'employees' && <EmployeesView employees={employees} onReload={load} setError={setError} setNotice={setNotice} />}
      {!loading && tab === 'assistant' && <AssistantView constraints={constraints} onReload={load} setError={setError} setNotice={setNotice} onGenerate={generate} />}
      {!loading && tab === 'analytics' && <AnalyticsView analytics={analytics} />}
    </div>
  )
}

function ScheduleView({ schedule, onGenerate, busy }) {
  const byCell = useMemo(() => {
    const m = {}
    for (const a of schedule?.assignments || []) { const k = `${a.day}|${a.shift}`; (m[k] ||= []).push(a) }
    return m
  }, [schedule])
  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>Weekly schedule</h2>
        <button className="btn primary" disabled={busy} onClick={onGenerate}>{busy ? 'Generating…' : '✦ Regenerate'}</button>
      </div>
      <p className="muted">4-hour shifts · Morning 07:00–11:00 · Midday 11:00–15:00 · Evening 15:00–19:00</p>
      <div className="calendar">
        <div /><div className="cal-head">Mon</div><div className="cal-head">Tue</div><div className="cal-head">Wed</div><div className="cal-head">Thu</div><div className="cal-head">Fri</div><div className="cal-head">Sat</div><div className="cal-head">Sun</div>
        {SHIFTS.map((s) => (
          <>
            <div key={s} className="cal-slot">{s}</div>
            {DAYS.map((d) => (
              <div key={`${d}-${s}`} className="cal-cell">
                {(byCell[`${d}|${s}`] || []).map((a, i) => (
                  <span key={i} className={`chip ${ROLE_CLASS[a.role] || ''}`} title={`${a.role}`}>{a.employee_name.split(' ')[0]}</span>
                ))}
                {(byCell[`${d}|${s}`] || []).length === 0 && <span className="muted">—</span>}
              </div>
            ))}
          </>
        ))}
      </div>
      <h3>Conflicts</h3>
      {(schedule?.conflicts || []).length === 0 ? <p className="muted">No conflicts detected.</p> : (
        <ul>{(schedule.conflicts || []).map((c, i) => <li key={i}><span className={`badge ${c.severity === 'error' ? 'error' : 'warn'}`}>{c.severity}</span> {c.message}</li>)}</ul>
      )}
    </div>
  )
}

function EmployeesView({ employees, onReload, setError, setNotice }) {
  const [form, setForm] = useState({ name: '', role: 'Server', max_hours_per_week: 20, email: '' })
  async function add(e) {
    e.preventDefault(); setError('')
    try {
      await api.addEmployee({ ...form, availability: { Monday: ['Morning', 'Midday', 'Evening'], Tuesday: ['Morning', 'Midday', 'Evening'], Wednesday: ['Morning', 'Midday', 'Evening'], Thursday: ['Morning', 'Midday', 'Evening'], Friday: ['Morning', 'Midday', 'Evening'], Saturday: ['Morning', 'Midday', 'Evening'], Sunday: ['Morning', 'Midday', 'Evening'] } })
      setNotice(`${form.name} added with full availability — edit availability via the API or seed data.`); setForm({ name: '', role: 'Server', max_hours_per_week: 20, email: '' }); onReload()
    } catch (err) { setError(err.message) }
  }
  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Employees ({employees.length})</h2>
        <p className="muted">Synthetic demo roster only — no real employee data. Availability shapes the optimiser: e.g. Jordan Lee has no weekday mornings (classes).</p>
        <table><thead><tr><th>Name</th><th>Role</th><th>Max h/wk</th><th>Available days</th><th></th></tr></thead>
          <tbody>{employees.map((e) => (
            <tr key={e.id}><td>{e.name}<br /><span className="muted">{e.email}</span></td><td>{e.role}</td><td>{e.max_hours_per_week}h</td><td>{Object.keys(e.availability || {}).filter((d) => (e.availability[d] || []).length).length} days</td>
              <td><button className="btn danger" onClick={async () => { await api.deleteEmployee(e.id); onReload() }}>Remove</button></td></tr>
          ))}</tbody></table>
      </div>
      <div className="card"><h3 style={{ marginTop: 0 }}>Add an employee</h3>
        <form onSubmit={add}>
          <label>Name</label><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required placeholder="e.g. Alex Morgan" />
          <label>Role</label><select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{['Cook', 'Server', 'Cashier', 'Dishwasher', 'Supervisor'].map((r) => <option key={r}>{r}</option>)}</select>
          <label>Max hours / week</label><input type="number" min="4" max="40" step="4" value={form.max_hours_per_week} onChange={(e) => setForm({ ...form, max_hours_per_week: Number(e.target.value) })} />
          <label>Email</label><input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@example.edu" />
          <p><button className="btn primary" type="submit">Add employee</button></p>
        </form>
      </div>
    </>
  )
}

function AssistantView({ constraints, onReload, setError, setNotice, onGenerate }) {
  const [text, setText] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  async function ask(example) {
    const q = example || text
    if (!q.trim()) return
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await api.parse(q)
      setResult(r)
      if (r.ok) { setNotice('Constraint saved. Regenerate the schedule to apply it.'); onReload() }
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Natural-language assistant</h2>
        <p className="muted">Type a scheduling instruction. It is parsed into a validated constraint — unknown names, impossible hours and contradictory rules are rejected with an explanation, never silently applied. Demo mode needs no API key; set <code>OPENAI_API_KEY</code> or <code>ANTHROPIC_API_KEY</code> in <code>.env</code> to let an LLM propose constraints (still validated the same way).</p>
        <label>Instruction</label>
        <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Give Alex fewer evening shifts next week" />
        <div className="pill-row">{EXAMPLES.map((ex) => <button key={ex} onClick={() => { setText(ex); ask(ex) }}>{ex}</button>)}</div>
        <p><button className="btn primary" disabled={busy} onClick={() => ask()}>{busy ? 'Parsing…' : 'Apply instruction'}</button>{' '}
          <button className="btn" onClick={onGenerate}>Regenerate schedule with constraints</button></p>
        {result && (result.ok
          ? <div className="success"><b>✓ {result.explanation}</b><br /><span className="muted">Kind: {result.kind} · Engine: {result.engine} · Confidence: {Math.round((result.confidence || 0) * 100)}%</span></div>
          : <div className="error"><b>Couldn’t apply that:</b> {result.error}</div>)}
      </div>
      <div className="card"><h3 style={{ marginTop: 0 }}>Active constraints ({constraints.length})</h3>
        {constraints.length === 0 ? <p className="muted">None yet — try an example above.</p> : (
          <ul>{constraints.map((c) => <li key={c.id}><b>{c.employee_name}</b> — {c.kind} <code>{JSON.stringify(c.payload)}</code> <span className="muted">“{c.source_text}”</span></li>)}</ul>
        )}
      </div>
    </>
  )
}

function AnalyticsView({ analytics }) {
  if (!analytics) return <p className="muted">Generate a schedule first.</p>
  const colors = ['#0f766e', '#0284c7', '#7c3aed', '#b45309', '#475569']
  return (
    <>
      <div className="grid cols-3">
        <div className="card stat"><b>{analytics.total_hours}h</b><span>Total scheduled hours</span></div>
        <div className="card stat"><b>{analytics.coverage_pct}%</b><span>Coverage</span></div>
        <div className="card stat"><b>{analytics.fairness_score}/100</b><span>Fairness score (even hours = 100)</span></div>
      </div>
      <div className="card"><h3 style={{ marginTop: 0 }}>Hours per employee</h3>
        <div style={{ height: 320 }}><ResponsiveContainer><BarChart data={analytics.hours_per_employee}>
          <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-30} textAnchor="end" height={70} /><YAxis /><Tooltip />
          <Bar dataKey="hours">{analytics.hours_per_employee.map((_, i) => <Cell key={i} fill={colors[i % colors.length]} />)}</Bar>
        </BarChart></ResponsiveContainer></div>
      </div>
      <div className="grid cols-2">
        <div className="card"><h3 style={{ marginTop: 0 }}>Shifts by day</h3>
          <table><tbody>{Object.entries(analytics.shifts_by_day).map(([d, n]) => <tr key={d}><td>{d}</td><td>{n} shifts</td></tr>)}</tbody></table></div>
        <div className="card"><h3 style={{ marginTop: 0 }}>Hours by role</h3>
          <table><tbody>{Object.entries(analytics.hours_by_role).map(([r, h]) => <tr key={r}><td>{r}</td><td>{h}h</td></tr>)}</tbody></table></div>
      </div>
    </>
  )
}
