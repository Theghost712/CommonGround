import { act, render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
vi.mock('../services/api', () => ({ api: { get } }))

const started: number[] = []
class FakeAudioContext {
  state = 'running'
  currentTime = 0
  destination = {}
  resume = vi.fn()
  createOscillator() { return { type: '', frequency: { value: 0 }, connect: (node: unknown) => node, start: () => started.push(1), stop: vi.fn() } }
  createGain() { return { gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() }, connect: (node: unknown) => node } }
}
const popups: { title: string; options: NotificationOptions }[] = []
class FakeNotification {
  static permission: NotificationPermission = 'granted'
  onclick: (() => void) | null = null
  constructor(title: string, options: NotificationOptions) { popups.push({ title, options }) }
  close() {}
}

async function mount(prefs: { sound_enabled: boolean; popup_enabled: boolean }) {
  vi.resetModules()
  get.mockResolvedValue({ data: prefs })
  const { useNotificationAlerts } = await import('./notificationAlerts')
  function Harness() { useNotificationAlerts(2); return null }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter><Harness /></MemoryRouter></QueryClientProvider>)
  await waitFor(() => expect(client.getQueryData(['notification-preferences'])).toEqual(prefs))
  window.dispatchEvent(new Event('pointerdown')) // unlocks audio like a real click
}

it('stays silent while preferences are still loading', async () => {
  vi.resetModules()
  started.length = 0
  vi.stubGlobal('AudioContext', FakeAudioContext)
  get.mockReturnValue(new Promise(() => {})) // never resolves
  const { useNotificationAlerts } = await import('./notificationAlerts')
  function Harness() { useNotificationAlerts(0); return null }
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Harness /></MemoryRouter></QueryClientProvider>)
  window.dispatchEvent(new Event('pointerdown'))
  act(() => { window.dispatchEvent(new CustomEvent('commonground:notification', { detail: { id: 1, notification_type: 'system', title: 't', body: '', target_url: '' } })) })
  expect(started.length).toBe(0)
  vi.unstubAllGlobals()
})

it('unlocks audio from a click that happens before the app layout mounts (e.g. "Sign in")', async () => {
  vi.resetModules()
  vi.stubGlobal('AudioContext', FakeAudioContext)
  const alerts = await import('./notificationAlerts')
  alerts.installAudioUnlock()
  window.dispatchEvent(new Event('pointerdown'))
  expect(alerts.playNotificationSound()).toBe(true)
  vi.unstubAllGlobals()
})

const fire = (type = 'discussion_comment') => act(() => {
  window.dispatchEvent(new CustomEvent('commonground:notification', { detail: { id: 9, notification_type: type, title: 'Juma commented', body: 'Nice idea', target_url: '/discussions/1' } }))
})

describe('useNotificationAlerts', () => {
  beforeEach(() => {
    started.length = 0
    popups.length = 0
    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.stubGlobal('Notification', FakeNotification)
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('plays a chime and puts the unread count in the tab title', async () => {
    await mount({ sound_enabled: true, popup_enabled: false })
    fire()
    expect(started.length).toBe(2)
    expect(document.title).toMatch(/^\(2\)/)
  })

  it('stays silent when sound is turned off', async () => {
    await mount({ sound_enabled: false, popup_enabled: false })
    fire()
    expect(started.length).toBe(0)
  })

  it('shows a system pop-up only when the page is in the background', async () => {
    await mount({ sound_enabled: false, popup_enabled: true })
    const hasFocus = vi.spyOn(document, 'hasFocus')
    hasFocus.mockReturnValue(true)
    fire()
    expect(popups).toHaveLength(0)

    hasFocus.mockReturnValue(false)
    fire()
    expect(popups).toEqual([{ title: 'Juma commented', options: { body: 'Nice idea', icon: '/favicon.svg', tag: 'commonground-9' } }])
  })
})
