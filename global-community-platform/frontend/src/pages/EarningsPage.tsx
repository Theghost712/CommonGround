import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Coins, Copy, Gift, Megaphone, Send, Trophy, Wallet as WalletIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { formatMoney, useMoneyConfig, type Promotion, type Referrals, type Wallet } from '../services/money'
import '../money.css'

const date = (value: string) => new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

function InviteCard() {
  const { data } = useQuery({ queryKey: ['referrals'], queryFn: async () => (await api.get<Referrals>('/money/referrals/')).data })
  const [copied, setCopied] = useState(false)
  if (!data) return <section className="money-card"><div className="loading-card">Loading your invite link…</div></section>
  const text = `Join me on CommonGround, a place for good conversations and communities: ${data.invite_url}`
  const copy = async () => {
    try { await navigator.clipboard.writeText(data.invite_url); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { window.prompt('Copy your invite link', data.invite_url) }
  }
  const share = async () => {
    if (navigator.share) { try { await navigator.share({ title: 'CommonGround', text, url: data.invite_url }) } catch { /* cancelled */ } } else void copy()
  }
  return <section className="money-card invite-card" aria-labelledby="invite-heading">
    <div className="money-card-head"><Gift size={20} /><div><h2 id="invite-heading">Invite friends, earn ad credit</h2><p>You get <strong>{formatMoney(data.reward, data.currency)}</strong> ad credit for every friend who joins with your link and confirms their email. Use it to promote your posts.</p></div></div>
    <div className="invite-link-row"><input readOnly value={data.invite_url} aria-label="Your invite link" onFocus={(event) => event.currentTarget.select()} /><button type="button" className="button button-outline" onClick={() => void copy()}>{copied ? <><Check size={15} /> Copied</> : <><Copy size={15} /> Copy</>}</button></div>
    <div className="invite-share-row">
      <a className="button invite-whatsapp" href={`https://wa.me/?text=${encodeURIComponent(text)}`} target="_blank" rel="noopener noreferrer">Share on WhatsApp</a>
      <a className="button button-outline" href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(data.invite_url)}`} target="_blank" rel="noopener noreferrer">Facebook</a>
      <a className="button button-outline" href={`https://x.com/intent/post?text=${encodeURIComponent(text)}`} target="_blank" rel="noopener noreferrer">X</a>
      {'share' in navigator && <button type="button" className="button button-outline" onClick={() => void share()}><Send size={15} /> More</button>}
    </div>
    <div className="money-stats"><div><strong>{data.joined}</strong><span>joined</span></div><div><strong>{data.confirmed}</strong><span>confirmed</span></div><div><strong>{formatMoney(data.credit_earned, data.currency)}</strong><span>credit earned</span></div></div>
    {data.leaderboard.length > 0 && <div className="leaderboard"><h3><Trophy size={15} /> Top inviters this month</h3><ol>{data.leaderboard.map((row) => <li key={row.username}><Link to={`/u/${row.username}`}>{row.display_name}</Link><span>{row.joined} joined</span></li>)}</ol></div>}
  </section>
}

function PayoutForm({ wallet }: { wallet: Wallet }) {
  const config = useMoneyConfig()
  const client = useQueryClient()
  const min = config.data?.payout_min ?? 5000
  const [form, setForm] = useState({ amount: wallet.earnings, network: 'mpesa', phone_number: '', account_name: '' })
  const [done, setDone] = useState(false)
  const mutation = useMutation({
    mutationFn: () => api.post('/money/wallet/', form),
    onSuccess: () => { setDone(true); client.invalidateQueries({ queryKey: ['wallet'] }) },
  })
  if (wallet.has_pending_payout || done) return <p className="money-note"><Check size={14} /> Your payout request is with our team. We send it to your mobile money, usually within 2 working days.</p>
  if (wallet.earnings < min) return <p className="money-note">You can ask for a payout once you have {formatMoney(min, wallet.currency)}.</p>
  const submit = (event: FormEvent) => { event.preventDefault(); mutation.mutate() }
  return <form className="payout-form" onSubmit={submit}>
    <label className="money-field"><span>Amount ({wallet.currency})</span><input type="number" min={min} max={wallet.earnings} value={form.amount} onChange={(event) => setForm({ ...form, amount: Math.round(Number(event.target.value)) })} required /></label>
    <label className="money-field"><span>Mobile money</span><select value={form.network} onChange={(event) => setForm({ ...form, network: event.target.value })}>{(config.data?.payout_networks || [{ value: 'mpesa', label: 'M-Pesa' }]).map((n) => <option key={n.value} value={n.value}>{n.label}</option>)}</select></label>
    <label className="money-field"><span>Phone number</span><input type="tel" inputMode="tel" placeholder="0712 345 678" value={form.phone_number} onChange={(event) => setForm({ ...form, phone_number: event.target.value })} required /></label>
    <label className="money-field"><span>Name on the account</span><input value={form.account_name} maxLength={120} onChange={(event) => setForm({ ...form, account_name: event.target.value })} required /></label>
    {mutation.error && <div className="error-message">{getErrorMessage(mutation.error)}</div>}
    <button className="button button-primary" disabled={mutation.isPending}>{mutation.isPending ? 'Sending…' : 'Ask for payout'}</button>
  </form>
}

function PromotionRow({ promotion, currency }: { promotion: Promotion; currency: string }) {
  const status = promotion.status === 'active' && !promotion.is_running ? 'Finished' : promotion.status_label
  return <li className="money-row">
    <div><Link to={`/discussions/${promotion.discussion}`}>{promotion.discussion_title || 'Your post'}</Link>
      <span>{promotion.days} day{promotion.days === 1 ? '' : 's'} · {formatMoney(promotion.total_price, currency)}{promotion.ends_at ? ` · until ${date(promotion.ends_at)}` : ''}</span>
      {promotion.rejection_reason && <span className="money-reason">{promotion.rejection_reason}</span>}</div>
    <div className="money-row-side"><span className={`money-status status-${promotion.is_running ? 'running' : promotion.status}`}>{promotion.is_running ? 'Running' : status}</span>{promotion.impressions > 0 && <small>{promotion.impressions.toLocaleString()} {promotion.impressions === 1 ? 'view' : 'views'} · {promotion.clicks.toLocaleString()} {promotion.clicks === 1 ? 'click' : 'clicks'}</small>}</div>
  </li>
}

export default function EarningsPage() {
  const wallet = useQuery({ queryKey: ['wallet'], queryFn: async () => (await api.get<Wallet>('/money/wallet/')).data })
  const promotions = useQuery({ queryKey: ['my-promotions'], queryFn: async () => (await api.get<Promotion[]>('/promotions/')).data })
  const config = useMoneyConfig()
  const data = wallet.data
  const currency = data?.currency || 'TZS'

  return <section className="earnings-page">
    <div className="page-intro-row"><div><span className="eyebrow">MONEY & INVITES</span><h1>Earnings</h1><p>Tips from your fans, your sponsored posts, and credit for inviting friends.</p></div><div className="bookmarks-page-icon"><WalletIcon size={22} /></div></div>
    {config.data?.test_mode && <div className="money-test-banner">Test mode: payments are simulated and no real money moves.</div>}
    {wallet.error && <div className="error-card">{getErrorMessage(wallet.error)}</div>}
    {data && <div className="money-balances">
      <div className="money-balance"><Coins size={18} /><span>Earnings you can withdraw</span><strong>{formatMoney(data.earnings, currency)}</strong></div>
      <div className="money-balance credit"><Megaphone size={18} /><span>Ad credit for sponsored posts</span><strong>{formatMoney(data.ad_credit, currency)}</strong></div>
    </div>}

    <InviteCard />

    {data && <section className="money-card"><div className="money-card-head"><Coins size={20} /><div><h2>Withdraw to mobile money</h2><p>Members tip you from the ⋯ menu on your posts or the Tip button on a discussion. You keep {100 - (config.data?.tip_fee_percent ?? 10)}% of each tip.</p></div></div><PayoutForm wallet={data} />
      {data.payouts.length > 0 && <ul className="money-list">{data.payouts.map((p) => <li className="money-row" key={p.id}><div><strong>{formatMoney(p.amount, currency)}</strong><span>{p.network} · {date(p.created_at)}</span>{p.note && <span className="money-reason">{p.note}</span>}</div><span className={`money-status status-${p.status}`}>{p.status_label}</span></li>)}</ul>}
    </section>}

    <section className="money-card"><div className="money-card-head"><Megaphone size={20} /><div><h2>Sponsored posts</h2><p>Reach more people: open one of your public posts, choose ⋯ then <em>Promote post</em>. From {formatMoney(config.data?.promotion_daily_price ?? 3000, currency)} a day.</p></div></div>
      {promotions.data && promotions.data.length === 0 && <p className="money-note">You haven&apos;t promoted a post yet.</p>}
      {promotions.data && promotions.data.length > 0 && <ul className="money-list">{promotions.data.map((p) => <PromotionRow key={p.id} promotion={p} currency={currency} />)}</ul>}
    </section>

    {data && data.tips.length > 0 && <section className="money-card"><div className="money-card-head"><Gift size={20} /><div><h2>Tips you received</h2></div></div>
      <ul className="money-list">{data.tips.map((tip) => <li className="money-row" key={tip.id}><div>{tip.sender ? <Link to={`/u/${tip.sender}`}><strong>{tip.sender_name}</strong></Link> : <strong>{tip.sender_name}</strong>}{tip.message && <span>“{tip.message}”</span>}<span>{date(tip.created_at)}{tip.discussion ? <> · <Link to={`/discussions/${tip.discussion}`}>for your post</Link></> : null}</span></div><strong className="money-plus">+{formatMoney(tip.creator_amount, currency)}</strong></li>)}</ul>
    </section>}

    {data && data.activity.length > 0 && <details className="money-card money-activity"><summary>All activity</summary>
      <ul className="money-list">{data.activity.map((entry) => <li className="money-row" key={entry.id}><div><strong>{entry.kind}</strong><span>{entry.description} · {date(entry.created_at)} · {entry.account === 'earnings' ? 'Earnings' : 'Ad credit'}</span></div><strong className={entry.amount >= 0 ? 'money-plus' : 'money-minus'}>{entry.amount >= 0 ? '+' : '−'}{formatMoney(Math.abs(entry.amount), currency)}</strong></li>)}</ul>
    </details>}
  </section>
}
