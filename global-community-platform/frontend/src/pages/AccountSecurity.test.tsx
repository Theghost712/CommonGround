import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import AccountSecurityPage from './AccountSecurityPage'
import { ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from './AccountRecoveryPages'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../services/api', () => ({
  api,
  ensureCsrfToken: vi.fn(async () => 'csrf'),
  getErrorMessage: (err: { message?: string }) => err?.message ?? 'Request failed',
}))
const auth = vi.hoisted(() => ({
  user: null as null | Record<string, unknown>,
  reloadUser: vi.fn(async () => {}),
  applySession: vi.fn(async () => {}),
}))
vi.mock('../context/AuthContext', () => ({ useAuth: () => auth }))

const amina = { id: 1, username: 'amina', email: 'amina@example.com', email_verified: false, first_name: 'Amina', last_name: '' }

beforeEach(() => {
  api.get.mockReset(); api.post.mockReset()
  auth.reloadUser.mockClear(); auth.applySession.mockClear()
  auth.user = null
})

describe('ForgotPasswordPage', () => {
  it('sends the reset request and shows the neutral answer', async () => {
    api.post.mockResolvedValue({ data: { detail: "If an account matches, we've sent a link." } })
    const user = userEvent.setup()
    renderWithProviders(<ForgotPasswordPage />, { route: '/forgot-password' })
    await user.type(screen.getByLabelText('Username or email'), '  amina@example.com ')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(api.post).toHaveBeenCalledWith('/auth/password/reset/', { login: 'amina@example.com' })
    expect(await screen.findByText('Check your email')).toBeInTheDocument()
    expect(screen.queryByLabelText('Username or email')).not.toBeInTheDocument()
  })
})

describe('ResetPasswordPage', () => {
  const route = '/reset-password?uid=MQ&token=abc-123'

  it('posts uid, token and the new password, then offers sign-in', async () => {
    api.post.mockResolvedValue({ data: { detail: 'Your password was reset.' } })
    const user = userEvent.setup()
    renderWithProviders(<ResetPasswordPage />, { route })
    await user.type(screen.getByLabelText('New password'), 'Brand-new-pass-456')
    await user.type(screen.getByLabelText('Confirm new password'), 'Brand-new-pass-456')
    await user.click(screen.getByRole('button', { name: /save new password/i }))
    expect(api.post).toHaveBeenCalledWith('/auth/password/reset/confirm/', {
      uid: 'MQ', token: 'abc-123', new_password: 'Brand-new-pass-456', new_password_confirm: 'Brand-new-pass-456',
    })
    expect(await screen.findByRole('heading', { name: 'Password changed' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login')
  })

  it('catches mismatched passwords without calling the server', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ResetPasswordPage />, { route })
    await user.type(screen.getByLabelText('New password'), 'Brand-new-pass-456')
    await user.type(screen.getByLabelText('Confirm new password'), 'Different-pass-456')
    await user.click(screen.getByRole('button', { name: /save new password/i }))
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('offers a new link when the token expired', async () => {
    api.post.mockRejectedValue(new Error('This reset link is invalid or has expired.'))
    const user = userEvent.setup()
    renderWithProviders(<ResetPasswordPage />, { route })
    await user.type(screen.getByLabelText('New password'), 'Brand-new-pass-456')
    await user.type(screen.getByLabelText('Confirm new password'), 'Brand-new-pass-456')
    await user.click(screen.getByRole('button', { name: /save new password/i }))
    expect(await screen.findByRole('link', { name: 'Ask for a new link.' })).toHaveAttribute('href', '/forgot-password')
  })

  it('explains a link with missing parts', () => {
    renderWithProviders(<ResetPasswordPage />, { route: '/reset-password?uid=MQ' })
    expect(screen.getByRole('heading', { name: 'Link incomplete' })).toBeInTheDocument()
  })
})

describe('VerifyEmailPage', () => {
  it('confirms once even under StrictMode and refreshes the signed-in user', async () => {
    auth.user = amina
    api.post.mockResolvedValue({ data: { detail: 'Thanks! Your email address is confirmed.' } })
    renderWithProviders(<StrictMode><VerifyEmailPage /></StrictMode>, { route: '/verify-email?token=strict-1' })
    expect(await screen.findByText('Thanks! Your email address is confirmed.')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(auth.reloadUser).toHaveBeenCalled())
    expect(screen.getByRole('link', { name: /go to your feed/i })).toHaveAttribute('href', '/home')
  })

  it('shows the failure and sends signed-out people to sign in', async () => {
    api.post.mockRejectedValue(new Error('This confirmation link is invalid, expired or already used.'))
    renderWithProviders(<VerifyEmailPage />, { route: '/verify-email?token=bad-1' })
    expect(await screen.findByRole('heading', { name: "We couldn't confirm it" })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login')
  })
})

describe('AccountSecurityPage', () => {
  beforeEach(() => { auth.user = amina })

  it('shows the email status and resends the confirmation link', async () => {
    api.post.mockResolvedValue({ data: { detail: 'We sent a new link to a••••@example.com.' } })
    const user = userEvent.setup()
    renderWithProviders(<AccountSecurityPage />)
    expect(screen.getByText('Not confirmed')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /send confirmation link again/i }))
    expect(api.post).toHaveBeenCalledWith('/auth/email/resend/')
    expect(await screen.findByText('We sent a new link to a••••@example.com.')).toBeInTheDocument()
  })

  it('changes the password and keeps this device signed in with the new token', async () => {
    api.post.mockResolvedValue({ data: { access: 'new-access', detail: 'Password changed. Other devices were signed out.' } })
    const user = userEvent.setup()
    renderWithProviders(<AccountSecurityPage />)
    await user.type(screen.getByLabelText('Current password'), 'Original-pass-123')
    await user.type(screen.getByLabelText('New password'), 'Brand-new-pass-456')
    await user.type(screen.getByLabelText('Confirm new password'), 'Brand-new-pass-456')
    await user.click(screen.getByRole('button', { name: 'Change password' }))
    expect(api.post).toHaveBeenCalledWith('/auth/password/change/', {
      current_password: 'Original-pass-123', new_password: 'Brand-new-pass-456', new_password_confirm: 'Brand-new-pass-456',
    })
    expect(await screen.findByText('Password changed. Other devices were signed out.')).toBeInTheDocument()
    expect(auth.applySession).toHaveBeenCalledWith('new-access')
    expect(screen.getByLabelText('Current password')).toHaveValue('')
  })

  it('requests an email change with the password', async () => {
    api.post.mockResolvedValue({ data: { detail: 'Check new@example.com and open the link to finish the change.' } })
    const user = userEvent.setup()
    renderWithProviders(<AccountSecurityPage />)
    await user.click(screen.getByRole('button', { name: 'Change email' }))
    await user.type(screen.getByLabelText('New email address'), 'new@example.com')
    await user.type(screen.getByLabelText('Your password'), 'Original-pass-123')
    await user.click(screen.getByRole('button', { name: 'Send confirmation link' }))
    expect(api.post).toHaveBeenCalledWith('/auth/email/change/', { new_email: 'new@example.com', password: 'Original-pass-123' })
    expect(await screen.findByText(/Check new@example.com/)).toBeInTheDocument()
  })

  it('signs out everywhere and returns to the login page', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.post.mockResolvedValue({ data: { detail: 'Signed out of all devices.' } })
    const user = userEvent.setup()
    renderWithProviders(<Routes><Route path="/settings/security" element={<AccountSecurityPage />} /><Route path="/login" element={<h1>Login page</h1>} /></Routes>, { route: '/settings/security' })
    await user.click(screen.getByRole('button', { name: 'Sign out everywhere' }))
    expect(api.post).toHaveBeenCalledWith('/auth/sessions/revoke/', { keep_current: false })
    expect(await screen.findByRole('heading', { name: 'Login page' })).toBeInTheDocument()
    expect(auth.applySession).toHaveBeenCalledWith(null)
  })
})
