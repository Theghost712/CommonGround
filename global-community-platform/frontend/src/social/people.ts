import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import type { Person, PersonProfile, RelationLabel } from '../types'

export const RELATION_LABELS: { value: RelationLabel; label: string }[] = [
  { value: 'family', label: 'Family' },
  { value: 'friend', label: 'Friend' },
  { value: 'colleague', label: 'Colleague' },
  { value: 'classmate', label: 'Classmate' },
  { value: 'neighbour', label: 'Neighbour' },
  { value: 'other', label: 'Other' },
]

export const personKey = (username: string) => ['person', username] as const
export const fetchPerson = async (username: string) => (await api.get<PersonProfile>(`/people/${encodeURIComponent(username)}/`)).data

/** Follow / unfollow, updating every cached copy of that person straight away. */
export function useFollow(username: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (follow: boolean) => {
      const url = `/people/${encodeURIComponent(username)}/follow/`
      return (follow ? await api.post<Person>(url) : await api.delete<Person>(url)).data
    },
    onSuccess: (person) => {
      queryClient.setQueryData<PersonProfile>(personKey(username), (old) => old ? { ...old, ...person, reason: old.reason } : old)
      for (const key of ['people-search', 'people-suggestions', 'people-list', 'contact-matches']) queryClient.invalidateQueries({ queryKey: [key] })
    },
  })
}

export function useRelationLabel(username: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (label: RelationLabel | null) => {
      const url = `/people/${encodeURIComponent(username)}/label/`
      return (label ? await api.put<{ label: RelationLabel }>(url, { label }) : await api.delete<{ label: null }>(url)).data
    },
    onSuccess: ({ label }) => {
      queryClient.setQueryData<PersonProfile>(personKey(username), (old) => old && old.relationship ? { ...old, relationship: { ...old.relationship, label } } : old)
      for (const key of ['people-search', 'people-suggestions', 'people-list']) queryClient.invalidateQueries({ queryKey: [key] })
    },
  })
}

export const initialsOf = (name: string) => (name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('') || '?').toUpperCase()
