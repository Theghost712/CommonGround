import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Bookmark, FileText, Heart, PenLine, Send, Sparkles, ThumbsUp, Trash2, Trophy } from 'lucide-react'
import DOMPurify from 'dompurify'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import type { Comment, Discussion, DiscussionAttachment } from '../types'
import UserLink from '../components/UserHoverCard'
import PostMedia from '../components/PostMedia'
import PollCard from '../components/PollCard'
import VideoPlayer from '../components/VideoPlayer'
import '../media-posts.css'
import ReportDialog from '../components/ReportDialog'
import RichText, { linkifyHtml } from '../components/RichText'
import '../home-feed.css'
import '../discussion-forum.css'


function AttachmentPreview({ file }: { file: DiscussionAttachment }) {
  const [url, setUrl] = useState('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // Blob URLs are fetched through the authenticated API client so private-community
    // attachments receive the same JWT authorization as other API requests.
    let active = true
    let objectUrl = ''
    api.get(`/attachments/${file.id}/download/`, { responseType: 'blob' })
      .then((response) => {
        objectUrl = URL.createObjectURL(response.data)
        if (active) setUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl)
      })
      .catch(() => { if (active) setFailed(true) })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [file.id])

  if (failed) return <div className="detail-file-attachment attachment-error"><FileText size={20} /><span>{file.original_name}</span><small>Could not load</small></div>
  if (!url) return <div className="detail-file-attachment attachment-loading"><FileText size={20} /><span>Loading {file.original_name}…</span></div>
  return file.is_image
    ? <a href={url} target="_blank" rel="noreferrer" className="detail-image-attachment"><img src={url} alt={file.original_name} /><span>{file.original_name}</span></a>
    : <a href={url} download={file.original_name} className="detail-file-attachment"><FileText size={20} /><span>{file.original_name}</span><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></a>
}

type CommentActions = {
  currentUserId?: number
  onReply: (id: number) => void
  onSave: (id: number, body: string) => Promise<void>
  onDelete: (id: number) => Promise<void>
}

function CommentNode({ comment, actions, depth = 0 }: { comment: Comment; actions: CommentActions; depth?: number }) {
  const [editing, setEditing] = useState(false)
  const [reporting, setReporting] = useState(false)
  const [draft, setDraft] = useState(comment.body)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const own = comment.author === actions.currentUserId
  const edited = new Date(comment.updated_at).getTime() - new Date(comment.created_at).getTime() > 1000

  const save = async () => {
    if (!draft.trim()) return
    setBusy(true); setError('')
    try { await actions.onSave(comment.id, draft.trim()); setEditing(false) } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }
  const remove = async () => {
    const extra = comment.replies?.length ? ' Its replies will be deleted too.' : ''
    if (!window.confirm(`Delete this comment?${extra}`)) return
    setBusy(true); setError('')
    try { await actions.onDelete(comment.id) } catch (err) { setError(getErrorMessage(err)); setBusy(false) }
  }

  return <div className={`comment-tree-node ${depth ? 'nested-comment' : ''}`}>
    <div className="comment-item"><div className="avatar avatar-tiny">{comment.author_username.slice(0, 1).toUpperCase()}</div><div className="comment-content">
      <div className="comment-top"><UserLink username={comment.author_username}><strong>{comment.author_username}</strong></UserLink><span>{new Date(comment.created_at).toLocaleString()}{edited && ' · edited'}</span></div>
      {editing
        ? <div className="comment-edit"><textarea rows={3} value={draft} maxLength={3000} onChange={(event) => setDraft(event.target.value)} aria-label="Edit comment" autoFocus /><div className="comment-edit-actions"><button type="button" className="button button-primary" onClick={save} disabled={busy || !draft.trim()}>{busy ? 'Saving…' : 'Save'}</button><button type="button" className="text-button" onClick={() => { setEditing(false); setDraft(comment.body); setError('') }} disabled={busy}>Cancel</button></div></div>
        : <p><RichText text={comment.body} /></p>}
      {error && <div className="error-message">{error}</div>}
      {!editing && <div className="comment-actions">
        <button className="reply-trigger" onClick={() => actions.onReply(comment.id)}>Reply</button>
        {own && <button className="reply-trigger" onClick={() => { setDraft(comment.body); setEditing(true) }} disabled={busy}>Edit</button>}
        {own && <button className="reply-trigger danger-trigger" onClick={remove} disabled={busy}>Delete</button>}
        {!own && <button className="reply-trigger" onClick={() => setReporting(true)}>Report</button>}
      </div>}
      {reporting && <ReportDialog targetType="comment" targetId={comment.id} onClose={() => setReporting(false)} />}
      {comment.replies?.map((reply) => <CommentNode key={reply.id} comment={reply} actions={actions} depth={depth + 1} />)}
    </div></div>
  </div>
}

export default function DiscussionPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const client = useQueryClient()
  const [body, setBody] = useState('')
  const [replyTo, setReplyTo] = useState<number | null>(null)
  const [error, setError] = useState('')
  const discussionQuery = useQuery({ queryKey: ['discussion', String(id)], queryFn: async () => (await api.get<Discussion>(`/discussions/${id}/`)).data, enabled: Boolean(id) })
  const discussion = discussionQuery.data
  const commentsQuery = useQuery({ queryKey: ['comments', id], queryFn: async () => (await api.get<Comment[]>(`/discussions/${id}/comments/`)).data, enabled: Boolean(id) })

  const refresh = () => {
    client.invalidateQueries({ queryKey: ['discussion', String(id)] })
    client.invalidateQueries({ queryKey: ['discussions'] })
    client.invalidateQueries({ queryKey: ['trending-discussions'] })
    client.invalidateQueries({ queryKey: ['bookmarked-discussions'] })
  }
  const reactMutation = useMutation({ mutationFn: (reaction_type: string) => api.post(`/discussions/${id}/react/`, { reaction_type }), onSuccess: refresh })
  const bookmarkMutation = useMutation({ mutationFn: () => api.post(`/discussions/${id}/bookmark/`), onSuccess: refresh })
  const commentMutation = useMutation({
    mutationFn: () => api.post(`/discussions/${id}/comments/`, { body: body.trim(), parent: replyTo }),
    onSuccess: () => { setBody(''); setReplyTo(null); client.invalidateQueries({ queryKey: ['comments', id] }); refresh() },
    onError: (err) => setError(getErrorMessage(err)),
  })
  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/discussions/${id}/`),
    onSuccess: () => {
      client.removeQueries({ queryKey: ['discussion', String(id)] })
      for (const key of ['discussions', 'trending-discussions', 'bookmarked-discussions', 'community-discussions', 'discussion-categories']) client.invalidateQueries({ queryKey: [key] })
      navigate('/home', { replace: true })
    },
    onError: (err) => window.alert(getErrorMessage(err)),
  })
  const deleteDiscussion = () => {
    if (window.confirm('Delete this discussion? Its comments, reactions and attachments will be removed for everyone.')) deleteMutation.mutate()
  }
  const commentActions: CommentActions = {
    currentUserId: user?.id,
    onReply: (commentId) => startReply(commentId),
    onSave: async (commentId, text) => {
      await api.patch(`/comments/${commentId}/`, { body: text })
      await client.invalidateQueries({ queryKey: ['comments', id] })
    },
    onDelete: async (commentId) => {
      await api.delete(`/comments/${commentId}/`)
      if (replyTo === commentId) setReplyTo(null)
      await client.invalidateQueries({ queryKey: ['comments', id] })
      refresh()
    },
  }
  const submit = (event: FormEvent) => { event.preventDefault(); if (!body.trim()) return; setError(''); commentMutation.mutate() }
  const startReply = (commentId: number) => {
    setReplyTo(commentId)
    document.querySelector('.comment-form textarea')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  if (discussionQuery.isLoading) return <div className="loading-card">Opening the conversation…</div>
  if (discussionQuery.error || !discussion) return <div className="error-card">{getErrorMessage(discussionQuery.error)}</div>

  return <div className="detail-page discussion-detail-page">
    <Link to="/home" className="back-link"><ArrowLeft size={16} /> Back to conversations</Link>
    <article className="detail-card">
      <div className="discussion-meta"><UserLink username={discussion.author_username} className="author-link"><div className="avatar avatar-tiny">{discussion.author_username.slice(0, 1).toUpperCase()}</div><span className="author-name">{discussion.author_username}</span></UserLink><span className="meta-separator">·</span><span>{new Date(discussion.created_at).toLocaleString()}</span>{discussion.community_name && <Link to={`/communities/${discussion.community}`} className="community-tag">{discussion.community_name}</Link>}</div>
      <div className="detail-topic-row"><span className="topic-pill">{discussion.category}</span>{discussion.author === user?.id && <div className="owner-actions"><Link to={`/discussions/${discussion.id}/edit`} className="action-button"><PenLine size={15} /> Edit</Link><button className="action-button danger-action" onClick={deleteDiscussion} disabled={deleteMutation.isPending}><Trash2 size={15} /> {deleteMutation.isPending ? 'Deleting…' : 'Delete'}</button></div>}</div>
      {discussion.attachments?.filter((file) => file.is_video).map((file) => <div className="detail-photos" key={file.id}><VideoPlayer file={file} /></div>)}
      {discussion.poll && <PollCard postId={discussion.id} poll={discussion.poll} />}
      {discussion.attachments?.some((file) => file.is_image) && <div className="detail-photos"><PostMedia images={discussion.attachments.filter((file) => file.is_image)} onDoubleTap={() => { if (discussion.my_reaction !== 'like') reactMutation.mutate('like') }} eager /></div>}
      {discussion.title ? <h1>{discussion.title}</h1> : <h1 className="sr-only">Post by {discussion.author_username}</h1>}
      {discussion.content_html ? <div className="rich-content-rendered" onClick={(event) => {
        // Hashtag/mention links inside rich text navigate inside the app.
        const link = (event.target as HTMLElement).closest('a[data-internal]')
        if (link) { event.preventDefault(); navigate(link.getAttribute('href') || '/') }
      }} dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(linkifyHtml(DOMPurify.sanitize(discussion.content_html)), { ADD_ATTR: ['data-internal'] }) }} /> : (discussion.poll && discussion.body === discussion.poll.question ? null : <p className="detail-body"><RichText text={discussion.body} /></p>)}
      {discussion.attachments?.some((file) => !file.is_image && !file.is_video) && <section className="detail-attachments"><h3>Files <span>{discussion.attachments.filter((file) => !file.is_image && !file.is_video).length}</span></h3><div className="detail-attachment-grid">{discussion.attachments.filter((file) => !file.is_image && !file.is_video).map((file) => <AttachmentPreview file={file} key={file.id} />)}</div></section>}
      <div className="detail-actions"><button className={`action-button ${discussion.my_reaction === 'like' ? 'liked' : ''}`} onClick={() => reactMutation.mutate('like')} disabled={reactMutation.isPending}><Heart size={17} fill={discussion.my_reaction === 'like' ? 'currentColor' : 'none'} /> Like · {discussion.reactions_count}</button><button className={`action-button ${discussion.my_reaction === 'insightful' ? 'liked' : ''}`} onClick={() => reactMutation.mutate('insightful')} disabled={reactMutation.isPending}><Sparkles size={16} /> Insightful</button><button className={`action-button ${discussion.my_reaction === 'support' ? 'liked' : ''}`} onClick={() => reactMutation.mutate('support')} disabled={reactMutation.isPending}><ThumbsUp size={16} /> Support</button><button className={`action-button ${discussion.my_reaction === 'celebrate' ? 'liked' : ''}`} onClick={() => reactMutation.mutate('celebrate')} disabled={reactMutation.isPending}><Trophy size={16} /> Celebrate</button><button className={`action-button detail-bookmark ${discussion.has_bookmarked ? 'saved' : ''}`} onClick={() => bookmarkMutation.mutate()} disabled={bookmarkMutation.isPending}><Bookmark size={16} fill={discussion.has_bookmarked ? 'currentColor' : 'none'} /> {discussion.has_bookmarked ? 'Saved' : 'Save'}</button></div>
    </article>

    <section className="comments-section"><div className="comments-heading"><div><span className="eyebrow">KEEP IT GOING</span><h2>The conversation</h2></div><span>{discussion.comments_count} comments</span></div>
      <form className="comment-form" onSubmit={submit}>{replyTo && <div className="reply-notice">Replying to a comment <button type="button" onClick={() => setReplyTo(null)}>Cancel</button></div>}<textarea rows={3} value={body} onChange={(event) => setBody(event.target.value)} placeholder="Add a thoughtful comment…" required /><div className="comment-form-footer"><span>Different perspectives make better conversations.</span><button className="button button-primary" disabled={commentMutation.isPending || !body.trim()}>{commentMutation.isPending ? 'Sending…' : 'Post comment'} <Send size={15} /></button></div>{error && <div className="error-message">{error}</div>}</form>
      <div className="comment-list">{commentsQuery.isLoading && <div className="loading-card">Loading comments…</div>}{commentsQuery.error && <div className="error-card">{getErrorMessage(commentsQuery.error)}</div>}{commentsQuery.data?.map((comment) => <CommentNode key={comment.id} comment={comment} actions={commentActions} />)}{commentsQuery.data?.length === 0 && <p className="no-comments">Be the first to add a perspective.</p>}</div>
    </section>
  </div>
}
