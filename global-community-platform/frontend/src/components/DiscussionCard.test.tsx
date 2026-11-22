import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Discussion } from '../types'
import DiscussionCard from './DiscussionCard'

const post = vi.hoisted(() => vi.fn())
vi.mock('../services/api', () => ({ api: { post } }))

function makeDiscussion(overrides: Partial<Discussion> = {}): Discussion {
  return {
    id: 7,
    community: null,
    community_name: null,
    author: 1,
    author_username: 'amani',
    title: 'How do we grow local tech hubs?',
    body: 'Short body',
    content_html: '',
    category: 'Technology',
    comments_count: 3,
    reactions_count: 5,
    bookmarks_count: 1,
    has_reacted: false,
    my_reaction: null,
    has_bookmarked: false,
    attachments: [],
    created_at: '2026-11-20T10:00:00Z',
    updated_at: '2026-11-20T10:00:00Z',
    ...overrides,
  }
}

describe('DiscussionCard', () => {
  beforeEach(() => {
    post.mockReset()
    post.mockResolvedValue({ data: {} })
  })

  it('shows the title, author, category and counts', () => {
    renderWithProviders(<DiscussionCard discussion={makeDiscussion()} />)

    expect(screen.getByRole('heading', { name: 'How do we grow local tech hubs?' })).toBeInTheDocument()
    expect(screen.getByText('amani')).toBeInTheDocument()
    expect(screen.getByText('Technology')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Like discussion' })).toHaveTextContent('5')
    expect(screen.getByRole('link', { name: /join conversation/i })).toHaveAttribute('href', '/discussions/7')
  })

  it('truncates long bodies to 240 characters', () => {
    const body = 'a'.repeat(300)
    renderWithProviders(<DiscussionCard discussion={makeDiscussion({ body })} />)

    expect(screen.getByText(`${'a'.repeat(240)}…`)).toBeInTheDocument()
  })

  it('shows the community and attachment hint when present', () => {
    renderWithProviders(<DiscussionCard discussion={makeDiscussion({
      community: 2,
      community_name: 'Dar Builders',
      attachments: [
        { id: 1, original_name: 'a.png', content_type: 'image/png', size: 10, url: '', is_image: true, created_at: '' },
        { id: 2, original_name: 'b.pdf', content_type: 'application/pdf', size: 10, url: '', is_image: false, created_at: '' },
      ],
    })} />)

    expect(screen.getByText('Dar Builders')).toBeInTheDocument()
    expect(screen.getByText('Image attached · 2 attachments')).toBeInTheDocument()
  })

  it('likes the discussion and refreshes cached feeds', async () => {
    const user = userEvent.setup()
    const { queryClient } = renderWithProviders(<DiscussionCard discussion={makeDiscussion()} />)
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    await user.click(screen.getByRole('button', { name: 'Like discussion' }))

    expect(post).toHaveBeenCalledWith('/discussions/7/react/', { reaction_type: 'like' })
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['discussions'] }))
  })

  it('toggles a bookmark with an accessible label that reflects state', async () => {
    const user = userEvent.setup()
    renderWithProviders(<DiscussionCard discussion={makeDiscussion({ has_bookmarked: true })} />)

    await user.click(screen.getByRole('button', { name: 'Remove bookmark' }))

    expect(post).toHaveBeenCalledWith('/discussions/7/bookmark/')
  })
})
