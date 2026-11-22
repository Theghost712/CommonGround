import { useDeferredValue, useRef, useState, type ChangeEvent } from 'react'
import { useInfiniteQuery, useMutation, useQuery } from '@tanstack/react-query'
import { BookUser, Check, Compass, Copy, FileUp, Mail, MessageCircle, Phone, Search, Send, Share2, ShieldCheck, Smartphone, Sparkles, UserPlus, UsersRound } from 'lucide-react'
import { Link } from 'react-router-dom'
import PersonRow from '../components/PersonRow'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import {
  chunk, contactPickerSupported, emailUrl, inviteLink, inviteMessage, parsePasted, parseVCard, pickDeviceContacts,
  smsUrl, whatsappUrl, type Contact,
} from '../social/contacts'
import type { Paginated, Person } from '../types'
import '../social.css'

type OwnProfile = { phone_number: string; discoverable_by_contacts: boolean }
type MatchResult = { members: Person[]; invitable: Contact[]; checked: number }

function FindableNotice() {
  const { data } = useQuery({ queryKey: ['profile'], queryFn: async () => (await api.get<OwnProfile>('/auth/profile/')).data })
  if (!data || (data.phone_number && data.discoverable_by_contacts)) return null
  return <div className="findable-notice"><ShieldCheck size={18} /><div><strong>Let friends find you too</strong><span>{data.phone_number ? 'Turn on “Let people who have my number find me”' : 'Add your phone number and turn on “Let people find me”'} in your profile. Your number is never shown to anyone.</span></div><Link to="/profile" className="text-button">Profile settings</Link></div>
}

/** Personal invite link: share it anywhere (WhatsApp, SMS, social apps) or copy it. */
function InviteCard() {
  const { user } = useAuth()
  const [copied, setCopied] = useState(false)
  if (!user) return null
  const link = inviteLink(user.username)
  const message = inviteMessage(user.username)
  const share = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: 'Join me on CommonGround', text: message, url: link }); return } catch { /* cancelled */ return }
    }
    await copy()
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { window.prompt('Copy your invite link:', link) }
  }
  return <section className="invite-card" aria-label="Invite friends">
    <div className="invite-card-text"><span className="eyebrow"><UserPlus size={12} /> INVITE</span><h2>Bring your people</h2><p>Friends who join with your link follow you automatically, and you'll get a notification.</p></div>
    <div className="invite-link-row"><code title={link}>{link.replace(/^https?:\/\//, '')}</code></div>
    <div className="invite-actions">
      <button type="button" className="button button-primary" onClick={() => void share()}><Share2 size={15} /> Share invite</button>
      <a className="button button-outline" href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer"><MessageCircle size={15} /> WhatsApp</a>
      <button type="button" className="button button-outline" onClick={() => void copy()}>{copied ? <><Check size={15} /> Copied</> : <><Copy size={15} /> Copy link</>}</button>
    </div>
  </section>
}

function InviteContactRow({ contact }: { contact: Contact }) {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  if (!user) return null
  const message = inviteMessage(user.username, contact.name)
  const phone = contact.phones[0]
  const email = contact.emails[0]
  const label = contact.name || phone || email
  return <li className="invite-row">
    <div className="avatar invite-avatar" aria-hidden="true">{(label || '?').slice(0, 1).toUpperCase()}</div>
    <div className="invite-row-text"><strong>{label}</strong>{contact.name && <small>{phone || email}</small>}</div>
    <div className="invite-row-actions">
      {!open && <button type="button" className="follow-button compact" onClick={() => setOpen(true)} aria-label={`Invite ${label}`}><Send size={13} /> Invite</button>}
      {open && <>
        {phone && <a className="invite-channel is-whatsapp" href={whatsappUrl(phone, message)} target="_blank" rel="noreferrer" aria-label={`Invite ${label} on WhatsApp`}><MessageCircle size={15} /></a>}
        {phone && <a className="invite-channel" href={smsUrl(phone, message)} aria-label={`Invite ${label} by SMS`}><Phone size={15} /></a>}
        {email && <a className="invite-channel" href={emailUrl(email, message)} aria-label={`Invite ${label} by email`}><Mail size={15} /></a>}
      </>}
    </div>
  </li>
}

function ContactsFinder() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [pasted, setPasted] = useState('')
  const [showPaste, setShowPaste] = useState(false)
  const [error, setError] = useState('')
  const pickerAvailable = contactPickerSupported()

  const match = useMutation({
    mutationFn: async (contacts: Contact[]): Promise<MatchResult> => {
      if (!contacts.length) throw new Error('No phone numbers or emails were found.')
      const members = new Map<number, Person>()
      const matchedKeys = new Set<string>()
      let checked = 0
      for (const part of chunk(contacts)) {
        const { data } = await api.post<{ checked: number; matches: Person[]; contacts: { key: string; user_id: number | null }[] }>(
          '/people/contacts/match/', { contacts: part.map(({ key, phones, emails }) => ({ key, phones, emails })) },
        )
        checked += data.checked
        data.matches.forEach((person) => members.set(person.id, person))
        data.contacts.forEach((c) => { if (c.user_id) matchedKeys.add(c.key) })
      }
      const invitable = contacts.filter((c) => !matchedKeys.has(c.key)).sort((a, b) => (a.name || '~').localeCompare(b.name || '~'))
      return { members: [...members.values()], invitable, checked }
    },
    onError: (err) => setError(err instanceof Error && !('isAxiosError' in err) ? err.message : getErrorMessage(err)),
  })

  const run = (contacts: Contact[]) => { setError(''); match.mutate(contacts) }
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
  const result = match.data

  return <section className="contacts-card">
    <div className="contacts-card-head"><div className="contacts-icon"><BookUser size={22} /></div><div><span className="eyebrow">FIND PEOPLE YOU KNOW</span><h2>Your contacts</h2><p>Choose contacts from your phone: see who's already here, and invite the rest. Numbers are checked once and never stored; only people who chose to be findable show up.</p></div></div>
    <div className="contacts-actions">
      {pickerAvailable && <button type="button" className="button button-primary" onClick={fromDevice} disabled={match.isPending}><Smartphone size={16} /> Open my phone contacts</button>}
      <button type="button" className={`button ${pickerAvailable ? 'button-outline' : 'button-primary'}`} onClick={() => fileRef.current?.click()} disabled={match.isPending}><FileUp size={16} /> Import contacts file (.vcf)</button>
      <button type="button" className="button button-outline" onClick={() => setShowPaste((value) => !value)} disabled={match.isPending}><Phone size={16} /> Type numbers</button>
      <input ref={fileRef} type="file" accept=".vcf,text/vcard,text/x-vcard" hidden onChange={fromFile} aria-label="Contacts file" />
    </div>
    {!pickerAvailable && <p className="contacts-hint">Phone contacts open directly in Chrome on Android. On iPhone, export contacts as a .vcf file (Contacts → select → Share), or share your invite link above.</p>}
    {showPaste && <div className="contacts-paste"><textarea rows={3} value={pasted} onChange={(event) => setPasted(event.target.value)} placeholder="Phone numbers or emails, separated by commas or new lines" aria-label="Phone numbers or emails" /><button type="button" className="button button-primary" onClick={() => run(parsePasted(pasted))} disabled={match.isPending || !pasted.trim()}>Find</button></div>}
    {match.isPending && <div className="loading-card">Checking your contacts…</div>}
    {error && <div className="error-message">{error}</div>}
    {result && <div className="contacts-results">
      <div className="contacts-results-title">{result.members.length ? `${result.members.length} of your contacts ${result.members.length === 1 ? 'is' : 'are'} on CommonGround` : 'None of these contacts are on CommonGround yet'}</div>
      {result.members.length > 0 && <div className="people-list">{result.members.map((person) => <PersonRow key={person.id} person={person} />)}</div>}
      {result.invitable.length > 0 && <>
        <div className="contacts-results-title">Invite {result.invitable.length === 1 ? 'this contact' : `these ${result.invitable.length} contacts`}</div>
        <ul className="invite-list">{result.invitable.map((contact) => <InviteContactRow key={contact.key} contact={contact} />)}</ul>
      </>}
    </div>}
  </section>
}

function DiscoverSection() {
  const [sort, setSort] = useState<'popular' | 'new'>('popular')
  const people = useInfiniteQuery({
    queryKey: ['people-discover', sort],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => (await api.get<Paginated<Person>>('/people/discover/', { params: { sort, page: pageParam } })).data,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  })
  const list = people.data?.pages.flatMap((page) => page.results) ?? []
  const total = people.data?.pages[0]?.count ?? 0
  return <section className="people-section" aria-label="Discover people">
    <div className="section-heading"><div><span className="eyebrow"><Compass size={12} /> DISCOVER</span><h2>Everyone on CommonGround</h2><p>{total ? `${total} ${total === 1 ? 'member' : 'members'} to follow and meet.` : 'Members to follow and meet.'}</p></div></div>
    <div className="home-tabs discover-tabs" role="tablist" aria-label="Sort people">
      <button role="tab" aria-selected={sort === 'popular'} className={`home-tab ${sort === 'popular' ? 'active' : ''}`} onClick={() => setSort('popular')}>Popular</button>
      <button role="tab" aria-selected={sort === 'new'} className={`home-tab ${sort === 'new' ? 'active' : ''}`} onClick={() => setSort('new')}>New members</button>
    </div>
    {people.isLoading && <div className="loading-card">Loading members…</div>}
    {people.error && <div className="error-card">{getErrorMessage(people.error)}</div>}
    {people.data && !list.length && <div className="empty-card"><h3>You're one of the first here</h3><p>Invite friends with your link above to get the conversation going.</p></div>}
    {list.length > 0 && <div className="people-list">{list.map((person) => <PersonRow key={person.id} person={person} />)}</div>}
    {people.hasNextPage && <button type="button" className="button button-outline discover-more" disabled={people.isFetchingNextPage} onClick={() => void people.fetchNextPage()}>{people.isFetchingNextPage ? 'Loading…' : 'Show more people'}</button>}
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
    <div className="page-intro-row"><div><span className="eyebrow"><UsersRound size={12} /> YOUR PEOPLE</span><h1>Find friends & family</h1><p>Search, discover members, and invite the people you know.</p></div><RequestsLink /></div>
    <label className="people-search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or username…" aria-label="Search people" autoFocus /></label>

    {query.length >= 2 && <section className="people-section">
      <div className="section-heading"><div><h2>Results for “{query}”</h2></div></div>
      {results.isLoading && <div className="loading-card">Searching…</div>}
      {results.error && <div className="error-card">{getErrorMessage(results.error)}</div>}
      {results.data && !results.data.results.length && <div className="empty-card"><h3>No one found</h3><p>Try a different spelling, or invite them with your link.</p></div>}
      {results.data && results.data.results.length > 0 && <div className="people-list">{results.data.results.map((person) => <PersonRow key={person.id} person={person} />)}</div>}
    </section>}

    <section className="people-section">
      <div className="section-heading"><div><span className="eyebrow"><Sparkles size={12} /> SUGGESTED FOR YOU</span><h2>People you may know</h2><p>From your contacts, followers, communities, and who's popular or new here.</p></div></div>
      {suggestions.isLoading && <div className="loading-card">Finding people…</div>}
      {suggestions.error && <div className="error-card">{getErrorMessage(suggestions.error)}</div>}
      {suggestions.data && !suggestions.data.length && <div className="empty-card"><h3>No suggestions yet</h3><p>Invite friends or join communities to get suggestions.</p></div>}
      {suggestions.data && suggestions.data.length > 0 && <div className="people-list">{suggestions.data.map((person) => <PersonRow key={person.id} person={person} />)}</div>}
    </section>

    <InviteCard />
    <FindableNotice />
    <ContactsFinder />
    <DiscoverSection />
  </div>
}
