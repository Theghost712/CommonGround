import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Person } from '../types'
import PeoplePage from './PeoplePage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'Mr.Paulo' } }) }))

const person = (id: number, username: string, extra: Partial<Person> = {}): Person => ({
  id, username, first_name: username, last_name: '', display_name: username, avatar_url: '', bio: '', country: '',
  followers_count: 0, following_count: 0, reason: null,
  relationship: { is_self: false, is_following: false, follows_you: false, is_mutual: false, in_contacts: false, mutual_followers_count: 0, mutual_followers_preview: [], label: null },
  ...extra,
})
const page = (results: Person[], next: string | null = null) => ({ data: { count: results.length + (next ? 20 : 0), next, previous: null, results } })

describe('PeoplePage', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.get.mockImplementation(async (url: string, config?: { params?: { sort?: string; page?: number } }) => {
      if (url === '/people/suggestions/') return { data: [person(3, 'asha', { reason: 'Follows you' })] }
      if (url === '/auth/profile/') return { data: { phone_number: '', discoverable_by_contacts: false } }
      if (url === '/people/') return page([person(4, 'juma')])
      if (url === '/people/discover/') {
        if (config?.params?.sort === 'new') return page([person(9, 'brand_new')])
        return config?.params?.page === 2 ? page([person(8, 'second_page')]) : page([person(7, 'popular_pat')], 'next')
      }
      throw new Error(url)
    })
    api.post.mockImplementation(async (_url: string, body: { contacts: { key: string }[] }) => ({
      data: {
        checked: 2,
        matches: [person(5, 'mama_neema', { relationship: { ...person(0, 'x').relationship!, in_contacts: true } })],
        contacts: body.contacts.map((c, i) => ({ key: c.key, user_id: i === 0 ? 5 : null })),
      },
    }))
  })

  it('shows suggestions with their reason and nudges the user to become findable', async () => {
    renderWithProviders(<PeoplePage />)
    expect(await screen.findByText('Follows you')).toBeInTheDocument()
    expect(await screen.findByText('Let friends find you too')).toBeInTheDocument()
  })

  it('searches people by name', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PeoplePage />)
    await user.type(screen.getByRole('textbox', { name: 'Search people' }), 'ju')
    expect(await screen.findByText('@juma')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/people/', { params: { search: 'ju' } })
  })

  it('matches contacts one by one: members to follow, everyone else to invite', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PeoplePage />)
    await user.click(screen.getByRole('button', { name: /type numbers/i }))
    await user.type(screen.getByRole('textbox', { name: 'Phone numbers or emails' }), '0712 345 678, friend@example.com')
    await user.click(screen.getByRole('button', { name: 'Find' }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/people/contacts/match/', {
      contacts: [expect.objectContaining({ phones: ['0712 345 678'], emails: [] }), expect.objectContaining({ phones: [], emails: ['friend@example.com'] })],
    }))
    expect(await screen.findByText('1 of your contacts is on CommonGround')).toBeInTheDocument()
    expect(screen.getByText('In your contacts')).toBeInTheDocument()
    const invites = screen.getByText('Invite this contact').nextElementSibling as HTMLElement
    await user.click(within(invites).getByRole('button', { name: 'Invite friend@example.com' }))
    const mail = within(invites).getByRole('link', { name: 'Invite friend@example.com by email' })
    expect(mail.getAttribute('href')).toMatch(/^mailto:friend@example\.com\?subject=Join%20me%20on%20CommonGround&body=.*register%3Finvite%3DMr.Paulo/)
  })

  it('shares a personal invite link', () => {
    renderWithProviders(<PeoplePage />)
    const card = screen.getByRole('region', { name: 'Invite friends' })
    expect(within(card).getByText(/\/register\?invite=Mr\.Paulo$/)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: /whatsapp/i }).getAttribute('href')).toMatch(/^https:\/\/wa\.me\/\?text=.*register%3Finvite%3DMr.Paulo/)
  })

  it('lists everyone, popular or newest first, with more on demand', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PeoplePage />)
    const discover = screen.getByRole('region', { name: 'Discover people' })
    expect(await within(discover).findByText('@popular_pat')).toBeInTheDocument()
    await user.click(within(discover).getByRole('button', { name: 'Show more people' }))
    expect(await within(discover).findByText('@second_page')).toBeInTheDocument()
    await user.click(within(discover).getByRole('tab', { name: 'New members' }))
    expect(await within(discover).findByText('@brand_new')).toBeInTheDocument()
  })
})
