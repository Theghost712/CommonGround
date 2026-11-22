import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Person, Relationship } from '../types'
import { FollowButton } from './PersonBits'
import ReportDialog from './ReportDialog'
import RichText, { linkifyHtml } from './RichText'
import SafetyMenu from './SafetyMenu'
import UserProfilePage from '../pages/UserProfilePage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'me' } }) }))

const relation = (extra: Partial<Relationship> = {}): Relationship => ({ is_self: false, is_following: false, follows_you: false, is_mutual: false, in_contacts: false, mutual_followers_count: 0, mutual_followers_preview: [], label: null, requested: false, is_private: false, can_view: true, blocked: false, muted_posts: false, muted_stories: false, ...extra })
const person = (extra: Partial<Relationship> = {}): Person => ({ id: 7, username: 'zuri', first_name: 'Zuri', last_name: '', display_name: 'Zuri', avatar_url: '', bio: '', country: '', followers_count: 1, following_count: 2, relationship: relation(extra), reason: null })

beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset()); Object.values(api).forEach((fn) => fn.mockResolvedValue({ data: {} })) })

describe('RichText', () => {
  it('links hashtags, mentions and URLs safely, and ignores look-alikes', () => {
    renderWithProviders(<RichText text={"Siku njema #Arusha with @asha_j. See https://example.org/water! #2026 a#b &#39;"} />)
    expect(screen.getByRole('link', { name: '#Arusha' })).toHaveAttribute('href', '/tags/arusha')
    expect(screen.getByRole('link', { name: '@asha_j' })).toHaveAttribute('href', '/u/asha_j')
    const external = screen.getByRole('link', { name: 'example.org/water' })
    expect(external).toHaveAttribute('href', 'https://example.org/water')
    expect(external).toHaveAttribute('target', '_blank')
    expect(external.getAttribute('rel')).toContain('noopener')
    expect(screen.queryByRole('link', { name: '#2026' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(3)
  })
})

describe('linkifyHtml', () => {
  it('links tags and mentions in rich text but not inside existing links or code', () => {
    const out = linkifyHtml('<p>Maji <strong>#Safi</strong> by @asha</p><p><a href="https://x.org">#nope</a> <code>#nocode</code></p>')
    const doc = new DOMParser().parseFromString(out, 'text/html')
    const internal = [...doc.querySelectorAll('a[data-internal]')].map((a) => [a.getAttribute('href'), a.textContent])
    expect(internal).toEqual([['/tags/safi', '#Safi'], ['/u/asha', '@asha']])
    expect(doc.querySelector('code')?.textContent).toBe('#nocode')
  })
})

describe('ReportDialog', () => {
  it('needs a reason, sends the report and confirms anonymously', async () => {
    api.post.mockResolvedValue({ data: { already_reported: false } })
    const user = userEvent.setup()
    renderWithProviders(<ReportDialog targetType="post" targetId={12} onClose={vi.fn()} />)
    const submit = screen.getByRole('button', { name: 'Submit report' })
    expect(submit).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: 'Scam or fraud' }))
    await user.type(screen.getByRole('textbox', { name: 'Details' }), 'Fake giveaway')
    await user.click(submit)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/safety/reports/', { target_type: 'post', target_id: 12, reason: 'scam', details: 'Fake giveaway' }))
    expect(await screen.findByText(/report is anonymous/i)).toBeInTheDocument()
  })
})

describe('FollowButton with private accounts', () => {
  it('shows Requested and cancels the request', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FollowButton person={person({ requested: true, is_private: true, can_view: false })} />)
    const button = screen.getByRole('button', { name: 'Cancel follow request to Zuri' })
    expect(button).toHaveTextContent('Requested')
    await user.click(button)
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/people/zuri/follow/'))
  })

  it('hides itself for blocked accounts', () => {
    renderWithProviders(<FollowButton person={person({ blocked: true })} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('SafetyMenu', () => {
  it('blocks after confirmation, mutes, and opens the report dialog', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderWithProviders(<SafetyMenu person={person()} />)
    await user.click(screen.getByRole('button', { name: 'More options' }))
    await user.click(screen.getByRole('menuitem', { name: 'Block' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/safety/blocks/zuri/'))
    expect(await screen.findByText('zuri is blocked.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'More options' }))
    await user.click(screen.getByRole('menuitemcheckbox', { name: 'Mute story' }))
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/safety/mutes/zuri/', { posts: false, stories: true }))

    await user.click(screen.getByRole('button', { name: 'More options' }))
    await user.click(screen.getByRole('menuitem', { name: 'Report account' }))
    expect(screen.getByRole('dialog', { name: 'Report account' })).toBeInTheDocument()
  })
})

describe('UserProfilePage privacy states', () => {
  const profile = (extra: Partial<Relationship>) => ({ ...person(extra), website: '', interests: [], date_joined: '2026-01-01T00:00:00Z', discussions_count: 4 })
  const renderProfile = () => renderWithProviders(<Routes><Route path="/u/:username" element={<UserProfilePage />} /></Routes>, { route: '/u/zuri' })

  it('locks a private account you do not follow', async () => {
    api.get.mockImplementation(async (url: string) => url === '/people/zuri/' ? { data: profile({ is_private: true, can_view: false }) } : { data: [] })
    renderProfile()
    expect(await screen.findByRole('heading', { name: 'This account is private' })).toBeInTheDocument()
    expect(api.get).not.toHaveBeenCalledWith('/discussions/', expect.anything())
  })

  it('shows the blocked state with Unblock', async () => {
    api.get.mockImplementation(async (url: string) => url === '/people/zuri/' ? { data: profile({ blocked: true }) } : { data: [] })
    const user = userEvent.setup()
    renderProfile()
    const panel = (await screen.findByRole('heading', { name: 'You blocked this account' })).closest('section') as HTMLElement
    expect(screen.queryByRole('button', { name: /message/i })).not.toBeInTheDocument()
    await user.click(within(panel).getByRole('button', { name: 'Unblock' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/safety/blocks/zuri/'))
  })
})
