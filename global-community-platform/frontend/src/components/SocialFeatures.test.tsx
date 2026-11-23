import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Discussion } from '../types'
import FeedPost from './FeedPost'
import { MessageBody } from './ChatMedia'
import SearchPage from '../pages/SearchPage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: (e: { message?: string }) => e?.message ?? 'Something failed', API_BASE: '/api/v1', getAccessToken: () => null }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'me' } }) }))

const post = (overrides: Partial<Discussion> = {}): Discussion => ({
  id: 7, community: null, community_name: null, author: 2, author_username: 'asha', author_display_name: 'Asha', author_avatar_url: '',
  title: '', body: 'Original thought', content_html: '', category: 'General', comments_count: 0, reactions_count: 0,
  bookmarks_count: 0, has_reacted: false, my_reaction: null, has_bookmarked: false, attachments: [],
  created_at: new Date().toISOString(), updated_at: '', ...overrides,
})

describe('reposts, sponsored posts and sharing', () => {
  beforeEach(() => { api.get.mockReset(); api.post.mockReset(); api.post.mockResolvedValue({ data: {} }) })

  it('shows a plain repost as "X reposted" with the original', () => {
    renderWithProviders(<FeedPost discussion={post({ id: 9, author: 3, author_username: 'juma', body: '', repost_of: post() })} />)
    expect(screen.getByText('reposted')).toBeInTheDocument()
    expect(screen.getAllByText('Original thought').length).toBeGreaterThan(0)
  })

  it('labels sponsored posts and counts "Learn more" clicks', async () => {
    api.post.mockResolvedValue({ data: { url: '/discussions/7' } })
    const assign = vi.fn()
    Object.defineProperty(window, 'location', { value: { ...window.location, assign, origin: 'http://localhost' }, writable: true })
    renderWithProviders(<FeedPost discussion={post({ sponsored: { name: 'Shop Ltd', has_link: true } })} />)
    expect(screen.getByText('Sponsored · Shop Ltd')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Learn more' }))
    expect(api.post).toHaveBeenCalledWith('/discussions/7/sponsored-click/')
  })

  it('reposts and sends to a chat from the share sheet', async () => {
    api.get.mockResolvedValue({ data: [{ id: 4, display_title: 'Neema', conversation_type: 'direct', other_user: { username: 'neema' } }] })
    const user = userEvent.setup()
    renderWithProviders(<FeedPost discussion={post()} />)
    await user.click(screen.getByRole('button', { name: 'Share' }))
    await user.click(screen.getByRole('button', { name: /Send in a chat/ }))
    await user.click(await screen.findByRole('button', { name: 'Send' }))
    expect(api.post).toHaveBeenCalledWith('/conversations/4/share-post/', { post_id: 7 })
    expect(await screen.findByRole('button', { name: 'Sent' })).toBeDisabled()
  })
})

describe('chat message kinds', () => {
  beforeEach(() => { api.post.mockReset() })
  const base = { id: 5, sender: 2, body: '', kind: 'photo' as const }

  it('view-once: recipients tap to view once; senders see the status', async () => {
    api.post.mockResolvedValue({ data: { url: '/api/v1/chat-media/5/?t=x' } })
    const user = userEvent.setup()
    const { unmount } = renderWithProviders(<MessageBody message={{ ...base, view_once: true, opened_by: [] }} own={false} conversationId={3} currentUserId={1} />)
    await user.click(screen.getByRole('button', { name: /Tap to view photo/ }))
    expect(api.post).toHaveBeenCalledWith('/conversations/3/messages/5/open/')
    expect(await screen.findByRole('dialog', { name: 'View-once media' })).toBeInTheDocument()
    unmount()
    renderWithProviders(<MessageBody message={{ ...base, view_once: true, opened_by: [1] }} own={false} conversationId={3} currentUserId={1} />)
    expect(screen.getByText(/Opened/)).toBeInTheDocument()
  })

  it('renders voice messages, shared posts and photos', () => {
    renderWithProviders(<>
      <MessageBody message={{ ...base, kind: 'voice', media_url: '/v.m4a', duration_ms: 65000 }} own={false} conversationId={3} />
      <MessageBody message={{ ...base, id: 6, kind: 'post', shared_post: { id: 7, author: 'asha', title: '', text: 'Sunset', thumb_url: '', is_video: false } }} own conversationId={3} />
      <MessageBody message={{ ...base, id: 8, media_url: '/p.webp', thumb_url: '/t.webp', body: 'Look' }} own conversationId={3} />
    </>)
    expect(screen.getByRole('button', { name: 'Play voice message' })).toBeInTheDocument()
    expect(screen.getByText('1:05')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Sunset/ })).toHaveAttribute('href', '/discussions/7')
    expect(screen.getByRole('button', { name: 'Open photo' })).toBeInTheDocument()
    expect(screen.getByText('Look')).toBeInTheDocument()
  })
})

describe('SearchPage', () => {
  it('searches people, tags, communities and posts', async () => {
    api.get.mockResolvedValue({ data: { q: 'bao', people: [{ id: 2, username: 'baobab', display_name: 'Bao', avatar_url: '', relationship: null }], posts: [], tags: [{ name: 'baobab', count: 3 }], communities: [{ id: 1, name: 'Tree lovers', members: 4, category: 'Environment', description: '' }] } })
    renderWithProviders(<SearchPage />)
    await userEvent.setup().type(screen.getByRole('searchbox', { name: 'Search' }), 'bao')
    expect(await screen.findByText('#baobab')).toBeInTheDocument()
    expect(screen.getByText('Tree lovers')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/search/', { params: { q: 'bao' } })
  })
})
