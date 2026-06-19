import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarDays, CheckCircle } from 'lucide-react'
import { useTasks, useUpdateTask } from '../hooks/useTasks'
import { Badge, TaskStatusBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { CalendarEventModal, type CalendarEventDraft } from '../components/CalendarEventModal'
import type { Task, TaskStatus } from '../types'
import {
  extractOriginalMessage,
  formatRiskLabel,
  formatTaskTitle,
  humanizeIntentLabel,
  taskBadgeLabels,
  taskIntent,
  taskRisk,
  taskSourceLabel,
} from '../utils/workflowDisplay'

const STATUS_TABS: { label: string; value: TaskStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Open', value: 'open' },
  { label: 'In progress', value: 'in_progress' },
  { label: 'Completed', value: 'completed' },
]

export function TasksPage() {
  const [searchParams] = useSearchParams()
  const selectedTaskId = searchParams.get('taskId')
  const [statusFilter, setStatusFilter] = useState<TaskStatus | undefined>(() => (selectedTaskId ? undefined : 'open'))
  const [calendarDraft, setCalendarDraft] = useState<CalendarEventDraft | null>(null)
  const selectedTaskRef = useRef<HTMLDivElement | null>(null)

  const tasks = useTasks({ status: statusFilter })
  const updateTask = useUpdateTask()

  useEffect(() => {
    if (selectedTaskId) setStatusFilter(undefined)
  }, [selectedTaskId])

  useEffect(() => {
    if (!selectedTaskId || !tasks.data?.some((task) => task.id === selectedTaskId)) return
    selectedTaskRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    selectedTaskRef.current?.focus({ preventScroll: true })
  }, [selectedTaskId, tasks.data])

  const handleStatusChange = (id: string, status: TaskStatus) => {
    updateTask.mutate({ id, data: { status } })
  }

  const openTaskCalendarModal = (task: Task) => {
    const start = task.due_at ? new Date(task.due_at) : nextTaskStart()
    if (!task.due_at) start.setHours(9, 0, 0, 0)
    const end = new Date(start.getTime() + 30 * 60_000)
    setCalendarDraft({
      title: task.title,
      description: task.description ?? '',
      date: dateInputValue(start),
      startTime: timeInputValue(start),
      endTime: timeInputValue(end),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      related_conversation_id: task.conversation_id ?? null,
      related_message_id: task.message_id ?? null,
      related_task_id: task.id,
    })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-medium text-text-primary">Tasks</h1>
          <p className="text-sm text-text-muted mt-0.5">Track and manage action items across all events</p>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-1 mb-5 bg-surface-warm border border-border rounded-lg p-1 w-fit">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => setStatusFilter(tab.value)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all ${
              statusFilter === tab.value ? 'bg-surface text-text-primary shadow-sm' : 'text-text-muted hover:text-text-primary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {tasks.isLoading ? (
        <PageLoader />
      ) : tasks.isError ? (
        <ErrorState onRetry={tasks.refetch} />
      ) : !tasks.data?.length ? (
        <EmptyState title="No tasks" description="No tasks match the current filter." icon={<CheckCircle className="w-6 h-6" />} />
      ) : (
        <div className="space-y-3">
          {tasks.data.map((task) => {
            const isSelected = selectedTaskId === task.id
            const intent = taskIntent(task)
            const risk = taskRisk(task)
            const originalMessage = extractOriginalMessage(task.description)
            const source = taskSourceLabel(task)
            const meta = [
              intent ? humanizeIntentLabel(intent) : 'Client follow-up',
              risk ? formatRiskLabel(risk) : '',
              source,
            ].filter(Boolean)

            return (
              <div
                key={task.id}
                ref={isSelected ? selectedTaskRef : undefined}
                tabIndex={isSelected ? -1 : undefined}
                className={`card p-5 scroll-mt-24 transition-colors focus:outline-none ${
                  isSelected
                    ? 'bg-accent-soft/40 border-accent/60 ring-2 ring-accent/40'
                    : 'hover:bg-surface-warm'
                }`}
              >
                <div className="flex items-start gap-4">
                  <button
                    type="button"
                    onClick={() => handleStatusChange(task.id, task.status === 'completed' ? 'open' : 'completed')}
                    className={`mt-1 w-5 h-5 rounded-full border flex-shrink-0 flex items-center justify-center transition-colors ${
                      task.status === 'completed' ? 'bg-success border-success' : 'border-border hover:border-success'
                    }`}
                    aria-label="Toggle task completion"
                  >
                    {task.status === 'completed' && <CheckCircle className="w-3.5 h-3.5 text-white" />}
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <p className={`text-base font-semibold leading-snug ${task.status === 'completed' ? 'line-through text-text-muted' : 'text-text-primary'}`}>
                          {formatTaskTitle(task)}
                        </p>
                        <p className="text-xs text-text-muted mt-1">{meta.join(' · ')}</p>
                      </div>

                      <select
                        value={task.status}
                        onChange={(e) => handleStatusChange(task.id, e.target.value as TaskStatus)}
                        aria-label={`Change status for task: ${task.title}`}
                        className="text-xs border border-border rounded-md px-2 py-1.5 text-text-muted bg-surface hover:bg-surface-warm transition-colors focus:outline-none flex-shrink-0"
                      >
                        <option value="open">Open</option>
                        <option value="in_progress">In progress</option>
                        <option value="completed">Completed</option>
                        <option value="cancelled">Cancelled</option>
                      </select>
                      <button
                        type="button"
                        onClick={() => openTaskCalendarModal(task)}
                        className="btn-secondary px-3 py-1.5 text-xs"
                      >
                        <CalendarDays className="h-3.5 w-3.5" />
                        Add to Calendar
                      </button>
                    </div>

                    {originalMessage && (
                      <div className="mt-4 rounded-lg border border-border bg-surface px-4 py-3">
                        <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Original message</p>
                        <p className="text-sm text-text-primary leading-relaxed mt-1 whitespace-pre-wrap break-words">
                          {originalMessage}
                        </p>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-2 mt-4">
                      <TaskStatusBadge status={task.status} />
                      {taskBadgeLabels(task).map((label) => (
                        <Badge key={label} variant={label === 'Overdue' ? 'danger' : 'neutral'}>{label}</Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
      {calendarDraft && (
        <CalendarEventModal
          open={Boolean(calendarDraft)}
          draft={calendarDraft}
          onClose={() => setCalendarDraft(null)}
        />
      )}
    </div>
  )
}

function nextTaskStart(): Date {
  const start = new Date()
  start.setDate(start.getDate() + 1)
  return start
}

function dateInputValue(date: Date): string {
  return date.toISOString().slice(0, 10)
}

function timeInputValue(date: Date): string {
  return date.toTimeString().slice(0, 5)
}
