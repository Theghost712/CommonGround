import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Coins, Megaphone, Smartphone, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { formatMoney, goToCheckout, useMoneyConfig, type Promotion } from '../services/money'
import '../money.css'

const TIP_PRESETS = [1000, 2000, 5000, 10000]

function Dialog({ label, icon, onClose, children }: { label: string; icon: React.ReactNode; onClose: () => void; children: React.ReactNode }) {
  return createPortal(<div className="money-backdrop" onClick={onClose}>
    <section className="money-dialog" role="dialog" aria-modal="true" aria-label={label} onClick={(event) => event.stopPropagation()}>
      <header><strong>{icon} {label}</strong><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button></header>
      {children}
    </section>
  </div>, document.body)
}

function PaymentNote({ testMode }: { testMode?: boolean }) {
  return <p className="money-note"><Smartphone size={14} /> {testMode
    ? 'Test mode: no real money moves. The payment succeeds at once.'
    : 'Pay with M-Pesa, Mixx by Yas (Tigo Pesa), Airtel Money, HaloPesa or a card on the secure Flutterwave page.'}</p>
}

/** Send money to a creator, optionally for one of their posts. */
export function TipDialog({ username, displayName, discussionId, onClose }: { username: string; displayName?: string; discussionId?: number; onClose: () => void }) {
  const config = useMoneyConfig()
  const [amount, setAmount] = useState(2000)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const currency = config.data?.currency || 'TZS'
  const min = config.data?.tip_min ?? 500
  const max = config.data?.tip_max ?? 1_000_000
  const valid = Number.isFinite(amount) && amount >= min && amount <= max

  const send = async () => {
    setSending(true); setError('')
    try {
      const { data } = await api.post<{ checkout_url: string; reference: string }>('/tips/', discussionId ? { discussion: discussionId, amount, message: message.trim() } : { username, amount, message: message.trim() })
      goToCheckout(data.checkout_url, data.reference)
    } catch (err) {
      setError(getErrorMessage(err))
      setSending(false)
    }
  }

  return <Dialog label={`Tip ${displayName || username}`} icon={<Coins size={16} />} onClose={onClose}>
    {config.data && !config.data.enabled
      ? <p className="money-intro">Tips are not available yet. Please check back soon.</p>
      : <>
        <p className="money-intro">Say thanks with money. {displayName || `@${username}`} receives {100 - (config.data?.tip_fee_percent ?? 10)}% of your tip.</p>
        <div className="money-presets" role="radiogroup" aria-label="Amount">
          {TIP_PRESETS.map((value) => <button key={value} type="button" role="radio" aria-checked={amount === value} className={amount === value ? 'active' : ''} onClick={() => setAmount(value)}>{formatMoney(value, currency)}</button>)}
        </div>
        <label className="money-field"><span>Other amount ({currency})</span><input type="number" inputMode="numeric" min={min} max={max} step={100} value={Number.isFinite(amount) ? amount : ''} onChange={(event) => setAmount(Math.round(Number(event.target.value)))} /></label>
        {!valid && <div className="error-message">Choose {formatMoney(min, currency)} to {formatMoney(max, currency)}.</div>}
        <label className="money-field"><span>Message (optional)</span><input value={message} maxLength={200} onChange={(event) => setMessage(event.target.value)} placeholder="Keep it up!" /></label>
        <PaymentNote testMode={config.data?.test_mode} />
        {error && <div className="error-message">{error}</div>}
        <button type="button" className="button button-primary" disabled={!valid || sending || !config.data} onClick={() => void send()}>{sending ? 'Opening payment…' : `Pay ${formatMoney(valid ? amount : 0, currency)}`}</button>
      </>}
  </Dialog>
}

type Quote = { days: number; daily_price: number; total: number; credit_used: number; amount_due: number }

/** Pay to show one of your posts in other members' feeds. */
export function PromoteDialog({ discussionId, onClose }: { discussionId: number; onClose: () => void }) {
  const config = useMoneyConfig()
  const [days, setDays] = useState(3)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState<Promotion | null>(null)
  const maxDays = config.data?.promotion_max_days ?? 30
  const quote = useQuery({ queryKey: ['promotion-quote', days], queryFn: async () => (await api.get<Quote>('/promotions/quote/', { params: { days } })).data })
  const currency = config.data?.currency || 'TZS'

  const start = async () => {
    setSending(true); setError('')
    try {
      const { data } = await api.post<{ promotion: Promotion; checkout_url: string | null; reference: string | null }>('/promotions/', { discussion: discussionId, days })
      if (data.checkout_url && data.reference) goToCheckout(data.checkout_url, data.reference)
      else { setSubmitted(data.promotion); setSending(false) }
    } catch (err) {
      setError(getErrorMessage(err))
      setSending(false)
    }
  }

  return <Dialog label="Promote this post" icon={<Megaphone size={16} />} onClose={onClose}>
    {submitted
      ? <div className="money-done"><CheckCircle2 size={40} /><p>{submitted.status === 'active' ? 'Your sponsored post is live.' : 'Paid with your ad credit. We review sponsored posts quickly, usually within a day.'}</p><Link to="/earnings" className="button button-primary" onClick={onClose}>See my sponsored posts</Link></div>
      : config.data && !config.data.enabled
        ? <p className="money-intro">Sponsored posts are not available yet. Please check back soon.</p>
        : <>
          <p className="money-intro">Your post appears in other members&apos; feeds, marked &ldquo;Sponsored&rdquo;. Every sponsored post is reviewed before it runs; if we can&apos;t approve it, you get the full amount back as ad credit.</p>
          <label className="money-field"><span>How many days? <strong>{days}</strong></span><input type="range" min={1} max={maxDays} value={days} onChange={(event) => setDays(Number(event.target.value))} /></label>
          {quote.data && <dl className="money-quote">
            <div><dt>{quote.data.days} day{quote.data.days === 1 ? '' : 's'} × {formatMoney(quote.data.daily_price, currency)}</dt><dd>{formatMoney(quote.data.total, currency)}</dd></div>
            {quote.data.credit_used > 0 && <div><dt>Your ad credit</dt><dd>−{formatMoney(quote.data.credit_used, currency)}</dd></div>}
            <div className="total"><dt>To pay</dt><dd>{formatMoney(quote.data.amount_due, currency)}</dd></div>
          </dl>}
          {quote.data && quote.data.amount_due > 0 && <PaymentNote testMode={config.data?.test_mode} />}
          {error && <div className="error-message">{error}</div>}
          <button type="button" className="button button-primary" disabled={sending || !quote.data} onClick={() => void start()}>{sending ? 'Please wait…' : quote.data?.amount_due === 0 ? 'Promote with ad credit' : `Pay ${formatMoney(quote.data?.amount_due ?? 0, currency)}`}</button>
          <p className="money-note">Invite friends to earn free ad credit. <Link to="/earnings" onClick={onClose}>Get your invite link</Link></p>
        </>}
  </Dialog>
}
