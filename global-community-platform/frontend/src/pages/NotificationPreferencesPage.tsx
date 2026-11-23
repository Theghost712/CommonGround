import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Bell, BellRing, Check, MessageCircle, MessageSquare, Users, AtSign, ShieldCheck, UserPlus, Volume2 } from 'lucide-react'
import { playNotificationSound, popupsSupported, requestPopupPermission } from '../context/notificationAlerts'
import { Link } from 'react-router-dom'
import PushCard from '../components/PushCard'
import { api, getErrorMessage } from '../services/api'

type Preferences = {
  messages_enabled: boolean
  discussions_enabled: boolean
  communities_enabled: boolean
  mentions_enabled: boolean
  system_enabled: boolean
  social_enabled: boolean
  sound_enabled: boolean
  popup_enabled: boolean
}

const defaults: Preferences = {
  messages_enabled: true,
  discussions_enabled: true,
  communities_enabled: true,
  mentions_enabled: true,
  system_enabled: true,
  social_enabled: true,
  sound_enabled: true,
  popup_enabled: true,
}

const options: { key: keyof Preferences; title: string; description: string; icon: typeof Bell }[] = [
  { key: 'messages_enabled', title: 'Messages', description: 'New private and group chat messages.', icon: MessageCircle },
  { key: 'discussions_enabled', title: 'Discussions', description: 'Comments, replies and reactions to your posts.', icon: MessageSquare },
  { key: 'communities_enabled', title: 'Communities', description: 'Membership requests, approvals and announcements.', icon: Users },
  { key: 'mentions_enabled', title: 'Mentions', description: 'When someone mentions your username with @.', icon: AtSign },
  { key: 'social_enabled', title: 'New followers', description: 'When someone starts following you.', icon: UserPlus },
  { key: 'system_enabled', title: 'System updates', description: 'Important platform and account updates.', icon: ShieldCheck },
]

function permissionText(permission: NotificationPermission | 'unsupported') {
  if (permission === 'granted') return 'Pop-ups are allowed in this browser.'
  if (permission === 'denied') return 'Pop-ups are blocked. Allow notifications for this site in your browser settings.'
  if (permission === 'unsupported') return 'This browser cannot show pop-up notifications.'
  return 'Your browser will ask for permission once.'
}

export default function NotificationPreferencesPage() {
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>(() => popupsSupported() ? Notification.permission : 'unsupported')
  const [soundNote, setSoundNote] = useState('')
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Preferences>(defaults)
  const [notice, setNotice] = useState('')
  const { data, isLoading, error } = useQuery({ queryKey: ['notification-preferences'], queryFn: async () => (await api.get<Preferences>('/notifications/preferences/')).data })
  useEffect(() => { if (data) setForm({ ...defaults, ...data }) }, [data])
  const mutation = useMutation({
    mutationFn: async () => (await api.patch('/notifications/preferences/', form)).data,
    onSuccess: (result) => { queryClient.setQueryData(['notification-preferences'], result); setNotice('Notification preferences saved.') },
    onError: (err) => setNotice(getErrorMessage(err)),
  })
  const submit = (event: FormEvent) => { event.preventDefault(); setNotice(''); mutation.mutate() }

  if (isLoading) return <div className="loading-card">Loading preferences…</div>
  if (error) return <div className="error-card">{getErrorMessage(error)}</div>

  return <section className="notification-preferences-page">
    <Link to="/notifications" className="back-link"><ArrowLeft size={16} /> Back to notifications</Link>
    <div className="page-intro-row"><div><span className="eyebrow">MAKE IT YOURS</span><h1>Notification preferences</h1><p>Choose the updates you would like CommonGround to send you.</p></div></div>
    <form className="preferences-card" onSubmit={submit}>
      {options.map(({ key, title, description, icon: Icon }) => <label className="preference-row" key={key}>
        <div className="preference-icon"><Icon size={18} /></div><div className="preference-copy"><strong>{title}</strong><span>{description}</span></div>
        <input type="checkbox" checked={form[key]} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.checked }))} />
      </label>)}
      <div className="preferences-subheading"><span className="eyebrow">HOW YOU ARE ALERTED</span><p>Applies on every device where you are signed in.</p></div>
      <PushCard />
      <label className="preference-row">
        <div className="preference-icon"><Volume2 size={18} /></div><div className="preference-copy"><strong>Play a sound</strong><span>A short chime when a new notification arrives.</span></div>
        <button type="button" className="text-button" onClick={(event) => { event.preventDefault(); setSoundNote(playNotificationSound() ? '' : 'Click anywhere on the page once, then try again (browsers block sound until you interact).') }}>Test sound</button>
        <input type="checkbox" checked={form.sound_enabled} onChange={(event) => setForm((current) => ({ ...current, sound_enabled: event.target.checked }))} />
      </label>
      {soundNote && <div className="form-hint">{soundNote}</div>}
      <label className="preference-row">
        <div className="preference-icon"><BellRing size={18} /></div><div className="preference-copy"><strong>Show pop-ups</strong><span>A system notification while CommonGround is open in a background tab. {permissionText(permission)}</span></div>
        {permission === 'default' && <button type="button" className="text-button" onClick={(event) => { event.preventDefault(); void requestPopupPermission().then(setPermission) }}>Allow pop-ups</button>}
        <input type="checkbox" checked={form.popup_enabled} onChange={(event) => setForm((current) => ({ ...current, popup_enabled: event.target.checked }))} />
      </label>
      {notice && <div className={mutation.isError ? 'error-message' : 'success-message'}>{notice}</div>}
      <div className="preferences-footer"><span>Saved to your account.</span><button className="button button-primary" disabled={mutation.isPending}><Check size={15} /> {mutation.isPending ? 'Saving…' : 'Save preferences'}</button></div>
    </form>
  </section>
}
