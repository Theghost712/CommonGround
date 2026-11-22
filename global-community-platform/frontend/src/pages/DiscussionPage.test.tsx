import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Comment, Discussion } from '../types'
import DiscussionPage from './DiscussionPage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))
const authState = vi.hoisted(() => ({ user: { id: 1, username: 'author' } as { id: number; username: string } | null }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: authState.user }) }))

const discussion: Discussion = {
  id: 7, community: null, community_name: null, author: 1, author_username: 'author',
  title: 'Water access in Arusha', body: 'Let us talk.', content_html: '', category: 'Health',
  comments_count: 2, reactions_count: 0, bookmarks_count: 0, has_reacted: false, my_reaction: null,
  has_bookmarked: false, attachments: [], created_at: '2026-11-20T10:00:00Z', updated_at: '2026-11-20T10:00:00Z',
}
const comment = (overrides: Partial<Comment>): Comment => ({
  id: 10, discussion: 7, author: 1, author_username: 'author', parent: null, body: 'My comment',
  replies_count: 0, replies: [], created_at: '2026-11-20T11:00:00Z', updated_at: '2026-11-20T11:00:00Z', ...overrides,
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/discussions/7']}><Routes>
    <Route path="/discussions/:id" element={<DiscussionPage />} />
    <Route path="/home" element={<h1>Home feed</h1>} />
  </Routes></MemoryRouter></QueryClientProvider>)
}

describe('DiscussionPage owner controls', () => {
  beforeEach(() => {
    authState.user = { id: 1, username: 'author' }
    Object.values(api).forEach((fn) => fn.mockReset())
    api.get.mockImplementation(async (url: string) => {
      if (url === '/discussions/7/') return { data: discussion }
      if (url === '/discussions/7/comments/') return { data: [comment({}), comment({ id: 11, author: 2, author_username: 'guest', body: 'Guest comment' })] }
      throw new Error(`unexpected GET ${url}`)
    })
    api.patch.mockResolvedValue({ data: {} })
    api.delete.mockResolvedValue({ data: {} })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('shows edit and delete to the author, and only on their own comments', async () => {
    renderPage()
    await screen.findByText('Guest comment')

    expect(screen.getByRole('link', { name: /edit/i })).toHaveAttribute('href', '/discussions/7/edit')
    expect(within(document.querySelector('.owner-actions') as HTMLElement).getByRole('button', { name: /delete/i })).toBeInTheDocument()
    const own = screen.getByText('My comment').closest('.comment-content') as HTMLElement
    const guest = screen.getByText('Guest comment').closest('.comment-content') as HTMLElement
    expect(within(own).getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(within(guest).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(within(guest).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('hides discussion controls from other users', async () => {
    authState.user = { id: 2, username: 'guest' }
    renderPage()
    await screen.findByText('My comment')

    expect(screen.queryByRole('link', { name: /edit/i })).not.toBeInTheDocument()
    const guest = screen.getByText('Guest comment').closest('.comment-content') as HTMLElement
    expect(within(guest).getByRole('button', { name: 'Edit' })).toBeInTheDocument()
  })

  it('edits a comment in place', async () => {
    const user = userEvent.setup()
    renderPage()
    const own = (await screen.findByText('My comment')).closest('.comment-content') as HTMLElement

    await user.click(within(own).getByRole('button', { name: 'Edit' }))
    const box = within(own).getByRole('textbox', { name: 'Edit comment' })
    await user.clear(box)
    await user.type(box, 'Better wording')
    await user.click(within(own).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/comments/10/', { body: 'Better wording' }))
  })

  it('deletes the discussion after confirmation and returns home', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Water access in Arusha')

    const ownerBar = document.querySelector('.owner-actions') as HTMLElement
    await user.click(within(ownerBar).getByRole('button', { name: /delete/i }))

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/discussions/7/'))
    expect(await screen.findByRole('heading', { name: 'Home feed' })).toBeInTheDocument()
  })

  it('does nothing when deletion is cancelled', async () => {
    vi.mocked(window.confirm).mockReturnValue(false)
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Water access in Arusha')

    await user.click(within(document.querySelector('.owner-actions') as HTMLElement).getByRole('button', { name: /delete/i }))

    expect(api.delete).not.toHaveBeenCalled()
  })
})
