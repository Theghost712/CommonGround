import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, ArrowRight, Bell, BookOpen, CalendarDays, Check, Globe2, LockKeyhole,
  Megaphone, Pencil, Plus, Settings2, Shield, ShieldCheck, Trash2,
  Users, X,
} from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import { useAuth } from '../context/AuthContext'
import '../community-management.css'
import DiscussionCard from '../components/DiscussionCard'
import CommunityEventsPanel from '../components/CommunityEventsPanel'
import type { Community, CommunityAnnouncement, CommunityMember, CommunityRule, Discussion, Paginated } from '../types'

type Tab = 'discussions' | 'events' | 'members' | 'about' | 'manage'
const toList = <T,>(data: Paginated<T> | T[] | undefined): T[] => !data ? [] : Array.isArray(data) ? data : data.results || []

export default function CommunityDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('discussions')
  const [notice, setNotice] = useState('')
  const [announcement, setAnnouncement] = useState({ title: '', body: '', is_pinned: false })
  const [rule, setRule] = useState({ title: '', description: '', position: 0 })
  const [edit, setEdit] = useState({ name: '', description: '', category: '', visibility: 'public', logo_url: '', cover_url: '' })

  const communityQuery = useQuery({
    queryKey: ['community', id],
    enabled: Boolean(id),
    queryFn: async () => (await api.get<Community>(`/communities/${id}/`)).data,
  })
  const community = communityQuery.data
  useEffect(() => {
    if (community) setEdit({
      name: community.name, description: community.description, category: community.category,
      visibility: community.visibility, logo_url: community.logo_url || '', cover_url: community.cover_url || '',
    })
  }, [community])

  const isApproved = community?.approval_status === 'approved'
  const canManage = Boolean(isApproved && community?.is_member && ['owner', 'admin'].includes(community.my_role || ''))
  const canModerate = Boolean(isApproved && community?.is_member && ['owner', 'admin', 'moderator'].includes(community.my_role || ''))
  const canManageMembers = canModerate
  const canReadDiscussions = Boolean(isApproved && community && (community.visibility === 'public' || community.is_member))

  const discussionsQuery = useQuery({
    queryKey: ['community-discussions', id], enabled: canReadDiscussions,
    queryFn: async () => (await api.get<Paginated<Discussion> | Discussion[]>('/discussions/', { params: { community: id } })).data,
  })
  const membersQuery = useQuery({
    queryKey: ['community-members', id], enabled: Boolean(community && (community.visibility !== 'private' || community.is_member)),
    queryFn: async () => (await api.get<CommunityMember[]>(`/communities/${id}/members/`)).data,
  })
  const requestsQuery = useQuery({
    queryKey: ['community-requests', id], enabled: canManage,
    queryFn: async () => (await api.get<CommunityMember[]>(`/communities/${id}/membership-requests/`)).data,
  })
  const rulesQuery = useQuery({
    queryKey: ['community-rules', id], enabled: Boolean(community),
    queryFn: async () => (await api.get<CommunityRule[]>(`/communities/${id}/rules/`)).data,
  })
  const announcementsQuery = useQuery({
    queryKey: ['community-announcements', id], enabled: Boolean(community),
    queryFn: async () => (await api.get<CommunityAnnouncement[]>(`/communities/${id}/announcements/`)).data,
  })

  const refresh = () => {
    for (const key of [
      ['community', id], ['communities'], ['community-members', id], ['community-requests', id],
      ['community-rules', id], ['community-announcements', id], ['community-discussions', id],
    ]) queryClient.invalidateQueries({ queryKey: key })
  }
  const success = (message: string) => setNotice(message)
  const failure = (error: unknown) => setNotice(getErrorMessage(error))

  const joinMutation = useMutation({ mutationFn: () => api.post(`/communities/${id}/join/`), onSuccess: (r) => { refresh(); success(r.data.status === 'pending' ? 'Your request has been sent for approval.' : 'You joined the community.') }, onError: failure })
  const leaveMutation = useMutation({ mutationFn: () => api.post(`/communities/${id}/leave/`), onSuccess: () => { refresh(); success('You left the community.') }, onError: failure })
  const approveMutation = useMutation({ mutationFn: (membership_id: number) => api.post(`/communities/${id}/approve-request/`, { membership_id }), onSuccess: () => { refresh(); success('Membership request approved.') }, onError: failure })
  const rejectMutation = useMutation({ mutationFn: (membership_id: number) => api.post(`/communities/${id}/reject-request/`, { membership_id }), onSuccess: () => { refresh(); success('Membership request rejected.') }, onError: failure })
  const roleMutation = useMutation({ mutationFn: (payload: { membership_id: number; role: string }) => api.patch(`/communities/${id}/update-member-role/`, payload), onSuccess: () => { refresh(); success('Member role updated.') }, onError: failure })
  const removeMutation = useMutation({ mutationFn: (membership_id: number) => api.post(`/communities/${id}/remove-member/`, { membership_id }), onSuccess: () => { refresh(); success('Member removed.') }, onError: failure })
  const announcementMutation = useMutation({ mutationFn: () => api.post(`/communities/${id}/announcements/`, announcement), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['community-announcements', id] }); setAnnouncement({ title: '', body: '', is_pinned: false }); success('Announcement published.') }, onError: failure })
  const ruleMutation = useMutation({ mutationFn: () => api.post(`/communities/${id}/rules/`, rule), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['community-rules', id] }); setRule({ title: '', description: '', position: 0 }); success('Rule added.') }, onError: failure })
  const editMutation = useMutation({ mutationFn: () => api.patch(`/communities/${id}/`, edit), onSuccess: () => { refresh(); success('Community details saved.') }, onError: failure })
  const deleteRuleMutation = useMutation({ mutationFn: (ruleId: number) => api.delete(`/communities/${id}/rules/${ruleId}/`), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['community-rules', id] }); success('Rule deleted.') }, onError: failure })
  const deleteAnnouncementMutation = useMutation({ mutationFn: (announcementId: number) => api.delete(`/communities/${id}/announcements/${announcementId}/`), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['community-announcements', id] }); success('Announcement deleted.') }, onError: failure })

  const tabs = useMemo(() => {
    const all: { key: Tab; label: string; icon: typeof Users }[] = [
  { key: 'discussions', label: 'Discussions', icon: BookOpen },
  { key: 'events', label: 'Events', icon: CalendarDays },
  { key: 'members', label: 'Members', icon: Users },
  { key: 'about', label: 'About & updates', icon: Bell },
    ]
    if (canModerate) all.push({ key: 'manage', label: 'Manage', icon: Settings2 })
    return all
  }, [canModerate])

  const onSubmit = (event: FormEvent, action: () => void) => { event.preventDefault(); setNotice(''); action() }
  if (communityQuery.isLoading) return <div className="loading-card">Opening community…</div>
  if (communityQuery.error || !community) return <div className="error-card">{getErrorMessage(communityQuery.error)}</div>

  const discussions = toList(discussionsQuery.data)
  const members = membersQuery.data || []
  const requests = requestsQuery.data || []
  const rules = rulesQuery.data || []
  const announcements = announcementsQuery.data || []
  const visibilityIcon = community.visibility === 'public' ? <Globe2 size={13} /> : community.visibility === 'restricted' ? <ShieldCheck size={13} /> : <LockKeyhole size={13} />
  const coverStyle = community.cover_url ? { backgroundImage: `linear-gradient(90deg, rgba(27,24,65,.78), rgba(44,38,93,.35)), url(${community.cover_url})` } : undefined

  return <div className="community-detail-page">
    <Link to="/communities" className="back-link"><ArrowLeft size={16} /> All communities</Link>
    <section className="community-hero community-hero-updated" style={coverStyle}>
      <div className="community-hero-logo">{community.logo_url ? <img src={community.logo_url} alt={`${community.name} logo`} /> : <span>{community.name.slice(0, 1).toUpperCase()}</span>}</div>
      <div className="community-hero-copy">
        <div className="community-hero-tags"><span className="topic-pill">{community.category}</span><span className="community-privacy">{visibilityIcon}{community.visibility}</span></div>
        <h1>{community.name}</h1><p>{community.description}</p>
        <div className="community-hero-meta"><span><Users size={15} /> {community.members_count} members</span><span>Created by {community.created_by_username}</span></div>
      </div>
      <div className="community-hero-action">
        {community.is_member ? <>{community.my_role === 'owner' ? <span className="owner-label">Community owner</span> : <button className="button button-outline" disabled={leaveMutation.isPending} onClick={() => { if (window.confirm('Leave this community?')) leaveMutation.mutate() }}>Leave community</button>}</>
          : community.membership_status === 'pending' ? <span className="status-pill status-pending">Request pending</span>
            : !user ? <Link className="button button-primary" to={`/register?next=${encodeURIComponent(`/communities/${id}`)}`}>Join community <ArrowRight size={16} /></Link>
            : <button className="button button-primary" disabled={joinMutation.isPending || community.visibility === 'private'} onClick={() => joinMutation.mutate()}>{community.visibility === 'restricted' ? 'Request to join' : 'Join community'} <ArrowRight size={16} /></button>}
      </div>
    </section>
    {notice && <div className="inline-message" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss"><X size={15} /></button></div>}
    <nav className="community-tabs" aria-label="Community sections">
      {tabs.map(({ key, label, icon: Icon }) => <button key={key} className={tab === key ? 'community-tab active' : 'community-tab'} onClick={() => setTab(key)}><Icon size={15} />{label}{key === 'manage' && (community.pending_requests_count || 0) > 0 && <span className="tab-count">{community.pending_requests_count}</span>}</button>)}
    </nav>

    {tab === 'discussions' && <>
      {!canReadDiscussions ? <div className="empty-card"><h3>Members-only discussions</h3><p>Join this community to read and contribute to its discussions.</p></div> : <>
        <div className="community-feed-heading"><div><span className="eyebrow">INSIDE THE COMMUNITY</span><h2>Community discussions</h2></div>{community.is_member && <Link to={`/discussions/new?community=${community.id}`} className="button button-primary"><Plus size={16} /> Start a discussion</Link>}</div>
        {discussionsQuery.isLoading && <div className="loading-card">Loading discussions…</div>}
        {discussions.map((item) => <DiscussionCard key={item.id} discussion={item} />)}
        {!discussionsQuery.isLoading && discussions.length === 0 && <div className="empty-card"><h3>Start the first conversation.</h3><p>This community is waiting for its first discussion.</p>{community.is_member && <Link to={`/discussions/new?community=${community.id}`} className="button button-primary">Create a discussion</Link>}</div>}
      </>}
    </>}

    {tab === 'events' && (
  <CommunityEventsPanel
    community={community}
    canManage={canModerate}
    canRSVP={community.is_member}
  />
)}
    {tab === 'members' && <section className="community-panel">
      <div className="panel-title-row"><div><span className="eyebrow">THE PEOPLE</span><h2>Community members</h2><p>{members.length} active members</p></div><Users size={22} /></div>
      {membersQuery.isLoading ? <div className="loading-card">Loading members…</div> : <div className="community-member-list">{members.map((member) => <div className="community-member-row" key={member.id}>
        <div className="member-avatar">{member.display_name.slice(0, 1).toUpperCase()}</div><div className="member-main"><strong>{member.display_name}</strong><span>@{member.username}</span></div><span className={`role-badge role-${member.role}`}>{member.role}</span>
        {canManageMembers && member.role !== 'owner' && <div className="member-actions">
          {canManage && !(community.my_role === 'admin' && member.role === 'admin') && <select aria-label={`Change role for ${member.username}`} value={member.role} disabled={roleMutation.isPending} onChange={(event) => roleMutation.mutate({ membership_id: member.id, role: event.target.value })}>
            <option value="member">Member</option><option value="moderator">Moderator</option>{community.my_role === 'owner' && <option value="admin">Administrator</option>}
          </select>}
          {!(community.my_role === 'moderator' && member.role !== 'member') && !(community.my_role === 'admin' && member.role === 'admin') && <button className="icon-button danger-icon" aria-label={`Remove ${member.username}`} onClick={() => { if (window.confirm(`Remove @${member.username} from this community?`)) removeMutation.mutate(member.id) }}><Trash2 size={15} /></button>}
        </div>}
      </div>)}</div>}
    </section>}

    {tab === 'about' && <div className="community-about-grid">
      <section className="community-panel"><div className="panel-title-row"><div><span className="eyebrow">COMMUNITY GUIDELINES</span><h2>Rules of the space</h2></div><Shield size={22} /></div>
        {rules.length ? <ol className="community-rule-list">{rules.map((item) => <li key={item.id}><strong>{item.title}</strong><p>{item.description}</p></li>)}</ol> : <div className="panel-empty">No rules have been published yet.</div>}
      </section>
      <section className="community-panel"><div className="panel-title-row"><div><span className="eyebrow">IMPORTANT INFORMATION</span><h2>Announcements</h2></div><Megaphone size={22} /></div>
        {announcements.length ? <div className="announcement-list">{announcements.map((item) => <article className="announcement-card" key={item.id}><div className="announcement-top"><h3>{item.title}</h3>{item.is_pinned && <span className="pinned-label">Pinned</span>}</div><p>{item.body}</p><span>Posted by @{item.posted_by_username} · {new Date(item.created_at).toLocaleDateString()}</span></article>)}</div> : <div className="panel-empty">No announcements yet.</div>}
      </section>
    </div>}

    {tab === 'manage' && canModerate && <div className="community-manage-grid">
      {canManage && <section className="community-panel management-panel"><div className="panel-title-row"><div><span className="eyebrow">MEMBERSHIP CONTROL</span><h2>Join requests</h2><p>Approve or reject people who want to join this community.</p></div><Users size={22} /></div>
        {requestsQuery.isLoading ? <div className="panel-empty">Loading requests…</div> : requests.length === 0 ? <div className="panel-empty">There are no pending requests.</div> : <div className="community-member-list">{requests.map((member) => <div className="community-member-row" key={member.id}><div className="member-avatar">{member.display_name.slice(0, 1).toUpperCase()}</div><div className="member-main"><strong>{member.display_name}</strong><span>@{member.username}</span></div><div className="request-actions"><button className="button button-small button-primary" disabled={approveMutation.isPending} onClick={() => approveMutation.mutate(member.id)}><Check size={14} /> Approve</button><button className="button button-small button-light-danger" disabled={rejectMutation.isPending} onClick={() => rejectMutation.mutate(member.id)}><X size={14} /> Reject</button></div></div>)}</div>}
      </section>}

      <section className="community-panel management-panel"><div className="panel-title-row"><div><span className="eyebrow">COMMUNITY UPDATES</span><h2>Publish announcement</h2><p>Share important information with community members.</p></div><Megaphone size={22} /></div>
        <form className="community-management-form" onSubmit={(event) => onSubmit(event, () => announcementMutation.mutate())}><label>Title<input required maxLength={140} value={announcement.title} onChange={(event) => setAnnouncement({ ...announcement, title: event.target.value })} placeholder="Announcement title" /></label><label>Message<textarea required rows={4} maxLength={5000} value={announcement.body} onChange={(event) => setAnnouncement({ ...announcement, body: event.target.value })} placeholder="Write an update for your community…" /></label><label className="checkbox-label"><input type="checkbox" checked={announcement.is_pinned} onChange={(event) => setAnnouncement({ ...announcement, is_pinned: event.target.checked })} /> Pin this announcement</label><button className="button button-primary" disabled={announcementMutation.isPending}>{announcementMutation.isPending ? 'Publishing…' : 'Publish announcement'}</button></form>
        {announcements.length > 0 && <div className="management-existing-list"><strong>Published announcements</strong>{announcements.map((item) => <div key={item.id}><span>{item.title}</span><button className="icon-button danger-icon" aria-label={`Delete ${item.title}`} onClick={() => { if (window.confirm('Delete this announcement?')) deleteAnnouncementMutation.mutate(item.id) }}><Trash2 size={14} /></button></div>)}</div>}
      </section>

      <section className="community-panel management-panel"><div className="panel-title-row"><div><span className="eyebrow">COMMUNITY STANDARDS</span><h2>Manage rules</h2><p>Keep expectations clear for everyone.</p></div><ShieldCheck size={22} /></div>
        <form className="community-management-form" onSubmit={(event) => onSubmit(event, () => ruleMutation.mutate())}><label>Rule title<input required maxLength={120} value={rule.title} onChange={(event) => setRule({ ...rule, title: event.target.value })} placeholder="e.g. Be respectful" /></label><label>Description<textarea required rows={3} maxLength={1000} value={rule.description} onChange={(event) => setRule({ ...rule, description: event.target.value })} placeholder="Explain what this rule means…" /></label><button className="button button-primary" disabled={ruleMutation.isPending}>{ruleMutation.isPending ? 'Saving…' : 'Add rule'}</button></form>
        {rules.length > 0 && <div className="management-existing-list"><strong>Current rules</strong>{rules.map((item) => <div key={item.id}><span>{item.title}</span><button className="icon-button danger-icon" aria-label={`Delete ${item.title}`} onClick={() => { if (window.confirm('Delete this rule?')) deleteRuleMutation.mutate(item.id) }}><Trash2 size={14} /></button></div>)}</div>}
      </section>

      {canManage && <section className="community-panel management-panel"><div className="panel-title-row"><div><span className="eyebrow">COMMUNITY SETTINGS</span><h2>Edit community</h2><p>Update your community identity and visibility.</p></div><Pencil size={22} /></div>
        <form className="community-management-form" onSubmit={(event) => onSubmit(event, () => editMutation.mutate())}><label>Community name<input required maxLength={100} value={edit.name} onChange={(event) => setEdit({ ...edit, name: event.target.value })} /></label><label>Description<textarea required rows={3} maxLength={1000} value={edit.description} onChange={(event) => setEdit({ ...edit, description: event.target.value })} /></label><div className="form-grid"><label>Category<input maxLength={60} value={edit.category} onChange={(event) => setEdit({ ...edit, category: event.target.value })} /></label><label>Visibility<select value={edit.visibility} onChange={(event) => setEdit({ ...edit, visibility: event.target.value })}><option value="public">Public</option><option value="restricted">Restricted</option><option value="private">Private</option></select></label></div><label>Logo URL<input type="url" value={edit.logo_url} onChange={(event) => setEdit({ ...edit, logo_url: event.target.value })} /></label><label>Cover URL<input type="url" value={edit.cover_url} onChange={(event) => setEdit({ ...edit, cover_url: event.target.value })} /></label><button className="button button-primary" disabled={editMutation.isPending}>{editMutation.isPending ? 'Saving…' : 'Save changes'}</button></form>
      </section>}
    </div>}
  </div>
}
