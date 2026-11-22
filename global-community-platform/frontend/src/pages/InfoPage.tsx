import { useDeferredValue, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CalendarDays, Camera, Compass, Flame, Globe2, LockKeyhole, MapPin, Search, ShieldCheck, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import DiscussionCard from '../components/DiscussionCard'
import PostGrid from '../components/PostGrid'
import { api, getErrorMessage } from '../services/api'
import type { Community, CommunityEvent, Discussion, DiscussionCategory, Paginated } from '../types'
import '../discussion-forum.css'
import '../explore.css'

const toList = <T,>(value: Paginated<T> | T[] | undefined): T[] => !value ? [] : Array.isArray(value) ? value : value.results || []

/** Discovery hub: trending conversations, topics, communities to join and upcoming events. */
export function ExplorePage() {
  const [search, setSearch] = useState('')
  const [topic, setTopic] = useState('')
  const query = useDeferredValue(search.trim())

  const categoriesQuery = useQuery({ queryKey: ['discussion-categories'], queryFn: async () => (await api.get<DiscussionCategory[]>('/discussions/categories/')).data })
  const trendingQuery = useQuery({
    queryKey: ['trending-discussions', 'explore', query, topic],
    queryFn: async () => (await api.get<Paginated<Discussion> | Discussion[]>('/discussions/trending/', { params: { search: query || undefined, category: topic || undefined } })).data,
  })
  const tagsQuery = useQuery({ queryKey: ['tags-trending'], queryFn: async () => (await api.get<{ name: string; posts: number }[]>('/tags/trending/')).data })
  const photosQuery = useQuery({
    queryKey: ['trending-discussions', 'explore-photos', query, topic],
    queryFn: async () => (await api.get<Paginated<Discussion> | Discussion[]>('/discussions/trending/', { params: { media: 'photos', search: query || undefined, category: topic || undefined } })).data,
  })
  const communitiesQuery = useQuery({
    queryKey: ['communities', 'explore', query],
    queryFn: async () => (await api.get<Paginated<Community> | Community[]>('/communities/', { params: { search: query || undefined } })).data,
  })
  const eventsQuery = useQuery({
    queryKey: ['events', 'explore', query],
    queryFn: async () => (await api.get<Paginated<CommunityEvent> | CommunityEvent[]>('/events/', { params: { status: 'scheduled', ordering: 'starts_at', search: query || undefined } })).data,
  })

  const topics = (categoriesQuery.data || []).filter((item) => item.count > 0)
  const trending = toList(trendingQuery.data).slice(0, 6)
  const communities = useMemo(() => toList(communitiesQuery.data)
    .filter((community) => community.approval_status === 'approved' && !community.is_member && community.membership_status !== 'pending' && community.visibility !== 'private')
    .sort((a, b) => b.members_count - a.members_count)
    .slice(0, 6), [communitiesQuery.data])
  const events = useMemo(() => {
    const now = Date.now()
    return toList(eventsQuery.data).filter((event) => new Date(event.ends_at).getTime() >= now).slice(0, 4)
  }, [eventsQuery.data])

  return <div className="explore-page">
    <section className="explore-hero">
      <div className="explore-hero-icon"><Compass size={24} /></div>
      <span className="eyebrow">DISCOVER SOMETHING NEW</span>
      <h1>Explore fresh perspectives.</h1>
      <p>Find the conversations people care about, communities worth joining and events coming up next.</p>
      <label className="explore-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search discussions, communities and events…" aria-label="Search everything" /></label>
    </section>

    {topics.length > 0 && <section className="explore-section">
      <div className="section-heading"><div><span className="eyebrow">BROWSE BY TOPIC</span><h2>What people talk about</h2></div></div>
      <div className="explore-topics">
        <button className={`filter-chip ${topic === '' ? 'selected' : ''}`} onClick={() => setTopic('')}>All topics</button>
        {topics.map((item) => <button key={item.name} className={`filter-chip ${topic === item.name ? 'selected' : ''}`} onClick={() => setTopic(topic === item.name ? '' : item.name)}>{item.name}<span className="explore-topic-count">{item.count}</span></button>)}
      </div>
    </section>}

    {(tagsQuery.data || []).length > 0 && <section className="explore-section">
      <div className="section-heading"><div><span className="eyebrow">#</span><h2>Trending hashtags</h2></div></div>
      <div className="explore-topics">{(tagsQuery.data || []).map((item) => <Link key={item.name} to={`/tags/${encodeURIComponent(item.name)}`} className="filter-chip">#{item.name}<span className="explore-topic-count">{item.posts}</span></Link>)}</div>
    </section>}

    {toList(photosQuery.data).length > 0 && <section className="explore-section">
      <div className="section-heading"><div><span className="eyebrow"><Camera size={12} /> PHOTOS</span><h2>{topic ? `Photos in ${topic}` : 'Photos people love'}</h2></div></div>
      <PostGrid posts={toList(photosQuery.data).slice(0, 12)} mosaic />
    </section>}

    <section className="explore-section">
      <div className="section-heading"><div><span className="eyebrow"><Flame size={12} /> TRENDING</span><h2>{topic ? `Trending in ${topic}` : 'Conversations worth joining'}</h2><p>Ranked by comments, reactions and saves over the last 30 days.</p></div><Link to="/home" className="subtle-link">Full feed <ArrowRight size={14} /></Link></div>
      {trendingQuery.isLoading && <div className="loading-card">Finding trending conversations…</div>}
      {trendingQuery.error && <div className="error-card">{getErrorMessage(trendingQuery.error)}</div>}
      {!trendingQuery.isLoading && !trendingQuery.error && trending.length === 0 && <div className="empty-card"><h3>No conversations found</h3><p>{query || topic ? 'Try a different search or topic.' : 'Be the first to start one.'}</p><Link to="/discussions/new" className="button button-primary">Start a discussion</Link></div>}
      {trending.map((discussion) => <DiscussionCard key={discussion.id} discussion={discussion} />)}
    </section>

    <section className="explore-section">
      <div className="section-heading"><div><span className="eyebrow"><Users size={12} /> COMMUNITIES</span><h2>Communities to discover</h2><p>Groups you have not joined yet.</p></div><Link to="/communities" className="subtle-link">All communities <ArrowRight size={14} /></Link></div>
      {communitiesQuery.isLoading && <div className="loading-card">Looking for communities…</div>}
      {communitiesQuery.error && <div className="error-card">{getErrorMessage(communitiesQuery.error)}</div>}
      {!communitiesQuery.isLoading && !communitiesQuery.error && communities.length === 0 && <div className="empty-card"><h3>{query ? 'No matching communities' : "You're in every community so far"}</h3><p>{query ? 'Try another search.' : 'Start a new one for something you care about.'}</p><Link to="/communities" className="button button-primary">Go to communities</Link></div>}
      {communities.length > 0 && <div className="community-grid">{communities.map((community) => <article className="community-card" key={community.id}>
        <div className={`community-art art-${community.category.toLowerCase().replace(/[^a-z]/g, '')}`}>
          {community.cover_url && <img className="community-card-cover" src={community.cover_url} alt="" />}
          {community.logo_url ? <img className="community-card-logo" src={community.logo_url} alt={`${community.name} logo`} /> : <span>{community.name.slice(0, 1).toUpperCase()}</span>}
          <div className="art-caption">{community.category}</div>
        </div>
        <div className="community-card-body"><div className="community-card-title"><Link to={`/communities/${community.id}`}><h3>{community.name}</h3></Link>{community.visibility === 'public' ? <Globe2 size={15} /> : community.visibility === 'restricted' ? <ShieldCheck size={15} /> : <LockKeyhole size={15} />}</div>
          <p>{community.description}</p>
          <div className="community-card-bottom"><span><Users size={14} /> {community.members_count} members</span><Link to={`/communities/${community.id}`} className="text-button">{community.visibility === 'restricted' ? 'Request to join' : 'View & join'} <ArrowRight size={13} /></Link></div>
        </div>
      </article>)}</div>}
    </section>

    <section className="explore-section">
      <div className="section-heading"><div><span className="eyebrow"><CalendarDays size={12} /> EVENTS</span><h2>Coming up next</h2><p>Scheduled community events, soonest first.</p></div><Link to="/events-calendar" className="subtle-link">Events calendar <ArrowRight size={14} /></Link></div>
      {eventsQuery.isLoading && <div className="loading-card">Checking the calendar…</div>}
      {eventsQuery.error && <div className="error-card">{getErrorMessage(eventsQuery.error)}</div>}
      {!eventsQuery.isLoading && !eventsQuery.error && events.length === 0 && <div className="empty-card"><h3>No upcoming events</h3><p>Community organisers can schedule events from their community page.</p></div>}
      {events.length > 0 && <div className="explore-events">{events.map((event) => {
        const start = new Date(event.starts_at)
        return <Link to={`/communities/${event.community}`} className="explore-event" key={event.id}>
          <div className="explore-event-date"><strong>{start.getDate()}</strong><span>{start.toLocaleDateString(undefined, { month: 'short' })}</span></div>
          <div className="explore-event-copy"><h3>{event.title}</h3><span>{start.toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' })} · {event.community_name}</span>{event.location && <span><MapPin size={11} /> {event.location}</span>}</div>
          <span className="explore-event-going">{event.rsvp_counts.going} going</span>
        </Link>
      })}</div>}
    </section>
  </div>
}
