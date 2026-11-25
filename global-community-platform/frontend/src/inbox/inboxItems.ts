import type { NotificationItem } from '../context/NotificationsContext'

/** The subset of a chat conversation the inbox needs (the chat page's full type is larger). */
export type InboxConversation = {
  id: number
  display_title: string
  unread_count: number
  updated_at: string
  last_message: { body: string; kind?: string; created_at: string } | null
}

export type InboxFilter = 'all' | 'unread' | 'chats' | 'updates'

export type InboxItem =
  | { kind: 'chat'; key: string; at: string; unread: boolean; title: string; preview: string; conversationId: number; unreadCount: number }
  | { kind: 'update'; key: string; at: string; unread: boolean; title: string; preview: string; notification: NotificationItem }

/** Text shown for a message in a list: media messages get a label instead of an empty line. */
const MEDIA_LABELS: Record<string, string> = { photo: 'Sent a photo', video: 'Sent a video', voice: 'Sent a voice message', post: 'Shared a post' }

export function messagePreview(message: InboxConversation['last_message']): string {
  if (!message) return 'No messages yet'
  return MEDIA_LABELS[message.kind ?? 'text'] ?? message.body
}

/**
 * One list of chats and notifications, newest first.
 * A chat's time is its latest message (or when it was last updated); an update's time is when it was created.
 */
export function buildInboxItems(conversations: InboxConversation[], notifications: NotificationItem[]): InboxItem[] {
  const chats: InboxItem[] = conversations.map((conversation) => ({
    kind: 'chat',
    key: `chat-${conversation.id}`,
    at: conversation.last_message?.created_at ?? conversation.updated_at,
    unread: conversation.unread_count > 0,
    title: conversation.display_title,
    preview: messagePreview(conversation.last_message),
    conversationId: conversation.id,
    unreadCount: conversation.unread_count,
  }))
  const updates: InboxItem[] = notifications.map((notification) => ({
    kind: 'update',
    key: `update-${notification.id}`,
    at: notification.created_at,
    unread: !notification.is_read,
    title: notification.title,
    preview: notification.body,
    notification,
  }))
  return [...chats, ...updates].sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
}

export function filterInboxItems(items: InboxItem[], filter: InboxFilter): InboxItem[] {
  switch (filter) {
    case 'unread': return items.filter((item) => item.unread)
    case 'chats': return items.filter((item) => item.kind === 'chat')
    case 'updates': return items.filter((item) => item.kind === 'update')
    default: return items
  }
}

/** Unread chats (counted as messages) plus unread updates. */
export function inboxUnreadTotal(items: InboxItem[]): number {
  return items.reduce((sum, item) => sum + (item.kind === 'chat' ? item.unreadCount : item.unread ? 1 : 0), 0)
}
