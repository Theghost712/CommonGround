import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import InboxPage from './InboxPage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: (e: { message?: string }) => e?.message ?? 'Request failed' }))
vi.mock('../context/NotificationsContext', () => ({
  useNotifications: () => ({ refreshUnreadCount: vi.fn(async () => undefined) }),
}))

const conversations = [
  { id: 7, display_title: 'Amina', unread_count: 2, updated_at: '2026-11-20T10:00:00Z', last_message: { body: 'See you at six', kind: 'text', created_at: '2026-11-20T10:00:00Z' } },
  { id: 8, display_title: 'Book club', unread_count: 0, updated_at: '2026-11-19T10:00:00Z', last_message: { body: '', kind: 'photo', created_at: '2026-11-19T10:00:00Z' } },
]
const notifications = [
  { id: 31, notification_type: 'mention', title: 'Neema mentioned you', body: 'Look at this', target_url: '/discussions/4', data: {}, actor: null, actor_username: 'neema', is_read: false, read_at: null, created_at: '2026-11-20T11:00:00Z' },
]

describe('InboxPage', () => {
  beforeEach(() => {
    api.get.mockReset()
    api.post.mockReset()
    api.get.mockImplementation(async (url: string) => ({
      data: url === '/conversations/' ? { count: 2, next: null, previous: null, results: conversations } : { count: 1, next: null, previous: null, results: notifications },
    }))
  })

  it('lists chats and updates together, newest first, with the unread total', async () => {
    renderWithProviders(<InboxPage />, { route: '/inbox' })
    expect(await screen.findByText('Neema mentioned you')).toBeTruthy()
    const rows = screen.getAllByRole('button').filter((button) => button.className.includes('inbox-row'))
    expect(rows.map((row) => within(row).getByText(/Neema|Amina|Book club/).textContent)).toEqual(['Neema mentioned you', 'Amina', 'Book club'])
    expect(screen.getByText('See you at six')).toBeTruthy()
    expect(screen.getByText('Sent a photo')).toBeTruthy()
    // 2 unread messages in Amina plus 1 unread update.
    expect(screen.getByText('3 unread')).toBeTruthy()
  })

  it('filters to unread items and to chats only', async () => {
    renderWithProviders(<InboxPage />, { route: '/inbox' })
    await screen.findByText('Neema mentioned you')
    await userEvent.click(screen.getByRole('tab', { name: 'Unread' }))
    expect(screen.queryByText('Book club')).toBeNull()
    expect(screen.getByText('Amina')).toBeTruthy()
    expect(screen.getByText('Neema mentioned you')).toBeTruthy()

    await userEvent.click(screen.getByRole('tab', { name: 'Chats' }))
    expect(screen.queryByText('Neema mentioned you')).toBeNull()
    expect(screen.getByText('Book club')).toBeTruthy()
  })

  it('shows an empty state when there is nothing to show', async () => {
    api.get.mockImplementation(async () => ({ data: [] }))
    renderWithProviders(<InboxPage />, { route: '/inbox' })
    await waitFor(() => expect(screen.getByText('Nothing here yet.')).toBeTruthy())
  })
})
