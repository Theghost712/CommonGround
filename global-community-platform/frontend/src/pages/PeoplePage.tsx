import { useDeferredValue, useRef, useState, type ChangeEvent } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { BookUser, FileUp, Phone, Search, ShieldCheck, Smartphone, Sparkles, UsersRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import PersonRow from '../components/PersonRow'
import { api, getErrorMessage } from '../services/api'
import { chunk, contactPickerSupported, parsePasted, parseVCard, pickDeviceContacts, type ContactBatch } from '../social/contacts'
import type { Paginated, Person } from '../types'
import '../social.css'

type OwnProfile = { phone_number: string; discoverable_by_contacts: boolean }

function FindableNotice() {
  const { data } = useQuery({ queryKey: ['profile'], queryFn: async () => (await api.get<OwnProfile>('/auth/profile/')).data })
  if (!data || (data.phone_number && data.discoverable_by_contacts)) return null
  return <div className="findable-notice"><ShieldCheck size={18} /><div><strong>Let friends find you too</strong><span>{data.phone_number ? 'Turn on “Let people who have my number find me”' : 'Add your phone number and turn on “Let people find me”'} in your profile. Your number is never shown to anyone.</span></div><Link to="/profile" className="text-button">Profile settings</Link></div>
}

function ContactsFinder() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [pasted, setPasted] = useState('')
  const [showPaste, setShowPaste] = useState(false)
  const [error, setError] = useState('')
  const pickerAvailable = contactPickerSupported()

  const match = useMutation({
    mutationFn: async (batch: ContactBatch) => {
      if (!batch.phones.length && !batch.emails.length) throw new Error('No phone numbers or emails were found.')
      const matches = new Map<number, Person>()
      let checked = 0
      for (const part of chunk(batch)) {
        const { data } = await api.post<{ checked: number; matches: Person[] }>('/people/contacts/match/', part)
        checked += data.checked
        data.matches.forEach((person) => matches.set(person.id, person))
      }
      return { checked, matches: [...matches.values()] }
    },
    onError: (err) => setError(err instanceof Error && !('isAxiosError' in err) ? err.message : getErrorMessage(err)),
  })

  const run = (batch: ContactBatch) => { setError(''); match.mutate(batch) }
  const fromDevice = async () => {
    setError('')
    try { run(await pickDeviceContacts()) } catch (err) { if ((err as Error)?.name !== 'AbortError') setError('Could not open your contacts. Please allow access and try again.') }
  }
  const fromFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (file.size > 5 * 1024 * 1024) { setError('That file is too large (max 5 MB).'); return }
    run(parseVCard(await file.text()))
  }

  return <section className="contacts-card">
    <div className="contacts-card-head"><div className="contacts-icon"><BookUser size={22} /></div><div><span className="eyebrow">FIND PEOPLE YOU KNOW</span><h2>Find friends from your contacts</h2><p>We check your contacts once to find members, then forget them. Only people who chose to be findable will appear.</p></div></div>
    <div className="contacts-actions">
      {pickerAvailable && <button type="button" className="button button-primary" onClick={fromDevice} disabled={match.isPending}><Smartphone size={16} /> Choose from phone contacts</button>}
      <button type="button" className={`button ${pickerAvailable ? 'button-outline' : 'button-primary'}`} onClick={() => fileRef.current?.click()} disabled={match.isPending}><FileUp size={16} /> Import contacts file (.vcf)</button>
      <button type="button" className="button button-outline" onClick={() => setShowPaste((value) => !value)} disabled={match.isPending}><Phone size={16} /> Type numbers</button>
      <input ref={fileRef} type="file" accept=".vcf,text/vcard,text/x-vcard" hidden onChange={fromFile} aria-label="Contacts file" />
    </div>
    {!pickerAvailable && <p className="contacts-hint">On Android, open CommonGround in Chrome over HTTPS to pick contacts directly. On iPhone or a computer, export your contacts as a .vcf file and import it here.</p>}
    {showPaste && <div className="contacts-paste"><textarea rows={3} value={pasted} onChange={(event) => setPasted(event.target.value)} placeholder="Phone numbers or emails, separated by commas or new lines" aria-label="Phone numbers or emails" /><button type="button" className="button button-primary" onClick={() => run(parsePasted(pasted))} disabled={match.isPending || !pasted.trim()}>Find</button></div>}
    {match.isPending && <div className="loading-card">Checking your contacts…</div>}
    {error && <div className="error-message">{error}</div>}
    {match.data && <div className="contacts-results">
      <div className="contacts-results-title">{match.data.matches.length ? `${match.data.matches.length} of your contacts ${match.data.matches.length === 1 ? 'is' : 'are'} on CommonGround` : `None of the ${match.data.checked} contacts checked are on CommonGround yet`}</div>
      <div className="people-list">{match.data.matches.map((person) => <PersonRow key={person.id} person={person} />)}</div>
    </div>}
  </section>
}

function RequestsLink() {
  const { data } = useQuery({ queryKey: ['follow-requests'], queryFn: async () => (await api.get<Paginated<Person>>('/people/requests/')).data })
  if (!data?.count) return null
  return <Link to="/people/requests" className="button button-outline requests-link">Follow requests <span className="notification-nav-badge">{data.count}</span></Link>
}

export default function PeoplePage() {
  const [search, setSearch] = useState('')
  const query = useDeferredValue(search.trim())
  const results = useQuery({
    queryKey: ['people-search', query],
    queryFn: async () => (await api.get<Paginated<Person>>('/people/', { params: { search: query } })).data,
    enabled: query.length >= 2,
  })
  const suggestions = useQuery({ queryKey: ['people-suggestions'], queryFn: async () => (await api.get<Person[]>('/people/suggestions/')).data })

  return <div className="people-page">
    <div className="page-intro-row"><div><span className="eyebrow"><UsersRound size={12} /> YOUR PEOPLE</span><h1>Find friends & family</h1><p>Search for people, follow them, and see how you are connected.</p></div><RequestsLink /></div>
    <label className="people-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or username…" aria-label="Search people" autoFocus /></label>

    {query.length >= 2 && <section className="people-section">
      <div className="section-heading"><div><h2>Results for “{query}”</h2></div></div>
      {results.isLoading && <div className="loading-card">Searching…</div>}
      {results.error && <div className="error-card">{getErrorMessage(results.error)}</div>}
      {results.data && !results.data.results.length && <div className="empty-card"><h3>No one found</h3><p>Try a different spelling, or find them from your contacts below.</p></div>}
      {results.data && results.data.results.length > 0 && <div className="people-list">{results.data.results.map((person) => <PersonRow key={person.id} person={person} />)}</div>}
    </section>}

    <FindableNotice />
    <ContactsFinder />

    <section className="people-section">
      <div className="section-heading"><div><span className="eyebrow"><Sparkles size={12} /> SUGGESTED FOR YOU</span><h2>People you may know</h2><p>Based on your contacts, who follows you, people you follow and your communities.</p></div></div>
      {suggestions.isLoading && <div className="loading-card">Finding people…</div>}
      {suggestions.error && <div className="error-card">{getErrorMessage(suggestions.error)}</div>}
      {suggestions.data && !suggestions.data.length && <div className="empty-card"><h3>No suggestions yet</h3><p>Join communities or find friends from your contacts to get suggestions.</p></div>}
      {suggestions.data && suggestions.data.length > 0 && <div className="people-list">{suggestions.data.map((person) => <PersonRow key={person.id} person={person} />)}</div>}
    </section>
  </div>
}
