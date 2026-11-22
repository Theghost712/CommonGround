import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { renderWithProviders } from '../test/utils'
import AuthPage from './AuthPage'

const auth = vi.hoisted(() => ({ login: vi.fn(), register: vi.fn() }))
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: null, loading: false, logout: vi.fn(), ...auth }),
}))

function renderAuth(mode: 'login' | 'register') {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<AuthPage mode={mode} />} />
      <Route path="/register" element={<AuthPage mode={mode} />} />
      <Route path="/home" element={<h1>Home feed</h1>} />
    </Routes>,
    { route: `/${mode}` },
  )
}

describe('AuthPage', () => {
  beforeEach(() => {
    auth.login.mockReset()
    auth.register.mockReset()
  })

  it('signs in and navigates to the home feed', async () => {
    auth.login.mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderAuth('login')

    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Email address')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Username'), 'amani')
    await user.type(screen.getByLabelText('Password'), 'Strong-password-123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(auth.login).toHaveBeenCalledWith('amani', 'Strong-password-123')
    expect(await screen.findByRole('heading', { name: 'Home feed' })).toBeInTheDocument()
  })

  it('links to password recovery from the sign-in form only', () => {
    renderAuth('login')
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/forgot-password')
  })

  it('shows the server error and stays on the page when login fails', async () => {
    const { AxiosError, AxiosHeaders } = await import('axios')
    const config = { headers: new AxiosHeaders() }
    auth.login.mockRejectedValue(new AxiosError('401', '401', config as never, null, {
      data: { detail: 'No active account found with the given credentials' }, status: 401, statusText: '401', headers: {}, config: config as never,
    }))
    const user = userEvent.setup()
    renderAuth('login')

    await user.type(screen.getByLabelText('Username'), 'amani')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByText('No active account found with the given credentials')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Home feed' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeEnabled()
  })

  it('registers with all account fields', async () => {
    auth.register.mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderAuth('register')

    expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('First name'), 'Amani')
    await user.type(screen.getByLabelText('Last name'), 'Juma')
    await user.type(screen.getByLabelText('Username'), 'amani')
    await user.type(screen.getByLabelText('Email address'), 'amani@example.test')
    await user.type(screen.getByLabelText('Password'), 'Strong-password-123')
    await user.type(screen.getByLabelText('Confirm password'), 'Strong-password-123')
    await user.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(auth.register).toHaveBeenCalledWith({
      username: 'amani',
      email: 'amani@example.test',
      first_name: 'Amani',
      last_name: 'Juma',
      password: 'Strong-password-123',
      password_confirm: 'Strong-password-123',
    }))
  })

  it('links between login and register', () => {
    renderAuth('login')

    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute('href', '/register')
  })
})
