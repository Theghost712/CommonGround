import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import ModerationPage from './ModerationPage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: (e: { message?: string }) => e?.message ?? 'Request failed' }))
const auth = vi.hoisted(() => ({ user: null as null | Record<string, unknown> }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => auth }))

const item = (extra = {}) => ({
  target_type: 'post', target_id: 9, report_count: 2, latest_at: '2026-11-22T10:00:00Z',
  reasons: [{ reason: 'spam', label: 'Spam', count: 2 }], details: ['Selling followers'],
  owner: { id: 3, username: 'troll', display_name: 'Troll', is_active: true, is_staff: false, suspended_until: null },
  community: null, preview: { text: 'Buy cheap followers', image: '', url: '/discussions/9', gone: false }, can_enforce: true, ...extra,
})

beforeEach(() => {
  api.get.mockReset(); api.post.mockReset()
  api.get.mockImplementation(async (url: string) => {
    if (url === '/moderation/queue/') return { data: { count: 1, results: [item()] } }
    if (url === '/moderation/log/') return { data: [] }
    throw new Error(url)
  })
  api.post.mockResolvedValue({ data: { detail: 'Done.' } })
})

describe('ModerationPage', () => {
  it('refuses people who cannot moderate', () => {
    auth.user = { username: 'x', can_moderate: false }
    renderWithProviders(<ModerationPage />)
    expect(screen.getByText('Only moderators can open this page.')).toBeInTheDocument()
  })

  it('shows grouped reports and dismisses with one click', async () => {
    auth.user = { username: 'boss', can_moderate: true, is_staff: true }
    const user = userEvent.setup()
    renderWithProviders(<ModerationPage />)
    const card = await screen.findByRole('article', { name: 'Post by troll' })
    expect(within(card).getByText('2 reports')).toBeInTheDocument()
    expect(within(card).getByText('Spam ×2')).toBeInTheDocument()
    expect(within(card).getByText('“Selling followers”')).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: /no violation/i }))
    expect(api.post).toHaveBeenCalledWith('/moderation/decisions/', expect.objectContaining({ target_type: 'post', target_id: 9, action: 'dismiss' }))
  })

  it('requires a reason and sends the suspension length', async () => {
    auth.user = { username: 'boss', can_moderate: true, is_staff: true }
    const user = userEvent.setup()
    renderWithProviders(<ModerationPage />)
    const card = await screen.findByRole('article', { name: 'Post by troll' })
    await user.click(within(card).getByRole('button', { name: /suspend/i }))
    const confirm = within(card).getByRole('button', { name: 'Suspend' })
    expect(confirm).toBeDisabled()
    await user.type(within(card).getByLabelText(/reason/i), 'Spam network')
    await user.selectOptions(within(card).getByLabelText('Length'), '30')
    await user.click(confirm)
    expect(api.post).toHaveBeenCalledWith('/moderation/decisions/', expect.objectContaining({ action: 'suspend', days: 30, reason: 'Spam network', remove_content: true }))
  })

  it('community moderators only get dismiss and remove', async () => {
    auth.user = { username: 'mod', can_moderate: true, is_staff: false }
    api.get.mockImplementation(async (url: string) => url === '/moderation/queue/' ? { data: { count: 1, results: [item({ can_enforce: false })] } } : { data: [] })
    renderWithProviders(<ModerationPage />)
    const card = await screen.findByRole('article', { name: 'Post by troll' })
    expect(within(card).getByRole('button', { name: /remove/i })).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: /suspend/i })).not.toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: /ban/i })).not.toBeInTheDocument()
  })
})
