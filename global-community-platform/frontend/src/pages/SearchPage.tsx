import { useDeferredValue, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Hash, Search, Users, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import FeedPost from '../components/FeedPost'
import { Avatar, FollowButton } from '../components/PersonBits'
import UserLink from '../components/UserHoverCard'
import { api, getErrorMessage } from '../services/api'
import type { Discussion, Person } from '../types'
import '../social.css'
import '../home-feed.css'

type Results = {
  q: string
  people: Person[]
  posts: Discussion[]
  tags: { name: string; count: number }[]
  communities: { id: number; name: string; members: number; category: string; description: string }[]
}

/** One search for people (@name), posts, hashtags (#tag) and communities. */
export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const [text, setText] = useState(params.get('q') ?? '')
  const q = useDeferredValue(text.trim())
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { input.current?.focus() }, [])
  useEffect(() => { const next = new URLSearchParams(); if (q) next.set('q', q); setParams(next, { replace: true }) }, [q, setParams])
  const enough = q.replace(/^[#@]/, '').length >= 2
  const results = useQuery({
    queryKey: ['search', q],
    enabled: enough,
    queryFn: async () => (await api.get<Results>('/search/', { params: { q } })).data,
    staleTime: 30_000,
  })
  const data = results.data
  const nothing = data && !data.people.length && !data.posts.length && !data.tags.length && !data.communities.length

  return <main className="search-page">
    <form className="search-box" role="search" onSubmit={(e) => e.preventDefault()}>
      <Search size={18} aria-hidden="true" />
      <input ref={input} type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search people, posts, #tags, communities" aria-label="Search" maxLength={80} />
      {text && <button type="button" className="icon-button" aria-label="Clear" onClick={() => setText('')}><X size={16} /></button>}
    </form>
    {!enough && <p className="search-hint">Type at least two letters. Start with <strong>@</strong> for people or <strong>#</strong> for hashtags.</p>}
    {results.isLoading && enough && <p className="search-hint">Searching…</p>}
    {results.error && <div className="error-card">{getErrorMessage(results.error)}</div>}
    {nothing && <p className="search-hint">No results for “{q}”.</p>}
    {data && data.people.length > 0 && <section className="search-section" aria-label="People">
      <h2><Users size={16} /> People</h2>
      {data.people.map((person) => <div className="home-rail-person" key={person.id}>
        <UserLink username={person.username}><Avatar person={person} size={40} /></UserLink>
        <div><UserLink username={person.username}><strong>{person.username}</strong></UserLink><span>{person.display_name}</span></div>
        <FollowButton person={person} compact />
      </div>)}
    </section>}
    {data && data.tags.length > 0 && <section className="search-section" aria-label="Hashtags">
      <h2><Hash size={16} /> Hashtags</h2>
      <div className="search-tags">{data.tags.map((tag) => <Link key={tag.name} to={`/tags/${tag.name}`} className="search-tag">#{tag.name}<small>{tag.count} {tag.count === 1 ? 'post' : 'posts'}</small></Link>)}</div>
    </section>}
    {data && data.communities.length > 0 && <section className="search-section" aria-label="Communities">
      <h2>Communities</h2>
      {data.communities.map((c) => <Link key={c.id} to={`/communities/${c.id}`} className="search-community"><strong>{c.name}</strong><span>{c.category} · {c.members} {c.members === 1 ? 'member' : 'members'}</span>{c.description && <small>{c.description}</small>}</Link>)}
    </section>}
    {data && data.posts.length > 0 && <section className="search-section" aria-label="Posts">
      <h2>Posts</h2>
      {data.posts.map((post) => <FeedPost key={post.id} discussion={post} />)}
    </section>}
  </main>
}
