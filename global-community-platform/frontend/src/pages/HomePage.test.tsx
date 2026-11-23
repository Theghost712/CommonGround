import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StoriesBar from '../components/StoriesBar'
import { renderWithProviders } from '../test/utils'
import type { Discussion, Person, Story, StoryTrayEntry } from '../types'
import HomePage from './HomePage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'me', first_name: 'Amani', last_name: '' } }) }))

const relation = { is_self: false, is_following: true, follows_you: false, is_mutual: false, in_contacts: false, mutual_followers_count: 0, mutual_followers_preview: [], label: null }
const person = (id: number, username: string): Person => ({ id, username, first_name: username, last_name: '', display_name: username, avatar_url: '', bio: '', country: '', followers_count: 0, following_count: 0, relationship: relation, reason: null })
const storyItem = (id: number, seen: boolean): Story => ({ id, media_type: 'text', media_url: '', thumbnail_url: '', text: `Story ${id}`, background: 'violet', alt_text: '', duration_ms: 5000, audience: 'followers', created_at: new Date().toISOString(), expires_at: '', seen, view_count: null, is_own: false })
const trayEntry = (id: number, username: string, seen: boolean): StoryTrayEntry => ({ user: person(id, username), stories: [storyItem(id * 10, seen)], all_seen: seen, latest_at: new Date().toISOString() })
const discussion = (id: number, title: string): Discussion => ({
  id, community: null, community_name: null, author: 2, author_username: 'asha', title, body: 'b', content_html: '', category: 'General',
  comments_count: 0, reactions_count: 0, bookmarks_count: 0, has_reacted: false, my_reaction: null, has_bookmarked: false, attachments: [],
  created_at: new Date().toISOString(), updated_at: '',
})
const page = (results: Discussion[], next: string | null = null) => ({ data: { count: results.length, next, previous: null, results } })

describe('HomePage', () => {
  beforeEach(() => {
    localStorage.clear()
    api.get.mockReset()
    api.get.mockImplementation(async (url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/stories/tray/') return { data: [trayEntry(2, 'asha', false), trayEntry(3, 'juma', true)] }
      if (url === '/people/suggestions/') return { data: [{ ...person(9, 'neema'), relationship: { ...relation, is_following: false }, reason: 'Follows you' }] }
      if (url === '/discussions/categories/') return { data: [] }
      if (url === '/feed/for-you/') return page([discussion(1, 'Everyone post')])
      if (url === '/discussions/') return config?.params?.feed === 'following' ? page([discussion(2, 'From people I follow')]) : page([discussion(1, 'Everyone post')])
      if (url === '/discussions/trending/') return page([discussion(3, 'Hot post')])
      throw new Error(url)
    })
  })

  it('shows stories, the composer, posts and suggestions', async () => {
    renderWithProviders(<HomePage />)
    expect(await screen.findByRole('heading', { name: 'Everyone post' })).toBeInTheDocument()
    expect(screen.getByText('Your story')).toBeInTheDocument()
    expect(await screen.findByText('juma')).toBeInTheDocument()
    expect(screen.getByText(/What's on your mind, Amani\?/)).toBeInTheDocument()
    expect(await screen.findByText('Suggested for you')).toBeInTheDocument()
  })

  it('switches between For you, Following and Trending', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HomePage />)
    await screen.findByRole('heading', { name: 'Everyone post' })

    await user.click(screen.getByRole('tab', { name: /following/i }))
    expect(await screen.findByRole('heading', { name: 'From people I follow' })).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/discussions/', { params: expect.objectContaining({ feed: 'following', paginate: 'cursor' }) })

    await user.click(screen.getByRole('tab', { name: /trending/i }))
    expect(await screen.findByRole('heading', { name: 'Hot post' })).toBeInTheDocument()
  })

  it('invites the user to follow people when Following is empty', async () => {
    api.get.mockImplementation(async (url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/discussions/' && config?.params?.feed === 'following') return page([])
      if (url === '/stories/tray/' || url === '/people/suggestions/' || url === '/discussions/categories/') return { data: [] }
      return page([discussion(1, 'Everyone post')])
    })
    const user = userEvent.setup()
    renderWithProviders(<HomePage />)
    await user.click(screen.getByRole('tab', { name: /following/i }))
    expect(await screen.findByRole('link', { name: /find people/i })).toHaveAttribute('href', '/people')
  })

  it('loads the next page with "Load more"', async () => {
    api.get.mockImplementation(async (url: string, config?: { params?: Record<string, unknown> }) => {
      // For you is ranked: page numbers.
      if (url === '/feed/for-you/') return config?.params?.page === '2' ? page([discussion(5, 'Second page post')]) : page([discussion(4, 'First page post')], 'http://localhost:8000/api/v1/feed/for-you/?page=2')
      return { data: [] }
    })
    const user = userEvent.setup()
    renderWithProviders(<HomePage />)
    await user.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByRole('heading', { name: 'Second page post' })).toBeInTheDocument()
  })
})

describe('StoriesBar', () => {
  beforeEach(() => { api.get.mockReset(); api.post.mockReset(); api.post.mockResolvedValue({ data: {} }) })

  it('shows unseen rings before seen ones and opens the full-screen viewer', async () => {
    api.get.mockImplementation(async (url: string) => url === '/stories/tray/' ? { data: [trayEntry(2, 'asha', false), trayEntry(3, 'juma', true)] } : { data: [] })
    const user = userEvent.setup()
    renderWithProviders(<StoriesBar />)
    const asha = await screen.findByRole('button', { name: "Watch asha's story" })
    expect(asha.querySelector('.story-ring.fresh')).toBeTruthy()
    expect(screen.getByRole('button', { name: "Watch again juma's story" }).querySelector('.story-ring.seen')).toBeTruthy()

    await user.click(asha)
    expect(await screen.findByRole('dialog', { name: 'Stories from asha' })).toBeInTheDocument()
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/stories/20/view/'))
  })

  it('falls back to suggestions when nobody you follow has a story', async () => {
    api.get.mockImplementation(async (url: string) => url === '/stories/tray/' ? { data: [] } : { data: [person(9, 'neema')] })
    renderWithProviders(<StoriesBar />)
    expect(await screen.findByText('Suggested')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('link', { name: /neema/ })).toHaveAttribute('href', '/u/neema'))
  })

  it('opens the story composer from "Your story"', async () => {
    api.get.mockResolvedValue({ data: [] })
    const user = userEvent.setup()
    renderWithProviders(<StoriesBar />)
    await user.click(await screen.findByRole('button', { name: 'Create a new story' }))
    expect(await screen.findByRole('dialog', { name: 'Create a story' })).toBeInTheDocument()
  })
})
