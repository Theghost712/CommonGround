import { useEffect, useState, type FormEvent, type ChangeEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, FileText, ImagePlus, PenLine, Paperclip, X } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import DOMPurify from 'dompurify'
import RichTextEditor from '../components/RichTextEditor'
import { useAuth } from '../context/AuthContext'
import { api, getErrorMessage } from '../services/api'
import type { Community, Discussion, Paginated } from '../types'
import '../discussion-forum.css'

export const DISCUSSION_TOPICS = ['General', 'Technology', 'Education', 'Business', 'Entrepreneurship', 'Politics', 'Governance', 'Health', 'Environment', 'Sports', 'Culture', 'Entertainment', 'Science', 'Community Development']
const MAX_ATTACHMENTS = 5

const cleanText = (html: string) => {
  const safeHtml = DOMPurify.sanitize(html).replace(/<\/(p|div|li|h[1-6]|blockquote)>/gi, ' ')
  const doc = new DOMParser().parseFromString(safeHtml, 'text/html')
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim()
}

/** Creates a discussion at /discussions/new and edits one at /discussions/:id/edit. */
export default function CreateDiscussionPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const { id: editId } = useParams()
  const isEdit = Boolean(editId)
  const [searchParams] = useSearchParams()
  const [title, setTitle] = useState('')
  const [html, setHtml] = useState('')
  const [category, setCategory] = useState('General')
  const [community, setCommunity] = useState(searchParams.get('community') || '')
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')
  const [prefilled, setPrefilled] = useState(false)

  const { data } = useQuery({ queryKey: ['communities'], queryFn: async () => (await api.get<Paginated<Community> | Community[]>('/communities/')).data, enabled: !isEdit })
  const communities = Array.isArray(data) ? data : data?.results || []
  const existingQuery = useQuery({
    queryKey: ['discussion', String(editId)],
    queryFn: async () => (await api.get<Discussion>(`/discussions/${editId}/`)).data,
    enabled: isEdit,
  })
  const existing = existingQuery.data

  useEffect(() => {
    if (!existing || prefilled) return
    setTitle(existing.title)
    setHtml(existing.content_html || `<p>${existing.body.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]!)}</p>`)
    setCategory(existing.category)
    setPrefilled(true)
  }, [existing, prefilled])

  const existingCount = existing?.attachments?.length ?? 0
  const slotsLeft = Math.max(0, MAX_ATTACHMENTS - existingCount)

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body = cleanText(html)
      if (!body) throw new Error('Please write something for your discussion.')
      const payload = { title: title.trim(), body, content_html: DOMPurify.sanitize(html), category }
      const response = isEdit
        ? await api.patch<Discussion>(`/discussions/${editId}/`, payload)
        : await api.post<Discussion>('/discussions/', { ...payload, community: community || null })
      const discussionId = response.data.id
      const uploadResults = await Promise.allSettled(files.map((file) => {
        const formData = new FormData()
        formData.append('file', file)
        return api.post(`/discussions/${discussionId}/attachments/`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      }))
      const failedUploads = uploadResults.filter((result) => result.status === 'rejected').length
      return { discussion: response.data, failedUploads }
    },
    onSuccess: ({ discussion, failedUploads }) => {
      for (const key of ['discussions', 'trending-discussions', 'bookmarked-discussions', 'community-discussions', 'discussion-categories']) queryClient.invalidateQueries({ queryKey: [key] })
      queryClient.invalidateQueries({ queryKey: ['discussion', String(discussion.id)] })
      if (failedUploads) window.alert(`Your discussion was saved, but ${failedUploads} attachment(s) could not be uploaded. You can add them again by editing the discussion.`)
      navigate(`/discussions/${discussion.id}`)
    },
    onError: (err) => setError(err instanceof Error && !('isAxiosError' in err) ? err.message : getErrorMessage(err)),
  })

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files || [])
    setFiles((current) => [...current, ...selected].slice(0, slotsLeft))
    event.target.value = ''
  }
  const submit = (event: FormEvent) => { event.preventDefault(); setError(''); saveMutation.mutate() }

  if (isEdit && existingQuery.isLoading) return <div className="loading-card">Loading your discussion…</div>
  if (isEdit && (existingQuery.error || !existing)) return <div className="error-card">{getErrorMessage(existingQuery.error)}</div>
  if (isEdit && existing && existing.author !== user?.id) return <div className="error-card">You can only edit your own discussions.</div>

  const backTo = isEdit ? `/discussions/${editId}` : '/home'
  return <div className="editor-page discussion-editor-page">
    <Link to={backTo} className="back-link"><ArrowLeft size={16} /> {isEdit ? 'Back to discussion' : 'Back to feed'}</Link>
    <div className="editor-heading"><div className="editor-icon">{isEdit ? <PenLine size={22} /> : <ImagePlus size={22} />}</div><span className="eyebrow">{isEdit ? 'REFINE YOUR IDEA' : 'PUT AN IDEA INTO THE WORLD'}</span><h1>{isEdit ? 'Edit discussion.' : 'Start a discussion.'}</h1><p>{isEdit ? 'Update the title, wording or topic. Comments and reactions stay attached.' : 'Ask a question, share a perspective, or open up a topic worth exploring.'}</p></div>
    <form className="editor-card discussion-composer" onSubmit={submit}>
      <label>Discussion title<input required maxLength={180} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What would you like to talk about?" /></label>
      <div className="composer-editor-label">Your perspective</div>
      <RichTextEditor value={html} onChange={setHtml} placeholder="Give people a little context. What made you think about this? Format your ideas with headings, lists, quotes and links…" />
      <div className="form-grid">
        <label>Topic<select value={category} onChange={(event) => setCategory(event.target.value)}>{DISCUSSION_TOPICS.map((item) => <option key={item}>{item}</option>)}</select></label>
        {isEdit
          ? <label>Community<input value={existing?.community_name || 'Open discussion (everyone)'} disabled readOnly /></label>
          : <label>Post to community<select value={community} onChange={(event) => setCommunity(event.target.value)}><option value="">Open discussion (everyone)</option>{communities.filter((item) => item.is_member).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      </div>
      {isEdit && existingCount > 0 && <div className="selected-files">{existing!.attachments.map((file) => <div className="selected-file" key={file.id}>{file.is_image ? <ImagePlus size={15} /> : <FileText size={15} />}<span>{file.original_name}</span><small>attached</small></div>)}</div>}
      <div className="attachment-picker-row">
        {slotsLeft > 0
          ? <label className="attachment-picker"><Paperclip size={16} /> {isEdit ? 'Add more images or documents' : 'Attach images or documents'}<input type="file" multiple accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.doc,.docx,.txt" onChange={handleFiles} /></label>
          : <span>This discussion already has the maximum of {MAX_ATTACHMENTS} attachments.</span>}
        <span>Up to {MAX_ATTACHMENTS} files · 10 MB each</span>
      </div>
      {files.length > 0 && <div className="selected-files">{files.map((file, index) => <div className="selected-file" key={`${file.name}-${index}`}>{file.type.startsWith('image/') ? <ImagePlus size={15} /> : <FileText size={15} />}<span>{file.name}</span><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small><button type="button" onClick={() => setFiles((current) => current.filter((_, i) => i !== index))} aria-label={`Remove ${file.name}`}><X size={14} /></button></div>)}</div>}
      {error && <div className="error-message">{error}</div>}
      <div className="editor-footer"><span>Be curious. Be kind. Keep it constructive.</span><button className="button button-primary" disabled={saveMutation.isPending || !title.trim() || !cleanText(html)}>{saveMutation.isPending ? (isEdit ? 'Saving…' : 'Publishing…') : (isEdit ? 'Save changes' : 'Publish discussion')} <ArrowRight size={16} /></button></div>
    </form>
  </div>
}
