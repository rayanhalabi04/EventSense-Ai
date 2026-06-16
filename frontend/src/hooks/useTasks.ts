import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { tasksService } from '../services/tasks'
import type { CreateTaskRequest, UpdateTaskRequest, TaskStatus } from '../types'

export function useTasks(filters?: { status?: TaskStatus; conversation_id?: string }) {
  return useQuery({
    queryKey: ['tasks', filters],
    queryFn: () => tasksService.list(filters),
  })
}

export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTaskRequest) => tasksService.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useUpdateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateTaskRequest }) =>
      tasksService.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}
