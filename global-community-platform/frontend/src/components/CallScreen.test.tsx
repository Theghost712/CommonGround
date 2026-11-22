import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import CallScreen from './CallScreen'

const call = vi.hoisted(() => ({ state: {} as Record<string, unknown> }))
vi.mock('../context/CallContext', () => ({ useCall: () => call.state }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 2, username: 'juma' } }) }))

const info = { id: 5, conversation_id: 1, kind: 'video', status: 'ringing', answered_device: '', caller: { id: 1, username: 'amina', display_name: 'Amina Said' }, callee: { id: 2, username: 'juma', display_name: 'Juma' } }
const base = { phase: 'idle', call: null, message: '', startedAt: null, localStream: null, remoteStream: null, muted: false, cameraOff: false, accept: vi.fn(), decline: vi.fn(), hangUp: vi.fn(), toggleMute: vi.fn(), toggleCamera: vi.fn(), dismiss: vi.fn() }

describe('CallScreen', () => {
  beforeEach(() => { call.state = { ...base } })

  it('renders nothing when there is no call', () => {
    renderWithProviders(<CallScreen />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('rings for an incoming video call with accept and decline', async () => {
    call.state = { ...base, phase: 'incoming', call: info }
    const user = userEvent.setup()
    renderWithProviders(<CallScreen />)
    expect(screen.getByRole('dialog', { name: 'Video call with Amina Said' })).toBeInTheDocument()
    expect(screen.getByText('Incoming video call')).toBeInTheDocument()
    expect(document.title).toBe('📞 Amina Said is calling…')
    await user.click(screen.getByRole('button', { name: 'Accept' }))
    expect(base.accept).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Decline' }))
    expect(base.decline).toHaveBeenCalled()
  })

  it('shows mute, camera and end controls during a call', async () => {
    call.state = { ...base, phase: 'connecting', call: info, muted: true }
    const user = userEvent.setup()
    renderWithProviders(<CallScreen />)
    expect(screen.getByText('Connecting…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unmute' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: 'Turn camera off' }))
    expect(base.toggleCamera).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'End call' }))
    expect(base.hangUp).toHaveBeenCalled()
  })

  it('shows why a call ended', () => {
    call.state = { ...base, phase: 'ended', call: { ...info, status: 'declined' }, message: 'Call declined' }
    renderWithProviders(<CallScreen />)
    expect(screen.getByText('Call declined')).toBeInTheDocument()
  })
})
