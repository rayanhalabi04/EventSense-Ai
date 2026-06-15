import { api } from './api'
import type { InboxSummary, InboxFilters, InboxMessage } from '../types'

export const inboxService = {
  summary: async (): Promise<InboxSummary> => {
    const res = await api.get<InboxSummary>('/api/v1/inbox/summary')
    return res.data
  },

  // `/api/v1/inbox/messages` returns a flat array of the latest message per
  // conversation. (The bare `/api/v1/inbox` endpoint returns a paginated
  // object, not an array — calling `.filter` on it crashed the page.)
  list: async (filters?: InboxFilters): Promise<InboxMessage[]> => {
    const res = await api.get<InboxMessage[]>('/api/v1/inbox/messages', { params: filters })
    return Array.isArray(res.data) ? res.data : []
  },
}
