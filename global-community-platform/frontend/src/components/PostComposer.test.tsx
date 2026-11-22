import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import type { Discussion, DiscussionAttachment } from '../types'
import PostComposer, { shrinkForUpload } from './PostComposer'
import PostGrid from './PostGrid'
import PostMedia from './PostMedia'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))

const png = (name: string, bytes = 10) => new File([new Uint8Array(bytes)], name, { type: 'image/png' })

describe('PostComposer', () => {
  beforeEach(() => {
    api.get.mockReset(); api.post.mockReset()
    api.get.mockResolvedValue({ data: [] })
    api.post.mockResolvedValue({ data: { id: 42 } })
    let n = 0
    URL.createObjectURL = vi.fn(() => `blob:${++n}`)
    URL.revokeObjectURL = vi.fn()
  })

  it('uploads photos in the chosen order with matching alt text, then opens the post', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Routes><Route path="/" element={<PostComposer onClose={vi.fn()} />} /><Route path="/discussions/:id" element={<h1>Post 42</h1>} /></Routes>)
    await user.upload(screen.getByLabelText('Post photos'), [png('first.png'), png('second.png')])
    await user.type(screen.getByRole('textbox', { name: 'Alt text for photo 1' }), 'A red door')
    await user.click(screen.getByRole('button', { name: 'Move photo later' }))
    await user.type(screen.getByRole('textbox', { name: 'Caption' }), 'Mlango #arusha')
    await user.click(screen.getByRole('button', { name: 'Share post' }))

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [url, form] = api.post.mock.calls[0] as [string, FormData]
    expect(url).toBe('/posts/')
    expect((form.getAll('images') as File[]).map((f) => f.name)).toEqual(['second.png', 'first.png'])
    expect(form.getAll('alt_texts')).toEqual(['', 'A red door'])
    expect(form.get('caption')).toBe('Mlango #arusha')
    expect(await screen.findByRole('heading', { name: 'Post 42' })).toBeInTheDocument()
  })

  it('caps a post at 10 photos and refuses non-photos', async () => {
    const user = userEvent.setup({ applyAccept: false })
    renderWithProviders(<PostComposer onClose={vi.fn()} />)
    await user.upload(screen.getByLabelText('Post photos'), Array.from({ length: 12 }, (_, i) => png(`${i}.png`)))
    expect(screen.getByText('A post can have up to 10 photos.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Photo \d+$/ })).toHaveLength(10)

    await user.upload(screen.getByLabelText('Post photos'), new File(['x'], 'notes.txt', { type: 'text/plain' }))
    expect(screen.getByText('Only photos can be added to a post.')).toBeInTheDocument()
  })

  it('keeps the share button disabled until a photo is added', () => {
    renderWithProviders(<PostComposer onClose={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Share post' })).toBeDisabled()
  })
})

describe('shrinkForUpload', () => {
  it('returns the original file when the browser cannot decode it', async () => {
    const original = png('x.png')
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('unsupported')))
    expect(await shrinkForUpload(original)).toBe(original)
    vi.unstubAllGlobals()
  })
})

const attachment = (id: number, extra: Partial<DiscussionAttachment> = {}): DiscussionAttachment => ({ id, original_name: `p${id}.jpg`, content_type: 'image/webp', size: 1, url: '', is_image: true, created_at: '', display_url: `/api/v1/images/${id}/?t=d`, thumb_url: `/api/v1/images/${id}/?t=t`, width: 1080, height: 1350, color: '#336699', alt_text: '', ...extra })
const post = (id: number, attachments: DiscussionAttachment[], extra: Partial<Discussion> = {}): Discussion => ({ id, community: null, community_name: null, author: 1, author_username: 'asha', title: '', body: 'caption', content_html: '', category: 'General', comments_count: 4, reactions_count: 9, bookmarks_count: 0, has_reacted: false, my_reaction: null, has_bookmarked: false, attachments, created_at: '', updated_at: '', ...extra })

describe('PostGrid', () => {
  it('shows thumbnails, a multi-photo marker and text tiles, all linking to the post', () => {
    renderWithProviders(<PostGrid posts={[post(1, [attachment(1, { alt_text: 'Sunset' }), attachment(2)]), post(2, [], { title: 'Just words' })]} />)
    const links = screen.getAllByRole('link')
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/discussions/1', '/discussions/2'])
    expect(screen.getByRole('img', { name: 'Sunset' })).toHaveAttribute('src', '/api/v1/images/1/?t=t')
    expect(screen.getByLabelText('Several photos')).toBeInTheDocument()
    expect(screen.getByText('Just words')).toBeInTheDocument()
  })
})

describe('PostMedia', () => {
  it('reserves space from stored dimensions and uses responsive sources', () => {
    const { container } = renderWithProviders(<PostMedia images={[attachment(5, { alt_text: 'Market day' })]} />)
    const frame = container.querySelector('.feed-media') as HTMLElement
    expect(frame.style.aspectRatio).toBe('0.8')
    expect(frame.style.backgroundColor).toBe('rgb(51, 102, 153)')
    const img = screen.getByRole('img', { name: 'Market day' })
    expect(img.getAttribute('srcset')).toContain('480w')
    expect(img).toHaveAttribute('loading', 'lazy')
  })
})
