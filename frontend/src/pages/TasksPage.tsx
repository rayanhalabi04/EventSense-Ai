import { useState } from 'react'
import { m } from 'framer-motion'
import { Plus, CheckCircle } from 'lucide-react'
import { useTasks, useUpdateTask, useCreateTask } from '../hooks/useTasks'
import { TaskStatusBadge, PriorityBadge } from '../components/ui/Badge'
import { PageLoader } from '../components/ui/LoadingSpinner'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { formatRelative } from '../utils/date'
import type { TaskStatus } from '../types'

const STATUS_TABS: { label: string; value: TaskStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Open', value: 'open' },
  { label: 'In progress', value: 'in_progress' },
  { label: 'Completed', value: 'completed' },
]

export function TasksPage() {
  const [statusFilter, setStatusFilter] = useState<TaskStatus | undefined>('open')
  const [showCreate, setShowCreate] = useState(false)
  const [newTask, setNewTask] = useState({ title: '', description: '', priority: 'medium', due_date: '' })

  const tasks = useTasks({ status: statusFilter })
  const updateTask = useUpdateTask()
  const createTask = useCreateTask()

  const handleStatusChange = (id: string, status: TaskStatus) => {
    updateTask.mutate({ id, data: { status } })
  }

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newTask.title.trim()) return
    createTask.mutate(
      { title: newTask.title, description: newTask.description || undefined, priority: newTask.priority as never, due_date: newTask.due_date || undefined },
      { onSuccess: () => { setShowCreate(false); setNewTask({ title: '', description: '', priority: 'medium', due_date: '' }) } },
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-3xl font-medium text-text-primary">Tasks</h1>
          <p className="text-sm text-text-muted mt-0.5">Track and manage action items across all events</p>
        </div>
        <button type="button" onClick={() => setShowCreate(true)} className="btn-primary gap-1.5">
          <Plus className="w-4 h-4" />
          New task
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setShowCreate(false) }}
        >
          <m.div
            initial={{ scale: 0.96, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="bg-surface rounded-xl border border-border shadow-modal p-6 w-full max-w-md"
          >
            <h2 className="text-base font-semibold text-text-primary mb-4">Create task</h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label htmlFor="task-title" className="block text-xs font-medium text-text-primary mb-1.5">Title</label>
                <input
                  id="task-title"
                  type="text"
                  value={newTask.title}
                  onChange={(e) => setNewTask((p) => ({ ...p, title: e.target.value }))}
                  placeholder="Task title…"
                  className="input-base"
                />
              </div>
              <div>
                <label htmlFor="task-description" className="block text-xs font-medium text-text-primary mb-1.5">Description</label>
                <textarea
                  id="task-description"
                  value={newTask.description}
                  onChange={(e) => setNewTask((p) => ({ ...p, description: e.target.value }))}
                  placeholder="Optional description…"
                  rows={2}
                  className="input-base resize-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="task-priority" className="block text-xs font-medium text-text-primary mb-1.5">Priority</label>
                  <select
                    id="task-priority"
                    value={newTask.priority}
                    onChange={(e) => setNewTask((p) => ({ ...p, priority: e.target.value }))}
                    className="input-base"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="task-due-date" className="block text-xs font-medium text-text-primary mb-1.5">Due date</label>
                  <input
                    id="task-due-date"
                    type="date"
                    value={newTask.due_date}
                    onChange={(e) => setNewTask((p) => ({ ...p, due_date: e.target.value }))}
                    className="input-base"
                  />
                </div>
              </div>
              <div className="flex gap-2 pt-1">
                <button type="submit" disabled={createTask.isPending} className="btn-primary flex-1">
                  {createTask.isPending ? 'Creating…' : 'Create task'}
                </button>
                <button type="button" onClick={() => setShowCreate(false)} className="btn-secondary">Cancel</button>
              </div>
            </form>
          </m.div>
        </m.div>
      )}

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
        <div className="card divide-y divide-border">
          {tasks.data.map((task) => (
            <div key={task.id} className="flex items-start gap-4 px-5 py-4 hover:bg-surface-warm transition-colors">
              {/* Complete button */}
              <button
                type="button"
                onClick={() => handleStatusChange(task.id, task.status === 'completed' ? 'open' : 'completed')}
                className={`mt-0.5 w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center transition-colors ${
                  task.status === 'completed' ? 'bg-success border-success' : 'border-border hover:border-success'
                }`}
                aria-label="Toggle task completion"
              >
                {task.status === 'completed' && <CheckCircle className="w-3 h-3 text-white" />}
              </button>

              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${task.status === 'completed' ? 'line-through text-text-muted' : 'text-text-primary'}`}>
                  {task.title}
                </p>
                {task.description && (
                  <p className="text-xs text-text-muted mt-0.5 truncate">{task.description}</p>
                )}
                <div className="flex items-center gap-3 mt-1.5">
                  <TaskStatusBadge status={task.status} />
                  <PriorityBadge priority={task.priority} />
                  {task.due_date && (
                    <span className="text-[11px] text-text-muted">Due {formatRelative(task.due_date)}</span>
                  )}
                </div>
              </div>

              {/* Status select */}
              <select
                value={task.status}
                onChange={(e) => handleStatusChange(task.id, e.target.value as TaskStatus)}
                aria-label={`Change status for task: ${task.title}`}
                className="text-xs border border-border rounded-md px-2 py-1 text-text-muted bg-surface hover:bg-surface-warm transition-colors focus:outline-none"
              >
                <option value="open">Open</option>
                <option value="in_progress">In progress</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
