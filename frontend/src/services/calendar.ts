import { api } from './api'
import type {
  CalendarAvailabilityCheckRequest,
  CalendarAvailabilityResponse,
  CalendarConnectResponse,
  CalendarEvent,
  CalendarStatus,
  CreateCalendarEventRequest,
} from '../types'

export const calendarService = {
  status: async (): Promise<CalendarStatus> => {
    const res = await api.get<CalendarStatus>('/api/v1/integrations/calendar/status')
    return res.data
  },

  connect: async (): Promise<CalendarConnectResponse> => {
    const res = await api.get<CalendarConnectResponse>('/api/v1/integrations/calendar/google/connect')
    return res.data
  },

  disconnect: async (): Promise<void> => {
    await api.delete('/api/v1/integrations/calendar')
  },

  createEvent: async (data: CreateCalendarEventRequest): Promise<CalendarEvent> => {
    const res = await api.post<CalendarEvent>('/api/v1/calendar/events', data)
    return res.data
  },

  checkAvailability: async (
    data: CalendarAvailabilityCheckRequest,
  ): Promise<CalendarAvailabilityResponse> => {
    const res = await api.post<CalendarAvailabilityResponse>(
      '/api/v1/calendar/availability/check',
      data,
    )
    return res.data
  },
}
