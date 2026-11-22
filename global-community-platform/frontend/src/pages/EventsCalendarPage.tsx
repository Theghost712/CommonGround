import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock,
  MapPin,
  Users,
  ArrowUpRight,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../services/api'
import type { CommunityEvent, Paginated } from '../types'

import '../events-calendar.css'

type EventsResponse = CommunityEvent[] | Paginated<CommunityEvent>
type EventFilter = 'all' | 'upcoming' | 'past' | 'cancelled'

const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function dayKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

// Uses the viewer's own time zone, matching dayKey() and the calendar grid,
// so an event's displayed time always agrees with the day it is placed on.
function formatDate(date: string): string {
  return new Date(date).toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function getCalendarDates(month: Date): Date[] {
  const firstDay = new Date(
    month.getFullYear(),
    month.getMonth(),
    1,
  )

  const mondayOffset = (firstDay.getDay() + 6) % 7

  const gridStart = new Date(
    month.getFullYear(),
    month.getMonth(),
    1 - mondayOffset,
  )

  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart)
    date.setDate(gridStart.getDate() + index)
    return date
  })
}

async function fetchAllEvents(): Promise<CommunityEvent[]> {
  let url: string | null = '/events/'
  let params: Record<string, number> | undefined = { page_size: 100 }

  const events: CommunityEvent[] = []

  while (url) {
    const response: import('axios').AxiosResponse<EventsResponse> =
  await api.get<EventsResponse>(url, { params })

    if (Array.isArray(response.data)) {
      events.push(...response.data)
      break
    }

    events.push(...response.data.results)
    url = response.data.next
    params = undefined
  }

  return events
}

export default function EventsCalendarPage() {
  const [currentMonth, setCurrentMonth] = useState(() => new Date())
  const [selectedDate, setSelectedDate] = useState(() => dayKey(new Date()))
  const [filter, setFilter] = useState<EventFilter>('upcoming')

  const eventsQuery = useQuery({
    queryKey: ['all-community-events'],
    queryFn: fetchAllEvents,
    staleTime: 30000,
  })

  const events = eventsQuery.data || []
  const now = Date.now()

  const filteredEvents = events.filter((event) => {
    if (filter === 'cancelled') return event.status === 'cancelled'

    if (filter === 'upcoming') {
      return (
        event.status === 'scheduled' &&
        new Date(event.starts_at).getTime() >= now
      )
    }

    if (filter === 'past') {
      return (
        event.status === 'scheduled' &&
        new Date(event.starts_at).getTime() < now
      )
    }

    return true
  })

  const calendarDates = getCalendarDates(currentMonth)

  const selectedDayEvents = filteredEvents
    .filter((event) => dayKey(new Date(event.starts_at)) === selectedDate)
    .sort(
      (a, b) =>
        new Date(a.starts_at).getTime() -
        new Date(b.starts_at).getTime(),
    )

  const changeMonth = (direction: number) => {
    const nextMonth = new Date(
      currentMonth.getFullYear(),
      currentMonth.getMonth() + direction,
      1,
    )

    setCurrentMonth(nextMonth)
    setSelectedDate(dayKey(nextMonth))
  }

  const monthLabel = currentMonth.toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  })

  const filters: { key: EventFilter; label: string }[] = [
    { key: 'upcoming', label: 'Upcoming' },
    { key: 'all', label: 'All events' },
    { key: 'past', label: 'Past events' },
    { key: 'cancelled', label: 'Cancelled' },
  ]

  return (
    <div className="events-calendar-page">

      <section className="events-calendar-hero">
        <div>
          <span className="events-calendar-eyebrow">
            COMMUNITY ACTIVITIES
          </span>

          <h1>Events Calendar</h1>

          <p>
            Discover upcoming events, community meetings and activities.
          </p>
        </div>

        <div className="events-calendar-hero-icon">
          <CalendarDays size={34} />
        </div>
      </section>

      <div className="events-calendar-summary">
        <div className="events-summary-card">
          <span>Total events</span>
          <strong>{events.length}</strong>
        </div>

        <div className="events-summary-card">
          <span>Upcoming</span>
          <strong>
            {events.filter(
              (event) =>
                event.status === 'scheduled' &&
                new Date(event.starts_at).getTime() >= now,
            ).length}
          </strong>
        </div>

        <div className="events-summary-card">
          <span>Cancelled</span>
          <strong>
            {events.filter((event) => event.status === 'cancelled').length}
          </strong>
        </div>
      </div>

      <section className="events-calendar-main">

        <div className="events-calendar-toolbar">
          <div>
            <span className="events-calendar-eyebrow">YOUR SCHEDULE</span>
            <h2>{monthLabel}</h2>
          </div>

          <div className="events-month-navigation">
            <button
              className="events-calendar-nav"
              aria-label="Previous month"
              onClick={() => changeMonth(-1)}
            >
              <ChevronLeft size={19} />
            </button>

            <button
              className="events-calendar-today"
              onClick={() => {
                const today = new Date()
                setCurrentMonth(today)
                setSelectedDate(dayKey(today))
              }}
            >
              Today
            </button>

            <button
              className="events-calendar-nav"
              aria-label="Next month"
              onClick={() => changeMonth(1)}
            >
              <ChevronRight size={19} />
            </button>
          </div>
        </div>

        <div className="events-calendar-grid">

          {weekdays.map((day) => (
            <div className="events-calendar-weekday" key={day}>
              {day}
            </div>
          ))}

          {calendarDates.map((date) => {
            const key = dayKey(date)

            const dayEvents = filteredEvents.filter(
              (event) =>
                dayKey(new Date(event.starts_at)) === key,
            )

            const isCurrentMonth =
              date.getMonth() === currentMonth.getMonth()

            const isToday = key === dayKey(new Date())
            const isSelected = key === selectedDate

            return (
              <button
                key={key}
                className={[
                  'events-calendar-day',
                  !isCurrentMonth ? 'outside-month' : '',
                  isToday ? 'is-today' : '',
                  isSelected ? 'is-selected' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => {
                  setSelectedDate(key)

                  if (!isCurrentMonth) {
                    setCurrentMonth(
                      new Date(date.getFullYear(), date.getMonth(), 1),
                    )
                  }
                }}
              >
                <span className="events-day-number">
                  {date.getDate()}
                </span>

                {dayEvents.length > 0 && (
                  <span className="events-day-indicator">
                    <i />
                    <span>{dayEvents.length}</span>
                  </span>
                )}
              </button>
            )
          })}
        </div>

        <div className="events-calendar-legend">
          <span><i /> Days with events</span>
          <span><i className="today-dot" /> Today</span>
          <span><i className="selected-dot" /> Selected day</span>
        </div>
      </section>

      <section className="events-calendar-list">

        <div className="events-list-heading">
          <div>
            <span className="events-calendar-eyebrow">
              EVENT DISCOVERY
            </span>

            <h2>
              {new Date(`${selectedDate}T12:00:00`).toLocaleDateString(
                'en-US',
                { dateStyle: 'full' },
              )}
            </h2>

            <p>
              {selectedDayEvents.length} events on this date
            </p>
          </div>
        </div>

        <div className="events-calendar-filters">
          {filters.map((item) => (
            <button
              key={item.key}
              className={
                filter === item.key
                  ? 'events-filter active'
                  : 'events-filter'
              }
              onClick={() => setFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {eventsQuery.isLoading && (
          <div className="loading-card">
            Loading community events...
          </div>
        )}

        {eventsQuery.isError && (
          <div className="error-card">
            Unable to load events. Please try again.
            <button onClick={() => eventsQuery.refetch()}>
              Retry
            </button>
          </div>
        )}

        {!eventsQuery.isLoading && selectedDayEvents.length === 0 && (
          <div className="events-calendar-empty">
            <CalendarDays size={34} />

            <h3>No events on this date</h3>

            <p>
              Select another date or explore a different event filter.
            </p>
          </div>
        )}

        <div className="events-calendar-cards">
          {selectedDayEvents.map((event) => (
            <article
              className="events-calendar-card"
              key={event.id}
            >
              <div className="events-card-date">
                <CalendarDays size={22} />

                <span>
                  {new Date(event.starts_at).toLocaleDateString(
                    'en-US',
                    {
                      month: 'short',
                      day: 'numeric',
                    },
                    )}
                </span>
              </div>

              <div className="events-card-content">
                <div className="events-card-heading">
                  <h3>{event.title}</h3>

                  <span className={
                    event.status === 'cancelled'
                      ? 'events-card-status cancelled'
                      : 'events-card-status scheduled'
                  }>
                    {event.status}
                  </span>
                </div>

                <p>{event.description}</p>

                <div className="events-card-meta">
                  <span>
                    <Clock size={15} />
                    {formatDate(event.starts_at)}
                  </span>

                  {event.location && (
                    <span>
                      <MapPin size={15} />
                      {event.location}
                    </span>
                  )}

                  <span>
                    <Users size={15} />
                    {event.rsvp_counts.going} going
                  </span>
                </div>

                {event.my_response && (
                  <div className="events-my-response">
                    Your response: {event.my_response.replace('_', ' ')}
                  </div>
                )}

                <Link
                  to={`/communities/${event.community}?tab=events`}
                  className="events-open-community"
                >
                  Open community
                  <ArrowUpRight size={15} />
                </Link>
              </div>
            </article>
          ))}
        </div>

        {filter !== 'all' && (
          <button
            className="events-show-all"
            onClick={() => setFilter('all')}
          >
            Show all events
          </button>
        )}
      </section>

      {events.length === 0 && !eventsQuery.isLoading && (
        <div className="events-calendar-note">
          Your communities have not published any events yet.
          Visit a community to create or discover events.
        </div>
      )}
    </div>
  )
}
