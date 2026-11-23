import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link2, MessageCircle, Repeat2, Search, Send, Share2, X } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'
import type { Discussion } from '../types'

type Conversation = { id: number; display_title: string; conversation_type: 'direct' | 'group'; other_user: { username: string } | null }

/** Share a post: repost, repost with a comment, send it in a chat, copy the link, or the phone's share sheet. */
export default function ShareSheet({ post, onClose, onDone }: { post: Discussion; onClose: () => void; onDone: (message: string) => void }) {
  const original = post.repost_of ?? post
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'menu' | 'quote' | 'chat'>('menu')
  const [comment, setComment] = useState('')
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState<number[]>([])
  const link = `${window.location.origin}/discussions/${original.id}`
  const chats = useQuery({
    queryKey: ['conversations'],
    enabled: mode === 'chat',
    queryFn: async () => { const { data } = await api.get<Conversation[] | { results: Conversation[] }>('/conversations/'); return Array.isArray(data) ? data : data.results },
  })
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const repost = async (withComment: boolean) => {
    setBusy(true); setError('')
    try {
      await api.post(`/discussions/${original.id}/repost/`, withComment ? { comment } : {})
      queryClient.invalidateQueries({ queryKey: ['discussions'] })
      onDone(withComment ? 'Posted with your comment' : 'Reposted to your followers')
      onClose()
    } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }
  const sendTo = async (chat: Conversation) => {
    setBusy(true); setError('')
    try {
      await api.post(`/conversations/${chat.id}/share-post/`, { post_id: original.id })
      setSent((ids) => [...ids, chat.id])
    } catch (err) { setError(getErrorMessage(err)) } finally { setBusy(false) }
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); onDone('Link copied') } catch { onDone(link) }
    onClose()
  }
  const native = async () => {
    try { await navigator.share({ title: original.title || `Post by ${original.author_username}`, url: link }); onClose() } catch { /* cancelled */ }
  }
  const list = (chats.data ?? []).filter((c) => c.display_title.toLowerCase().includes(filter.trim().toLowerCase()))

  return createPortal(<div className="sheet-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
    <div className="sheet" role="dialog" aria-modal="true" aria-label="Share post">
      <div className="sheet-head">
        <strong>{mode === 'chat' ? 'Send in a chat' : mode === 'quote' ? 'Repost with your thoughts' : 'Share'}</strong>
        <button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
      </div>
      {error && <p className="sheet-error" role="alert">{error}</p>}
      {mode === 'menu' && <div className="sheet-actions">
        <button type="button" disabled={busy} onClick={() => void repost(false)}><Repeat2 size={20} /><span>Repost<small>Share it to your followers</small></span></button>
        <button type="button" onClick={() => setMode('quote')}><MessageCircle size={20} /><span>Repost with comment<small>Add what you think</small></span></button>
        <button type="button" onClick={() => setMode('chat')}><Send size={20} /><span>Send in a chat<small>To a friend or a group</small></span></button>
        <button type="button" onClick={() => void copy()}><Link2 size={20} /><span>Copy link</span></button>
        {typeof navigator !== 'undefined' && 'share' in navigator && <button type="button" onClick={() => void native()}><Share2 size={20} /><span>More apps…<small>WhatsApp, SMS and others</small></span></button>}
      </div>}
      {mode === 'quote' && <form className="sheet-quote" onSubmit={(e) => { e.preventDefault(); void repost(true) }}>
        <textarea autoFocus maxLength={2000} rows={4} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Say something about this…" aria-label="Your comment" />
        <div className="sheet-quote-preview"><strong>@{original.author_username}</strong> {(original.body || original.title).slice(0, 120)}</div>
        <div className="sheet-row"><button type="button" className="button button-outline" onClick={() => setMode('menu')}>Back</button><button className="button button-primary" disabled={busy || !comment.trim()}>{busy ? 'Posting…' : 'Post'}</button></div>
      </form>}
      {mode === 'chat' && <div className="sheet-chats">
        <label className="sheet-search"><Search size={16} /><input autoFocus value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search chats" aria-label="Search chats" /></label>
        {chats.isLoading && <p className="sheet-muted">Loading chats…</p>}
        {!chats.isLoading && list.length === 0 && <p className="sheet-muted">No chats yet. Start one from Messages.</p>}
        <ul>{list.map((chat) => <li key={chat.id}>
          <span className="sheet-chat-name">{chat.display_title}<small>{chat.conversation_type === 'group' ? 'Group' : chat.other_user ? `@${chat.other_user.username}` : ''}</small></span>
          <button type="button" className={`button ${sent.includes(chat.id) ? 'button-outline' : 'button-primary'}`} disabled={busy || sent.includes(chat.id)} onClick={() => void sendTo(chat)}>{sent.includes(chat.id) ? 'Sent' : 'Send'}</button>
        </li>)}</ul>
      </div>}
    </div>
  </div>, document.body)
}
