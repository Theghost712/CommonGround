import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Discussion } from '../types'
import FeedPost, { clampRatio, timeAgo } from './FeedPost'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Something failed' }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'me' } }) }))

const post = (overrides: Partial<Discussion> = {}): Discussion => ({
  id: 7, community: null, community_name: null, author: 2, author_username: 'asha', author_display_name: 'Asha J', author_avatar_url: '',
  title: 'Clean water for Olmoti', body: 'Short body', content_html: '', category: 'Health', comments_count: 3, reactions_count: 5,
  bookmarks_count: 0, has_reacted: false, my_reaction: null, has_bookmarked: false, attachments: [],
  created_at: new Date(Date.now() - 2 * 3600e3).toISOString(), updated_at: '', ...overrides,
})

describe('FeedPost', () => {
  beforeEach(() => {
    api.get.mockReset(); api.post.mockReset()
    api.post.mockImplementation(async (url: string) => url.endsWith('/react/') ? { data: { reactions_count: 6 } } : { data: {} })
  })

  it('shows the Instagram-style header, caption and comment link', () => {
    renderWithProviders(<FeedPost discussion={post()} />)
    expect(screen.getAllByText('asha').length).toBeGreaterThan(0)
    expect(screen.getByText('2h')).toBeInTheDocument()
    expect(screen.getByText('5 reactions')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View all 3 comments' })).toHaveAttribute('href', '/discussions/7')
    expect(screen.getByRole('heading', { name: 'Clean water for Olmoti' })).toBeInTheDocument()
  })

  it('likes instantly and keeps the server count', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FeedPost discussion={post()} />)
    await user.click(screen.getByRole('button', { name: 'Like' }))
    expect(screen.getByRole('button', { name: 'Unlike' })).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/discussions/7/react/', { reaction_type: 'like' }))
    expect(screen.getByText('6 reactions')).toBeInTheDocument()
  })

  it('rolls the like back if the server refuses', async () => {
    api.post.mockRejectedValueOnce(new Error('nope'))
    const user = userEvent.setup()
    renderWithProviders(<FeedPost discussion={post()} />)
    await user.click(screen.getByRole('button', { name: 'Like' }))
    expect(await screen.findByText('Something failed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Like' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('5 reactions')).toBeInTheDocument()
  })

  it('double-tap likes but never unlikes', async () => {
    const { container } = renderWithProviders(<FeedPost discussion={post({ my_reaction: 'like', reactions_count: 5 })} />)
    fireEvent.doubleClick(container.querySelector('.feed-text-post')!)
    expect(container.querySelector('.feed-heart-burst')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Unlike' })).toBeInTheDocument()
  })

  it('double-tap on an unliked post likes it', async () => {
    const { container } = renderWithProviders(<FeedPost discussion={post()} />)
    fireEvent.doubleClick(container.querySelector('.feed-text-post')!)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/discussions/7/react/', { reaction_type: 'like' }))
  })

  it('switching from another reaction to a like keeps the count', async () => {
    const user = userEvent.setup()
    api.post.mockImplementation(() => new Promise(() => {}))
    renderWithProviders(<FeedPost discussion={post({ my_reaction: 'insightful', reactions_count: 5 })} />)
    await user.click(screen.getByRole('button', { name: 'Like' }))
    expect(screen.getByText('5 reactions')).toBeInTheDocument()
  })

  it('expands long captions with "more"', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FeedPost discussion={post({ body: 'x'.repeat(300) })} />)
    await user.click(screen.getByRole('button', { name: 'more' }))
    expect(screen.queryByRole('button', { name: 'more' })).not.toBeInTheDocument()
  })

  it('posts a quick comment and bumps the count', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FeedPost discussion={post()} />)
    await user.type(screen.getByRole('textbox', { name: /comment on/i }), 'Great idea')
    await user.click(screen.getByRole('button', { name: 'Post' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/discussions/7/comments/', { body: 'Great idea', parent: null }))
    expect(await screen.findByRole('link', { name: 'View all 4 comments' })).toBeInTheDocument()
  })

  it('saves with the bookmark button', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FeedPost discussion={post()} />)
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/discussions/7/bookmark/'))
    expect(screen.getByRole('button', { name: 'Remove from saved' })).toBeInTheDocument()
  })
})

describe('timeAgo', () => {
  const now = new Date('2026-11-22T12:00:00Z').getTime()
  it('uses short Instagram-style units', () => {
    expect(timeAgo('2026-11-22T11:59:40Z', now)).toBe('now')
    expect(timeAgo('2026-11-22T11:45:00Z', now)).toBe('15m')
    expect(timeAgo('2026-11-22T09:00:00Z', now)).toBe('3h')
    expect(timeAgo('2026-11-19T12:00:00Z', now)).toBe('3d')
    expect(timeAgo('2026-10-01T12:00:00Z', now)).toMatch(/Oct/)
  })
})

describe('clampRatio', () => {
  it('keeps the photo shape within Instagram limits', () => {
    expect(clampRatio(1080, 1080)).toBe(1)
    expect(clampRatio(1080, 1350)).toBe(0.8)
    expect(clampRatio(1000, 3000)).toBe(0.8)
    expect(clampRatio(1910, 1000)).toBe(1.91)
    expect(clampRatio(4000, 1000)).toBe(1.91)
    expect(clampRatio(0, 0)).toBe(1)
  })
})
