import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Person, Story, StoryTrayEntry } from '../types'
import StoryComposer from './StoryComposer'
import StoryViewer from './StoryViewer'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))

const person = (id: number, username: string): Person => ({ id, username, first_name: username, last_name: '', display_name: username, avatar_url: '', bio: '', country: '', followers_count: 0, following_count: 0, relationship: null, reason: null })
const story = (id: number, extra: Partial<Story> = {}): Story => ({ id, media_type: 'text', media_url: '', thumbnail_url: '', text: `Story number ${id}`, background: 'violet', alt_text: '', duration_ms: 5000, audience: 'followers', created_at: new Date().toISOString(), expires_at: '', seen: false, view_count: null, is_own: false, ...extra })
const entry = (id: number, username: string, stories: Story[]): StoryTrayEntry => ({ user: person(id, username), stories, all_seen: false, latest_at: '' })

function tap(side: 'left' | 'right') {
  const stage = document.querySelector('.story-stage') as HTMLElement
  stage.getBoundingClientRect = () => ({ left: 0, width: 300, top: 0, height: 500, right: 300, bottom: 500, x: 0, y: 0, toJSON: () => ({}) })
  // jsdom's PointerEvent drops clientX, so send mouse events under the pointer event names.
  const clientX = side === 'left' ? 20 : 250
  act(() => {
    stage.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, clientX }))
    stage.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientX }))
  })
}

describe('StoryViewer', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.post.mockResolvedValue({ data: {} })
    api.delete.mockResolvedValue({ data: {} })
  })

  it('taps through stories and on to the next person, marking each as seen', async () => {
    const onClose = vi.fn()
    renderWithProviders(<StoryViewer entries={[entry(1, 'asha', [story(1), story(2)]), entry(2, 'juma', [story(3)])]} onClose={onClose} />)
    expect(screen.getByText('Story number 1')).toBeInTheDocument()

    tap('right')
    expect(screen.getByText('Story number 2')).toBeInTheDocument()
    tap('left')
    expect(screen.getByText('Story number 1')).toBeInTheDocument()
    tap('right'); tap('right')
    expect(screen.getByRole('dialog', { name: 'Stories from juma' })).toBeInTheDocument()
    tap('right')
    expect(onClose).toHaveBeenCalled()
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/stories/3/view/'))
    expect(api.post).toHaveBeenCalledWith('/stories/1/view/')
  })

  it('starts at the first unseen story', () => {
    renderWithProviders(<StoryViewer entries={[entry(1, 'asha', [story(1, { seen: true }), story(2)])]} onClose={vi.fn()} />)
    expect(screen.getByText('Story number 2')).toBeInTheDocument()
  })

  it('closes with Escape and moves with arrow keys', () => {
    const onClose = vi.fn()
    renderWithProviders(<StoryViewer entries={[entry(1, 'asha', [story(1), story(2)])]} onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByText('Story number 2')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('advances automatically when a story finishes', async () => {
    let now = 0
    const frames: FrameRequestCallback[] = []
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => { frames.push(cb); return frames.length })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    renderWithProviders(<StoryViewer entries={[entry(1, 'asha', [story(1, { duration_ms: 1000 }), story(2)])]} onClose={vi.fn()} />)
    now = 1200
    act(() => { frames.splice(0).forEach((cb) => cb(now)) })
    expect(await screen.findByText('Story number 2')).toBeInTheDocument()
  })

  it('sends a private reply', async () => {
    const user = userEvent.setup()
    renderWithProviders(<StoryViewer entries={[entry(1, 'asha', [story(7)])]} onClose={vi.fn()} />)
    await user.type(screen.getByRole('textbox', { name: 'Reply to asha' }), 'So nice!')
    await user.click(screen.getByRole('button', { name: 'Send reply' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/stories/7/reply/', { body: 'So nice!' }))
    expect(await screen.findByText('Reply sent')).toBeInTheDocument()
  })

  it('shows viewers and delete on your own story, without marking it seen', async () => {
    api.get.mockResolvedValue({ data: { count: 1, viewers: [{ viewed_at: new Date().toISOString(), person: person(5, 'neema') }] } })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderWithProviders(<StoryViewer entries={[entry(1, 'me', [story(9, { is_own: true, view_count: 1 }), story(10, { is_own: true, view_count: 0 })])]} onClose={vi.fn()} />)

    expect(screen.queryByRole('textbox', { name: /reply/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /seen by 1/i }))
    expect((await screen.findAllByText('neema')).length).toBeGreaterThan(0)
    expect(api.post).not.toHaveBeenCalledWith('/stories/9/view/')

    await user.click(screen.getByRole('button', { name: 'Close viewers' }))
    await user.click(screen.getByRole('button', { name: 'Delete story' }))
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/stories/9/'))
    expect(await screen.findByText('Story number 10')).toBeInTheDocument()
  })
})

describe('StoryComposer', () => {
  beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset()); api.post.mockResolvedValue({ data: {} }); api.get.mockResolvedValue({ data: [] }) })

  it('shares a text story to close friends', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<StoryComposer onClose={onClose} />)
    await user.click(screen.getByRole('tab', { name: /text/i }))
    await user.type(screen.getByRole('textbox', { name: 'Story text' }), 'Habari za asubuhi')
    await user.click(screen.getByRole('radio', { name: 'sunset' }))
    await user.click(screen.getByRole('radio', { name: /close friends/i }))
    await user.click(screen.getByRole('button', { name: 'Share to Close friends' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [url, form] = api.post.mock.calls[0] as [string, FormData]
    expect(url).toBe('/stories/')
    expect(Object.fromEntries(form.entries())).toEqual({ audience: 'close_friends', media_type: 'text', text: 'Habari za asubuhi', background: 'sunset' })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('rejects videos longer than 60 seconds before uploading', async () => {
    const original = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const element = original(tag)
      if (tag === 'video') {
        Object.defineProperty(element, 'duration', { value: 95 })
        setTimeout(() => (element as HTMLVideoElement).onloadedmetadata?.(new Event('loadedmetadata')), 0)
        Object.defineProperty(element, 'currentTime', { set() { setTimeout(() => (element as HTMLVideoElement).onseeked?.(new Event('seeked')), 0) }, get() { return 0 } })
      }
      return element
    }) as typeof document.createElement)
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<StoryComposer onClose={vi.fn()} />)
    await user.upload(screen.getByLabelText('Story photo or video'), new File(['x'], 'long.mp4', { type: 'video/mp4' }))
    expect(await screen.findByText(/up to 60 seconds\. This one is 95 seconds/)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('measures videos whose files report an unknown (Infinity) length', async () => {
    const { inspectVideo } = await import('./StoryComposer')
    const original = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const element = original(tag)
      if (tag === 'video') {
        let duration = Infinity
        Object.defineProperty(element, 'duration', { get: () => duration })
        Object.defineProperty(element, 'currentTime', {
          get: () => 0,
          set(value: number) {
            const video = element as HTMLVideoElement
            if (value > 1e100) setTimeout(() => { duration = 12.4; video.ondurationchange?.(new Event('durationchange')) }, 0)
            else setTimeout(() => video.onseeked?.(new Event('seeked')), 0)
          },
        })
        setTimeout(() => (element as HTMLVideoElement).onloadedmetadata?.(new Event('loadedmetadata')), 0)
      }
      return element
    }) as typeof document.createElement)
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    const result = await inspectVideo(new File(['x'], 'recorded.webm', { type: 'video/webm' }))
    expect(result.seconds).toBeCloseTo(12.4)
  })
})
