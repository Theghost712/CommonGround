import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Clock3, XCircle } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { formatMoney, recallPayment, type PaymentStatus } from '../services/money'
import '../money.css'

/** The payment page sends people back here. We ask our server, which asks the gateway. */
export default function PayReturnPage() {
  const [params] = useSearchParams()
  const client = useQueryClient()
  const reference = params.get('tx_ref') || recallPayment()
  const [attempts, setAttempts] = useState(0)
  const query = useQuery({
    queryKey: ['payment', reference, attempts],
    enabled: /^cg-[0-9a-f]{32}$/.test(reference),
    queryFn: async () => (await api.get<PaymentStatus>(`/payments/${reference}/`)).data,
  })
  const payment = query.data

  // Mobile money can take a minute to confirm: check again a few times.
  useEffect(() => {
    if (payment?.status !== 'pending' || attempts >= 12) return
    const timer = setTimeout(() => setAttempts((n) => n + 1), 5000)
    return () => clearTimeout(timer)
  }, [payment?.status, attempts])

  useEffect(() => {
    if (payment?.status === 'successful') for (const key of ['wallet', 'my-promotions', 'referrals']) client.invalidateQueries({ queryKey: [key] })
  }, [payment?.status, client])

  if (!reference) return <div className="empty-card"><h3>No payment to check</h3><Link to="/earnings" className="button button-primary">Go to Earnings</Link></div>
  if (query.isLoading) return <div className="loading-card">Checking your payment…</div>
  if (query.error || !payment) return <div className="error-card">{getErrorMessage(query.error)}</div>

  const amount = formatMoney(payment.amount, payment.currency)
  return <section className="pay-result">
    {payment.status === 'successful' && <>
      <CheckCircle2 size={52} className="pay-ok" />
      <h1>Thank you!</h1>
      {payment.purpose === 'tip'
        ? <p>Your tip of {amount} was sent to @{payment.recipient}.</p>
        : <p>We received {amount}. {payment.promotion?.status === 'active' ? 'Your sponsored post is live.' : 'We review sponsored posts quickly, usually within a day, and let you know when it goes live.'}</p>}
      {payment.purpose === 'tip'
        ? <Link className="button button-primary" to={payment.discussion ? `/discussions/${payment.discussion}` : `/u/${payment.recipient}`}>Back to {payment.discussion ? 'the post' : 'their profile'}</Link>
        : <Link className="button button-primary" to="/earnings">See my sponsored posts</Link>}
    </>}
    {payment.status === 'pending' && <>
      <Clock3 size={52} className="pay-wait" />
      <h1>Waiting for confirmation</h1>
      <p>If you were asked to approve {amount} on your phone, enter your PIN there. This page updates by itself.</p>
      {attempts >= 12 && <button type="button" className="button button-outline" onClick={() => setAttempts(0)}>Check again</button>}
    </>}
    {payment.status === 'failed' && <>
      <XCircle size={52} className="pay-fail" />
      <h1>Payment not completed</h1>
      <p>{payment.failure_reason || 'The payment was cancelled or declined.'} If money left your account anyway, contact us with reference {payment.reference}.</p>
      <Link className="button button-primary" to={payment.purpose === 'tip' && payment.recipient ? `/u/${payment.recipient}` : '/earnings'}>Try again</Link>
    </>}
  </section>
}
