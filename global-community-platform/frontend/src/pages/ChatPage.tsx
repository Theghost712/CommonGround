import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Check, CheckCheck, LogOut, MessageCircle, MoreHorizontal,
  Plus, Search, Send, UserMinus, UserPlus, Users, X, Wifi, WifiOff,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import '../chat.css'
import { useAuth } from '../context/AuthContext'
import type { Paginated } from '../types'
import { useCall, type CallKind } from '../context/CallContext'
import { useGroupCall } from '../context/GroupCallContext'
import { Phone as PhoneIcon, Video as VideoIcon } from 'lucide-react'
import '../calls.css'
import '../media-posts.css'
import { ChatAttachments, DISAPPEAR_OPTIONS, DisappearingBadge, MessageBody, type ChatMediaMessage } from '../components/ChatMedia'

function CallButtons({ conversationId }: { conversationId: number }) {
  const call = useCall()
  const [error, setError] = useState('')
  if (!call.available) return null
  const busy = call.phase !== 'idle' && call.phase !== 'ended'
  const start = (kind: CallKind) => { setError(''); call.startCall(conversationId, kind).catch((err: Error) => setError(err.message)) }
  return <>
    <button className="icon-button chat-call-button" title="Voice call" aria-label="Voice call" disabled={busy} onClick={() => start('audio')}><PhoneIcon size={18} /></button>
    <button className="icon-button chat-call-button" title="Video call" aria-label="Video call" disabled={busy} onClick={() => start('video')}><VideoIcon size={19} /></button>
    {error && <div className="chat-call-error" role="alert" onClick={() => setError('')}>{error}</div>}
  </>
}

function GroupCallButtons({ conversationId }: { conversationId: number }) {
  const call = useCall()
  const group = useGroupCall()
  const [error, setError] = useState('')
  if (!group.available) return null
  const busy = (call.phase !== 'idle' && call.phase !== 'ended') || (group.phase !== 'idle' && group.phase !== 'ended')
  const live = group.liveCalls[conversationId]
  const start = (kind: CallKind) => { setError(''); group.join(conversationId, kind).catch((err: Error) => setError(err.message)) }
  return <>
    {live ? <button className="chat-join-call" disabled={busy} onClick={() => start(live.kind)} title={`Join the ${live.kind === 'video' ? 'video' : 'voice'} call`}>
      {live.kind === 'video' ? <VideoIcon size={14} /> : <PhoneIcon size={14} />} Join · {live.participants.length}
    </button> : <>
      <button className="icon-button chat-call-button" title="Group voice call" aria-label="Group voice call" disabled={busy} onClick={() => start('audio')}><PhoneIcon size={18} /></button>
      <button className="icon-button chat-call-button" title="Group video call" aria-label="Group video call" disabled={busy} onClick={() => start('video')}><VideoIcon size={19} /></button>
    </>}
    {error && <div className="chat-call-error" role="alert" onClick={() => setError('')}>{error}</div>}
  </>
}

type ChatUser = {
  id: number
  username: string
  first_name: string
  last_name: string
  display_name: string
  avatar_url: string | null
}
type ChatMember = {
  id: number
  user: ChatUser
  role: 'owner' | 'admin' | 'member'
  joined_at: string
  last_read_at: string | null
}
type ChatMessage = Omit<ChatMediaMessage, 'id' | 'sender' | 'body' | 'kind'> & {
  kind?: ChatMediaMessage['kind']
  id: number
  conversation: number
  sender: number
  sender_username: string
  sender_display_name: string
  body: string
  created_at: string
  edited_at: string | null
  is_edited: boolean
  is_deleted: boolean
  read_by: string[]
  read_count: number
}
type ChatConversation = {
  id: number
  conversation_type: 'direct' | 'group'
  title: string
  display_title: string
  created_by: number
  disappear_seconds?: number
  members: ChatMember[]
  other_user: ChatUser | null
  last_message: ChatMessage | null
  unread_count: number
  created_at: string
  updated_at: string
}

type IncomingEvent = {
  type: string
  message?: ChatMessage
  username?: string
  user_id?: number
  is_typing?: boolean
  status?: string
  message_ids?: number[]
}

function asList<T>(value: Paginated<T> | T[] | undefined): T[] {
  if (!value) return []
  return Array.isArray(value) ? value : value.results || []
}

function initials(label: string) {
  return (label.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('') || '?').toUpperCase()
}

function timeLabel(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export default function ChatPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedId = Number(searchParams.get('c')) || null
  const [selectedId, setSelectedId] = useState<number | null>(requestedId)
  const [mobileShowChat, setMobileShowChat] = useState(Boolean(requestedId))
  const [messageText, setMessageText] = useState('')
  const [conversationFilter, setConversationFilter] = useState('')
  const [showNewChat, setShowNewChat] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [newChatMode, setNewChatMode] = useState<'direct' | 'group'>('direct')
  const [userSearch, setUserSearch] = useState('')
  const [groupTitle, setGroupTitle] = useState('')
  const [selectedUsers, setSelectedUsers] = useState<number[]>([])
  const [socketStatus, setSocketStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected')
  const [typingUsername, setTypingUsername] = useState('')
  const [onlineUsers, setOnlineUsers] = useState<number[]>([])
  const socketRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Put a newly created/opened conversation into the cached list before selecting it.
  // Otherwise the auto-select effect sees an id that is not in the (stale) list yet
  // and jumps to a different conversation.
  const rememberConversation = (conversation: ChatConversation) => {
    queryClient.setQueryData<Paginated<ChatConversation> | ChatConversation[]>(['chat-conversations'], (old) => {
      if (!old) return [conversation]
      const list = Array.isArray(old) ? old : old.results
      const next = [conversation, ...list.filter((item) => item.id !== conversation.id)]
      return Array.isArray(old) ? next : { ...old, results: next }
    })
  }

  const conversationsQuery = useQuery({
    queryKey: ['chat-conversations'],
    queryFn: async () => (await api.get<Paginated<ChatConversation> | ChatConversation[]>('/conversations/')).data,
    refetchInterval: 30000,
  })
  const conversations = asList(conversationsQuery.data)
  const selectedConversation = conversations.find((conversation) => conversation.id === selectedId) || null

  // Opened from a profile's "Message" button (/messages?c=<id>): select it, then tidy the URL.
  useEffect(() => {
    if (!requestedId) return
    setSelectedId(requestedId)
    setMobileShowChat(true)
    if (conversations.some((item) => item.id === requestedId)) setSearchParams({}, { replace: true })
  }, [requestedId, conversations, setSearchParams])

  useEffect(() => {
    if (requestedId && conversationsQuery.isFetching) return
    if (selectedId === null && conversations.length) setSelectedId(conversations[0].id)
    if (selectedId !== null && conversations.length && !conversations.some((item) => item.id === selectedId)) setSelectedId(conversations[0]?.id ?? null)
  }, [conversations, selectedId])

  const messagesQuery = useQuery({
    queryKey: ['chat-messages', selectedId],
    enabled: selectedId !== null,
    queryFn: async () => (await api.get<ChatMessage[]>(`/conversations/${selectedId}/messages/`)).data,
  })
  const messages = messagesQuery.data || []

  const usersQuery = useQuery({
    queryKey: ['chat-user-search', userSearch],
    enabled: showNewChat && userSearch.trim().length >= 2,
    queryFn: async () => (await api.get<{ results: ChatUser[] }>('/messaging/users/', { params: { q: userSearch.trim() } })).data.results,
  })
  const foundUsers = usersQuery.data || []

  const startDirectMutation = useMutation({
    mutationFn: async (userId: number) => (await api.post<ChatConversation>('/conversations/start-direct/', { user_id: userId })).data,
    onSuccess: (conversation) => {
      rememberConversation(conversation)
      queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
      setSelectedId(conversation.id)
      setMobileShowChat(true)
      setShowNewChat(false)
      setUserSearch('')
    },
  })

  const createGroupMutation = useMutation({
    mutationFn: async () => (await api.post<ChatConversation>('/conversations/', { title: groupTitle.trim(), member_ids: selectedUsers })).data,
    onSuccess: (conversation) => {
      rememberConversation(conversation)
      queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
      setSelectedId(conversation.id)
      setMobileShowChat(true)
      setShowNewChat(false)
      setUserSearch('')
      setGroupTitle('')
      setSelectedUsers([])
    },
  })

  useEffect(() => {
    if (!selectedId) {
      socketRef.current?.close()
      socketRef.current = null
      setSocketStatus('disconnected')
      return
    }
    setSocketStatus('connecting')
    let cancelled = false
    let socket: WebSocket | null = null
    void api.post<{ ticket: string }>('/auth/ws-ticket/', {}).then(({ data }) => {
      if (cancelled) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${protocol}//${window.location.host}/ws/chat/${selectedId}/?ticket=${encodeURIComponent(data.ticket)}`
      const connectedSocket = new WebSocket(url)
      socket = connectedSocket
      socketRef.current = connectedSocket

    connectedSocket.onopen = () => {
      setSocketStatus('connected')
      connectedSocket.send(JSON.stringify({ type: 'mark_read' }))
      queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
    }
    connectedSocket.onmessage = (event) => {
      let payload: IncomingEvent
      try { payload = JSON.parse(event.data) as IncomingEvent } catch { return }
      if (payload.type === 'message.created' && payload.message) {
        const incoming = payload.message
        // New message, an update (e.g. a view-once was opened) or an unsend.
        queryClient.setQueryData<ChatMessage[]>(['chat-messages', selectedId], (old = []) => incoming.is_deleted
          ? old.filter((item) => item.id !== incoming.id)
          : old.some((item) => item.id === incoming.id) ? old.map((item) => item.id === incoming.id ? incoming : item) : [...old, incoming])
        queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
        if (payload.message.sender !== user?.id) connectedSocket.send(JSON.stringify({ type: 'mark_read' }))
      }
      if (payload.type === 'typing' && payload.user_id !== user?.id) {
        setTypingUsername(payload.is_typing ? payload.username || 'Someone' : '')
        if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
        if (payload.is_typing) typingTimeoutRef.current = setTimeout(() => setTypingUsername(''), 1800)
      }
      if (payload.type === 'presence' && payload.user_id) {
        setOnlineUsers((old) => payload.status === 'online'
          ? [...new Set([...old, payload.user_id!])]
          : old.filter((id) => id !== payload.user_id))
      }
      if (payload.type === 'message.read') {
        queryClient.invalidateQueries({ queryKey: ['chat-messages', selectedId] })
        queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
      }
      if (payload.type === 'error') console.warn('Chat socket:', payload)
    }
    connectedSocket.onclose = () => setSocketStatus('disconnected')
    connectedSocket.onerror = () => setSocketStatus('disconnected')
    }).catch(() => setSocketStatus('disconnected'))

    return () => {
      cancelled = true
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current)
      socket?.close()
      if (socketRef.current === socket) socketRef.current = null
      setOnlineUsers([])
    }
  }, [selectedId, queryClient, user?.id])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, typingUsername])

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault()
    const body = messageText.trim()
    if (!body || selectedId === null) return
    setMessageText('')
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'message', body }))
      socket.send(JSON.stringify({ type: 'typing', is_typing: false }))
      return
    }
    try {
      const response = await api.post<ChatMessage>(`/conversations/${selectedId}/messages/`, { body })
      queryClient.setQueryData<ChatMessage[]>(['chat-messages', selectedId], (old = []) => [...old, response.data])
      queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })
    } catch (error) {
      setMessageText(body)
      window.alert(getErrorMessage(error))
    }
  }

  const onMessageChange = (value: string) => {
    setMessageText(value)
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: 'typing', is_typing: Boolean(value.trim()) }))
    }
  }

  const filteredConversations = useMemo(() => conversations.filter((conversation) => {
    const q = conversationFilter.toLowerCase()
    return !q || conversation.display_title.toLowerCase().includes(q) || conversation.members.some((member) => member.user.username.toLowerCase().includes(q))
  }), [conversations, conversationFilter])

  const closeNewChat = () => {
    setShowNewChat(false); setUserSearch(''); setSelectedUsers([]); setGroupTitle('')
  }

  const toggleUser = (id: number) => setSelectedUsers((old) => old.includes(id) ? old.filter((value) => value !== id) : [...old, id])

  return <div className="chat-page">
    <section className={`chat-workspace ${mobileShowChat ? 'chat-mobile-show-chat' : ''}`}>
      <aside className="chat-sidebar">
        <div className="chat-sidebar-heading"><div><span className="eyebrow">YOUR INBOX</span><h1>Messages</h1></div><button className="chat-new-button" onClick={() => setShowNewChat(true)} title="New conversation"><Plus size={19} /></button></div>
        <label className="chat-search"><Search size={15} /><input value={conversationFilter} onChange={(event) => setConversationFilter(event.target.value)} placeholder="Search conversations" /></label>
        <div className="chat-conversation-list">
          {conversationsQuery.isLoading && <div className="chat-list-hint">Loading your conversations…</div>}
          {conversationsQuery.isError && <div className="chat-list-error">{getErrorMessage(conversationsQuery.error)}</div>}
          {filteredConversations.map((conversation) => {
            const subtitle = conversation.last_message
              ? `${conversation.last_message.sender_username === user?.username ? 'You: ' : ''}${conversation.last_message.preview ?? conversation.last_message.body}`
              : conversation.conversation_type === 'group' ? 'Group conversation' : 'Start the conversation'
            const avatarText = conversation.conversation_type === 'group' ? initials(conversation.display_title) : initials(conversation.other_user?.display_name || conversation.display_title)
            return <button key={conversation.id} className={`chat-conversation-item ${selectedId === conversation.id ? 'selected' : ''}`} onClick={() => { setSelectedId(conversation.id); setMobileShowChat(true) }}>
              <div className={`chat-list-avatar ${conversation.conversation_type === 'group' ? 'group' : ''}`}>{avatarText}</div>
              <div className="chat-list-copy"><div className="chat-list-top"><strong>{conversation.display_title}</strong><time>{timeLabel(conversation.last_message?.created_at || conversation.updated_at)}</time></div><p>{subtitle}</p></div>
              {conversation.unread_count > 0 && <span className="chat-unread-count">{conversation.unread_count > 99 ? '99+' : conversation.unread_count}</span>}
            </button>
          })}
          {!conversationsQuery.isLoading && !filteredConversations.length && <div className="chat-empty-list"><MessageCircle size={24} /><strong>No conversations yet</strong><span>Start a private chat or create a group.</span><button onClick={() => setShowNewChat(true)}>Start a conversation</button></div>}
        </div>
      </aside>

      <main className="chat-main">
        {selectedConversation ? <>
          <header className="chat-header"><button className="chat-mobile-back" onClick={() => setMobileShowChat(false)} aria-label="Back to conversations"><ArrowLeft size={18} /></button><div className={`chat-list-avatar chat-header-avatar ${selectedConversation.conversation_type === 'group' ? 'group' : ''}`}>{initials(selectedConversation.display_title)}</div><div className="chat-header-copy"><h2>{selectedConversation.display_title}</h2><span><DisappearingBadge seconds={selectedConversation.disappear_seconds} /> {selectedConversation.conversation_type === 'group' ? `${selectedConversation.members.length} participants` : selectedConversation.other_user && onlineUsers.includes(selectedConversation.other_user.id) ? 'Online now' : 'Direct conversation'}</span></div><div className={`socket-indicator ${socketStatus}`} title={`Realtime connection ${socketStatus}`}>{socketStatus === 'connected' ? <Wifi size={15} /> : <WifiOff size={15} />}<span>{socketStatus === 'connected' ? 'Live' : socketStatus === 'connecting' ? 'Connecting' : 'Offline'}</span></div>{selectedConversation.conversation_type === 'direct' ? <CallButtons conversationId={selectedConversation.id} /> : <GroupCallButtons conversationId={selectedConversation.id} />}<button className="icon-button" title="Conversation details" aria-label="Conversation details" onClick={() => setShowDetails(true)}><MoreHorizontal size={19} /></button></header>
          <div className="chat-message-area">
            {messagesQuery.isLoading && <div className="chat-list-hint">Loading messages…</div>}
            {messagesQuery.isError && <div className="chat-list-error">{getErrorMessage(messagesQuery.error)}</div>}
            {!messagesQuery.isLoading && !messages.length && <div className="chat-started-empty"><div className="chat-empty-icon"><MessageCircle size={24} /></div><h3>Say hello 👋</h3><p>This is the beginning of your conversation with {selectedConversation.display_title}.</p></div>}
            {messages.map((message, index) => {
              const own = message.sender === user?.id
              const previous = messages[index - 1]
              const showDate = !previous || new Date(previous.created_at).toDateString() !== new Date(message.created_at).toDateString()
              const dateDivider = showDate && <div className="chat-date-divider"><span>{new Date(message.created_at).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}</span></div>
              if (message.kind === 'system') return <div key={message.id}>{dateDivider}<div className="chat-system"><span>{message.body}</span></div></div>
              const isMedia = Boolean(message.kind && message.kind !== 'text')
              return <div key={message.id}>
                {dateDivider}
                <div className={`chat-message-row ${own ? 'own' : ''}`}>
                  {!own && <div className="chat-message-avatar">{initials(message.sender_display_name)}</div>}
                  <div className="chat-message-content">
                    {!own && selectedConversation.conversation_type === 'group' && <strong className="chat-sender-name">{message.sender_display_name}</strong>}
                    <div className={`chat-bubble ${isMedia ? 'has-media' : ''}`}><MessageBody message={{ ...message, kind: message.kind ?? 'text' }} own={own} conversationId={selectedConversation.id} currentUserId={user?.id} onChanged={() => queryClient.invalidateQueries({ queryKey: ['chat-messages', selectedId] })} /></div>
                    <div className="chat-message-meta"><time>{timeLabel(message.created_at)}</time>{message.is_edited && <span>edited</span>}{own && (message.read_count > 0 ? <CheckCheck size={13} className="read-check" /> : <Check size={13} />)}{own && <button type="button" className="chat-unsend" onClick={() => { if (window.confirm('Unsend this message for everyone?')) void api.delete(`/conversations/${selectedConversation.id}/messages/${message.id}/`).then(() => queryClient.setQueryData<ChatMessage[]>(['chat-messages', selectedId], (old = []) => old.filter((item) => item.id !== message.id))).catch((err) => window.alert(getErrorMessage(err))) }}>Unsend</button>}</div>
                  </div>
                </div>
              </div>
            })}
            {typingUsername && <div className="chat-typing"><span className="typing-dots"><i /><i /><i /></span>{typingUsername} is typing…</div>}
            <div ref={messagesEndRef} />
          </div>
          <form className="chat-composer" onSubmit={sendMessage}><div className="chat-composer-row"><ChatAttachments conversationId={selectedConversation.id} onSent={() => { queryClient.invalidateQueries({ queryKey: ['chat-messages', selectedId] }); queryClient.invalidateQueries({ queryKey: ['chat-conversations'] }) }} /><textarea value={messageText} onChange={(event) => onMessageChange(event.target.value)} onBlur={() => { const activeSocket = socketRef.current; if (activeSocket?.readyState === WebSocket.OPEN) activeSocket.send(JSON.stringify({ type: 'typing', is_typing: false })) }} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage(event as unknown as FormEvent) } }} placeholder="Write a message…" rows={1} maxLength={4000} /></div><div className="chat-composer-footer"><span>Enter to send · Shift + Enter for a new line</span><button className="button button-primary" disabled={!messageText.trim()}><Send size={15} /> Send</button></div></form>
        </> : <div className="chat-welcome"><div className="chat-empty-icon"><MessageCircle size={28} /></div><span className="eyebrow">A SPACE FOR CONVERSATION</span><h2>Your messages, all in one place.</h2><p>Start a private conversation or bring people together in a group chat.</p><button className="button button-primary" onClick={() => setShowNewChat(true)}><Plus size={16} /> New conversation</button></div>}
      </main>
    </section>

    {showDetails && selectedConversation && <ConversationDetails
      conversation={selectedConversation}
      currentUserId={user?.id}
      onlineUsers={onlineUsers}
      onClose={() => setShowDetails(false)}
      onLeft={(leftId) => {
        // Drop the group from the cached list first so the auto-select effect
        // cannot pick it again and open a socket the server will now refuse.
        queryClient.setQueryData<Paginated<ChatConversation> | ChatConversation[]>(['chat-conversations'], (old) => {
          if (!old) return old
          return Array.isArray(old) ? old.filter((item) => item.id !== leftId) : { ...old, results: old.results.filter((item) => item.id !== leftId) }
        })
        queryClient.removeQueries({ queryKey: ['chat-messages', leftId] })
        setShowDetails(false); setSelectedId(null); setMobileShowChat(false)
      }}
    />}

    {showNewChat && <div className="modal-backdrop" onClick={closeNewChat}><section className="modal-card chat-new-modal" onClick={(event) => event.stopPropagation()}>
      <div className="modal-heading"><div><span className="eyebrow">START CONNECTING</span><h2>New conversation</h2></div><button className="icon-button" onClick={closeNewChat}><X size={19} /></button></div>
      <div className="chat-mode-switch"><button className={newChatMode === 'direct' ? 'active' : ''} onClick={() => setNewChatMode('direct')}>Private message</button><button className={newChatMode === 'group' ? 'active' : ''} onClick={() => setNewChatMode('group')}>Group chat</button></div>
      {newChatMode === 'group' && <label className="chat-modal-label">Group name<input value={groupTitle} onChange={(event) => setGroupTitle(event.target.value)} placeholder="e.g. Product design team" maxLength={120} /></label>}
      <label className="chat-modal-label">Find people<input autoFocus value={userSearch} onChange={(event) => setUserSearch(event.target.value)} placeholder="Search by name or username…" /></label>
      {newChatMode === 'group' && selectedUsers.length > 0 && <div className="chat-selected-people">{selectedUsers.length} participant{selectedUsers.length > 1 ? 's' : ''} selected</div>}
      <div className="chat-user-results">
        {usersQuery.isFetching && <span>Searching…</span>}
        {usersQuery.isError && <span className="chat-list-error">{getErrorMessage(usersQuery.error)}</span>}
        {!usersQuery.isFetching && userSearch.trim().length >= 2 && !foundUsers.length && <span>No users found.</span>}
        {foundUsers.map((person) => {
          const selected = selectedUsers.includes(person.id)
          return <button key={person.id} className={`chat-user-result ${selected ? 'chosen' : ''}`} onClick={() => newChatMode === 'direct' ? startDirectMutation.mutate(person.id) : toggleUser(person.id)} disabled={startDirectMutation.isPending}>
            <div className="chat-list-avatar">{initials(person.display_name)}</div><div><strong>{person.display_name}</strong><span>@{person.username}</span></div>{newChatMode === 'group' && <span className="chat-select-check">{selected ? <Check size={15} /> : <Plus size={15} />}</span>}
          </button>
        })}
      </div>
      {newChatMode === 'group' && <button className="button button-primary full-button" onClick={() => createGroupMutation.mutate()} disabled={!groupTitle.trim() || !selectedUsers.length || createGroupMutation.isPending}>{createGroupMutation.isPending ? 'Creating group…' : `Create group (${selectedUsers.length})`} <Users size={15} /></button>}
      {(startDirectMutation.isError || createGroupMutation.isError) && <div className="error-message">{getErrorMessage(startDirectMutation.error || createGroupMutation.error)}</div>}
    </section></div>}
  </div>
}

const ROLE_LABEL: Record<ChatMember['role'], string> = { owner: 'Owner', admin: 'Admin', member: 'Member' }

function ConversationDetails({ conversation, currentUserId, onlineUsers, onClose, onLeft }: {
  conversation: ChatConversation
  currentUserId?: number
  onlineUsers: number[]
  onClose: () => void
  onLeft: (conversationId: number) => void
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const isGroup = conversation.conversation_type === 'group'
  const me = conversation.members.find((member) => member.user.id === currentUserId)
  const canManage = isGroup && (me?.role === 'owner' || me?.role === 'admin')
  const memberIds = new Set(conversation.members.map((member) => member.user.id))
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['chat-conversations'] })

  const usersQuery = useQuery({
    queryKey: ['chat-user-search', search],
    enabled: canManage && search.trim().length >= 2,
    queryFn: async () => (await api.get<{ results: ChatUser[] }>('/messaging/users/', { params: { q: search.trim() } })).data.results,
  })
  const candidates = (usersQuery.data || []).filter((person) => !memberIds.has(person.id))

  const addMutation = useMutation({
    mutationFn: (userId: number) => api.post(`/conversations/${conversation.id}/add-members/`, { member_ids: [userId] }),
    onSuccess: () => { setSearch(''); setError(''); void refresh() },
    onError: (err) => setError(getErrorMessage(err)),
  })
  const removeMutation = useMutation({
    mutationFn: (userId: number) => api.post(`/conversations/${conversation.id}/remove-member/`, { user_id: userId }),
    onSuccess: () => { setError(''); void refresh() },
    onError: (err) => setError(getErrorMessage(err)),
  })
  const leaveMutation = useMutation({
    mutationFn: () => api.post(`/conversations/${conversation.id}/leave/`),
    onSuccess: () => { onLeft(conversation.id); void refresh() },
    onError: (err) => setError(getErrorMessage(err)),
  })

  const canRemove = (member: ChatMember) => canManage && member.user.id !== currentUserId && member.role !== 'owner' && !(me?.role === 'admin' && member.role === 'admin')
  const leave = () => {
    const note = me?.role === 'owner' && conversation.members.length > 1 ? ' Ownership will pass to another participant.' : ''
    if (window.confirm(`Leave "${conversation.display_title}"? You will stop receiving its messages.${note}`)) leaveMutation.mutate()
  }

  return <div className="modal-backdrop" onClick={onClose}><section className="modal-card chat-details-modal" role="dialog" aria-label="Conversation details" onClick={(event) => event.stopPropagation()}>
    <div className="modal-heading"><div><span className="eyebrow">{isGroup ? 'GROUP CHAT' : 'PRIVATE CONVERSATION'}</span><h2>{conversation.display_title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close details"><X size={19} /></button></div>
    <div className="chat-details-section-title">Disappearing messages</div>
    <p className="chat-details-help">New messages are deleted for everyone after this time.{isGroup && !canManage ? ' Only admins can change it.' : ''}</p>
    <div className="chat-disappear-select" role="group" aria-label="Disappearing messages">
      {DISAPPEAR_OPTIONS.map((option) => <button key={option.seconds} type="button" disabled={isGroup && !canManage} className={(conversation.disappear_seconds ?? 0) === option.seconds ? 'active' : ''}
        onClick={() => void api.post(`/conversations/${conversation.id}/disappearing/`, { seconds: option.seconds }).then(() => { void refresh(); void queryClient.invalidateQueries({ queryKey: ['chat-messages', conversation.id] }) }).catch((err) => setError(getErrorMessage(err)))}>{option.label}</button>)}
    </div>
    <div className="chat-details-section-title">{isGroup ? `${conversation.members.length} participants` : 'Participants'}</div>
    <div className="chat-details-members">
      {conversation.members.map((member) => <div className="chat-details-member" key={member.user.id}>
        <div className="chat-list-avatar">{initials(member.user.display_name || member.user.username)}</div>
        <div className="chat-details-member-copy"><strong>{member.user.display_name || member.user.username}{member.user.id === currentUserId && ' (you)'}</strong><span>@{member.user.username}{onlineUsers.includes(member.user.id) ? ' · online' : ''}</span></div>
        {isGroup && <span className={`chat-role-badge role-${member.role}`}>{ROLE_LABEL[member.role]}</span>}
        {canRemove(member) && <button className="icon-button" title={`Remove ${member.user.username}`} aria-label={`Remove ${member.user.username}`} onClick={() => { if (window.confirm(`Remove ${member.user.display_name || member.user.username} from this group?`)) removeMutation.mutate(member.user.id) }} disabled={removeMutation.isPending}><UserMinus size={16} /></button>}
      </div>)}
    </div>
    {canManage && <div className="chat-details-add">
      <label className="chat-modal-label">Add people<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or username…" /></label>
      <div className="chat-user-results">
        {usersQuery.isFetching && <span>Searching…</span>}
        {!usersQuery.isFetching && search.trim().length >= 2 && !candidates.length && <span>No one new to add.</span>}
        {candidates.map((person) => <button key={person.id} className="chat-user-result" onClick={() => addMutation.mutate(person.id)} disabled={addMutation.isPending}>
          <div className="chat-list-avatar">{initials(person.display_name)}</div><div><strong>{person.display_name}</strong><span>@{person.username}</span></div><span className="chat-select-check"><UserPlus size={15} /></span>
        </button>)}
      </div>
    </div>}
    {error && <div className="error-message">{error}</div>}
    {isGroup && <button className="button chat-leave-button" onClick={leave} disabled={leaveMutation.isPending}><LogOut size={15} /> {leaveMutation.isPending ? 'Leaving…' : 'Leave group'}</button>}
  </section></div>
}
