import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bookmark, Heart, MessageCircle, ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import type { Discussion } from '../types'
import UserLink from './UserHoverCard'
import '../discussion-forum.css'

export default function DiscussionCard({ discussion }: { discussion: Discussion }) {
  const client = useQueryClient()
  const refresh = () => {
    client.invalidateQueries({ queryKey: ['discussions'] })
    client.invalidateQueries({ queryKey: ['trending-discussions'] })
    client.invalidateQueries({ queryKey: ['discussion', String(discussion.id)] })
    client.invalidateQueries({ queryKey: ['bookmarked-discussions'] })
    client.invalidateQueries({ queryKey: ['community-discussions'] })
  }
  const reactMutation = useMutation({ mutationFn: () => api.post(`/discussions/${discussion.id}/react/`, { reaction_type: 'like' }), onSuccess: refresh })
  const bookmarkMutation = useMutation({ mutationFn: () => api.post(`/discussions/${discussion.id}/bookmark/`), onSuccess: refresh })
  const date = new Date(discussion.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

  return <article className="discussion-card">
    <div className="discussion-meta"><UserLink username={discussion.author_username} className="author-link"><div className="avatar avatar-tiny">{discussion.author_username.slice(0, 1).toUpperCase()}</div><span className="author-name">{discussion.author_username}</span></UserLink><span className="meta-separator">·</span><span>{date}</span>{discussion.community_name && <><span className="meta-separator">in</span><span className="community-tag">{discussion.community_name}</span></>}</div>
    <Link to={`/discussions/${discussion.id}`} className="discussion-title-link"><h2>{discussion.title || (discussion.body ? discussion.body.slice(0, 90) : `Photo by ${discussion.author_username}`)}</h2></Link>
    <p className="discussion-excerpt">{discussion.body.length > 240 ? `${discussion.body.slice(0, 240)}…` : discussion.body}</p>
    {discussion.attachments?.length > 0 && <div className="discussion-attachment-hint">{discussion.attachments.some((file) => file.is_image) ? 'Image attached' : 'File attached'} · {discussion.attachments.length} attachment{discussion.attachments.length === 1 ? '' : 's'}</div>}
    <div className="discussion-footer"><span className="topic-pill">{discussion.category}</span><div className="discussion-actions">
      <button className={`action-button ${discussion.my_reaction === 'like' ? 'liked' : ''}`} onClick={() => reactMutation.mutate()} disabled={reactMutation.isPending} aria-label="Like discussion"><Heart size={16} fill={discussion.my_reaction === 'like' ? 'currentColor' : 'none'} /><span>{discussion.reactions_count}</span></button>
      <Link to={`/discussions/${discussion.id}`} className="action-button"><MessageCircle size={16} /><span>{discussion.comments_count}</span></Link>
      <button className={`action-button bookmark-action ${discussion.has_bookmarked ? 'saved' : ''}`} onClick={() => bookmarkMutation.mutate()} disabled={bookmarkMutation.isPending} aria-label={discussion.has_bookmarked ? 'Remove bookmark' : 'Bookmark discussion'}><Bookmark size={16} fill={discussion.has_bookmarked ? 'currentColor' : 'none'} /><span>{discussion.bookmarks_count}</span></button>
      <Link to={`/discussions/${discussion.id}`} className="action-button read-more"><span>Join conversation</span><ArrowUpRight size={15} /></Link>
    </div></div>
  </article>
}
