import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { calendarService } from '../services/calendar'
import type { CalendarAvailabilityCheckRequest, CreateCalendarEventRequest } from '../types'

export function useCalendarStatus() {
  return useQuery({
    queryKey: ['calendar', 'status'],
    queryFn: calendarService.status,
  })
}

export function useConnectCalendar() {
  return useMutation({
    mutationFn: calendarService.connect,
  })
}

export function useDisconnectCalendar() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: calendarService.disconnect,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['calendar', 'status'] }),
  })
}

export function useCreateCalendarEvent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCalendarEventRequest) => calendarService.createEvent(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calendar'] })
      qc.invalidateQueries({ queryKey: ['conversations'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
}

export function useCheckCalendarAvailability() {
  return useMutation({
    mutationFn: (data: CalendarAvailabilityCheckRequest) => calendarService.checkAvailability(data),
  })
}
