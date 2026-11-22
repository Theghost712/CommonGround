import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, UserPlus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Avatar } from '../components/PersonBits'
import UserLink from '../components/UserHoverCard'
import { api, getErrorMessage } from '../services/api'
import type { Paginated, Person } from '../types'
import '../social.css'

export default function FollowRequestsPage() {
  const queryClient = useQueryClient()
  const requests = useQuery({ queryKey: ['follow-requests'], queryFn: async () => (await api.get<Paginated<Person>>('/people/requests/')).data })
  const decide = useMutation({
    mutationFn: ({ username, approve }: { username: string; approve: boolean }) => api.post(`/people/requests/${encodeURIComponent(username)}/${approve ? 'approve' : 'decline'}/`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['follow-requests'] }); queryClient.invalidateQueries({ queryKey: ['person'] }) },
  })
  const people = requests.data?.results || []
  return <div className="people-page">
    <Link to="/people" className="back-link"><ArrowLeft size={16} /> Back to People</Link>
    <div className="page-intro-row"><div><span className="eyebrow"><UserPlus size={12} /> PRIVATE ACCOUNT</span><h1>Follow requests</h1><p>People who asked to see your posts and stories.</p></div></div>
    {requests.isLoading && <div className="loading-card">Loading requests…</div>}
    {requests.error && <div className="error-card">{getErrorMessage(requests.error)}</div>}
    {requests.data && !people.length && <div className="empty-card"><h3>No pending requests</h3><p>When someone asks to follow your private account, they'll appear here.</p></div>}
    <div className="people-list">{people.map((person) => <article className="person-row" key={person.id}>
      <UserLink username={person.username}><Avatar person={person} size={48} /></UserLink>
      <div className="person-row-copy"><UserLink username={person.username} className="person-row-name"><strong>{person.display_name}</strong><span>@{person.username}</span></UserLink></div>
      <div className="request-actions">
        <button type="button" className="follow-button compact" disabled={decide.isPending} onClick={() => decide.mutate({ username: person.username, approve: true })}>Confirm</button>
        <button type="button" className="follow-button compact is-following" disabled={decide.isPending} onClick={() => decide.mutate({ username: person.username, approve: false })}>Delete</button>
      </div>
    </article>)}</div>
  </div>
}
