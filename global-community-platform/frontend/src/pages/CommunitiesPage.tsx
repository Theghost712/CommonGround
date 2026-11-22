import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Globe2, LockKeyhole, Plus, Users, X, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import type { Community, Paginated } from '../types'

const initialForm = { name: '', description: '', category: 'Technology', visibility: 'public', logo_url: '', cover_url: '' }

export default function CommunitiesPage() {
  const client = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(initialForm)
  const [message, setMessage] = useState('')
  const { data, isLoading, error } = useQuery({
    queryKey: ['communities'],
    queryFn: async () => (await api.get<Paginated<Community> | Community[]>('/communities/')).data,
  })
  const communities = Array.isArray(data) ? data : data?.results || []

  const createMutation = useMutation({
    mutationFn: () => api.post('/communities/', form),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['communities'] })
      setShowForm(false)
      setForm(initialForm)
      setMessage('Your community has been created. You are its owner.')
    },
    onError: (err) => setMessage(getErrorMessage(err)),
  })
  const joinMutation = useMutation({
    mutationFn: (id: number) => api.post(`/communities/${id}/join/`),
    onSuccess: (response, id) => {
      client.invalidateQueries({ queryKey: ['communities'] })
      client.invalidateQueries({ queryKey: ['community', String(id)] })
      setMessage(response.data.status === 'pending' ? 'Membership request sent. A community manager must approve it.' : 'You joined the community.')
    },
    onError: (err) => setMessage(getErrorMessage(err)),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setMessage('')
    createMutation.mutate()
  }

  return <>
    <div className="page-intro-row">
      <div><span className="eyebrow">BELONG TO SOMETHING</span><h1>Find your community.</h1><p>Shared interests are a starting point. Shared conversations are where connection grows.</p></div>
      <button className="button button-primary" onClick={() => setShowForm(true)}><Plus size={17} /> Create community</button>
    </div>
    {message && <div className="inline-message" role="status">{message}<button onClick={() => setMessage('')} aria-label="Dismiss message"><X size={15} /></button></div>}

    {showForm && <div className="modal-backdrop" onClick={() => setShowForm(false)}>
      <form className="modal-card community-create-form" onSubmit={submit} onClick={(event) => event.stopPropagation()}>
        <div className="modal-heading"><div><span className="eyebrow">START SOMETHING GOOD</span><h2>Create a community</h2></div><button type="button" className="icon-button" onClick={() => setShowForm(false)} aria-label="Close"><X size={19} /></button></div>
        <label>Community name<input required maxLength={100} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="e.g. Curious Minds" /></label>
        <label>Description<textarea required maxLength={1000} rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="What brings people together here?" /></label>
        <div className="form-grid">
          <label>Category<select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>{['Technology', 'Education', 'Business', 'Culture', 'Environment', 'Health', 'Sports', 'General'].map((item) => <option key={item}>{item}</option>)}</select></label>
          <label>Visibility<select value={form.visibility} onChange={(event) => setForm({ ...form, visibility: event.target.value })}><option value="public">Public — anyone can join</option><option value="restricted">Restricted — approval required</option><option value="private">Private — invitation only</option></select></label>
        </div>
        <label>Logo image URL<input type="url" value={form.logo_url} onChange={(event) => setForm({ ...form, logo_url: event.target.value })} placeholder="https://example.com/logo.png" /></label>
        <label>Cover image URL<input type="url" value={form.cover_url} onChange={(event) => setForm({ ...form, cover_url: event.target.value })} placeholder="https://example.com/cover.jpg" /></label>
        <p className="form-hint">Public communities are open to everyone. Restricted communities require approval. Private communities are visible only to active members.</p>
        <button className="button button-primary full-button" disabled={createMutation.isPending}>{createMutation.isPending ? 'Creating…' : 'Create community'} <ArrowRight size={16} /></button>
      </form>
    </div>}

    <div className="community-toolbar"><span>{communities.length} communities to explore</span><span className="toolbar-caption">A place for every perspective</span></div>
    {isLoading && <div className="loading-card">Finding communities…</div>}
    {error && <div className="error-card">{getErrorMessage(error)}</div>}
    <div className="community-grid">{communities.map((community) => <article className="community-card" key={community.id}>
      <div className={`community-art art-${community.category.toLowerCase().replace(/[^a-z]/g, '')}`}>
        {community.cover_url && <img className="community-card-cover" src={community.cover_url} alt="" />}
        {community.logo_url ? <img className="community-card-logo" src={community.logo_url} alt={`${community.name} logo`} /> : <span>{community.name.slice(0, 1).toUpperCase()}</span>}
        <div className="art-caption">{community.category}</div>
      </div>
      <div className="community-card-body"><div className="community-card-title"><Link to={`/communities/${community.id}`}><h3>{community.name}</h3></Link>{community.visibility === 'public' ? <Globe2 size={15} /> : community.visibility === 'restricted' ? <ShieldCheck size={15} /> : <LockKeyhole size={15} />}</div>
        <p>{community.description}</p><div className="community-card-bottom"><span><Users size={14} /> {community.members_count} members</span>
          {community.is_member ? <Link className="text-button" to={`/communities/${community.id}`}>View <ArrowRight size={14} /></Link>
            : community.membership_status === 'pending' ? <span className="status-pill status-pending">Request pending</span>
              : <button className="text-button" onClick={() => joinMutation.mutate(community.id)} disabled={joinMutation.isPending || community.visibility === 'private'}>{community.visibility === 'restricted' ? 'Request to join' : 'Join'} <ArrowRight size={14} /></button>}
        </div>
      </div>
    </article>)}</div>
    {!isLoading && !error && communities.length === 0 && <div className="empty-card"><h3>No communities yet</h3><p>Create the first one and give people a place to connect.</p><button className="button button-primary" onClick={() => setShowForm(true)}>Create a community</button></div>}
  </>
}
