import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Community, CommunityEvent } from '../types'
import { ExplorePage } from './InfoPage'

const get = vi.hoisted(() => vi.fn())
vi.mock('../services/api', () => ({ api: { get, post: vi.fn() }, getErrorMessage: () => 'Request failed' }))

const community = (id: number, name: string, overrides: Partial<Community> = {}): Community => ({
  id, name, slug: name.toLowerCase(), description: `${name} description`, category: 'General', visibility: 'public',
  approval_status: 'approved', logo_url: '', cover_url: '', created_by: 1, created_by_username: 'owner',
  members_count: id, pending_requests_count: null, is_member: false, my_role: null, membership_status: null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z', ...overrides,
})
const event = (id: number, title: string, startsInHours: number): CommunityEvent => ({
  id, community: 1, community_name: 'Olmoti', created_by: 1, created_by_username: 'owner', title, description: '',
  location: 'Arusha', starts_at: new Date(Date.now() + startsInHours * 3600e3).toISOString(),
  ends_at: new Date(Date.now() + (startsInHours + 1) * 3600e3).toISOString(), status: 'scheduled',
  rsvp_counts: { going: 4, interested: 1, not_going: 0 }, my_response: null, created_at: '', updated_at: '',
})

describe('ExplorePage', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation(async (url: string, config?: { params?: Record<string, string | undefined> }) => {
      if (url === '/discussions/categories/') return { data: [{ name: 'Health', count: 2 }, { name: 'Sports', count: 0 }] }
      if (url === '/discussions/trending/') return { data: { count: 0, next: null, previous: null, results: [] }, config }
      if (url === '/communities/') return { data: [
        community(1, 'Open Circle'),
        community(2, 'Already In', { is_member: true, my_role: 'member', membership_status: 'active' }),
        community(3, 'Waiting Room', { visibility: 'restricted', membership_status: 'pending' }),
        community(4, 'Secret Club', { visibility: 'private' }),
        community(5, 'Not Approved', { approval_status: 'pending' }),
        community(6, 'Restricted Hall', { visibility: 'restricted' }),
      ] }
      if (url === '/events/') return { data: [event(1, 'Finished meetup', -5), event(2, 'Tree planting day', 48)] }
      throw new Error(`unexpected GET ${url}`)
    })
  })

  it('suggests only approved communities the user can still join', async () => {
    renderWithProviders(<ExplorePage />)

    expect(await screen.findByText('Open Circle')).toBeInTheDocument()
    expect(screen.getByText('Restricted Hall')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /request to join/i })).toHaveAttribute('href', '/communities/6')
    for (const hidden of ['Already In', 'Waiting Room', 'Secret Club', 'Not Approved']) expect(screen.queryByText(hidden)).not.toBeInTheDocument()
  })

  it('lists upcoming events and drops ones that already ended', async () => {
    renderWithProviders(<ExplorePage />)

    expect(await screen.findByText('Tree planting day')).toBeInTheDocument()
    expect(screen.queryByText('Finished meetup')).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/events/', { params: { status: 'scheduled', ordering: 'starts_at', search: undefined } })
  })

  it('shows only topics with discussions and filters trending by topic', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ExplorePage />)

    const health = await screen.findByRole('button', { name: /health/i })
    expect(screen.queryByRole('button', { name: /sports/i })).not.toBeInTheDocument()
    await user.click(health)

    expect(await screen.findByRole('heading', { name: 'Trending in Health' })).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/discussions/trending/', { params: { search: undefined, category: 'Health' } })
  })
})
