import { lazy, Suspense, useDeferredValue, useEffect, useRef, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { ArrowRight, Compass, Flame, Clapperboard, ImagePlus, ListChecks, Search, Sparkles, UsersRound, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import FeedPost from '../components/FeedPost'
import { Avatar, FollowButton } from '../components/PersonBits'
import StoriesBar from '../components/StoriesBar'
import UserLink from '../components/UserHoverCard'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import type { Discussion, DiscussionCategory, Paginated, Person } from '../types'
import '../discussion-forum.css'
import '../social.css'
import '../home-feed.css'

const PostComposer = lazy(() => import('../components/PostComposer'))
const VideoComposer = lazy(() => import('../components/MediaComposers').then((m) => ({ default: m.VideoComposer })))
const PollComposer = lazy(() => import('../components/MediaComposers').then((m) => ({ default: m.PollComposer })))

type FeedTab = 'for-you' | 'following' | 'trending'

const TABS: { key: FeedTab; label: string; icon: typeof Sparkles }[] = [
  { key: 'for-you', label: 'For you', icon: Sparkles },
  { key: 'following', label: 'Following', icon: UsersRound },
  { key: 'trending', label: 'Trending', icon: Flame },
]

function SuggestionsRail() {
  const { user } = useAuth()
  const { data } = useQuery({ queryKey: ['people-suggestions'], queryFn: async () => (await api.get<Person[]>('/people/suggestions/')).data })
  const me = { display_name: [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username || '', avatar_url: '' }
  return <aside className="home-rail">
    <div className="home-rail-me">
      <Link to={`/u/${user?.username}`}><Avatar person={me} size={46} /></Link>
      <div><Link to={`/u/${user?.username}`}><strong>{user?.username}</strong></Link><span>{me.display_name}</span></div>
      <Link to="/profile" className="home-rail-link">Edit</Link>
    </div>
    {data && data.length > 0 && <div className="home-rail-section">
      <div className="home-rail-heading"><span>Suggested for you</span><Link to="/people">See all</Link></div>
      {data.slice(0, 5).map((person) => <div className="home-rail-person" key={person.id}>
        <UserLink username={person.username}><Avatar person={person} size={34} /></UserLink>
        <div><UserLink username={person.username}><strong>{person.username}</strong></UserLink><span>{person.reason || person.display_name}</span></div>
        <FollowButton person={person} compact />
      </div>)}
    </div>}
    <nav className="home-rail-footer"><Link to="/explore">Explore</Link> · <Link to="/communities">Communities</Link> · <Link to="/events-calendar">Events</Link> · <Link to="/bookmarks">Saved</Link><span>© {new Date().getFullYear()} CommonGround</span></nav>
  </aside>
}

export default function HomePage() {
  const { user } = useAuth()
  const [tab, setTab] = useState<FeedTab>('for-you')
  const [search, setSearch] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [category, setCategory] = useState('')
  const [composing, setComposing] = useState<'photo' | 'video' | 'poll' | null>(null)
  const query = useDeferredValue(search.trim())
  const sentinel = useRef<HTMLDivElement>(null)

  const categoriesQuery = useQuery({ queryKey: ['discussion-categories'], queryFn: async () => (await api.get<DiscussionCategory[]>('/discussions/categories/')).data })
  const feed = useInfiniteQuery({
    queryKey: [tab === 'trending' ? 'trending-discussions' : 'discussions', 'home', tab, query, category],
    // Chronological feeds use cursor paging (constant cost however far you scroll);
    // trending is ranked by score, so it keeps page numbers.
    initialPageParam: tab === 'trending' ? '1' : '',
    queryFn: async ({ pageParam }) => (await api.get<Paginated<Discussion>>(tab === 'trending' ? '/discussions/trending/' : '/discussions/', {
      params: tab === 'trending'
        ? { page: pageParam, search: query || undefined, category: category || undefined }
        : { paginate: 'cursor', cursor: pageParam || undefined, search: query || undefined, category: category || undefined, feed: tab === 'following' ? 'following' : undefined },
    })).data,
    getNextPageParam: (last, pages) => {
      if (!last.next) return undefined
      if (tab === 'trending') return String(pages.length + 1)
      return new URL(last.next, window.location.origin).searchParams.get('cursor') ?? undefined
    },
  })
  const organic = feed.data?.pages.flatMap((page) => page.results) ?? []
  // Sponsored posts: one after the 3rd post, then one every 8 posts, in For you only.
  const sponsored = useQuery({
    queryKey: ['sponsored-feed'], enabled: tab === 'for-you', staleTime: 5 * 60_000,
    queryFn: async () => (await api.get<Discussion[]>('/promotions/feed/')).data,
  })
  const ads = tab === 'for-you' && !query && !category && Array.isArray(sponsored.data) ? sponsored.data : []
  // A sponsored post replaces its ordinary copy, so it shows once, in its paid slot.
  const rest = ads.length ? organic.filter((post) => !ads.some((ad) => ad.id === post.id)) : organic
  const posts = rest.flatMap((post, index) => {
    const slot = index === 2 ? 0 : index > 2 && (index - 2) % 8 === 0 ? (index - 2) / 8 : -1
    return slot >= 0 && slot < ads.length ? [post, ads[slot]] : [post]
  })
  if (ads.length && rest.length < 3 && feed.isSuccess && !feed.hasNextPage) posts.push(ads[0])
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = feed

  // Endless scrolling: fetch the next page when the bottom of the feed comes into view.
  useEffect(() => {
    const node = sentinel.current
    if (!node || !hasNextPage || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && !isFetchingNextPage) void fetchNextPage()
    }, { rootMargin: '600px 0px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, posts.length])

  const filtered = Boolean(query || category)
  const me = { display_name: [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.username || '', avatar_url: '' }

  return <div className="home-layout">
    <main className="home-feed">
      <StoriesBar />

      <div className="home-composer">
        <Avatar person={me} size={38} />
        <Link to="/discussions/new" className="home-composer-prompt">What&apos;s on your mind, {user?.first_name || user?.username}?</Link>
        <div className="home-composer-kinds">
          <button type="button" className="home-composer-photo" aria-label="New photo post" onClick={() => setComposing('photo')}><ImagePlus size={18} /> <span>Photo</span></button>
          <button type="button" className="home-composer-photo is-video" aria-label="New video post" onClick={() => setComposing('video')}><Clapperboard size={18} /> <span>Video</span></button>
          <button type="button" className="home-composer-photo is-poll" aria-label="New poll" onClick={() => setComposing('poll')}><ListChecks size={18} /> <span>Poll</span></button>
        </div>
      </div>
      <Suspense fallback={null}>
        {composing === 'photo' && <PostComposer onClose={() => setComposing(null)} />}
        {composing === 'video' && <VideoComposer onClose={() => setComposing(null)} />}
        {composing === 'poll' && <PollComposer onClose={() => setComposing(null)} />}
      </Suspense>

      <div className="home-tabs" role="tablist" aria-label="Feed">
        {TABS.map(({ key, label, icon: Icon }) => <button key={key} role="tab" aria-selected={tab === key} className={`home-tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}><Icon size={15} />{label}</button>)}
        <button type="button" className={`home-tab-icon ${searchOpen ? 'active' : ''}`} aria-label={searchOpen ? 'Close search' : 'Search posts'} onClick={() => { setSearchOpen((open) => !open); if (searchOpen) setSearch('') }}>{searchOpen ? <X size={17} /> : <Search size={17} />}</button>
      </div>
      {(searchOpen || category) && <div className="home-filters">
        {searchOpen && <label className="home-search"><Search size={15} /><input autoFocus type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search posts, topics or people…" aria-label="Search posts" /></label>}
        <select className="home-topic" value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter by topic"><option value="">All topics</option>{(categoriesQuery.data || []).filter((item) => item.count > 0 || item.name === category).map((item) => <option key={item.name} value={item.name}>{item.name} ({item.count})</option>)}</select>
      </div>}

      {feed.isLoading && Array.from({ length: 2 }, (_, i) => <div key={i} className="feed-post feed-post-skeleton"><span className="skeleton skeleton-line short" /><span className="skeleton feed-skeleton-media" /><span className="skeleton skeleton-line" /></div>)}
      {feed.error && <div className="error-card">{getErrorMessage(feed.error)}</div>}
      {!feed.isLoading && !feed.error && posts.length === 0 && (tab === 'following' && !filtered
        ? <div className="empty-card"><div className="empty-icon"><UsersRound size={23} /></div><h3>Your Following feed is quiet</h3><p>Follow friends and family to see their posts here.</p><Link to="/people" className="button button-primary">Find people <ArrowRight size={16} /></Link></div>
        : <div className="empty-card"><div className="empty-icon"><Compass size={23} /></div><h3>{filtered ? 'No matching posts' : 'No posts yet'}</h3><p>{filtered ? 'Try another search or topic.' : 'Share the first one with your community.'}</p>{!filtered && <Link to="/discussions/new" className="button button-primary">Create a post <ArrowRight size={16} /></Link>}</div>)}
      {posts.map((discussion) => <FeedPost key={discussion.sponsored ? `ad-${discussion.promotion_id}` : discussion.id} discussion={discussion} />)}
      <div ref={sentinel} className="feed-sentinel" />
      {isFetchingNextPage && <div className="feed-loading-more">Loading more…</div>}
      {hasNextPage && !isFetchingNextPage && <button type="button" className="button button-outline feed-load-more" onClick={() => void fetchNextPage()}>Load more</button>}
      {!hasNextPage && posts.length > 3 && <div className="feed-end"><Sparkles size={16} /> You&apos;re all caught up</div>}
    </main>
    <SuggestionsRail />
  </div>
}
