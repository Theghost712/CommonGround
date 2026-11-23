import { useEffect, useRef, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Clapperboard, Heart, MessageCircle, Send } from 'lucide-react'
import { Link } from 'react-router-dom'
import RichText from '../components/RichText'
import VideoPlayer from '../components/VideoPlayer'
import ShareSheet from '../components/ShareSheet'
import { recordView, trackVisibility } from '../services/viewTracker'
import { api, getErrorMessage } from '../services/api'
import type { Discussion } from '../types'
import '../media-posts.css'

type FeedPage = { results: Discussion[]; next: string | null }

function Reel({ post }: { post: Discussion }) {
  const video = post.attachments.find((file) => file.is_video)
  const [liked, setLiked] = useState(post.my_reaction === 'like')
  const [count, setCount] = useState(post.reactions_count)
  const [error, setError] = useState('')
  const [sharing, setSharing] = useState(false)
  const ref = useRef<HTMLElement>(null)
  const watched = useRef(false)
  useEffect(() => (ref.current ? trackVisibility(ref.current, post.id) : undefined), [post.id])
  if (!video) return null
  const like = async () => {
    const before = { liked, count }
    setLiked(!liked); setCount(count + (liked ? -1 : post.my_reaction && post.my_reaction !== 'like' ? 0 : 1))
    try { setCount((await api.post<{ reactions_count: number }>(`/discussions/${post.id}/react/`, { reaction_type: 'like' })).data.reactions_count) }
    catch (err) { setLiked(before.liked); setCount(before.count); setError(getErrorMessage(err)) }
  }
  const onProgress = (fraction: number, seconds: number) => {
    if (!watched.current && fraction >= 0.9) { watched.current = true; recordView(post.id, seconds * 1000, true) }
  }
  return <article ref={ref} className="reel" aria-label={`Video by ${post.author_username}`}>
    <VideoPlayer file={video} fill onProgress={onProgress} />
    <div className="reel-overlay">
      <div className="reel-info">
        <Link to={`/u/${post.author_username}`} className="reel-author">@{post.author_username}</Link>
        {post.sponsored && <span className="reel-sponsored">Sponsored · {post.sponsored.name}</span>}
        {post.body && <p><RichText text={post.body} /></p>}
        {error && <small className="reel-error">{error}</small>}
      </div>
      <div className="reel-actions">
        <button type="button" aria-label={liked ? 'Unlike' : 'Like'} aria-pressed={liked} className={liked ? 'is-liked' : ''} onClick={() => void like()}><Heart size={26} fill={liked ? 'currentColor' : 'none'} /><span>{count}</span></button>
        <Link to={`/discussions/${post.id}`} aria-label="Comments"><MessageCircle size={26} /><span>{post.comments_count}</span></Link>
        <button type="button" aria-label="Share" onClick={() => setSharing(true)}><Send size={25} /><span>{post.share_count || ''}</span></button>
      </div>
      {sharing && <ShareSheet post={post} onClose={() => setSharing(false)} onDone={setError} />}
    </div>
  </article>
}

/** Full-height, snap-scrolling video feed. Each video plays when it fills the screen. */
export default function ReelsPage() {
  const sentinel = useRef<HTMLDivElement>(null)
  const reels = useInfiniteQuery({
    queryKey: ['reels'],
    initialPageParam: 1,
    // Ranked for each person, like the main For You feed, videos only.
    queryFn: async ({ pageParam }) => (await api.get<FeedPage>('/feed/for-you/', { params: { media: 'videos', page: pageParam } })).data,
    getNextPageParam: (last, pages) => last.next ? pages.length + 1 : undefined,
  })
  const posts = reels.data?.pages.flatMap((page) => page.results) ?? []
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = reels

  useEffect(() => {
    const node = sentinel.current
    if (!node || !hasNextPage || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(([entry]) => { if (entry.isIntersecting && !isFetchingNextPage) void fetchNextPage() }, { rootMargin: '600px' })
    observer.observe(node)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, posts.length])

  if (reels.isLoading) return <div className="loading-card">Loading videos…</div>
  if (reels.error) return <div className="error-card">{getErrorMessage(reels.error)}</div>
  if (!posts.length) return <div className="empty-card"><div className="empty-icon"><Clapperboard size={20} /></div><h3>No videos yet</h3><p>Share the first one from the Home feed with the Video button.</p><Link to="/home" className="button button-primary">Go to Home</Link></div>
  return <div className="reels-page">
    {posts.map((post) => <Reel key={post.id} post={post} />)}
    <div ref={sentinel} className="reels-sentinel" aria-hidden="true" />
    {isFetchingNextPage && <p className="reels-loading">Loading more…</p>}
  </div>
}
