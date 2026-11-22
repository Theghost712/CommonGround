import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Person, Relationship } from '../types'
import { FollowButton, RelationshipChips, formatCount } from './PersonBits'

const api = vi.hoisted(() => ({ post: vi.fn(), delete: vi.fn(), put: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))

const relation = (overrides: Partial<Relationship> = {}): Relationship => ({
  is_self: false, is_following: false, follows_you: false, is_mutual: false, in_contacts: false,
  mutual_followers_count: 0, mutual_followers_preview: [], label: null, ...overrides,
})
const person = (overrides: Partial<Relationship> = {}): Person => ({
  id: 2, username: 'neema', first_name: 'Neema', last_name: 'K', display_name: 'Neema K', avatar_url: '', bio: '',
  country: '', followers_count: 3, following_count: 4, relationship: relation(overrides), reason: null,
})

describe('FollowButton', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.post.mockResolvedValue({ data: person({ is_following: true }) })
    api.delete.mockResolvedValue({ data: person() })
  })

  it('says Follow, Follow back or Following depending on the relationship', () => {
    const cases: [Partial<Relationship>, string][] = [[{}, 'Follow'], [{ follows_you: true }, 'Follow back'], [{ is_following: true }, 'Following']]
    for (const [state, text] of cases) {
      const { unmount } = renderWithProviders(<FollowButton person={person(state)} />)
      expect(screen.getByRole('button')).toHaveTextContent(new RegExp(`^${text}$`))
      expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', String(Boolean(state.is_following)))
      unmount()
    }
  })

  it('follows with POST and unfollows with DELETE after confirmation', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const first = renderWithProviders(<FollowButton person={person()} />)
    await user.click(screen.getByRole('button', { name: 'Follow Neema K' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/people/neema/follow/'))
    first.unmount()

    renderWithProviders(<FollowButton person={person({ is_following: true })} />)
    await user.click(screen.getByRole('button', { name: 'Unfollow Neema K' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/people/neema/follow/'))
  })

  it('renders nothing on your own profile', () => {
    renderWithProviders(<FollowButton person={person({ is_self: true })} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('RelationshipChips', () => {
  it('explains how you are connected', () => {
    renderWithProviders(<RelationshipChips person={person({ is_mutual: true, is_following: true, follows_you: true, in_contacts: true, label: 'family', mutual_followers_count: 3, mutual_followers_preview: ['juma', 'asha'] })} />)
    for (const text of ['Family', 'Mutual', 'In your contacts', 'Followed by juma, asha +1']) expect(screen.getByText(text)).toBeInTheDocument()
  })

  it('shows "Follows you" when only they follow you', () => {
    renderWithProviders(<RelationshipChips person={person({ follows_you: true })} />)
    expect(screen.getByText('Follows you')).toBeInTheDocument()
  })
})

it('formats large counts compactly', () => {
  expect([formatCount(999), formatCount(1200), formatCount(15000), formatCount(2_000_000)]).toEqual(['999', '1.2K', '15K', '2M'])
})
