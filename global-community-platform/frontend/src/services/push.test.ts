import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { vi.unstubAllGlobals(); vi.resetModules(); vi.restoreAllMocks() })

describe('push service', () => {
  it('reports unsupported browsers without calling the server', async () => {
    const { api } = await import('./api')
    const get = vi.spyOn(api, 'get')
    const { getPushState } = await import('./push')
    expect(await getPushState()).toBe('unsupported')
    expect(get).not.toHaveBeenCalled()
  })

  it('asks iPhone users to add the app to the home screen first', async () => {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)')
    const { getPushState } = await import('./push')
    expect(await getPushState()).toBe('needs-install')
  })

  it('subscribes with the server key and registers the device', async () => {
    const subscription = { endpoint: 'https://fcm.googleapis.com/x', options: { applicationServerKey: null }, toJSON: () => ({ endpoint: 'https://fcm.googleapis.com/x', keys: { p256dh: 'p', auth: 'a' } }) }
    const subscribe = vi.fn().mockResolvedValue(subscription)
    const registration = { pushManager: { getSubscription: vi.fn().mockResolvedValue(null), subscribe } }
    vi.stubGlobal('PushManager', function PushManager() {})
    vi.stubGlobal('Notification', Object.assign(function Notification() {}, { permission: 'default', requestPermission: vi.fn().mockResolvedValue('granted') }))
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { register: vi.fn().mockResolvedValue(registration), ready: Promise.resolve(registration) } })
    const { api } = await import('./api')
    vi.spyOn(api, 'get').mockResolvedValue({ data: { enabled: true, public_key: 'BPpq', devices: 0 } })
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} })
    const { enablePush, isPushActiveHere } = await import('./push')
    expect(await enablePush()).toBe('on')
    expect(subscribe).toHaveBeenCalledWith(expect.objectContaining({ userVisibleOnly: true }))
    expect(post).toHaveBeenCalledWith('/push/subscriptions/', { endpoint: 'https://fcm.googleapis.com/x', keys: { p256dh: 'p', auth: 'a' } })
    expect(isPushActiveHere()).toBe(true)
    // @ts-expect-error cleanup of the test stub
    delete navigator.serviceWorker
  })
})
