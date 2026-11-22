import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Ban, BellOff, EyeOff, Lock, ShieldCheck, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Avatar } from '../components/PersonBits'
import { AudienceList } from '../components/StoryComposer'
import { api, getErrorMessage } from '../services/api'
import type { Person } from '../types'
import '../social.css'
import '../stories.css'

function PeopleList({ kind, empty, action }: { kind: 'blocks' | 'mutes'; empty: string; action: string }) {
  const queryClient = useQueryClient()
  const list = useQuery({ queryKey: ['safety', kind], queryFn: async () => (await api.get<Person[]>(`/safety/${kind}/`)).data })
  const undo = useMutation({
    mutationFn: (username: string) => api.delete(`/safety/${kind}/${encodeURIComponent(username)}/`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['safety'] }); queryClient.invalidateQueries({ queryKey: ['person'] }) },
  })
  if (list.isLoading) return <p className="privacy-empty">Loading…</p>
  if (list.error) return <div className="error-message">{getErrorMessage(list.error)}</div>
  if (!list.data?.length) return <p className="privacy-empty">{empty}</p>
  return <ul className="privacy-people">{list.data.map((person) => <li key={person.id}><Avatar person={person} size={36} /><span><strong>{person.username}</strong><small>{person.display_name}</small></span><button type="button" className="follow-button compact is-following" disabled={undo.isPending} onClick={() => undo.mutate(person.username)}>{action}</button></li>)}</ul>
}

export default function PrivacySettingsPage() {
  const queryClient = useQueryClient()
  const [panel, setPanel] = useState<'close-friends' | 'hidden-from' | null>(null)
  const profile = useQuery({ queryKey: ['profile'], queryFn: async () => (await api.get<{ username: string; is_private: boolean }>('/auth/profile/')).data })
  const [optimistic, setOptimistic] = useState<boolean | null>(null)
  const setPrivate = useMutation({
    mutationFn: async (value: boolean) => (await api.patch('/auth/profile/', { is_private: value })).data,
    onMutate: (value) => setOptimistic(value), // the switch flips immediately
    onError: () => setOptimistic(null), // …and flips back if the server refuses
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['person'] })
      setOptimistic(null)
    },
  })
  const isPrivate = optimistic ?? Boolean(profile.data?.is_private)

  return <div className="people-page privacy-page">
    <Link to="/profile" className="back-link"><ArrowLeft size={16} /> Back to profile settings</Link>
    <div className="page-intro-row"><div><span className="eyebrow"><ShieldCheck size={12} /> SETTINGS</span><h1>Privacy &amp; safety</h1><p>Decide who sees what, and keep unwanted people out.</p></div></div>

    <section className="privacy-card">
      <label className="toggle-row">
        <input type="checkbox" checked={isPrivate} disabled={!profile.data || setPrivate.isPending} onChange={(event) => { if (event.target.checked || window.confirm('Make your account public? Anyone will be able to see your posts, and pending follow requests will be approved.')) setPrivate.mutate(event.target.checked) }} />
        <span><strong><Lock size={14} /> Private account</strong><small>Only people you approve can see your posts, stories and who you follow. People who already follow you stay.</small></span>
      </label>
      {isPrivate && <Link to="/people/requests" className="text-button">See follow requests →</Link>}
      {setPrivate.error && <div className="error-message">{getErrorMessage(setPrivate.error)}</div>}
    </section>

    <section className="privacy-card"><h2><Star size={16} /> Stories</h2>
      <div className="privacy-links"><button type="button" onClick={() => setPanel('close-friends')}>Close friends list</button><button type="button" onClick={() => setPanel('hidden-from')}><EyeOff size={13} /> Hide story from…</button></div>
      {panel && <div className="privacy-panel"><AudienceList kind={panel} onClose={() => setPanel(null)} /></div>}
    </section>

    <section className="privacy-card"><h2><Ban size={16} /> Blocked accounts</h2><p className="privacy-help">They can't find your profile, posts or stories, or message you. They aren't notified.</p><PeopleList kind="blocks" empty="You haven't blocked anyone." action="Unblock" /></section>
    <section className="privacy-card"><h2><BellOff size={16} /> Muted accounts</h2><p className="privacy-help">Their posts and stories stay out of your feed. They don't know.</p><PeopleList kind="mutes" empty="You haven't muted anyone." action="Unmute" /></section>
  </div>
}
