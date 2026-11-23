import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Bell,
  Bookmark,
  CalendarDays,
  Compass,
  Home,
  LogOut,
  MessageCircle,
  Users,
  Menu,
  X,
  Sparkles,
  UserRound,
  UsersRound,
  MailWarning,
  Clapperboard,
  Gavel,
} from 'lucide-react'
import { Suspense, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { NotificationsProvider, useNotifications } from '../context/NotificationsContext'
import '../notifications.css'
import { PresenceProvider, usePresence } from '../context/PresenceContext'
import { useNotificationAlerts } from '../context/notificationAlerts'
import { CallProvider } from '../context/CallContext'
import CallScreen from './CallScreen'
import GroupCallScreen, { GroupCallInvite } from './GroupCallScreen'
import { GroupCallProvider } from '../context/GroupCallContext'
import { api, getErrorMessage } from '../services/api'
import '../account-security.css'

const links = [
  { to: '/home', label: 'Home feed', icon: Home },
  { to: '/explore', label: 'Explore', icon: Compass },
  { to: '/reels', label: 'Reels', icon: Clapperboard },
  { to: '/people', label: 'People', icon: UsersRound },
  { to: '/communities', label: 'Communities', icon: Users },
  { to: '/events-calendar', label: 'Events Calendar', icon: CalendarDays },
  { to: '/messages', label: 'Messages', icon: MessageCircle },
]
const BANNER_DISMISSED = 'commonground:verify-banner-dismissed'

function readDismissed() {
  try { return sessionStorage.getItem(BANNER_DISMISSED) === '1' } catch { return false }
}

/** Reminds signed-in people with an unconfirmed email (needed for password resets). */
function VerifyEmailBanner() {
  const { user } = useAuth()
  const [dismissed, setDismissed] = useState(readDismissed)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  if (!user || user.email_verified || !user.email || dismissed) return null
  const resend = async () => {
    setBusy(true)
    try { setMessage((await api.post<{ detail: string }>('/auth/email/resend/')).data.detail) }
    catch (err) { setMessage(getErrorMessage(err)) }
    finally { setBusy(false) }
  }
  const dismiss = () => { setDismissed(true); try { sessionStorage.setItem(BANNER_DISMISSED, '1') } catch { /* private mode */ } }
  return <div className="verify-banner" role="status">
    <MailWarning size={16} />
    <span>{message || <>Please confirm your email <strong>{user.email}</strong> so you can reset your password if you ever forget it.</>}</span>
    {!message && <button type="button" disabled={busy} onClick={resend}>{busy ? 'Sending…' : 'Send link'}</button>}
    <Link to="/settings/security">Settings</Link>
    <button type="button" className="verify-banner-close" aria-label="Hide this reminder" onClick={dismiss}><X size={15} /></button>
  </div>
}

function AppLayoutContent() {
  const { user, logout } = useAuth()
  const { unreadCount } = useNotifications()
  useNotificationAlerts(unreadCount)
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const initials = (user?.first_name?.[0] || user?.username?.[0] || 'U').toUpperCase()
  const closeMenu = () => setMobileOpen(false)
  const { connected: presenceConnected } = usePresence()

  return <div className="app-shell">
    {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={closeMenu} />}
    <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
      <div className="brand-row"><div className="brand-mark"><Sparkles size={19} /></div><span>commonground</span><button className="icon-button sidebar-close" onClick={closeMenu}><X size={18} /></button></div>
      <div className="workspace-label">YOUR SPACE</div>
      <nav className="main-nav">{links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} onClick={closeMenu} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={18} strokeWidth={1.9} /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-divider" />
      <div className="workspace-label">YOUR ACCOUNT</div>
      <NavLink to="/bookmarks" onClick={closeMenu} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Bookmark size={18} /><span>Saved discussions</span></NavLink>
      <NavLink to="/notifications" onClick={closeMenu} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Bell size={18} /><span>Notifications</span>{unreadCount > 0 && <span className="notification-nav-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>}</NavLink>
      <NavLink to="/profile" onClick={closeMenu} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><UserRound size={18} /><span>My profile</span></NavLink>
      {user?.can_moderate && <NavLink to="/moderation" onClick={closeMenu} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Gavel size={18} /><span>Moderation</span></NavLink>}
      <div className="sidebar-bottom">
        <div className="sidebar-note"><div className="note-icon"><Sparkles size={16} /></div><strong>Good conversations<br />start here.</strong><p>Bring your curiosity. Find your people.</p></div>
        <div className="profile-mini"><Link to={`/u/${user?.username}`} onClick={closeMenu} className="profile-mini-link" title="View your public profile"><div className="avatar">{initials}</div><div className="profile-mini-text"><strong>{user?.first_name || user?.username}</strong><span>@{user?.username}</span></div></Link><button className="icon-button logout-button" title="Log out" onClick={async () => { await logout(); navigate('/login') }}><LogOut size={17} /></button></div>
      </div>
    </aside>
    <main className="main-area">
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)}><Menu size={21} /></button><div className="breadcrumb">Community <span>/</span> <strong>Discover together</strong></div><div className="topbar-actions"><span className="topbar-status">
  <i />
  {presenceConnected ? 'Presence Live' : 'Connecting Presence...'}
</span><Link to={`/u/${user?.username}`} className="avatar avatar-small" title="Your profile" aria-label="Your profile">{initials}</Link></div></header>
      <VerifyEmailBanner />
      <div className="page-content"><Suspense fallback={<div className="loading-card">Loading…</div>}><Outlet /></Suspense></div>
    </main>
  </div>
}


export default function AppLayout() {
  return (
    <PresenceProvider>
      <NotificationsProvider>
        <CallProvider>
          <GroupCallProvider>
            <AppLayoutContent />
            <CallScreen />
            <GroupCallScreen />
            <GroupCallInvite />
          </GroupCallProvider>
        </CallProvider>
      </NotificationsProvider>
    </PresenceProvider>
  )
}
