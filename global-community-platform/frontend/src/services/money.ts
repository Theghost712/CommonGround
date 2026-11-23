import { useQuery } from '@tanstack/react-query'
import { api } from './api'

export type MoneyConfig = {
  enabled: boolean
  test_mode: boolean
  currency: string
  tip_min: number
  tip_max: number
  tip_fee_percent: number
  payout_min: number
  promotion_daily_price: number
  promotion_max_days: number
  referral_reward: number
  payout_networks: { value: string; label: string }[]
}

export type Promotion = {
  id: number
  discussion: number
  discussion_title: string
  days: number
  total_price: number
  credit_used: number
  status: 'awaiting_payment' | 'in_review' | 'active' | 'rejected' | 'cancelled'
  status_label: string
  rejection_reason: string
  starts_at: string | null
  ends_at: string | null
  is_running: boolean
  impressions: number
  clicks: number
  created_at: string
}

export type Wallet = {
  currency: string
  earnings: number
  ad_credit: number
  has_pending_payout: boolean
  tips: { id: number; amount: number; creator_amount: number; message: string; sender: string | null; sender_name: string; discussion: number | null; created_at: string }[]
  payouts: { id: number; amount: number; network: string; phone_number: string; status: 'requested' | 'paid' | 'rejected'; status_label: string; note: string; created_at: string }[]
  activity: { id: number; account: 'earnings' | 'ad_credit'; kind: string; amount: number; description: string; created_at: string }[]
}

export type Referrals = {
  invite_url: string
  reward: number
  currency: string
  joined: number
  confirmed: number
  credit_earned: number
  leaderboard: { username: string; display_name: string; joined: number }[]
}

export type PaymentStatus = {
  reference: string
  status: 'pending' | 'successful' | 'failed'
  purpose: 'tip' | 'promotion'
  amount: number
  currency: string
  failure_reason: string
  recipient?: string
  discussion?: number | null
  promotion?: Promotion
}

export function formatMoney(amount: number, currency = 'TZS'): string {
  return `${currency} ${Math.round(amount).toLocaleString('en-US')}`
}

export function useMoneyConfig() {
  return useQuery({ queryKey: ['money-config'], staleTime: 10 * 60_000, queryFn: async () => (await api.get<MoneyConfig>('/money/config/')).data })
}

/** Where the gateway sends the payer back to. Remembered so /pay/return can find it. */
const PENDING_KEY = 'commonground:pending-payment'

export function rememberPayment(reference: string) {
  try { sessionStorage.setItem(PENDING_KEY, reference) } catch { /* private mode */ }
}

export function recallPayment(): string {
  try { return sessionStorage.getItem(PENDING_KEY) || '' } catch { return '' }
}

export function goToCheckout(url: string, reference: string) {
  rememberPayment(reference)
  window.location.assign(url)
}

/** Counts a sponsored post being seen or clicked (once per viewer per day, server-side). */
export function recordPromotion(id: number, event: 'seen' | 'click') {
  void api.post(`/promotions/${id}/${event}/`).catch(() => undefined)
}
