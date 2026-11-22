import { useEffect, useRef, useState, type FormEvent, type TouchEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BellOff, Bookmark, FileText, Flag, Heart, Link2, MessageCircle, MoreHorizontal, PenLine, Send, SquareArrowOutUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import type { Discussion } from '../types'
import { Avatar } from './PersonBits'
import UserLink from './UserHoverCard'
import PostMedia from './PostMedia'
import PollCard from './PollCard'
import VideoPlayer from './VideoPlayer'
import '../media-posts.css'
import ReportDialog from './ReportDialog'
import RichText from './RichText'

export function timeAgo(value: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(value).getTime()) / 1000))
  if (seconds < 60) return 'now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days}d`
  const date = new Date(value)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', ...(date.getFullYear() !== new Date(now).getFullYear() ? { year: 'numeric' } : {}) })
}

export { clampRatio } from './PostMedia'

const DOUBLE_TAP_MS = 300

export default function FeedPost({ discussion }: { discussion: Discussion }) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const images = discussion.attachments.filter((file) => file.is_image)
  const video = discussion.attachments.find((file) => file.is_video)
  const files = discussion.attachments.filter((file) => !file.is_image && !file.is_video)
  const hasMedia = images.length > 0 || Boolean(video) || Boolean(discussion.poll)
  // A poll post without a caption stores the question as its text; don't repeat it.
  const captionText = discussion.poll && discussion.body === discussion.poll.question ? '' : discussion.body
  const [liked, setLiked] = useState(discussion.my_reaction === 'like')
  const [reacted, setReacted] = useState(discussion.my_reaction !== null)
  const [reactions, setReactions] = useState(discussion.reactions_count)
  const [saved, setSaved] = useState(discussion.has_bookmarked)
  const [comments, setComments] = useState(discussion.comments_count)
  const [burst, setBurst] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const [comment, setComment] = useState('')
  const [posting, setPosting] = useState(false)
  const [toast, setToast] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [reporting, setReporting] = useState(false)
  const lastTap = useRef(0)
  const menuRef = useRef<HTMLDivElement>(null)

  // Server data wins whenever the feed refetches.
  useEffect(() => {
    setLiked(discussion.my_reaction === 'like')
    setReacted(discussion.my_reaction !== null)
    setReactions(discussion.reactions_count)
    setSaved(discussion.has_bookmarked)
    setComments(discussion.comments_count)
  }, [discussion.my_reaction, discussion.reactions_count, discussion.has_bookmarked, discussion.comments_count])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(''), 2200)
    return () => clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    if (!menuOpen) return
    const close = (event: MouseEvent) => { if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [menuOpen])

  const refreshPost = () => {
    queryClient.invalidateQueries({ queryKey: ['discussion', String(discussion.id)] })
    queryClient.invalidateQueries({ queryKey: ['bookmarked-discussions'] })
  }

  const setLike = async (next: boolean) => {
    if (next === liked) return
    const before = { liked, reacted, reactions }
    setLiked(next)
    setReacted(next)
    // Switching from another reaction (e.g. "Insightful") to a like keeps the count.
    setReactions((count) => next ? (reacted ? count : count + 1) : count - 1)
    try {
      const { data } = await api.post<{ reactions_count: number }>(`/discussions/${discussion.id}/react/`, { reaction_type: 'like' })
      setReactions(data.reactions_count)
      refreshPost()
    } catch (err) {
      setLiked(before.liked); setReacted(before.reacted); setReactions(before.reactions)
      setToast(getErrorMessage(err))
    }
  }

  const likeFromDoubleTap = () => {
    setBurst((n) => n + 1)
    void setLike(true) // a double-tap only ever likes, never unlikes
  }

  const onMediaTouchEnd = (event: TouchEvent) => {
    const now = Date.now()
    if (now - lastTap.current < DOUBLE_TAP_MS) {
      event.preventDefault()
      lastTap.current = 0
      likeFromDoubleTap()
    } else {
      lastTap.current = now
    }
  }

  const toggleSave = async () => {
    const before = saved
    setSaved(!before)
    try {
      await api.post(`/discussions/${discussion.id}/bookmark/`)
      refreshPost()
      setToast(before ? 'Removed from saved' : 'Saved')
    } catch (err) {
      setSaved(before)
      setToast(getErrorMessage(err))
    }
  }

  const link = `${window.location.origin}/discussions/${discussion.id}`
  const copyLink = async () => {
    try { await navigator.clipboard.writeText(link); setToast('Link copied') } catch { setToast(link) }
  }
  const share = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: discussion.title || `Post by ${discussion.author_username}`, url: link }); return } catch (err) { if ((err as Error)?.name === 'AbortError') return }
    }
    await copyLink()
  }

  const submitComment = async (event: FormEvent) => {
    event.preventDefault()
    const body = comment.trim()
    if (!body) return
    setPosting(true)
    try {
      await api.post(`/discussions/${discussion.id}/comments/`, { body, parent: null })
      setComment('')
      setComments((count) => count + 1)
      setToast('Comment posted')
      queryClient.invalidateQueries({ queryKey: ['comments', String(discussion.id)] })
    } catch (err) {
      setToast(getErrorMessage(err))
    } finally {
      setPosting(false)
    }
  }

  const author = { display_name: discussion.author_display_name || discussion.author_username, avatar_url: discussion.author_avatar_url || '' }
  const own = discussion.author === user?.id
  const longBody = discussion.body.length > 140
  const postUrl = `/discussions/${discussion.id}`

  return <article className="feed-post" aria-label={`Post by ${discussion.author_username}: ${discussion.title || discussion.body.slice(0, 80) || 'photo'}`}>
    <header className="feed-post-header">
      <UserLink username={discussion.author_username} className="feed-avatar-link"><span className="feed-avatar-ring"><Avatar person={author} size={34} /></span></UserLink>
      <div className="feed-post-who">
        <div><UserLink username={discussion.author_username}><strong>{discussion.author_username}</strong></UserLink><span className="feed-dot">•</span><time dateTime={discussion.created_at} title={new Date(discussion.created_at).toLocaleString()}>{timeAgo(discussion.created_at)}</time></div>
        {discussion.community_name ? <Link to={`/communities/${discussion.community}`} className="feed-post-place">{discussion.community_name}</Link> : <span className="feed-post-place">{discussion.category}</span>}
      </div>
      <div className="feed-menu" ref={menuRef}>
        <button type="button" className="icon-button" aria-label="More options" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}><MoreHorizontal size={20} /></button>
        {menuOpen && <div className="feed-menu-list" role="menu">
          <Link role="menuitem" to={postUrl}><SquareArrowOutUpRight size={15} /> Go to post</Link>
          <button role="menuitem" type="button" onClick={() => { setMenuOpen(false); void copyLink() }}><Link2 size={15} /> Copy link</button>
          {own && <Link role="menuitem" to={`${postUrl}/edit`}><PenLine size={15} /> Edit</Link>}
          {!own && <button role="menuitem" type="button" onClick={() => { setMenuOpen(false); void api.put(`/safety/mutes/${encodeURIComponent(discussion.author_username)}/`, { posts: true, stories: false }).then(() => { setToast(`Muted ${discussion.author_username}. They won't know.`); queryClient.invalidateQueries({ queryKey: ['discussions'] }) }).catch((err) => setToast(getErrorMessage(err))) }}><BellOff size={15} /> Mute {discussion.author_username}</button>}
          {!own && <button role="menuitem" type="button" className="danger" onClick={() => { setMenuOpen(false); setReporting(true) }}><Flag size={15} /> Report post</button>}
        </div>}
      </div>
    </header>

    {video ? <div onDoubleClick={likeFromDoubleTap}><VideoPlayer file={video} /></div>
     : images.length > 0 ? <PostMedia images={images} onDoubleTap={likeFromDoubleTap} />
     : discussion.poll ? <div className="feed-poll"><PollCard postId={discussion.id} poll={discussion.poll} /></div>
     : <div className="feed-text-post" onDoubleClick={likeFromDoubleTap} onTouchEnd={onMediaTouchEnd}>
      <Link to={postUrl}><h2>{discussion.title}</h2></Link>
      {burst > 0 && <Heart key={burst} className="feed-heart-burst" size={80} fill="currentColor" aria-hidden="true" />}
    </div>}

    <div className="feed-actions">
      <button type="button" className={`feed-action ${liked ? 'is-liked' : ''}`} aria-label={liked ? 'Unlike' : 'Like'} aria-pressed={liked} onClick={() => void setLike(!liked)}><Heart size={24} fill={liked ? 'currentColor' : 'none'} /></button>
      <Link to={postUrl} className="feed-action" aria-label="Comment"><MessageCircle size={24} /></Link>
      <button type="button" className="feed-action" aria-label="Share" onClick={() => void share()}><Send size={23} /></button>
      <button type="button" className={`feed-action feed-save ${saved ? 'is-saved' : ''}`} aria-label={saved ? 'Remove from saved' : 'Save'} aria-pressed={saved} onClick={() => void toggleSave()}><Bookmark size={24} fill={saved ? 'currentColor' : 'none'} /></button>
    </div>

    <div className="feed-post-body">
      <strong className="feed-reactions">{reactions} {reactions === 1 ? 'reaction' : 'reactions'}</strong>
      <p className={`feed-caption ${expanded ? 'expanded' : ''}`}>
        <UserLink username={discussion.author_username}><strong>{discussion.author_username}</strong></UserLink>{' '}
        {hasMedia && discussion.title && <Link to={postUrl} className="feed-caption-title">{discussion.title}</Link>}
        {hasMedia && discussion.title && captionText && ' — '}
        <RichText text={captionText} />
      </p>
      {longBody && !expanded && <button type="button" className="feed-more" onClick={() => setExpanded(true)}>more</button>}
      {files.length > 0 && <Link to={postUrl} className="feed-files"><FileText size={14} /> {files.length} {files.length === 1 ? 'file' : 'files'} attached</Link>}
      {comments > 0 && <Link to={postUrl} className="feed-view-comments">View {comments === 1 ? '1 comment' : `all ${comments} comments`}</Link>}
      <form className="feed-comment" onSubmit={submitComment}>
        <input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Add a comment…" aria-label={`Comment on ${discussion.title || `${discussion.author_username}'s post`}`} maxLength={3000} />
        {comment.trim() && <button type="submit" disabled={posting}>{posting ? 'Posting…' : 'Post'}</button>}
      </form>
    </div>
    {toast && <div className="feed-toast" role="status">{toast}</div>}
    {reporting && <ReportDialog targetType="post" targetId={discussion.id} onClose={() => setReporting(false)} />}
  </article>
}
