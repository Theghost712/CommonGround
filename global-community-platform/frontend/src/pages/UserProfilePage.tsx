import { lazy, Suspense, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Ban, Bookmark, CalendarDays, Globe, Grid3x3, Heart, List, Lock, MapPin, MessageCircle, PenLine, UserPlus } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import DiscussionCard from '../components/DiscussionCard'
import PostGrid from '../components/PostGrid'
import Highlights from '../components/Highlights'
import { Avatar, FollowButton, RelationshipChips, formatCount } from '../components/PersonBits'
import PersonRow from '../components/PersonRow'
import { openDirectChat } from '../components/UserHoverCard'
import RichText from '../components/RichText'
import SafetyMenu, { useSafetyRefresh } from '../components/SafetyMenu'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import { RELATION_LABELS, fetchPerson, personKey, useRelationLabel } from '../social/people'
import type { Discussion, Paginated, Person, RelationLabel, Story } from '../types'
import '../social.css'
import '../stories.css'

const StoryViewer = lazy(() => import('../components/StoryViewer'))

type Tab = 'posts' | 'followers' | 'following' | 'saved'

function PeopleTab({ username, kind }: { username: string; kind: 'followers' | 'following' }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['people-list', username, kind],
    queryFn: async () => (await api.get<Paginated<Person>>(`/people/${encodeURIComponent(username)}/${kind}/`)).data,
  })
  if (isLoading) return <div className="loading-card">Loading…</div>
  if (error) return <div className="error-card">{getErrorMessage(error)}</div>
  if (!data?.results.length) return <div className="empty-card"><h3>{kind === 'followers' ? 'No followers yet' : 'Not following anyone yet'}</h3></div>
  return <div className="people-list">{data.results.map((person) => <PersonRow key={person.id} person={person} />)}</div>
}

function PostsTab({ username, saved = false }: { username: string; saved?: boolean }) {
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const { data, isLoading, error } = useQuery({
    queryKey: saved ? ['bookmarked-discussions', 'profile'] : ['discussions', 'author', username],
    queryFn: async () => saved
      ? (await api.get<Paginated<Discussion> | Discussion[]>('/discussions/bookmarked/')).data
      : (await api.get<Paginated<Discussion>>('/discussions/', { params: { author: username } })).data,
  })
  const posts = !data ? [] : Array.isArray(data) ? data : data.results
  if (isLoading) return <div className="loading-card">Loading posts…</div>
  if (error) return <div className="error-card">{getErrorMessage(error)}</div>
  if (!posts.length) return <div className="empty-card"><h3>{saved ? 'Nothing saved yet' : 'No posts yet'}</h3><p>{saved ? 'Tap the bookmark on any post to keep it here. Only you can see what you save.' : 'Photos and discussions this person shares will appear here.'}</p></div>
  return <div>
    <div className="up-view-toggle" role="group" aria-label="Layout">
      <button type="button" aria-pressed={view === 'grid'} aria-label="Grid view" className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')}><Grid3x3 size={17} /></button>
      <button type="button" aria-pressed={view === 'list'} aria-label="List view" className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}><List size={17} /></button>
    </div>
    {view === 'grid' ? <PostGrid posts={posts} /> : posts.map((discussion) => <DiscussionCard key={discussion.id} discussion={discussion} />)}
  </div>
}

function RelationPicker({ username, value }: { username: string; value: RelationLabel | null }) {
  const mutation = useRelationLabel(username)
  return <label className="relation-picker" title="Only you can see this">
    <Heart size={14} />
    <select value={value || ''} onChange={(event) => mutation.mutate((event.target.value || null) as RelationLabel | null)} disabled={mutation.isPending} aria-label="Your relation (private)">
      <option value="">Add relation…</option>
      {RELATION_LABELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
    </select>
  </label>
}

export default function UserProfilePage() {
  const { username: rawUsername = '' } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const username = rawUsername === 'me' ? user?.username || '' : rawUsername
  const [tab, setTab] = useState<Tab>('posts')
  const [messageError, setMessageError] = useState('')
  const [watching, setWatching] = useState(false)
  const refreshSafety = useSafetyRefresh()
  useEffect(() => { setTab('posts'); setMessageError(''); setWatching(false) }, [username])
  const storiesQuery = useQuery({
    queryKey: ['story-user', username],
    queryFn: async () => (await api.get<Story[]>(`/stories/user/${encodeURIComponent(username)}/`)).data,
    enabled: Boolean(username),
  })
  const activeStories = storiesQuery.data || []
  const { data: person, isLoading, error } = useQuery({ queryKey: personKey(username), queryFn: () => fetchPerson(username), enabled: Boolean(username) })

  if (isLoading) return <div className="loading-card">Loading profile…</div>
  if (error || !person) return <div className="error-card">{getErrorMessage(error)}</div>
  const self = Boolean(person.relationship?.is_self)
  const joined = new Date(person.date_joined).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  const websiteHost = (() => { try { return new URL(person.website).host } catch { return person.website } })()

  const stats: { key: Tab; label: string; value: number }[] = [
    { key: 'posts', label: 'Posts', value: person.discussions_count },
    { key: 'followers', label: 'Followers', value: person.followers_count },
    { key: 'following', label: 'Following', value: person.following_count },
  ]

  return <div className="up-page">
    <section className="up-hero">
      <div className="up-cover" />
      <div className="up-hero-body">
        {activeStories.length > 0
          ? <button type="button" className={`up-avatar-ring has-story ${activeStories.every((st) => st.seen) ? 'seen' : ''}`} aria-label={`Watch ${person.username}'s story`} onClick={() => setWatching(true)}><Avatar person={person} size={112} /></button>
          : <div className="up-avatar-ring"><Avatar person={person} size={112} /></div>}
        <div className="up-identity">
          <h1>{person.display_name}</h1>
          <span className="up-handle">@{person.username}{person.relationship?.is_private && <Lock size={13} aria-label="Private account" />}</span>
          <RelationshipChips person={person} />
        </div>
        <div className="up-actions">
          {self ? <>
            <Link to="/profile" className="button button-outline"><PenLine size={15} /> Edit profile</Link>
            <Link to="/people" className="button button-primary"><UserPlus size={15} /> Find friends</Link>
          </> : <>
            <FollowButton person={person} />
            {!person.relationship?.blocked && <button type="button" className="button button-outline" onClick={() => { setMessageError(''); openDirectChat(person.id, navigate).catch((err) => setMessageError(getErrorMessage(err))) }}><MessageCircle size={15} /> Message</button>}
            {!person.relationship?.blocked && <RelationPicker username={person.username} value={person.relationship?.label ?? null} />}
            <SafetyMenu person={person} />
          </>}
        </div>
      </div>
      {messageError && <div className="error-message">{messageError}</div>}
      <div className="up-stats" role="tablist" aria-label="Profile sections">
        {stats.map((item) => <button key={item.key} role="tab" aria-selected={tab === item.key} className={`up-stat ${tab === item.key ? 'active' : ''}`} onClick={() => setTab(item.key)}><strong>{formatCount(item.value)}</strong><span>{item.label}</span></button>)}
        {self && <button role="tab" aria-selected={tab === 'saved'} className={`up-stat up-stat-saved ${tab === 'saved' ? 'active' : ''}`} onClick={() => setTab('saved')} title="Only you can see what you've saved"><Bookmark size={19} /><span>Saved</span></button>}
      </div>
      <div className="up-about">
        {person.bio ? <p className="up-bio"><RichText text={person.bio} /></p> : self && <p className="up-bio muted">Add a short bio so people know who you are. <Link to="/profile">Edit profile</Link></p>}
        <div className="up-facts">
          {person.country && <span><MapPin size={13} /> {person.country}</span>}
          {person.website && <a href={person.website} target="_blank" rel="noreferrer noopener"><Globe size={13} /> {websiteHost}</a>}
          <span><CalendarDays size={13} /> Joined {joined}</span>
        </div>
        {person.interests.length > 0 && <div className="up-interests">{person.interests.map((item) => <span key={item}>{item}</span>)}</div>}
      </div>
      {!person.relationship?.blocked && (self || person.relationship?.can_view !== false) && <Highlights person={person} self={self} />}
    </section>

    {watching && activeStories.length > 0 && <Suspense fallback={null}><StoryViewer
      entries={[{ user: person, stories: activeStories, all_seen: activeStories.every((st) => st.seen), latest_at: activeStories[activeStories.length - 1].created_at }]}
      onClose={() => { setWatching(false); void storiesQuery.refetch() }}
    /></Suspense>}
    {person.relationship?.blocked
      ? <section className="up-locked"><Ban size={34} /><h3>You blocked this account</h3><p>They can't see your profile, posts or stories, and can't message you.</p><button type="button" className="button button-outline" onClick={() => { void api.delete(`/safety/blocks/${encodeURIComponent(person.username)}/`).then(() => refreshSafety(person.username)) }}>Unblock</button></section>
      : !self && person.relationship?.can_view === false
        ? <section className="up-locked"><Lock size={34} /><h3>This account is private</h3><p>{person.relationship?.requested ? 'Your follow request is waiting for approval.' : 'Follow this account to see their photos, videos and stories.'}</p></section>
        : <section className="up-tab-panel" role="tabpanel">
      {tab === 'posts' && <PostsTab username={person.username} />}
      {tab === 'saved' && self && <PostsTab username={person.username} saved />}
      {tab === 'followers' && <PeopleTab username={person.username} kind="followers" />}
      {tab === 'following' && <PeopleTab username={person.username} kind="following" />}
    </section>}
  </div>
}
