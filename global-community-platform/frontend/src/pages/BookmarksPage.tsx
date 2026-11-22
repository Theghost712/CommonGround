import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Bookmark } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import DiscussionCard from '../components/DiscussionCard'
import type { Discussion, Paginated } from '../types'
import '../discussion-forum.css'

export default function BookmarksPage() {
  const query = useQuery({ queryKey: ['bookmarked-discussions'], queryFn: async () => (await api.get<Paginated<Discussion> | Discussion[]>('/discussions/bookmarked/')).data })
  const discussions = !query.data ? [] : Array.isArray(query.data) ? query.data : query.data.results || []
  return <section className="bookmarks-page"><Link to="/home" className="back-link"><ArrowLeft size={16} /> Back to feed</Link><div className="page-intro-row"><div><span className="eyebrow">YOUR READING LIST</span><h1>Saved discussions.</h1><p>Keep thoughtful conversations close and return whenever you like.</p></div><div className="bookmarks-page-icon"><Bookmark size={22} /></div></div>{query.isLoading && <div className="loading-card">Loading saved discussions…</div>}{query.error && <div className="error-card">{getErrorMessage(query.error)}</div>}{discussions.map((item) => <DiscussionCard key={item.id} discussion={item} />)}{!query.isLoading && !query.error && discussions.length === 0 && <div className="empty-card"><div className="empty-icon"><Bookmark size={22} /></div><h3>No saved discussions yet.</h3><p>Use the bookmark icon on any discussion to save it here.</p><Link className="button button-primary" to="/home">Explore discussions</Link></div>}</section>
}
