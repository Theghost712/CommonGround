import { Suspense } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import '../money.css'

/** Signed-out visitors (and search engines) reading a public discussion or community. */
export default function PublicLayout() {
  const { pathname } = useLocation()
  const next = encodeURIComponent(pathname)
  return <div className="public-shell">
    <header className="public-topbar">
      <Link to="/register" className="brand-row"><div className="brand-mark"><Sparkles size={19} /></div><span>commonground</span></Link>
      <nav className="public-topbar-actions"><Link to={`/login?next=${next}`} className="button button-outline">Sign in</Link><Link to={`/register?next=${next}`} className="button button-primary">Join free</Link></nav>
    </header>
    <main className="public-content"><Suspense fallback={<div className="loading-card">Loading…</div>}><Outlet /></Suspense></main>
    <div className="public-join"><span>Join CommonGround to comment, follow people and find your communities.</span><Link to={`/register?next=${next}`} className="button">Create a free account</Link></div>
  </div>
}

/** Shown in place of comment boxes and reaction buttons when signed out. */
export function JoinPrompt({ action }: { action: string }) {
  const { pathname } = useLocation()
  const next = encodeURIComponent(pathname)
  return <div className="join-prompt"><span>{action}</span><span><Link to={`/login?next=${next}`} className="button button-outline">Sign in</Link> <Link to={`/register?next=${next}`} className="button button-primary">Join free</Link></span></div>
}
