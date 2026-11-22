import { lazy, Suspense, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api } from '../services/api'
import type { Person, StoryTrayEntry } from '../types'
import { Avatar } from './PersonBits'
import '../stories.css'

// The viewer and composer are only downloaded when someone actually opens them.
const StoryViewer = lazy(() => import('./StoryViewer'))
const StoryComposer = lazy(() => import('./StoryComposer'))

export const storyTrayKey = ['story-tray'] as const

/** Instagram-style story tray: your story first, then unseen, then already-watched. */
export default function StoriesBar() {
  const { user } = useAuth()
  const scroller = useRef<HTMLDivElement>(null)
  const [viewing, setViewing] = useState<number | null>(null)
  const [composing, setComposing] = useState(false)
  const tray = useQuery({ queryKey: storyTrayKey, queryFn: async () => (await api.get<StoryTrayEntry[]>('/stories/tray/')).data, staleTime: 30_000, refetchInterval: 120_000 })
  const entries = tray.data || []
  const ownIndex = entries.findIndex((entry) => entry.user.id === user?.id)
  const others = entries.map((entry, index) => ({ entry, index })).filter(({ index }) => index !== ownIndex)
  const suggestions = useQuery({
    queryKey: ['people-suggestions'],
    queryFn: async () => (await api.get<Person[]>('/people/suggestions/')).data,
    enabled: tray.isSuccess && others.length === 0,
  })
  const me = { display_name: [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username || '', avatar_url: '' }
  const scrollBy = (direction: 1 | -1) => scroller.current?.scrollBy({ left: direction * 320, behavior: 'smooth' })

  return <section className="stories-bar" aria-label="Stories">
    <button type="button" className="stories-scroll left" aria-label="Scroll stories left" onClick={() => scrollBy(-1)}><ChevronLeft size={16} /></button>
    <div className="stories-track" ref={scroller}>
      <div className="story story-self">
        <button type="button" className={`story-ring ${ownIndex >= 0 ? 'seen' : 'self'}`} aria-label={ownIndex >= 0 ? 'View your story' : 'Add to your story'} onClick={() => ownIndex >= 0 ? setViewing(ownIndex) : setComposing(true)}>
          <Avatar person={me} size={60} />
        </button>
        <button type="button" className="story-plus" aria-label="Create a new story" onClick={() => setComposing(true)}><Plus size={13} strokeWidth={3} /></button>
        <span className="story-name">Your story</span>
      </div>
      {others.map(({ entry, index }) => <button type="button" key={entry.user.id} className="story" onClick={() => setViewing(index)} aria-label={`${entry.all_seen ? 'Watch again' : 'Watch'} ${entry.user.username}'s story`}>
        <span className={`story-ring ${entry.all_seen ? 'seen' : 'fresh'} ${entry.stories.some((s) => s.audience === 'close_friends') ? 'close-friends' : ''}`}><Avatar person={entry.user} size={60} /></span>
        <span className="story-name">{entry.user.username}</span>
      </button>)}
      {others.length === 0 && tray.isSuccess && (suggestions.data || []).slice(0, 10).map((person) => <Link key={person.id} to={`/u/${person.username}`} className="story" title={person.reason || person.display_name}>
        <span className="story-ring idle"><Avatar person={person} size={60} /></span>
        <span className="story-name">{person.username}</span>
        <span className="story-hint">Suggested</span>
      </Link>)}
      {tray.isLoading && Array.from({ length: 6 }, (_, i) => <span key={i} className="story"><span className="story-ring idle"><span className="skeleton skeleton-avatar" /></span><span className="skeleton skeleton-line" /></span>)}
    </div>
    <button type="button" className="stories-scroll right" aria-label="Scroll stories right" onClick={() => scrollBy(1)}><ChevronRight size={16} /></button>
    <Suspense fallback={null}>
      {viewing !== null && <StoryViewer entries={entries} startIndex={viewing} onClose={() => setViewing(null)} />}
      {composing && <StoryComposer onClose={() => setComposing(false)} />}
    </Suspense>
  </section>
}
