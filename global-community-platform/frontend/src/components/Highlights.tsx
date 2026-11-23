import { lazy, Suspense, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Plus, Trash2, X } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'
import type { Person, Story } from '../types'
import '../stories.css'

const StoryViewer = lazy(() => import('./StoryViewer'))

type Highlight = { id: number; title: string; cover_url: string; stories: Story[]; is_own: boolean; background: string }

/** Story highlights on a profile: circles that replay saved stories, plus "New" for your own profile. */
export default function Highlights({ person, self }: { person: Person; self: boolean }) {
  const queryClient = useQueryClient()
  const [watching, setWatching] = useState<Highlight | null>(null)
  const [creating, setCreating] = useState(false)
  const query = useQuery({
    queryKey: ['highlights', person.username],
    queryFn: async () => (await api.get<Highlight[]>(`/stories/highlights/user/${encodeURIComponent(person.username)}/`)).data,
  })
  const highlights = query.data ?? []
  if (!self && highlights.length === 0) return null
  const remove = async (highlight: Highlight) => {
    if (!window.confirm(`Delete the highlight “${highlight.title}”? The stories in it will be removed after 24 hours.`)) return
    await api.delete(`/stories/highlights/${highlight.id}/`).catch(() => {})
    setWatching(null)
    void queryClient.invalidateQueries({ queryKey: ['highlights', person.username] })
  }
  return <section className="highlights" aria-label="Story highlights">
    {self && <button type="button" className="highlight" onClick={() => setCreating(true)}>
      <span className="highlight-ring is-new"><Plus size={26} /></span><span className="highlight-title">New</span>
    </button>}
    {highlights.map((h) => <button type="button" key={h.id} className="highlight" onClick={() => setWatching(h)}>
      <span className={`highlight-ring bg-${h.background}`}>{h.cover_url ? <img src={h.cover_url} alt="" loading="lazy" /> : <span className="highlight-letter">{h.title.slice(0, 1).toUpperCase()}</span>}</span>
      <span className="highlight-title">{h.title}</span>
    </button>)}
    {watching && <Suspense fallback={null}>
      <StoryViewer entries={[{ user: person, stories: watching.stories, all_seen: true, latest_at: watching.stories[watching.stories.length - 1]?.created_at ?? '' }]} onClose={() => setWatching(null)} />
      {watching.is_own && createPortal(<button type="button" className="highlight-delete" onClick={() => void remove(watching)}><Trash2 size={15} /> Delete highlight</button>, document.body)}
    </Suspense>}
    {creating && <NewHighlight onClose={() => setCreating(false)} onCreated={() => { setCreating(false); void queryClient.invalidateQueries({ queryKey: ['highlights', person.username] }) }} />}
  </section>
}

function NewHighlight({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [chosen, setChosen] = useState<number[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const stories = useQuery({ queryKey: ['my-stories'], queryFn: async () => (await api.get<Story[]>('/stories/mine/')).data })
  const toggle = (id: number) => setChosen((ids) => ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id])
  const save = async () => {
    setBusy(true); setError('')
    try { await api.post('/stories/highlights/', { title: title.trim(), story_ids: chosen }); onCreated() } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }
  return createPortal(<div className="sheet-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
    <div className="sheet" role="dialog" aria-modal="true" aria-label="New highlight">
      <div className="sheet-head"><strong>New highlight</strong><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></div>
      <input className="chat-draft-caption" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={40} placeholder="Name (e.g. Travel)" aria-label="Highlight name" autoFocus />
      <p className="sheet-muted">Choose stories to keep on your profile. Stories can be added while they're live (24 hours).</p>
      {stories.isLoading && <p className="sheet-muted">Loading your stories…</p>}
      {stories.data?.length === 0 && <p className="sheet-muted">You have no stories right now. Post one, then come back.</p>}
      <div className="highlight-pick">
        {stories.data?.map((s) => <button type="button" key={s.id} aria-pressed={chosen.includes(s.id)} className={`highlight-pick-item bg-${s.background} ${chosen.includes(s.id) ? 'chosen' : ''}`} onClick={() => toggle(s.id)}>
          {s.thumbnail_url || (s.media_type === 'image' && s.media_url) ? <img src={s.thumbnail_url || s.media_url} alt="" /> : <span>{s.text.slice(0, 40)}</span>}
          {chosen.includes(s.id) && <i><Check size={14} /></i>}
        </button>)}
      </div>
      {error && <p className="sheet-error">{error}</p>}
      <div className="sheet-row"><button type="button" className="button button-primary" disabled={busy || !title.trim() || !chosen.length} onClick={() => void save()}>{busy ? 'Saving…' : `Add ${chosen.length || ''}`.trim()}</button></div>
    </div>
  </div>, document.body)
}
