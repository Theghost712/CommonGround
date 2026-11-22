import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bell, Check, CheckCheck, MessageCircle, MessageSquare, Heart, AtSign,
  Users, Megaphone, ShieldCheck, Settings2, Trash2, Inbox,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { useNotifications, type NotificationItem } from '../context/NotificationsContext'
import type { Paginated } from '../types'

const TYPE_LABELS: Record<string, string> = {
  message: 'Message',
  discussion_comment: 'Comment',
  discussion_reply: 'Reply',
  discussion_reaction: 'Reaction',
  mention: 'Mention',
  membership_request: 'Membership request',
  membership_approved: 'Membership approved',
  community_announcement: 'Announcement',
  community_invitation: 'Invitation',
  system: 'System',
}

function NotificationIcon({ type }: { type: string }) {
  const props = { size: 18 }
  if (type === 'message') return <MessageCircle {...props} />
  if (type === 'discussion_comment' || type === 'discussion_reply') return <MessageSquare {...props} />
  if (type === 'discussion_reaction') return <Heart {...props} />
  if (type === 'mention') return <AtSign {...props} />
  if (type.startsWith('membership_') || type === 'community_invitation') return <Users {...props} />
  if (type === 'community_announcement') return <Megaphone {...props} />
  if (type === 'system') return <ShieldCheck {...props} />
  return <Bell {...props} />
}

function relativeTime(value: string) {
  const date = new Date(value)
  const seconds = Math.max(1, Math.floor((Date.now() - date.getTime()) / 1000))
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: date.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined })
}

export default function NotificationsPage() {
  const client = useQueryClient()
  const navigate = useNavigate()
  const { unreadCount, setUnreadCount, refreshUnreadCount } = useNotifications()
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const [notice, setNotice] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['notifications', filter],
    queryFn: async () => (await api.get<Paginated<NotificationItem> | NotificationItem[]>('/notifications/', {
      params: filter === 'unread' ? { unread: 'true' } : undefined,
    })).data,
  })
  const notifications = Array.isArray(data) ? data : data?.results || []

  useEffect(() => {
    const handler = () => { void client.invalidateQueries({ queryKey: ['notifications'] }) }
    window.addEventListener('commonground:notification', handler)
    return () => window.removeEventListener('commonground:notification', handler)
  }, [client])

  const markReadMutation = useMutation({
    mutationFn: (id: number) => api.post(`/notifications/${id}/mark-read/`),
    onSuccess: (response) => {
      setUnreadCount(response.data.unread_count)
      void client.invalidateQueries({ queryKey: ['notifications'] })
    },
    onError: (err) => setNotice(getErrorMessage(err)),
  })
  const markAllMutation = useMutation({
    mutationFn: () => api.post('/notifications/mark-all-read/'),
    onSuccess: () => {
      setUnreadCount(0)
      void client.invalidateQueries({ queryKey: ['notifications'] })
      setNotice('All notifications have been marked as read.')
    },
    onError: (err) => setNotice(getErrorMessage(err)),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/notifications/${id}/`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['notifications'] })
      void refreshUnreadCount()
    },
    onError: (err) => setNotice(getErrorMessage(err)),
  })

  const openNotification = async (item: NotificationItem) => {
    try {
      if (!item.is_read) await markReadMutation.mutateAsync(item.id)
      if (item.target_url) navigate(item.target_url)
    } catch {
      // Keep the user on the notification centre if updating its read status fails.
    }
  }

  return <section className="notifications-page">
    <div className="notifications-heading-row">
      <div><span className="eyebrow">YOUR UPDATES</span><h1>Notifications</h1><p>Stay connected to the conversations and communities you care about.</p></div>
      <div className="notifications-heading-actions">
        <span className="unread-summary"><i /> {unreadCount} unread</span>
        <button className="button button-light" onClick={() => markAllMutation.mutate()} disabled={!unreadCount || markAllMutation.isPending}><CheckCheck size={15} /> Mark all read</button>
      </div>
    </div>

    {notice && <div className="inline-message" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss"><Check size={14} /></button></div>}

    <div className="notifications-toolbar">
      <div className="notification-filter-tabs"><button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All updates</button><button className={filter === 'unread' ? 'active' : ''} onClick={() => setFilter('unread')}>Unread <span>{unreadCount}</span></button></div>
      <button className="notification-preferences-link" onClick={() => navigate('/notifications/preferences')}><Settings2 size={14} /> Preferences</button>
    </div>

    <div className="notification-list-card">
      {isLoading && <div className="loading-card">Loading notifications…</div>}
      {error && <div className="error-card">{getErrorMessage(error)}</div>}
      {!isLoading && !error && notifications.length === 0 && <div className="notification-empty"><div><Inbox size={24} /></div><h2>{filter === 'unread' ? 'You are all caught up.' : 'Nothing to see just yet.'}</h2><p>When something happens in your communities, your updates will appear here.</p></div>}
      {notifications.map((item) => <article className={`notification-row ${item.is_read ? '' : 'notification-unread'}`} key={item.id}>
        <button className={`notification-type-icon type-${item.notification_type}`} onClick={() => void openNotification(item)} aria-label={`Open ${TYPE_LABELS[item.notification_type] || 'notification'}`}><NotificationIcon type={item.notification_type} /></button>
        <button className="notification-main" onClick={() => void openNotification(item)}>
          <div className="notification-title-row"><strong>{item.title}</strong><span>{relativeTime(item.created_at)}</span></div>
          {item.body && <p>{item.body}</p>}
          <span className="notification-kind">{TYPE_LABELS[item.notification_type] || 'Update'}{item.actor_username ? ` · @${item.actor_username}` : ''}</span>
        </button>
        <div className="notification-row-actions">
          {!item.is_read && <button className="icon-button" title="Mark as read" onClick={() => markReadMutation.mutate(item.id)}><Check size={16} /></button>}
          <button className="icon-button danger-icon" title="Delete notification" onClick={() => deleteMutation.mutate(item.id)}><Trash2 size={15} /></button>
          {!item.is_read && <span className="notification-unread-dot" />}
        </div>
      </article>)}
    </div>
  </section>
}
