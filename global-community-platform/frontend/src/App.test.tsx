import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const authState = vi.hoisted(() => ({ user: null as null | { id: number; username: string }, loading: false }))
vi.mock('./context/AuthContext', () => ({
  useAuth: () => ({ ...authState, login: vi.fn(), register: vi.fn(), logout: vi.fn() }),
}))

// The real layout opens WebSockets; routing only needs it to render its child route.
vi.mock('./components/AppLayout', async () => {
  const { Outlet } = await import('react-router-dom')
  return { default: () => <div data-testid="app-layout"><Outlet /></div> }
})
vi.mock('./pages/HomePage', () => ({ default: () => <h1>Home page</h1> }))
vi.mock('./pages/ChatPage', () => ({ default: () => <h1>Chat page</h1> }))

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
}

describe('App routing', () => {
  beforeEach(() => {
    authState.user = null
    authState.loading = false
  })

  it('sends signed-out visitors to the login page', () => {
    renderAt('/messages')

    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    expect(screen.queryByTestId('app-layout')).not.toBeInTheDocument()
  })

  it('shows a loading state while the session is being restored', () => {
    authState.loading = true
    renderAt('/home')

    expect(screen.getByText('Loading CommonGround…')).toBeInTheDocument()
  })

  // Pages are lazy-loaded chunks now, so they appear after a tick.
  it('opens protected pages for signed-in users', async () => {
    authState.user = { id: 1, username: 'amani' }
    renderAt('/messages')

    expect(await screen.findByRole('heading', { name: 'Chat page' })).toBeInTheDocument()
    expect(screen.getByTestId('app-layout')).toBeInTheDocument()
  })

  it('redirects signed-in users away from login and unknown routes to home', async () => {
    authState.user = { id: 1, username: 'amani' }
    renderAt('/login')
    expect(await screen.findByRole('heading', { name: 'Home page' })).toBeInTheDocument()
  })

  it('redirects unknown routes to home', async () => {
    authState.user = { id: 1, username: 'amani' }
    renderAt('/does-not-exist')
    expect(await screen.findByRole('heading', { name: 'Home page' })).toBeInTheDocument()
  })
})
