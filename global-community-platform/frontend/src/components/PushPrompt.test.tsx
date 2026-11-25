import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PushPrompt from './PushPrompt'

const push = vi.hoisted(() => ({ getPushState: vi.fn(), enablePush: vi.fn() }))
vi.mock('../services/push', () => push)

const KEY = 'cg-push-prompt-dismissed-at'

describe('PushPrompt', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.clear()
    push.getPushState.mockReset()
    push.enablePush.mockReset()
  })

  async function settle() {
    // The prompt waits 4 s before asking, then checks the device state.
    await act(async () => { await vi.advanceTimersByTimeAsync(4100) })
  }

  it('asks when push is off on this device, and turning it on hides the prompt', async () => {
    push.getPushState.mockResolvedValue('off')
    push.enablePush.mockResolvedValue('on')
    render(<PushPrompt />)
    expect(screen.queryByRole('dialog')).toBeNull()
    await settle()
    expect(screen.getByRole('dialog', { name: 'Turn on notifications' })).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: 'Turn on' }))
    expect(push.enablePush).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('stays hidden when push is already on, not set up, or blocked', async () => {
    for (const state of ['on', 'server-off', 'denied', 'unsupported', 'needs-install'] as const) {
      push.getPushState.mockResolvedValue(state)
      const { unmount } = render(<PushPrompt />)
      await settle()
      expect(screen.queryByRole('dialog')).toBeNull()
      unmount()
    }
  })

  it('remembers "Not now" so it does not come back for a week', async () => {
    push.getPushState.mockResolvedValue('off')
    const { unmount } = render(<PushPrompt />)
    await settle()
    await userEvent.click(screen.getByRole('button', { name: 'Not now' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(Number(localStorage.getItem(KEY))).toBeGreaterThan(0)
    unmount()

    render(<PushPrompt />)
    await settle()
    expect(push.getPushState).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('stops asking after the browser says the permission was refused', async () => {
    push.getPushState.mockResolvedValue('off')
    push.enablePush.mockResolvedValue('denied')
    render(<PushPrompt />)
    await settle()
    await userEvent.click(screen.getByRole('button', { name: 'Turn on' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(localStorage.getItem(KEY)).not.toBeNull()
  })
})
