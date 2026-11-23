import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import GroupCallScreen, { GroupCallInvite } from './GroupCallScreen'
import VideoPlayer from './VideoPlayer'

const group = vi.hoisted(() => ({ state: {} as Record<string, unknown> }))
vi.mock('../context/GroupCallContext', () => ({ useGroupCall: () => group.state }))
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'amina' } }) }))

const person = (id: number, name: string) => ({ id, username: name.toLowerCase(), display_name: name, device_id: `d${id}`, joined_at: null })
const call = { id: 9, conversation_id: 4, kind: 'video', status: 'live', started_by: person(1, 'Amina'), created_at: null, participants: [person(1, 'Amina'), person(2, 'Juma'), person(3, 'Neema')], max_participants: 8 }
const base = { phase: 'idle', call: null, message: '', joinedAt: null, localStream: null, peers: {}, muted: false, cameraOff: false, invite: null, liveCalls: {}, available: true, join: vi.fn(() => Promise.resolve()), leave: vi.fn(), toggleMute: vi.fn(), toggleCamera: vi.fn(), dismissInvite: vi.fn(), dismiss: vi.fn() }

describe('GroupCallScreen', () => {
  beforeEach(() => { group.state = { ...base } })

  it('renders nothing outside a call', () => {
    renderWithProviders(<GroupCallScreen />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows a tile per person with connection state and the controls', async () => {
    group.state = { ...base, phase: 'active', call, joinedAt: Date.now(), peers: { 2: { userId: 2, stream: null, connection: 'connected' }, 3: { userId: 3, stream: null, connection: 'failed' } } }
    const user = userEvent.setup()
    renderWithProviders(<GroupCallScreen />)
    expect(screen.getByRole('dialog', { name: 'Group video call' })).toBeInTheDocument()
    expect(screen.getByText('3 people')).toBeInTheDocument()
    expect(screen.getByText('You')).toBeInTheDocument()
    expect(screen.getByText('Juma')).toBeInTheDocument()
    expect(screen.getByText('Neema · connection lost')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mute' }))
    expect(base.toggleMute).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Turn camera off' }))
    expect(base.toggleCamera).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Leave call' }))
    expect(base.leave).toHaveBeenCalled()
  })

  it('says when you are alone in the call', () => {
    group.state = { ...base, phase: 'active', call: { ...call, kind: 'audio', participants: [person(1, 'Amina')] } }
    renderWithProviders(<GroupCallScreen />)
    expect(screen.getByText('Waiting for others to join…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Turn camera off' })).not.toBeInTheDocument()
  })

  it('invites you to join a call someone started', async () => {
    group.state = { ...base, invite: { ...call, started_by: person(2, 'Juma'), participants: [person(2, 'Juma')] } }
    const user = userEvent.setup()
    renderWithProviders(<GroupCallInvite />)
    expect(screen.getByText('Juma started a group video call')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Join' }))
    expect(base.join).toHaveBeenCalledWith(4, 'video')
  })
})

describe('VideoPlayer', () => {
  it('explains when a video could not be processed', () => {
    renderWithProviders(<VideoPlayer file={{ id: 1, original_name: 'clip', content_type: 'video/mp4', size: 0, url: '', is_image: false, created_at: '', is_video: true, video_url: '', processing: 'failed' }} />)
    expect(screen.getByRole('status')).toHaveTextContent("This video couldn't be processed.")
  })
})
