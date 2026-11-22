import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import AppLayout from './components/AppLayout'
import AuthPage from './pages/AuthPage'

// Each page is its own chunk, loaded on first visit: the first screen downloads far less.
const EventsCalendarPage = lazy(() => import('./pages/EventsCalendarPage'))
const HomePage = lazy(() => import('./pages/HomePage'))
const CommunitiesPage = lazy(() => import('./pages/CommunitiesPage'))
const CommunityDetailPage = lazy(() => import('./pages/CommunityDetailPage'))
const CreateDiscussionPage = lazy(() => import('./pages/CreateDiscussionPage'))
const DiscussionPage = lazy(() => import('./pages/DiscussionPage'))
const BookmarksPage = lazy(() => import('./pages/BookmarksPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'))
const NotificationPreferencesPage = lazy(() => import('./pages/NotificationPreferencesPage'))
const ExplorePage = lazy(() => import('./pages/InfoPage').then((m) => ({ default: m.ExplorePage })))
const PeoplePage = lazy(() => import('./pages/PeoplePage'))
const UserProfilePage = lazy(() => import('./pages/UserProfilePage'))
const FollowRequestsPage = lazy(() => import('./pages/FollowRequestsPage'))
const PrivacySettingsPage = lazy(() => import('./pages/PrivacySettingsPage'))
const TagPage = lazy(() => import('./pages/TagPage'))
const AccountSecurityPage = lazy(() => import('./pages/AccountSecurityPage'))
const ReelsPage = lazy(() => import('./pages/ReelsPage'))
const ModerationPage = lazy(() => import('./pages/ModerationPage'))
const ForgotPasswordPage = lazy(() => import('./pages/AccountRecoveryPages').then((m) => ({ default: m.ForgotPasswordPage })))
const ResetPasswordPage = lazy(() => import('./pages/AccountRecoveryPages').then((m) => ({ default: m.ResetPasswordPage })))
const VerifyEmailPage = lazy(() => import('./pages/AccountRecoveryPages').then((m) => ({ default: m.VerifyEmailPage })))

function ProtectedLayout() {
  const { user, loading } = useAuth()
  if (loading) return <div className="app-loading">Loading CommonGround…</div>
  return user ? <AppLayout /> : <Navigate to="/login" replace />
}

export default function App() {
  const { user } = useAuth()
  return <Suspense fallback={<div className="app-loading">Loading…</div>}><Routes>
    <Route path="/login" element={user ? <Navigate to="/home" replace /> : <AuthPage mode="login" />} />
    <Route path="/register" element={user ? <Navigate to="/home" replace /> : <AuthPage mode="register" />} />
    <Route path="/forgot-password" element={<ForgotPasswordPage />} />
    <Route path="/reset-password" element={<ResetPasswordPage />} />
    {/* Works signed in or out: the emailed link is the proof. */}
    <Route path="/verify-email" element={<VerifyEmailPage />} />
    <Route element={<ProtectedLayout />}>
      <Route path="/" element={<Navigate to="/home" replace />} />
      <Route path="/home" element={<HomePage />} />
      <Route path="/explore" element={<ExplorePage />} />
      <Route path="/reels" element={<ReelsPage />} />
      <Route path="/communities" element={<CommunitiesPage />} />
      <Route path="/communities/:id" element={<CommunityDetailPage />} />
      <Route path="/events-calendar" element={<EventsCalendarPage />} />
      <Route path="/discussions/new" element={<CreateDiscussionPage />} />
      <Route path="/discussions/:id" element={<DiscussionPage />} />
      <Route path="/discussions/:id/edit" element={<CreateDiscussionPage />} />
      <Route path="/bookmarks" element={<BookmarksPage />} />
      <Route path="/messages" element={<ChatPage />} />
      <Route path="/notifications" element={<NotificationsPage />} />
      <Route path="/notifications/preferences" element={<NotificationPreferencesPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/people" element={<PeoplePage />} />
      <Route path="/people/requests" element={<FollowRequestsPage />} />
      <Route path="/settings/privacy" element={<PrivacySettingsPage />} />
      <Route path="/settings/security" element={<AccountSecurityPage />} />
      <Route path="/moderation" element={<ModerationPage />} />
      <Route path="/tags/:name" element={<TagPage />} />
      <Route path="/u/:username" element={<UserProfilePage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense>
}
