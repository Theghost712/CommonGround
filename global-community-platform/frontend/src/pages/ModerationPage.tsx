import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, CheckCircle2, ExternalLink, Gavel, History, Search, ShieldAlert, Trash2, TriangleAlert, UserX } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import '../moderation.css'

type Person = { id: number; username: string; display_name: string; is_active: boolean; is_staff: boolean; suspended_until: string | null }
type QueueItem = {
  target_type: 'post' | 'comment' | 'story' | 'message' | 'user'
  target_id: number
  report_count: number
  latest_at: string
  reasons: { reason: string; label: string; count: number }[]
  details: string[]
  owner: Person | null
  community: { id: number; name: string } | null
  preview: { text: string; image: string; url: string; gone: boolean }
  can_enforce: boolean
}
type LogRow = {
  id: number; action: string; action_label: string; moderator: string | null; target_type: string; target_id: number | null
  target_user: string | null; community: string | null; reason: string; snapshot: { text?: string }; reports_closed: number
  suspended_until: string | null; created_at: string
}
type Action = 'dismiss' | 'remove' | 'warn' | 'suspend' | 'ban'

const TYPE_LABEL: Record<QueueItem['target_type'], string> = { post: 'Post', comment: 'Comment', story: 'Story', message: 'Message', user: 'Account' }
const ACTION_COPY: Record<Exclude<Action, 'dismiss'>, { title: string; button: string; help: string }> = {
  remove: { title: 'Remove this content', button: 'Remove', help: 'It is deleted for everyone. The author is told why. A copy stays in the audit log.' },
  warn: { title: 'Warn the account', button: 'Send warning', help: 'The content stays. The person gets a notice with your reason.' },
  suspend: { title: 'Suspend the account', button: 'Suspend', help: 'They are signed out everywhere and cannot sign in until the suspension ends.' },
  ban: { title: 'Ban the account', button: 'Ban', help: 'The account is switched off until staff lift the ban. They are signed out everywhere.' },
}
const DAYS = [1, 3, 7, 30, 90, 365]

function QueueCard({ item }: { item: QueueItem }) {
  const queryClient = useQueryClient()
  const [action, setAction] = useState<Exclude<Action, 'dismiss'> | null>(null)
  const [reason, setReason] = useState('')
  const [days, setDays] = useState(7)
  const [alsoRemove, setAlsoRemove] = useState(true)
  const [error, setError] = useState('')
  const decide = useMutation({
    mutationFn: async (chosen: Action) => (await api.post('/moderation/decisions/', {
      target_type: item.target_type, target_id: item.target_id, action: chosen, reason: reason.trim(),
      ...(chosen === 'suspend' ? { days } : {}),
      ...(chosen === 'suspend' || chosen === 'ban' ? { remove_content: alsoRemove && item.target_type !== 'user' } : {}),
    })).data,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['moderation'] }) },
    onError: (err) => setError(getErrorMessage(err)),
  })
  const contentAction = item.target_type !== 'user' && !item.preview.gone
  const label = `${TYPE_LABEL[item.target_type]} by ${item.owner?.username ?? 'deleted account'}`

  return <article className="mod-card" aria-label={label}>
    <header>
      <span className="mod-type">{TYPE_LABEL[item.target_type]}</span>
      <strong className="mod-count"><ShieldAlert size={14} /> {item.report_count} {item.report_count === 1 ? 'report' : 'reports'}</strong>
      {item.community && <span className="mod-community">in {item.community.name}</span>}
      <time dateTime={item.latest_at}>{new Date(item.latest_at).toLocaleString()}</time>
    </header>
    <div className="mod-reasons">{item.reasons.map((r) => <span key={r.reason}>{r.label}{r.count > 1 && ` ×${r.count}`}</span>)}</div>
    <div className="mod-preview">
      {item.preview.image && <img src={item.preview.image} alt="" loading="lazy" />}
      <div>
        {item.preview.gone ? <p className="mod-gone">Already deleted.</p> : <p>{item.preview.text || <em>No text</em>}</p>}
        <div className="mod-links">
          {item.owner && <Link to={`/u/${item.owner.username}`}>@{item.owner.username}</Link>}
          {item.owner?.suspended_until && <span className="mod-flag">Suspended</span>}
          {item.owner && !item.owner.is_active && <span className="mod-flag">Banned</span>}
          {item.preview.url && <Link to={item.preview.url}>Open <ExternalLink size={12} /></Link>}
        </div>
      </div>
    </div>
    {item.details.length > 0 && <ul className="mod-details">{item.details.map((d, i) => <li key={i}>“{d}”</li>)}</ul>}

    {action
      ? <div className="mod-panel">
        <strong>{ACTION_COPY[action].title}</strong>
        <p>{ACTION_COPY[action].help}</p>
        <label>Reason (shown to the person)<textarea rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Advertising followers is spam." /></label>
        {action === 'suspend' && <label>Length<select value={days} onChange={(e) => setDays(Number(e.target.value))}>{DAYS.map((d) => <option key={d} value={d}>{d === 1 ? '1 day' : `${d} days`}</option>)}</select></label>}
        {(action === 'suspend' || action === 'ban') && contentAction && <label className="mod-check"><input type="checkbox" checked={alsoRemove} onChange={(e) => setAlsoRemove(e.target.checked)} /> Also remove this {TYPE_LABEL[item.target_type].toLowerCase()}</label>}
        {error && <div className="error-message">{error}</div>}
        <div className="mod-actions">
          <button type="button" className="button button-outline" onClick={() => { setAction(null); setError('') }}>Cancel</button>
          <button type="button" className={`button ${action === 'warn' ? 'button-primary' : 'button-danger'}`} disabled={decide.isPending || !reason.trim()} onClick={() => { setError(''); decide.mutate(action) }}>{decide.isPending ? 'Working…' : ACTION_COPY[action].button}</button>
        </div>
      </div>
      : <div className="mod-actions">
        <button type="button" className="button button-outline" disabled={decide.isPending} onClick={() => decide.mutate('dismiss')}><CheckCircle2 size={15} /> No violation</button>
        {contentAction && <button type="button" className="button button-outline mod-danger" onClick={() => setAction('remove')}><Trash2 size={15} /> Remove</button>}
        {item.can_enforce && item.owner && <>
          <button type="button" className="button button-outline" onClick={() => setAction('warn')}><TriangleAlert size={15} /> Warn</button>
          <button type="button" className="button button-outline mod-danger" onClick={() => setAction('suspend')}><UserX size={15} /> Suspend</button>
          <button type="button" className="button button-outline mod-danger" onClick={() => setAction('ban')}><Ban size={15} /> Ban</button>
        </>}
        {error && <div className="error-message">{error}</div>}
      </div>}
  </article>
}

function AccountLookup() {
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('')
  const [lookup, setLookup] = useState('')
  const record = useQuery({
    queryKey: ['moderation', 'account', lookup],
    enabled: Boolean(lookup),
    queryFn: async () => (await api.get<{ user: Person; reports_received: number; open_reports: number; history: LogRow[] }>(`/moderation/accounts/${encodeURIComponent(lookup)}/`)).data,
  })
  const restore = useMutation({
    mutationFn: async () => (await api.post(`/moderation/accounts/${encodeURIComponent(lookup)}/restore/`, { reason: 'Lifted by staff' })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['moderation'] }),
  })
  const user = record.data?.user
  const restricted = user && (!user.is_active || user.suspended_until)
  return <section className="mod-lookup">
    <form onSubmit={(e) => { e.preventDefault(); setLookup(username.trim().replace(/^@/, '')) }}>
      <label className="home-search"><Search size={15} /><input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Look up an account by username" aria-label="Look up an account" /></label>
      <button className="button button-outline">Look up</button>
    </form>
    {record.error && <div className="error-message">{getErrorMessage(record.error)}</div>}
    {user && <div className="mod-record">
      <div><strong>@{user.username}</strong> · {user.display_name}</div>
      <div className="mod-record-status">{!user.is_active ? <span className="mod-flag">Banned</span> : user.suspended_until ? <span className="mod-flag">Suspended until {new Date(user.suspended_until).toLocaleString()}</span> : <span className="mod-ok">In good standing</span>} · {record.data!.reports_received} reports received ({record.data!.open_reports} open)</div>
      {restricted && <button type="button" className="button button-primary" disabled={restore.isPending} onClick={() => restore.mutate()}>{restore.isPending ? 'Lifting…' : user.is_active ? 'Lift suspension' : 'Lift ban'}</button>}
      {restore.error && <div className="error-message">{getErrorMessage(restore.error)}</div>}
    </div>}
  </section>
}

function AuditLog() {
  const { user } = useAuth()
  const log = useQuery({ queryKey: ['moderation', 'log'], queryFn: async () => (await api.get<LogRow[]>('/moderation/log/')).data })
  return <>
    {user?.is_staff && <AccountLookup />}
    {log.isLoading && <div className="loading-card">Loading…</div>}
    {log.error && <div className="error-card">{getErrorMessage(log.error)}</div>}
    {log.data && !log.data.length && <div className="empty-card"><h3>No decisions yet</h3><p>Every moderation decision is recorded here.</p></div>}
    <ul className="mod-log">{log.data?.map((row) => <li key={row.id}>
      <div><strong>{row.action_label}</strong>{row.target_user && <> · <Link to={`/u/${row.target_user}`}>@{row.target_user}</Link></>}{row.community && <> · {row.community}</>}</div>
      <small>{new Date(row.created_at).toLocaleString()} by {row.moderator ?? 'deleted moderator'}{row.reports_closed > 0 && ` · closed ${row.reports_closed} ${row.reports_closed === 1 ? 'report' : 'reports'}`}{row.suspended_until && ` · until ${new Date(row.suspended_until).toLocaleDateString()}`}</small>
      {row.reason && <p>{row.reason}</p>}
      {row.snapshot?.text && <details><summary>What it said</summary><p>{row.snapshot.text}</p></details>}
    </li>)}</ul>
  </>
}

export default function ModerationPage() {
  const { user } = useAuth()
  const [tab, setTab] = useState<'queue' | 'log'>('queue')
  const queue = useQuery({ queryKey: ['moderation', 'queue'], queryFn: async () => (await api.get<{ count: number; results: QueueItem[] }>('/moderation/queue/')).data, enabled: Boolean(user?.can_moderate) })
  if (!user?.can_moderate) return <div className="error-card">Only moderators can open this page.</div>

  return <div className="people-page moderation-page">
    <div className="page-intro-row"><div><span className="eyebrow"><Gavel size={12} /> {user.is_staff ? 'SITE STAFF' : 'COMMUNITY MODERATOR'}</span><h1>Moderation</h1><p>Review what people reported. Every decision is logged.</p></div></div>
    <div className="home-tabs" role="tablist" aria-label="Moderation">
      <button role="tab" aria-selected={tab === 'queue'} className={`home-tab ${tab === 'queue' ? 'active' : ''}`} onClick={() => setTab('queue')}><ShieldAlert size={15} /> Reports{queue.data ? ` (${queue.data.count})` : ''}</button>
      <button role="tab" aria-selected={tab === 'log'} className={`home-tab ${tab === 'log' ? 'active' : ''}`} onClick={() => setTab('log')}><History size={15} /> Activity log</button>
    </div>
    {tab === 'queue'
      ? queue.isLoading ? <div className="loading-card">Loading reports…</div>
        : queue.error ? <div className="error-card">{getErrorMessage(queue.error)}</div>
        : !queue.data?.results.length ? <div className="empty-card"><div className="empty-icon"><CheckCircle2 size={20} /></div><h3>All clear</h3><p>No open reports right now.</p></div>
        : <div className="mod-queue">{queue.data.results.map((item) => <QueueCard key={`${item.target_type}-${item.target_id}`} item={item} />)}</div>
      : <AuditLog />}
  </div>
}
