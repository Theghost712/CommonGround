import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/utils'
import { safeNext } from '../pages/AuthPage'
import { PromoteDialog, TipDialog } from './MoneyDialogs'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../services/api', () => ({ api, getErrorMessage: () => 'Request failed' }))
const config = { enabled: true, test_mode: false, currency: 'TZS', tip_min: 500, tip_max: 1000000, tip_fee_percent: 10, payout_min: 5000, promotion_daily_price: 3000, promotion_max_days: 30, referral_reward: 1000, payout_networks: [] }

describe('money dialogs', () => {
  const assign = vi.fn()
  beforeEach(() => {
    api.get.mockReset(); api.post.mockReset(); assign.mockReset()
    Object.defineProperty(window, 'location', { configurable: true, value: { ...window.location, assign } })
    api.get.mockImplementation(async (url: string, options?: { params?: { days?: number } }) => {
      if (url === '/money/config/') return { data: config }
      if (url === '/promotions/quote/') { const days = options?.params?.days ?? 1; return { data: { days, daily_price: 3000, total: days * 3000, credit_used: 2000, amount_due: days * 3000 - 2000 } } }
      throw new Error(url)
    })
  })

  it('tips a post and goes to the payment page', async () => {
    const user = userEvent.setup()
    api.post.mockResolvedValue({ data: { checkout_url: 'https://checkout.example/pay', reference: 'cg-abc' } })
    renderWithProviders(<TipDialog username="asha" displayName="Asha" discussionId={5} onClose={() => undefined} />)
    expect(await screen.findByText(/receives 90% of your tip/)).toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'TZS 5,000' }))
    await user.type(screen.getByPlaceholderText('Keep it up!'), 'Asante!')
    await user.click(screen.getByRole('button', { name: 'Pay TZS 5,000' }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://checkout.example/pay'))
    expect(api.post).toHaveBeenCalledWith('/tips/', { discussion: 5, amount: 5000, message: 'Asante!' })
  })

  it('quotes a promotion with ad credit taken off', async () => {
    renderWithProviders(<PromoteDialog discussionId={5} onClose={() => undefined} />)
    expect(await screen.findByText('TZS 9,000')).toBeInTheDocument()
    expect(screen.getByText('−TZS 2,000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pay TZS 7,000' })).toBeEnabled()
  })

  it('only follows in-app paths after sign-in', () => {
    expect(safeNext('/discussions/12')).toBe('/discussions/12')
    expect(safeNext('//evil.example')).toBe('/home')
    expect(safeNext('https://evil.example')).toBe('/home')
    expect(safeNext('/login')).toBe('/home')
    expect(safeNext(null)).toBe('/home')
  })
})
