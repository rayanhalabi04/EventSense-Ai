import { useQuery } from '@tanstack/react-query'
import { inboxService } from '../services/inbox'
import type { InboxFilters } from '../types'

export function useInboxSummary() {
  return useQuery({
    queryKey: ['inbox', 'summary'],
    queryFn: inboxService.summary,
    refetchInterval: 60_000,
  })
}

export function useInbox(filters?: InboxFilters) {
  return useQuery({
    queryKey: ['inbox', filters],
    queryFn: () => inboxService.list(filters),
  })
}
