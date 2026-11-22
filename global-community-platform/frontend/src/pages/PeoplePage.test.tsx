import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Person } from '../types'
import PeoplePage from './PeoplePage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))

const person = (id: number, username: string, extra: Partial<Person> = {}): Person => ({
  id, username, first_name: username, last_name: '', display_name: username, avatar_url: '', bio: '', country: '',
  followers_count: 0, following_count: 0, reason: null,
  relationship: { is_self: false, is_following: false, follows_you: false, is_mutual: false, in_contacts: false, mutual_followers_count: 0, mutual_followers_preview: [], label: null },
  ...extra,
})

describe('PeoplePage', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.get.mockImplementation(async (url: string) => {
      if (url === '/people/suggestions/') return { data: [person(3, 'asha', { reason: 'Follows you' })] }
      if (url === '/auth/profile/') return { data: { phone_number: '', discoverable_by_contacts: false } }
      if (url === '/people/') return { data: { count: 1, next: null, previous: null, results: [person(4, 'juma')] } }
      throw new Error(url)
    })
    api.post.mockResolvedValue({ data: { checked: 2, matches: [person(5, 'mama_neema', { relationship: { ...person(0, 'x').relationship!, in_contacts: true } })] } })
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

  it('matches typed contacts and lists the members found', async () => {
    const user = userEvent.setup()
    renderWithProviders(<PeoplePage />)
    await user.click(screen.getByRole('button', { name: /type numbers/i }))
    await user.type(screen.getByRole('textbox', { name: 'Phone numbers or emails' }), '0712 345 678, mama@example.com')
    await user.click(screen.getByRole('button', { name: 'Find' }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/people/contacts/match/', { phones: ['0712 345 678'], emails: ['mama@example.com'] }))
    expect(await screen.findByText('1 of your contacts is on CommonGround')).toBeInTheDocument()
    expect(screen.getByText('In your contacts')).toBeInTheDocument()
  })
})
