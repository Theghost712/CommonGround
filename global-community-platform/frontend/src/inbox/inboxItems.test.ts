import { describe, expect, it } from 'vitest'
import type { NotificationItem } from '../context/NotificationsContext'
import {
  buildInboxItems, filterInboxItems, inboxUnreadTotal, messagePreview,
  type InboxConversation,
} from './inboxItems'

const at = (iso: string) => iso

const chat = (overrides: Partial<InboxConversation> & { id: number }): InboxConversation => ({
  display_title: `Chat ${overrides.id}`,
  unread_count: 0,
  updated_at: at('2026-11-20T10:00:00Z'),
  last_message: null,
  ...overrides,
})

const update = (overrides: Partial<NotificationItem> & { id: number }): NotificationItem => ({
  notification_type: 'mention',
  title: `Update ${overrides.id}`,
  body: '',
  target_url: '/discussions/1',
  data: {},
  actor: null,
  actor_username: null,
  is_read: false,
  read_at: null,
  created_at: at('2026-11-20T10:00:00Z'),
  ...overrides,
})

describe('messagePreview', () => {
  it('labels media and falls back to the text', () => {
    expect(messagePreview(null)).toBe('No messages yet')
    expect(messagePreview({ body: 'hi', kind: 'text', created_at: '' })).toBe('hi')
    expect(messagePreview({ body: '', kind: 'photo', created_at: '' })).toBe('Sent a photo')
    expect(messagePreview({ body: '', kind: 'voice', created_at: '' })).toBe('Sent a voice message')
    expect(messagePreview({ body: 'Team: meeting moved', kind: 'system', created_at: '' })).toBe('Team: meeting moved')
  })
})

describe('buildInboxItems', () => {
  it('merges chats and updates, newest first', () => {
    const items = buildInboxItems(
      [chat({ id: 1, last_message: { body: 'old', created_at: '2026-11-20T08:00:00Z' } })],
      [update({ id: 9, created_at: '2026-11-20T09:00:00Z' }), update({ id: 10, created_at: '2026-11-20T11:00:00Z' })],
    )
    expect(items.map((item) => item.key)).toEqual(['update-10', 'update-9', 'chat-1'])
  })

  it('places a chat by its last message, falling back to its update time', () => {
    const items = buildInboxItems(
      [chat({ id: 2, updated_at: '2026-11-20T12:00:00Z', last_message: null })],
      [update({ id: 3, created_at: '2026-11-20T09:00:00Z' })],
    )
    expect(items[0].key).toBe('chat-2')
  })

  it('marks unread chats and unread updates', () => {
    const items = buildInboxItems(
      [chat({ id: 1, unread_count: 3 }), chat({ id: 2, unread_count: 0 })],
      [update({ id: 5, is_read: true }), update({ id: 6, is_read: false })],
    )
    const unread = Object.fromEntries(items.map((item) => [item.key, item.unread]))
    expect(unread).toEqual({ 'chat-1': true, 'chat-2': false, 'update-5': false, 'update-6': true })
  })
})

describe('filterInboxItems', () => {
  const items = buildInboxItems(
    [chat({ id: 1, unread_count: 2 }), chat({ id: 2 })],
    [update({ id: 5, is_read: false }), update({ id: 6, is_read: true })],
  )

  it('filters by kind and by unread', () => {
    expect(filterInboxItems(items, 'all')).toHaveLength(4)
    expect(filterInboxItems(items, 'chats').every((item) => item.kind === 'chat')).toBe(true)
    expect(filterInboxItems(items, 'updates').every((item) => item.kind === 'update')).toBe(true)
    expect(filterInboxItems(items, 'unread').map((item) => item.key).sort()).toEqual(['chat-1', 'update-5'])
  })
})

describe('inboxUnreadTotal', () => {
  it('counts every unread message in a chat, and each unread update once', () => {
    const items = buildInboxItems(
      [chat({ id: 1, unread_count: 4 }), chat({ id: 2, unread_count: 0 })],
      [update({ id: 5, is_read: false }), update({ id: 6, is_read: true })],
    )
    expect(inboxUnreadTotal(items)).toBe(5)
  })
})
