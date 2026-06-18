import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { m } from 'framer-motion'
import { CalendarDays, ExternalLink, X } from 'lucide-react'
import { useCreateCalendarEvent } from '../hooks/useCalendar'
import { apiErrorDetail } from '../utils/apiError'
import type { CalendarEvent, CreateCalendarEventRequest } from '../types'

export interface CalendarEventDraft {
  title: string
  description?: string
  date: string
  startTime: string
  endTime: string
  timezone?: string
  related_conversation_id?: string | null
  related_message_id?: string | null
  related_task_id?: string | null
  related_escalation_id?: string | null
}

interface CalendarEventModalProps {
  open: boolean
  draft: CalendarEventDraft
  onClose: () => void
}

function toCalendarDateTime(date: string, time: string): string {
  return new Date(`${date}T${time}:00`).toISOString()
}

export function CalendarEventModal({ open, draft, onClose }: CalendarEventModalProps) {
  const timezone = useMemo(
    () => draft.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    [draft.timezone],
  )
  const [title, setTitle] = useState(draft.title)
  const [description, setDescription] = useState(draft.description ?? '')
  const [date, setDate] = useState(draft.date)
  const [startTime, setStartTime] = useState(draft.startTime)
  const [endTime, setEndTime] = useState(draft.endTime)
  const [createdEvent, setCreatedEvent] = useState<CalendarEvent | null>(null)
  const createEvent = useCreateCalendarEvent()

  if (!open) return null

  const error = apiErrorDetail(createEvent.error)
  const canSubmit = title.trim() && date && startTime && endTime && !createEvent.isPending

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    const payload: CreateCalendarEventRequest = {
      title: title.trim(),
      description: description.trim() || null,
      start_time: toCalendarDateTime(date, startTime),
      end_time: toCalendarDateTime(date, endTime),
      timezone,
      related_conversation_id: draft.related_conversation_id ?? null,
      related_message_id: draft.related_message_id ?? null,
      related_task_id: draft.related_task_id ?? null,
      related_escalation_id: draft.related_escalation_id ?? null,
    }
    createEvent.mutate(payload, { onSuccess: setCreatedEvent })
  }

  return (
    <m.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={(event) => { if (event.target === event.currentTarget && !createEvent.isPending) onClose() }}
    >
      <m.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-md rounded-lg border border-border bg-surface p-5 shadow-modal"
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-accent" />
            <h2 className="text-base font-semibold text-text-primary">Create Calendar Event</h2>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost p-2" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        {createdEvent ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-success/20 bg-success-soft px-4 py-3">
              <p className="text-sm font-semibold text-success">Calendar event created</p>
              <p className="mt-1 text-xs text-text-muted">{createdEvent.title}</p>
            </div>
            {createdEvent.provider_event_link && (
              <a
                href={createdEvent.provider_event_link}
                target="_blank"
                rel="noreferrer"
                className="btn-secondary w-full"
              >
                <ExternalLink className="h-4 w-4" />
                Open in Google Calendar
              </a>
            )}
            <button type="button" onClick={onClose} className="btn-primary w-full">Done</button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label htmlFor="calendar-title" className="mb-1.5 block text-xs font-medium text-text-primary">Title</label>
              <input id="calendar-title" value={title} onChange={(event) => setTitle(event.target.value)} className="input-base" />
            </div>
            <div>
              <label htmlFor="calendar-date" className="mb-1.5 block text-xs font-medium text-text-primary">Date</label>
              <input id="calendar-date" type="date" value={date} onChange={(event) => setDate(event.target.value)} className="input-base" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="calendar-start" className="mb-1.5 block text-xs font-medium text-text-primary">Start time</label>
                <input id="calendar-start" type="time" value={startTime} onChange={(event) => setStartTime(event.target.value)} className="input-base" />
              </div>
              <div>
                <label htmlFor="calendar-end" className="mb-1.5 block text-xs font-medium text-text-primary">End time</label>
                <input id="calendar-end" type="time" value={endTime} onChange={(event) => setEndTime(event.target.value)} className="input-base" />
              </div>
            </div>
            <div>
              <label htmlFor="calendar-description" className="mb-1.5 block text-xs font-medium text-text-primary">Description</label>
              <textarea id="calendar-description" rows={4} value={description} onChange={(event) => setDescription(event.target.value)} className="input-base resize-none" />
            </div>
            <p className="text-[11px] text-text-muted">{timezone}</p>
            {error && <p className="text-xs text-danger">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} disabled={createEvent.isPending} className="btn-secondary">Cancel</button>
              <button type="submit" disabled={!canSubmit} className="btn-primary disabled:opacity-50">
                {createEvent.isPending ? 'Creating...' : 'Create event'}
              </button>
            </div>
          </form>
        )}
      </m.div>
    </m.div>
  )
}
