import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck, Inbox, MessageCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { useNotifications, type NotificationItem } from '../context/NotificationsContext'
import type { Paginated } from '../types'
import {
  buildInboxItems, filterInboxItems, inboxUnreadTotal,
  type InboxConversation, type InboxFilter, type InboxItem,
} from '../inbox/inboxItems'
import '../inbox.css'

const FILTERS: { value: InboxFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'unread', label: 'Unread' },
  { value: 'chats', label: 'Chats' },
  { value: 'updates', label: 'Updates' },
]

function relativeTime(value: string) {
  const date = new Date(value)
  const seconds = Math.max(1, Math.floor((Date.now() - date.getTime()) / 1000))
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

/** Your chats and notifications in one list, newest first. */
export default function InboxPage() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const { refreshUnreadCount } = useNotifications()
  const [filter, setFilter] = useState<InboxFilter>('all')
  const [notice, setNotice] = useState('')

  const conversations = useQuery({
    queryKey: ['chat-conversations'],
    queryFn: async () => {
      const { data } = await api.get<Paginated<InboxConversation> | InboxConversation[]>('/conversations/')
      return Array.isArray(data) ? data : data.results
    },
  })
  const notifications = useQuery({
    queryKey: ['notifications', 'inbox'],
    queryFn: async () => {
      const { data } = await api.get<Paginated<NotificationItem> | NotificationItem[]>('/notifications/')
      return Array.isArray(data) ? data : data.results
    },
  })

  const markRead = useMutation({
    mutationFn: (id: number) => api.post(`/notifications/${id}/mark-read/`),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['notifications'] })
      void refreshUnreadCount()
    },
  })
  const markAll = useMutation({
    mutationFn: () => api.post('/notifications/mark-all-read/'),
    onSuccess: () => setNotice('All updates are marked as read.'),
    onError: (err) => setNotice(getErrorMessage(err)),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['notifications'] })
      void refreshUnreadCount()
    },
  })

  const loading = conversations.isLoading || notifications.isLoading
  const failed = conversations.error || notifications.error
  const items = buildInboxItems(conversations.data ?? [], notifications.data ?? [])
  const visible = filterInboxItems(items, filter)
  const unread = inboxUnreadTotal(items)

  const open = (item: InboxItem) => {
    if (item.kind === 'chat') {
      navigate(`/messages?c=${item.conversationId}`)
      return
    }
    const { notification } = item
    const go = () => { if (notification.target_url) navigate(notification.target_url) }
    if (notification.is_read) return go()
    markRead.mutate(notification.id, { onSettled: go })
  }

  const emptyText = filter === 'unread'
    ? "You're all caught up."
    : filter === 'chats' ? 'No conversations yet. Start one from Messages.' : filter === 'updates' ? 'No updates yet.' : 'Nothing here yet.'

  return <section className="inbox-page">
    <div className="inbox-heading">
      <div>
        <span className="eyebrow">YOUR INBOX</span>
        <h1>Inbox</h1>
        <p>Messages, replies and updates, newest first.</p>
      </div>
      <div className="inbox-heading-actions">
        <span className="unread-summary"><i /> {unread} unread</span>
        <button className="button button-light" onClick={() => markAll.mutate()} disabled={!notifications.data?.some((n) => !n.is_read) || markAll.isPending}>
          <CheckCheck size={15} /> Mark updates read
        </button>
      </div>
    </div>

    {notice && <div className="inline-message" role="status">{notice}</div>}

    <div className="inbox-filters" role="tablist" aria-label="Filter inbox">
      {FILTERS.map((option) => (
        <button key={option.value} role="tab" aria-selected={filter === option.value} className={filter === option.value ? 'active' : ''} onClick={() => setFilter(option.value)}>
          {option.label}
        </button>
      ))}
    </div>

    <div className="inbox-list-card">
      {loading && <div className="loading-card">Loading your inbox…</div>}
      {failed && !loading && <div className="error-card">{getErrorMessage(failed)}</div>}
      {!loading && !failed && visible.length === 0 && (
        <div className="notification-empty">
          <div><Inbox size={24} /></div>
          <h2>{emptyText}</h2>
        </div>
      )}
      {visible.map((item) => (
        <button key={item.key} className={`inbox-row ${item.unread ? 'is-unread' : ''}`} onClick={() => open(item)}>
          <span className="inbox-row-icon" aria-hidden="true">
            {item.kind === 'chat' ? <MessageCircle size={18} /> : <Bell size={18} />}
          </span>
          <span className="inbox-row-body">
            <span className="inbox-row-top">
              <strong>{item.title}</strong>
              <time dateTime={item.at}>{relativeTime(item.at)}</time>
            </span>
            <span className="inbox-row-preview">{item.preview}</span>
          </span>
          {item.kind === 'chat' && item.unreadCount > 0 && <span className="inbox-count">{item.unreadCount > 99 ? '99+' : item.unreadCount}</span>}
          {item.kind === 'update' && item.unread && <span className="notification-unread-dot" aria-label="Unread" />}
        </button>
      ))}
    </div>
  </section>
}
