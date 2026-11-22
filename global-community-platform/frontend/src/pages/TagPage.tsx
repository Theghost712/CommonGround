import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Hash } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import PostGrid from '../components/PostGrid'
import { formatCount } from '../components/PersonBits'
import { api, getErrorMessage } from '../services/api'
import type { Discussion, Paginated } from '../types'
import '../home-feed.css'
import '../social.css'

export default function TagPage() {
  const { name = '' } = useParams()
  const tag = name.toLowerCase()
  const info = useQuery({ queryKey: ['tag', tag], queryFn: async () => (await api.get<{ name: string; posts: number }>(`/tags/${encodeURIComponent(tag)}/`)).data })
  const posts = useInfiniteQuery({
    queryKey: ['discussions', 'tag', tag],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => (await api.get<Paginated<Discussion>>('/discussions/', { params: { tag, page: pageParam } })).data,
    getNextPageParam: (last, pages) => last.next ? pages.length + 1 : undefined,
  })
  const items = posts.data?.pages.flatMap((page) => page.results) ?? []
  return <div className="people-page">
    <Link to="/explore" className="back-link"><ArrowLeft size={16} /> Explore</Link>
    <header className="tag-header"><div className="tag-badge"><Hash size={34} /></div><div><h1>#{tag}</h1><p>{info.data ? `${formatCount(info.data.posts)} ${info.data.posts === 1 ? 'post' : 'posts'}` : '…'}</p></div></header>
    {posts.isLoading && <div className="loading-card">Loading posts…</div>}
    {posts.error && <div className="error-card">{getErrorMessage(posts.error)}</div>}
    {posts.data && !items.length && <div className="empty-card"><h3>No posts yet</h3><p>Be the first to use #{tag}.</p></div>}
    {items.length > 0 && <PostGrid posts={items} />}
    {posts.hasNextPage && <button type="button" className="button button-outline feed-load-more" onClick={() => void posts.fetchNextPage()} disabled={posts.isFetchingNextPage}>{posts.isFetchingNextPage ? 'Loading…' : 'Load more'}</button>}
  </div>
}
