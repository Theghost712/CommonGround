import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Discussion, Poll } from '../types'
import PollCard, { timeLeft } from './PollCard'
import PostGrid from './PostGrid'
import VideoPlayer, { formatDuration } from './VideoPlayer'
import { PollComposer } from './MediaComposers'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: (e: { message?: string }) => e?.message ?? 'Request failed' }))

const poll = (extra: Partial<Poll> = {}): Poll => ({
  id: 1, question: 'Best time to meet?', allows_multiple: false, closes_at: new Date(Date.now() + 5 * 3_600_000).toISOString(),
  is_closed: false, total_voters: 0, my_votes: [], results_visible: false,
  options: [{ id: 10, text: 'Morning', votes: null, percent: null }, { id: 11, text: 'Evening', votes: null, percent: null }],
  ...extra,
})
const voted: Poll = poll({ total_voters: 3, my_votes: [11], results_visible: true, options: [{ id: 10, text: 'Morning', votes: 1, percent: 33 }, { id: 11, text: 'Evening', votes: 2, percent: 67 }] })

beforeEach(() => { api.get.mockReset(); api.post.mockReset(); api.delete.mockReset() })

describe('PollCard', () => {
  it('hides numbers until you vote, then shows results and lets you undo', async () => {
    api.post.mockResolvedValue({ data: voted })
    api.delete.mockResolvedValue({ data: poll({ total_voters: 2 }) })
    const user = userEvent.setup()
    renderWithProviders(<PollCard postId={7} poll={poll()} />)
    expect(screen.queryByText('%', { exact: false })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Evening' }))
    expect(api.post).toHaveBeenCalledWith('/discussions/7/vote/', { option_ids: [11] })
    expect(await screen.findByText('67%')).toBeInTheDocument()
    expect(screen.getByLabelText('Your vote')).toBeInTheDocument()
    expect(screen.getByText('3 votes')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Undo vote' }))
    expect(api.delete).toHaveBeenCalledWith('/discussions/7/vote/')
    expect(await screen.findByRole('button', { name: 'Morning' })).toBeInTheDocument()
  })

  it('collects several answers before voting on a multi-choice poll', async () => {
    api.post.mockResolvedValue({ data: voted })
    const user = userEvent.setup()
    renderWithProviders(<PollCard postId={7} poll={poll({ allows_multiple: true })} />)
    expect(screen.getByText('Choose one or more')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Morning' }))
    await user.click(screen.getByRole('button', { name: 'Evening' }))
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Vote' }))
    expect(api.post).toHaveBeenCalledWith('/discussions/7/vote/', { option_ids: [10, 11] })
  })

  it('formats the time left', () => {
    const now = Date.parse('2026-11-22T10:00:00Z')
    expect(timeLeft('2026-11-22T10:20:00Z', now)).toBe('20 minutes left')
    expect(timeLeft('2026-11-22T13:00:00Z', now)).toBe('3 hours left')
    expect(timeLeft('2026-11-25T10:00:00Z', now)).toBe('3 days left')
    expect(timeLeft('2026-11-22T09:00:00Z', now)).toBe('Final results')
  })
})

describe('VideoPlayer', () => {
  it('renders a lazy, muted, inline video with its poster and length', () => {
    const { container } = renderWithProviders(<VideoPlayer file={{ id: 3, original_name: 'clip.mp4', content_type: 'video/mp4', size: 1, url: '', is_image: false, is_video: true, created_at: '', video_url: '/api/v1/videos/3/?t=x', display_url: '/api/v1/images/3/?t=y', duration_ms: 75_000, width: 720, height: 1280 }} />)
    const video = container.querySelector('video')!
    expect(video).toHaveAttribute('src', '/api/v1/videos/3/?t=x')
    expect(video).toHaveAttribute('poster', '/api/v1/images/3/?t=y')
    expect(video).toHaveAttribute('preload', 'none')
    expect(video.muted).toBe(true)
    expect(screen.getByText('1:15')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Turn sound on' })).toBeInTheDocument()
    expect(formatDuration(5_000)).toBe('0:05')
  })
})

describe('PostGrid', () => {
  it('marks video and poll tiles', () => {
    const base = { community: null, community_name: null, author: 1, author_username: 'asha', title: '', body: '', content_html: '', category: 'General', comments_count: 0, reactions_count: 0, bookmarks_count: 0, has_reacted: false, my_reaction: null, has_bookmarked: false, created_at: '', updated_at: '' }
    const posts: Discussion[] = [
      { ...base, id: 1, attachments: [{ id: 5, original_name: 'v.mp4', content_type: 'video/mp4', size: 1, url: '', is_image: false, is_video: true, created_at: '', thumb_url: '/thumb', video_url: '/v' }] },
      { ...base, id: 2, attachments: [], poll: poll() },
    ]
    renderWithProviders(<PostGrid posts={posts} />)
    expect(screen.getByLabelText('Video')).toBeInTheDocument()
    expect(screen.getByLabelText('Poll')).toBeInTheDocument()
    expect(screen.getByText('Best time to meet?')).toBeInTheDocument()
  })
})

describe('PollComposer', () => {
  it('validates, then posts the poll', async () => {
    api.get.mockResolvedValue({ data: [] })
    api.post.mockResolvedValue({ data: { id: 42 } })
    const user = userEvent.setup()
    renderWithProviders(<PollComposer onClose={() => {}} />)
    const dialog = screen.getByRole('dialog', { name: 'New poll' })
    await user.type(within(dialog).getByLabelText('Question'), 'Where next?')
    await user.type(within(dialog).getByLabelText('Option 1'), 'Arusha')
    await user.click(within(dialog).getByRole('button', { name: /post poll/i }))
    expect(within(dialog).getByText('Add at least two options.')).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Option 2'), 'Zanzibar')
    await user.click(within(dialog).getByRole('button', { name: /add option/i }))
    await user.type(within(dialog).getByLabelText('Option 3'), 'Mwanza')
    await user.selectOptions(within(dialog).getByLabelText('Poll length'), '72')
    await user.click(within(dialog).getByRole('button', { name: /post poll/i }))
    expect(api.post).toHaveBeenCalledWith('/posts/poll/', expect.objectContaining({
      question: 'Where next?', options: ['Arusha', 'Zanzibar', 'Mwanza'], allows_multiple: false, duration_hours: 72,
    }))
  })
})
