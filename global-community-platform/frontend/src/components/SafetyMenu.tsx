import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BellOff, Ban, Flag, MoreHorizontal } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'
import { personKey } from '../social/people'
import type { Person } from '../types'
import ReportDialog from './ReportDialog'

/** Refresh every cached view that depends on who is blocked or muted. */
export function useSafetyRefresh() {
  const queryClient = useQueryClient()
  return (username: string) => {
    queryClient.invalidateQueries({ queryKey: personKey(username) })
    for (const key of ['discussions', 'trending-discussions', 'story-tray', 'people-search', 'people-suggestions', 'safety']) queryClient.invalidateQueries({ queryKey: [key] })
  }
}

/** "⋯" menu on a profile: mute posts/stories, block/unblock, report. */
export default function SafetyMenu({ person }: { person: Person }) {
  const refresh = useSafetyRefresh()
  const [open, setOpen] = useState(false)
  const [reporting, setReporting] = useState(false)
  const [toast, setToast] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const relation = person.relationship

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 2400); return () => clearTimeout(t) }, [toast])

  if (!relation || relation.is_self) return null
  const name = person.username

  const run = async (request: () => Promise<unknown>, message: string) => {
    setOpen(false)
    try { await request(); refresh(name); setToast(message) } catch (err) { setToast(getErrorMessage(err)) }
  }
  const mute = (posts: boolean, stories: boolean) => run(
    () => api.put(`/safety/mutes/${encodeURIComponent(name)}/`, { posts, stories }),
    posts || stories ? `Muted. ${name} won't know.` : 'Unmuted.',
  )
  const block = () => {
    if (!window.confirm(`Block ${name}? They won't be able to find your profile, posts or stories, or message you. They won't be notified. Any follows between you will be removed.`)) return
    void run(() => api.put(`/safety/blocks/${encodeURIComponent(name)}/`), `${name} is blocked.`)
  }
  const unblock = () => run(() => api.delete(`/safety/blocks/${encodeURIComponent(name)}/`), `${name} is unblocked.`)
  const posts = Boolean(relation.muted_posts)
  const stories = Boolean(relation.muted_stories)

  return <div className="safety-menu" ref={ref}>
    <button type="button" className="button button-outline safety-trigger" aria-label="More options" aria-expanded={open} onClick={() => setOpen(!open)}><MoreHorizontal size={18} /></button>
    {open && <div className="feed-menu-list safety-list" role="menu">
      {!relation.blocked && <>
        <button role="menuitemcheckbox" aria-checked={posts} type="button" onClick={() => void mute(!posts, stories)}><BellOff size={15} /> {posts ? 'Unmute posts' : 'Mute posts'}</button>
        <button role="menuitemcheckbox" aria-checked={stories} type="button" onClick={() => void mute(posts, !stories)}><BellOff size={15} /> {stories ? 'Unmute story' : 'Mute story'}</button>
      </>}
      {relation.blocked
        ? <button role="menuitem" type="button" onClick={() => void unblock()}><Ban size={15} /> Unblock</button>
        : <button role="menuitem" type="button" className="danger" onClick={block}><Ban size={15} /> Block</button>}
      <button role="menuitem" type="button" className="danger" onClick={() => { setOpen(false); setReporting(true) }}><Flag size={15} /> Report account</button>
    </div>}
    {reporting && <ReportDialog targetType="user" targetId={person.id} onClose={() => setReporting(false)} />}
    {toast && <div className="safety-toast" role="status">{toast}</div>}
  </div>
}
