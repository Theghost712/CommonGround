import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarDays,
  Clock,
  MapPin,
  Users,
  Plus,
  Pencil,
  Trash2,
  X,
} from 'lucide-react'

import { api, getErrorMessage } from '../services/api'
import type {
  Community,
  CommunityEvent,
  EventRSVP,
  EventResponse,
  Paginated,
} from '../types'

import '../community-events.css'

type Props = {
  community: Community
  canManage: boolean
  canRSVP: boolean
}

type EventForm = {
  title: string
  description: string
  location: string
  starts_at: string
  ends_at: string
}

const emptyForm: EventForm = {
  title: '',
  description: '',
  location: '',
  starts_at: '',
  ends_at: '',
}

function toList<T>(data: Paginated<T> | T[] | undefined): T[] {
  if (!data) return []
  return Array.isArray(data) ? data : data.results || []
}

function toLocalInput(value: string) {
  const date = new Date(value)
  const pad = (number: number) => String(number).padStart(2, '0')

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatDate(value: string) {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export default function CommunityEventsPanel({
  community,
  canManage,
  canRSVP,
}: Props) {
  const queryClient = useQueryClient()

  const [form, setForm] = useState<EventForm>(emptyForm)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [notice, setNotice] = useState('')
  const [attendeesEventId, setAttendeesEventId] = useState<number | null>(null)

  const eventsQuery = useQuery({
    queryKey: ['community-events', community.id],
    queryFn: async () => (
      await api.get<Paginated<CommunityEvent> | CommunityEvent[]>(
        '/events/',
        { params: { community: community.id } },
      )
    ).data,
  })

  const attendeesQuery = useQuery({
    queryKey: ['event-attendees', attendeesEventId],
    enabled: Boolean(attendeesEventId && canRSVP),
    queryFn: async () => (
      await api.get<Paginated<EventRSVP> | EventRSVP[]>(
        `/events/${attendeesEventId}/attendees/`,
      )
    ).data,
  })

  const refreshEvents = () => {
    queryClient.invalidateQueries({
      queryKey: ['community-events', community.id],
    })

    if (attendeesEventId) {
      queryClient.invalidateQueries({
        queryKey: ['event-attendees', attendeesEventId],
      })
    }
  }

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post('/events/', payload),
    onSuccess: () => {
      refreshEvents()
      setForm(emptyForm)
      setNotice('Event created successfully.')
    },
    onError: (error) => setNotice(getErrorMessage(error)),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: {
      id: number
      payload: Partial<EventForm>
    }) => api.patch(`/events/${id}/`, payload),
    onSuccess: () => {
      refreshEvents()
      setEditingId(null)
      setForm(emptyForm)
      setNotice('Event updated successfully.')
    },
    onError: (error) => setNotice(getErrorMessage(error)),
  })

  const rsvpMutation = useMutation({
    mutationFn: ({ id, response }: {
      id: number
      response: EventResponse
    }) => api.post(`/events/${id}/rsvp/`, { response }),
    onSuccess: () => {
      refreshEvents()
      setNotice('Your RSVP has been saved.')
    },
    onError: (error) => setNotice(getErrorMessage(error)),
  })

  const cancelMutation = useMutation({
    mutationFn: (id: number) => api.post(`/events/${id}/cancel/`),
    onSuccess: () => {
      refreshEvents()
      setNotice('Event cancelled successfully.')
    },
    onError: (error) => setNotice(getErrorMessage(error)),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/events/${id}/`),
    onSuccess: () => {
      refreshEvents()
      setNotice('Event deleted successfully.')
    },
    onError: (error) => setNotice(getErrorMessage(error)),
  })

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    setNotice('')

    const startsAt = new Date(form.starts_at)
    const endsAt = new Date(form.ends_at)

    if (
      Number.isNaN(startsAt.getTime()) ||
      Number.isNaN(endsAt.getTime()) ||
      endsAt <= startsAt
    ) {
      setNotice('Event end date must be after its start date.')
      return
    }

    const payload = {
      title: form.title.trim(),
      description: form.description.trim(),
      location: form.location.trim(),
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
    }

    if (editingId) {
      updateMutation.mutate({
        id: editingId,
        payload,
      })
    } else {
      createMutation.mutate({
        ...payload,
        community: community.id,
      })
    }
  }

  const startEditing = (event: CommunityEvent) => {
    setEditingId(event.id)
    setForm({
      title: event.title,
      description: event.description,
      location: event.location || '',
      starts_at: toLocalInput(event.starts_at),
      ends_at: toLocalInput(event.ends_at),
    })
    setNotice('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const stopEditing = () => {
    setEditingId(null)
    setForm(emptyForm)
    setNotice('')
  }

  const events = toList(eventsQuery.data)
  const attendees = toList(attendeesQuery.data)

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="ce-events">
      {notice && (
        <div className="ce-notice" role="status">
          <span>{notice}</span>
          <button onClick={() => setNotice('')} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}

      {canManage && (
        <section className="community-panel ce-create-panel">
          <div className="ce-section-heading">
            <div>
              <span className="eyebrow">
                COMMUNITY ACTIVITIES
              </span>
              <h2>{editingId ? 'Edit event' : 'Create an event'}</h2>
              <p>
                Organize a meeting, workshop or activity for your members.
              </p>
            </div>
            <CalendarDays size={25} />
          </div>

          <form onSubmit={handleSubmit} className="community-management-form">
            <label>
              Event title
              <input
                required
                maxLength={160}
                value={form.title}
                onChange={(e) =>
                  setForm({ ...form, title: e.target.value })
                }
                placeholder="e.g. Community Technology Workshop"
              />
            </label>

            <label>
              Description
              <textarea
                required
                rows={4}
                maxLength={5000}
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
                placeholder="Describe the event..."
              />
            </label>

            <label>
              Location
              <input
                maxLength={255}
                value={form.location}
                onChange={(e) =>
                  setForm({ ...form, location: e.target.value })
                }
                placeholder="Enter event location or meeting link"
              />
            </label>

            <div className="form-grid">
              <label>
                Start date and time
                <input
                  type="datetime-local"
                  required
                  value={form.starts_at}
                  onChange={(e) =>
                    setForm({ ...form, starts_at: e.target.value })
                  }
                />
              </label>

              <label>
                End date and time
                <input
                  type="datetime-local"
                  required
                  min={form.starts_at || undefined}
                  value={form.ends_at}
                  onChange={(e) =>
                    setForm({ ...form, ends_at: e.target.value })
                  }
                />
              </label>
            </div>

            <div className="ce-form-actions">
              <button
                className="button button-primary"
                disabled={isSaving}
              >
                <Plus size={16} />
                {isSaving
                  ? 'Saving...'
                  : editingId
                    ? 'Save event changes'
                    : 'Create event'}
              </button>

              {editingId && (
                <button
                  type="button"
                  className="button button-outline"
                  onClick={stopEditing}
                >
                  Cancel editing
                </button>
              )}
            </div>
          </form>
        </section>
      )}

      <div className="ce-events-heading">
        <div>
          <span className="eyebrow">WHAT'S HAPPENING</span>
          <h2>Community events</h2>
          <p>
            Discover upcoming activities and connect with other members.
          </p>
        </div>

        <span className="ce-event-count">
          {events.length} {events.length === 1 ? 'event' : 'events'}
        </span>
      </div>

      {eventsQuery.isLoading && (
        <div className="loading-card">Loading community events...</div>
      )}

      {eventsQuery.isError && (
        <div className="error-card">
          {getErrorMessage(eventsQuery.error)}
          <button
            className="button button-outline"
            onClick={() => eventsQuery.refetch()}
          >
            Try again
          </button>
        </div>
      )}

      {!eventsQuery.isLoading && events.length === 0 && (
        <div className="empty-card">
          <CalendarDays size={30} />
          <h3>No events yet</h3>
          <p>
            {canManage
              ? 'Create the first event for this community.'
              : 'This community has not published any events yet.'}
          </p>
        </div>
      )}

      <div className="ce-event-list">
        {events.map((event) => (
          <article className="community-panel ce-event-card" key={event.id}>
            <div className="ce-event-top">
              <div>
                <span className={`ce-status ce-status-${event.status}`}>
                  {event.status === 'cancelled' ? 'Cancelled' : 'Scheduled'}
                </span>
                <h3>{event.title}</h3>
              </div>

              {canManage && (
                <div className="ce-manager-actions">
                  <button
                    className="icon-button"
                    title="Edit event"
                    onClick={() => startEditing(event)}
                  >
                    <Pencil size={16} />
                  </button>

                  {event.status !== 'cancelled' && (
                    <button
                      className="icon-button"
                      title="Cancel event"
                      disabled={cancelMutation.isPending}
                      onClick={() => {
                        if (window.confirm(`Cancel "${event.title}"?`)) {
                          cancelMutation.mutate(event.id)
                        }
                      }}
                    >
                      <X size={16} />
                    </button>
                  )}

                  <button
                    className="icon-button danger-icon"
                    title="Delete event"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (window.confirm(`Permanently delete "${event.title}"?`)) {
                        deleteMutation.mutate(event.id)
                      }
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              )}
            </div>

            <p className="ce-event-description">{event.description}</p>

            <div className="ce-event-meta">
              <span>
                <CalendarDays size={16} />
                {formatDate(event.starts_at)}
              </span>
              <span>
                <Clock size={16} />
                Ends {formatDate(event.ends_at)}
              </span>
              {event.location && (
                <span>
                  <MapPin size={16} />
                  {event.location}
                </span>
              )}
            </div>

            <div className="ce-event-stats">
              <span><Users size={16} /> {event.rsvp_counts.going} Going</span>
              <span>{event.rsvp_counts.interested} Interested</span>
              <span>{event.rsvp_counts.not_going} Not going</span>
            </div>

            {canRSVP && event.status === 'scheduled' && (
              <div className="ce-rsvp-section">
                <strong>Your response</strong>
                <div className="ce-rsvp-actions">
                  {([
                    ['going', 'Going'],
                    ['interested', 'Interested'],
                    ['not_going', 'Not going'],
                  ] as [EventResponse, string][]).map(([response, label]) => (
                    <button
                      key={response}
                      className={
                        event.my_response === response
                          ? 'ce-rsvp-button selected'
                          : 'ce-rsvp-button'
                      }
                      disabled={rsvpMutation.isPending}
                      onClick={() =>
                        rsvpMutation.mutate({
                          id: event.id,
                          response,
                        })
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="ce-event-footer">
              <span>Organized by @{event.created_by_username}</span>

              {canRSVP ? (
                <button
                  className="ce-attendees-button"
                  onClick={() =>
                    setAttendeesEventId(
                      attendeesEventId === event.id ? null : event.id,
                    )
                  }
                >
                  <Users size={15} />
                  {attendeesEventId === event.id
                    ? 'Hide attendees'
                    : 'View attendees'}
                </button>
              ) : (
                <span>Join the community to view attendees and RSVP.</span>
              )}
            </div>

            {attendeesEventId === event.id && canRSVP && (
              <div className="ce-attendees">
                <h4>Event attendees</h4>

                {attendeesQuery.isLoading && <p>Loading attendees...</p>}

                {attendeesQuery.isError && (
                  <p>{getErrorMessage(attendeesQuery.error)}</p>
                )}

                {!attendeesQuery.isLoading && attendees.length === 0 && (
                  <p>No responses yet.</p>
                )}

                {attendees.map((attendee) => (
                  <div className="ce-attendee-row" key={attendee.id}>
                    <span>@{attendee.username}</span>
                    <span className={`ce-response ce-response-${attendee.response}`}>
                      {attendee.response.replace('_', ' ')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  )
}

