import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, Globe2, KeyRound, MapPin, Phone, Save, ShieldCheck, UserRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'

type Profile = {
  id: number
  username: string
  email: string
  first_name: string
  last_name: string
  date_joined: string
  bio: string
  country: string
  preferred_language: string
  interests: string
  avatar_url: string
  website: string
  phone_number: string
  discoverable_by_contacts: boolean
}

type ProfileForm = Pick<Profile, 'first_name' | 'last_name' | 'bio' | 'country' | 'preferred_language' | 'interests' | 'avatar_url' | 'website' | 'phone_number' | 'discoverable_by_contacts'>

const emptyForm: ProfileForm = {
  first_name: '', last_name: '', bio: '', country: '', preferred_language: 'en',
  interests: '', avatar_url: '', website: '', phone_number: '', discoverable_by_contacts: false,
}

export default function ProfilePage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<ProfileForm>(emptyForm)
  const [notice, setNotice] = useState('')
  const { data, isLoading, error } = useQuery({
    queryKey: ['my-profile'],
    queryFn: async () => (await api.get<Profile>('/auth/profile/')).data,
  })

  useEffect(() => {
    if (data) {
      setForm({
        first_name: data.first_name || '', last_name: data.last_name || '',
        bio: data.bio || '', country: data.country || '',
        preferred_language: data.preferred_language || 'en',
        interests: data.interests || '', avatar_url: data.avatar_url || '',
        website: data.website || '', phone_number: data.phone_number || '',
        discoverable_by_contacts: Boolean(data.discoverable_by_contacts),
      })
    }
  }, [data])

  const updateMutation = useMutation({
    mutationFn: async () => (await api.patch<Profile>('/auth/profile/', form)).data,
    onSuccess: (profile) => {
      queryClient.setQueryData(['my-profile'], profile)
      queryClient.invalidateQueries({ queryKey: ['my-profile'] })
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['person', profile.username] })
      setNotice('Your profile has been updated.')
    },
    onError: (err) => setNotice(getErrorMessage(err)),
  })

  const setField = <K extends keyof ProfileForm>(field: K, value: ProfileForm[K]) => {
    setForm((current) => ({ ...current, [field]: value }))
    setNotice('')
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setNotice('')
    updateMutation.mutate()
  }

  if (isLoading) return <div className="loading-card">Loading your profile…</div>
  if (error) return <div className="error-card">{getErrorMessage(error)}</div>
  if (!data) return <div className="error-card">Your profile could not be loaded.</div>

  const displayName = [form.first_name, form.last_name].filter(Boolean).join(' ') || data.username
  const initials = displayName.slice(0, 1).toUpperCase()

  return <section className="profile-page">
    <div className="page-intro-row">
      <div><span className="eyebrow">YOUR IDENTITY</span><h1>Your profile</h1><p>Tell the community a little about yourself and the conversations you care about.</p></div>
      <Link to={`/u/${data.username}`} className="button button-outline">View public profile <ArrowUpRight size={14} /></Link>
    </div>

    <div className="profile-layout">
      <aside className="profile-preview-card">
        <div className="profile-cover" />
        {form.avatar_url ? <img className="profile-large-avatar" src={form.avatar_url} alt="Profile avatar" onError={(event) => { event.currentTarget.style.visibility = 'hidden' }} /> : <div className="profile-large-avatar profile-avatar-fallback">{initials}</div>}
        <div className="profile-preview-copy">
          <h2>{displayName}</h2>
          <span>@{data.username}</span>
          <p>{form.bio || 'Your bio will appear here. Share what brings you to CommonGround.'}</p>
          <div className="profile-facts">
            {form.country && <span><MapPin size={14} />{form.country}</span>}
            <span><Globe2 size={14} />{form.preferred_language.toUpperCase()}</span>
          </div>
          {form.website && <a className="profile-website" href={form.website} target="_blank" rel="noreferrer">Visit website <ArrowUpRight size={13} /></a>}
        </div>
        <div className="profile-preview-footer"><UserRound size={15} /> Member since {new Date(data.date_joined).toLocaleDateString()}</div>
      </aside>

      <form className="profile-form-card" onSubmit={submit}>
        <div className="profile-form-heading"><div><span className="eyebrow">PROFILE SETTINGS</span><h2>Personal information</h2><p>Keep your information current so other members can get to know you.</p></div></div>
        {notice && <div className={updateMutation.isError ? 'error-message' : 'success-message'}>{notice}</div>}
        <div className="form-grid">
          <label>First name<input value={form.first_name} maxLength={150} onChange={(e) => setField('first_name', e.target.value)} placeholder="Your first name" /></label>
          <label>Last name<input value={form.last_name} maxLength={150} onChange={(e) => setField('last_name', e.target.value)} placeholder="Your last name" /></label>
        </div>
        <label>Bio<textarea value={form.bio} maxLength={300} rows={4} onChange={(e) => setField('bio', e.target.value)} placeholder="What are you interested in? What would you like to discuss?" /><span className="field-hint">{form.bio.length}/300 characters</span></label>
        <div className="form-grid">
          <label>Country<input value={form.country} maxLength={100} onChange={(e) => setField('country', e.target.value)} placeholder="e.g. Tanzania" /></label>
          <label>Preferred language<select value={form.preferred_language} onChange={(e) => setField('preferred_language', e.target.value)}><option value="en">English</option><option value="sw">Kiswahili</option><option value="fr">French</option><option value="es">Spanish</option><option value="ar">Arabic</option></select></label>
        </div>
        <label>Interests<input value={form.interests} maxLength={500} onChange={(e) => setField('interests', e.target.value)} placeholder="Technology, education, business" /><span className="field-hint">Separate interests with commas.</span></label>
        <label>Avatar image URL<input type="url" value={form.avatar_url} onChange={(e) => setField('avatar_url', e.target.value)} placeholder="https://example.com/photo.jpg" /></label>
        <label>Website or portfolio<input type="url" value={form.website} onChange={(e) => setField('website', e.target.value)} placeholder="https://yourwebsite.com" /></label>
        <fieldset className="privacy-fieldset">
          <legend><ShieldCheck size={15} /> Finding friends (private)</legend>
          <label>Phone number<input type="tel" inputMode="tel" autoComplete="tel" value={form.phone_number} maxLength={25} onChange={(e) => setField('phone_number', e.target.value)} placeholder="+255 712 345 678" /><span className="field-hint"><Phone size={11} /> Never shown on your profile. Numbers starting with 0 are treated as Tanzanian (+255).</span></label>
          <label className="toggle-row"><input type="checkbox" checked={form.discoverable_by_contacts} onChange={(e) => setField('discoverable_by_contacts', e.target.checked)} /><span><strong>Let people who have my number or email find me</strong><small>When friends check their contacts, you can appear in their results. Turn off to stay hidden.</small></span></label>
        </fieldset>
        <Link to="/settings/security" className="privacy-settings-link"><KeyRound size={16} /> Account security: email, password, signed-in devices →</Link>
        <Link to="/settings/privacy" className="privacy-settings-link"><ShieldCheck size={16} /> Privacy &amp; safety: private account, blocked and muted people, close friends →</Link>
        <div className="profile-account-meta"><span>Username</span><strong>@{data.username}</strong><span>Email address</span><strong>{data.email}</strong><small>Change your email in <Link to="/settings/security">Account security</Link>.</small></div>
        <div className="profile-form-actions"><span>Changes are saved to your account.</span><button className="button button-primary" disabled={updateMutation.isPending}><Save size={16} />{updateMutation.isPending ? 'Saving…' : 'Save changes'}</button></div>
      </form>
    </div>
  </section>
}
